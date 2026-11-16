"""Run the checker on the real-world sample reports and score every sentence against its expected.json (v4, run_log J; default config v5, run_log K, which the lite web app runs).

    python scripts/real/check_samples.py                          # v5 config, stand-in readers (no model loads)
    python scripts/real/check_samples.py -c configs/exp/local_real.yaml     # the config the web app used before v4
    python scripts/real/check_samples.py --readers real           # the real models (Qwen, DePlot): slow, ~11 GB
    python scripts/real/check_samples.py --reports 03,04 --out results/samples_v4.md

Readers:
    stub   the real OCR+pixel reader, and DePlot / VLM table / VLM crop replaced by readers that return the TRUE value
           of each plotted point (from truth.json). This tests everything except model reading: PDF reading, finding
           and parsing claims, picking the figure, the hand-off rules and the decision. Nothing is loaded.
    real   the tools of the config, models included (the same system the web app runs).

Each sentence of expected.json gets one of
    ok        the verdict is one of the acceptable ones
    WRONG     a harmful verdict: a true claim flagged, a false one accepted, a claim checked on a figure that does not
              show it, a negated sentence judged
    other     neither (for example NO_FIGURE for a claim that should have been decided): lost coverage, not harm
    missing   no sentence of the report matched it (text extraction changed it beyond recognition)
Exit code 1 when anything is WRONG.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from rapidfuzz import fuzz

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from chart_claim_verifier.config import load_config  # noqa: E402
from chart_claim_verifier.pipeline import Context, build_agent, load_table, verify_pdf  # noqa: E402
from chart_claim_verifier.schemas import Figure, PointQuery  # noqa: E402
from chart_claim_verifier.tools.base import TableTool, Tool, ToolError, lookup  # noqa: E402

SAMPLES = ROOT / "sample_reports" / "real_world"


def _norm(s: str) -> str:
    s = s.replace("ﬁ", "fi").replace("ﬂ", "fl").replace("−", "-").replace("–", "-")
    return re.sub(r"\s+", " ", s.strip().lower())


class _Truth:
    def __init__(self, truth: dict):
        self.by_fig = {}
        for f in truth["figures"]:
            self.by_fig[(f["number"], f.get("panel"))] = {s: dict(zip(f["x_values"], v)) for s, v in f["series"].items()}

    def table(self, fig: Figure) -> dict:
        tab = self.by_fig.get((fig.number, fig.panel)) or self.by_fig.get((fig.number, None))
        if tab is None:
            raise ToolError("no_truth")
        return tab


class StubTable(TableTool):
    """A table reader that returns the true values of the figure (stand-in for DePlot / the VLM table pass)."""
    kind, version = "simulated", "truth"

    def __init__(self, name: str, truth: _Truth):
        super().__init__(None)
        self.name, self.truth = name, truth

    def extract_table(self, fig: Figure) -> dict:
        return self.truth.table(fig)


class StubPoint(Tool):
    """A point reader that returns the true value (stand-in for the VLM crop reader)."""
    kind, version, scope = "simulated", "truth", "point"

    def __init__(self, name: str, truth: _Truth):
        super().__init__(None)
        self.name, self.truth = name, truth

    def _read(self, fig: Figure, q: PointQuery) -> float:
        return lookup(self.truth.table(fig), q.series, q.x)


def score(expected: list[dict], traces: list, loose: bool) -> list[dict]:
    rows = []
    for e in expected:
        want = _norm(e["sentence"])
        best, best_score = [], 0.0
        for t in traces:
            sc = fuzz.ratio(want, _norm(t.sentence))
            if sc > best_score + 0.5:
                best, best_score = [t], sc
            elif abs(sc - best_score) <= 0.5:
                best.append(t)
        cutoff = 80 if loose else 90
        if best_score < cutoff:
            rows.append({**e, "verdict": None, "status": "missing", "reason": "", "found": ""})
            continue
        verdicts = [t.decision.verdict for t in best]
        harmful = [v for v in verdicts if v in e["wrong"]]
        verdict = harmful[0] if harmful else verdicts[0]
        status = "WRONG" if harmful else ("ok" if verdict in e["accept"] else "other")
        t = next(t for t in best if t.decision.verdict == verdict)
        rows.append({**e, "verdict": verdict, "status": status, "reason": t.decision.reason,
                     "found": t.sentence, "estimate": t.decision.estimate})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default="configs/exp/v5.yaml")
    ap.add_argument("--readers", choices=["stub", "real"], default="stub")
    ap.add_argument("--reports", default="", help="comma-separated prefixes, e.g. 01,03 (default: all)")
    ap.add_argument("--work", default=None, help="where parsed figures go (default: a temporary folder)")
    ap.add_argument("--out", default=None, help="also write the table as markdown here")
    args = ap.parse_args()

    import tempfile
    work = Path(args.work) if args.work else Path(tempfile.mkdtemp(prefix="ccv_samples_"))
    cfg = load_config(ROOT / args.config)
    for key, value in list(cfg["paths"].items()):
        if not Path(value).is_absolute():
            cfg["paths"][key] = str(ROOT / value)
    if args.readers == "stub":                     # a throw-away reading cache: the stub run must not add to the real one
        work.mkdir(parents=True, exist_ok=True)
        cfg["paths"]["cache_db"] = str(work / "readings.sqlite")
    ctx = Context(cfg, offline=args.readers == "stub")
    agent, rc, pol = build_agent(ctx, load_table(ctx), cfg["agent"]["policy"], "rule" if args.readers == "stub" else "agent")
    real_tools = dict(agent.controller.tools)
    if args.readers == "stub":
        agent.controller.repairs = {}

    folders = sorted(p for p in SAMPLES.iterdir() if (p / "expected.json").exists())
    if args.reports:
        folders = [p for p in folders if any(p.name.startswith(x.strip()) for x in args.reports.split(","))]
    lines = [f"# Sample reports: {Path(args.config).name}, readers = {args.readers}", ""]
    total = Counter()
    for folder in folders:
        expected = json.loads((folder / "expected.json").read_text())
        truth = _Truth(json.loads((folder / "truth.json").read_text()))
        if args.readers == "stub":
            agent.controller.tools = {name: (real_tools[name] if name == "ocr_pixel" else
                                             StubPoint(name, truth) if name == "vlm_crop" else StubTable(name, truth))
                                      for name in real_tools}
        report, traces = verify_pdf(ctx, agent, rc, folder / "report.pdf", work / folder.name, report_id=folder.name)
        rows = score(expected["claims"], traces, loose="scanned" in folder.name)
        c = Counter(r["status"] for r in rows)
        total.update(c)
        figs = ", ".join(f"{f.figure_id}" + ("" if f.y_span else " (axis unread)") + (f" [{', '.join(f.flags)}]" if f.flags else "")
                         for f in report.figures)
        lines += [f"## {folder.name}", "", f"{expected['about']}", "",
                  f"{len(report.sentences)} sentences, figures: {figs or 'none'}. "
                  f"Result: {c['ok']} ok, {c['WRONG']} WRONG, {c['other']} other, {c['missing']} missing.", "",
                  "| status | truth | verdict | sentence | why it is expected | system's reason |", "|---|---|---|---|---|---|"]
        for r in rows:
            lines.append(f"| {r['status']} | {r['truth']} | {r['verdict'] or '-'} | {r['sentence']} | {r['why']} | "
                         f"{(r['reason'] or '')[:110]} |")
        lines.append("")
    lines.insert(2, f"**Total: {total['ok']} ok, {total['WRONG']} WRONG, {total['other']} other, "
                    f"{total['missing']} missing** (of {sum(total.values())} sentences)\n")
    text = "\n".join(lines)
    print(text)
    if args.out:
        Path(args.out).write_text(text)
    return 1 if total["WRONG"] else 0


if __name__ == "__main__":
    sys.exit(main())
