"""Generated report -> ingest -> real OCR+pixel tool -> calibration -> agent -> verdicts."""
import random

import pytest

from chart_claim_verifier.agent.controller import ClaimController
from chart_claim_verifier.agent.policies import FixedOrderPolicy
from chart_claim_verifier.agent.report_agent import ReportAgent, finalize
from chart_claim_verifier.calibration.collect import collect_figure
from chart_claim_verifier.calibration.fit import fit_table
from chart_claim_verifier.claims.parser import RuleParser
from chart_claim_verifier.config import load_config
from chart_claim_verifier.decide.rule import RuleConfig
from chart_claim_verifier.evaluation.metrics import join, summarize
from chart_claim_verifier.generator.report_builder import build_report
from chart_claim_verifier.generator.tables import ChartTable
from chart_claim_verifier.ingest.pdf_parser import parse_pdf
from chart_claim_verifier.lms.guard import ActionGuard
from chart_claim_verifier.lms.mock_lms import MockLMS
from chart_claim_verifier.schemas import Figure, PointQuery
from chart_claim_verifier.tools.ocr_pixel import OcrPixelTool
from chart_claim_verifier.tools.registry import build_tools
from chart_claim_verifier.tools.simulated import TruthIndex

pytest.importorskip("pytesseract")


def _ingest(tmp_path, rid, seed, truth_index):
    gen = load_config()["generator"]
    truth = build_report(rid, random.Random(seed), tmp_path / rid, gen)
    report = parse_pdf(tmp_path / rid / "report.pdf", tmp_path / "work" / rid, rid)
    by_num = {f["number"]: f for f in truth["figures"]}
    for f in report.figures:
        truth_index.add(f.image_path, ChartTable.from_dict(by_num[f.number]["table"]))
    return report, truth


def test_ocr_pixel_reads_a_bar_chart(tmp_path):
    from chart_claim_verifier.generator.plot import render, sample_style
    from chart_claim_verifier.generator.tables import make_table
    rng = random.Random(7)
    t = make_table(rng, "t", "grouped_bar")
    style = sample_style(rng)
    style["legend_loc"] = "upper left"
    render(t, style, tmp_path / "c.png")
    fig = Figure(figure_id="f", report_id="r", image_path=str(tmp_path / "c.png"), chart_type="grouped_bar")
    errs = []
    for s in t.series:
        for x in t.x_values:
            r = OcrPixelTool().read(fig, PointQuery(series=s, x=x))
            if r.ok:
                errs.append(abs(r.value - t.value(s, x)) / t.span)
    assert len(errs) >= 0.7 * sum(len(v) for v in t.series.values())
    assert max(errs) < 0.02


def test_pipeline_end_to_end(tmp_path):
    truth_index = TruthIndex()
    tools = build_tools(["ocr_pixel", "sim_deplot", "sim_vlm_table", "sim_vlm_crop"], truth=truth_index)

    # calibrate on 4 reports
    items = []
    for i in range(4):
        report, truth = _ingest(tmp_path, f"cal{i}", f"e2e-cal-{i}", truth_index)
        by_num = {f["number"]: f for f in truth["figures"]}
        for f in report.figures:
            items += collect_figure(f, ChartTable.from_dict(by_num[f.number]["table"]), tools, random.Random(0))[0]
    table = fit_table(items, eps=0.005, min_group_size=20)
    assert table.groups

    # check 2 reports
    rc = RuleConfig()
    agent = ReportAgent(RuleParser(), ClaimController(tools, FixedOrderPolicy(list(tools)), table, rc))
    traces, truths = [], []
    for i in range(2):
        report, truth = _ingest(tmp_path, f"test{i}", f"e2e-test-{i}", truth_index)
        truths.append(truth)
        traces += agent.run(report)[0]
    guard = ActionGuard(MockLMS())
    final = finalize(traces, guard, rc.alpha)
    m = summarize(join(final, truths))
    assert m["n_claims"] > 0
    assert m["parse_accuracy"]["value"] == 1.0
    assert guard.unsafe_executed == 0
    assert all(t.decision.verdict in ("CONSISTENT", "MISMATCH", "NOT_SURE", "NO_FIGURE", "SKIPPED") for t in final)
    assert all(t.tool_calls <= 8 for t in final)


def test_activity_feed_reports_steps_and_changes_nothing(tmp_path):
    """The web app's live feed (agent/events.py): it logs each step, and verdicts are the same with or without it,
    even when the listener itself fails."""
    truth_index = TruthIndex()
    tools = build_tools(["ocr_pixel", "sim_deplot", "sim_vlm_table", "sim_vlm_crop"], truth=truth_index)
    items = []
    for i in range(3):
        report, truth = _ingest(tmp_path, f"cal{i}", f"e2e-cal-{i}", truth_index)
        by_num = {f["number"]: f for f in truth["figures"]}
        for f in report.figures:
            items += collect_figure(f, ChartTable.from_dict(by_num[f.number]["table"]), tools, random.Random(0))[0]
    table = fit_table(items, eps=0.005, min_group_size=20)
    agent = ReportAgent(RuleParser(), ClaimController(tools, FixedOrderPolicy(list(tools)), table, RuleConfig()))
    report, _ = _ingest(tmp_path, "test0", "e2e-test-0", truth_index)

    def verdicts():
        return [(t.sentence_id, t.atom, t.decision.verdict, t.decision.estimate, t.tool_calls) for t in agent.run(report)[0]]

    plain = verdicts()
    events = []
    agent.on_event = agent.controller.on_event = events.append
    watched = verdicts()

    def broken(_):
        raise RuntimeError("listener down")
    agent.on_event = agent.controller.on_event = broken
    with_broken = verdicts()
    assert plain == watched == with_broken

    stages = [e["stage"] for e in events]
    assert "plan" in stages and "parse" in stages and "decide" in stages
    starts = [e for e in events if e["stage"] == "tool" and e["status"] == "start"]
    ends = [e for e in events if e["stage"] == "tool" and e.get("status") in ("ok", "error")]
    assert starts and len(starts) == len(ends)                    # every tool call that began also finished
    assert all(e["tool"] in tools and e["text"] for e in starts)
    checked = [t for t in agent.run(report)[0] if t.figure_id]   # one decide event per claim measured on a figure
    assert sum(e["stage"] == "decide" for e in events) >= len(checked)
