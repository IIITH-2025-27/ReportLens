"""Fixes made before the final run (9 Nov): safe defaults, explicit calibration order, never-pair, the check command."""
import random

import pytest

from chart_claim_verifier.agent.planner import InformedPolicy, Thresholds, wrong_when_agree
from chart_claim_verifier.config import load_config
from chart_claim_verifier.decide.rule import RuleConfig
from chart_claim_verifier.pipeline import calibration_order
from test_planner import PROFILE, state


def test_rejected_tool_set_margins_are_off_by_default():
    assert RuleConfig().by_tool_set is False
    cfg = load_config()
    del cfg["decision"]["by_tool_set"]
    assert RuleConfig.from_cfg(cfg).by_tool_set is False


def test_calibration_order_does_not_follow_the_run_time_policy():
    cfg = load_config()
    for policy in ("fixed_order", "informed", "all_tools"):
        cfg["agent"]["policy"] = policy
        assert calibration_order(cfg) == cfg["agent"]["fixed_order"]
    cfg["calibration"]["order"] = "random"
    assert calibration_order(cfg) is None
    assert calibration_order(load_config("configs/exp/E4_homogeneous.yaml")) is None
    cfg["calibration"]["order"] = "nonsense"
    with pytest.raises(ValueError):
        calibration_order(cfg)


def test_never_pair_reads_from_config():
    cfg = load_config()
    assert Thresholds.from_cfg(cfg).never_pair == ()
    cfg["agent"]["informed"]["never_pair"] = [["vlm_table", "vlm_crop"]]
    th = Thresholds.from_cfg(cfg)
    assert th.shares_model("vlm_crop", "vlm_table") and not th.shares_model("ocr_pixel", "vlm_crop")


def test_tools_that_share_a_model_never_cross_check_each_other():
    th = Thresholds(never_pair=(frozenset(("vlm_table", "vlm_crop")),))
    assert wrong_when_agree(PROFILE, "bar|easy", "vlm_table", "vlm_crop", th) == 1.0
    # with only the two model tools left, the planner hands off instead of pairing them
    a = InformedPolicy(PROFILE, th).next_action(
        state("bar|easy", readings=["vlm_crop"], available=["vlm_crop", "vlm_table"]))
    assert a["action"] == "handoff" and "same model" in a["why"]
    # without the rule the same state reads vlm_table
    b = InformedPolicy(PROFILE).next_action(state("bar|easy", readings=["vlm_crop"], available=["vlm_crop", "vlm_table"]))
    assert b["action"] == "read" and b["tool"] == "vlm_table"


def test_check_ingests_a_pdf_without_a_truth_file(tmp_path):
    pytest.importorskip("pytesseract")
    from chart_claim_verifier.generator.report_builder import build_report
    from chart_claim_verifier.pipeline import Context, ingest_pdf
    build_report("r0", random.Random("check-0"), tmp_path / "gen" / "r0", load_config()["generator"])
    pdf = tmp_path / "student.pdf"
    pdf.write_bytes((tmp_path / "gen" / "r0" / "report.pdf").read_bytes())       # no truth.json next to it
    cfg = load_config()
    cfg["paths"].update(data_dir=str(tmp_path / "data" / "generated"), cache_db=str(tmp_path / "c.sqlite"))
    report = ingest_pdf(Context(cfg, offline=True), pdf)
    assert report.report_id == "student" and report.figures and report.sentences
    assert (tmp_path / "data" / "work" / "check" / "student" / "report.json").exists()
