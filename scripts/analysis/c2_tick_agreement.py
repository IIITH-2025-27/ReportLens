"""C2 (run_log H19): are two tools that agree exactly on a tick-label value wrong together more often?

On the calibration charts (true values known), every pair of tools that answered a point and agreed (within the
accept cap, 3% of the axis) is sorted into "agreed on a tick value" (both readings within 0.2% of the axis of a y
tick label) and "agreed elsewhere". For each group: how often both readings are badly wrong (> 5% of the axis), and on
how many charts that happens.

    python scripts/analysis/c2_tick_agreement.py --out results/c2_tick_agreement.md

Rule written before running it: build a rule only if tick agreements are badly wrong >= 3x as often as other
agreements, on >= 5 charts.
"""
import argparse
import itertools
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from chart_claim_verifier.generator.tables import ChartTable  # noqa: E402
from chart_claim_verifier.tools.axis import ChartReadError, analyse  # noqa: E402

TOOLS = ["ocr_pixel", "deplot", "vlm_table", "vlm_crop"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--errors", default="calibration_tables/local/ocr_pixel_deplot_vlm_table_vlm_crop.errors.json")
    ap.add_argument("--agree", type=float, default=0.03)
    ap.add_argument("--snap", type=float, default=0.002)
    ap.add_argument("--big", type=float, default=0.05)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    errors = json.loads(Path(args.errors).read_text())
    tables, ticks = {}, {}
    for e in errors:
        f = e["figure"]
        if f in tables:
            continue
        rep = Path(f).parent
        report = json.loads((rep / "report.json").read_text())
        truth = json.loads((Path("data/local/generated") / rep.parent.name / rep.name / "truth.json").read_text())
        num = next(x["number"] for x in report["figures"] if x["image_path"] == f)
        tables[f] = ChartTable.from_dict(next(x for x in truth["figures"] if x["number"] == num)["table"])
        try:
            ticks[f] = [v for _, v in analyse(f).yfit.ticks]
        except ChartReadError:
            ticks[f] = []
    groups = {"tick": defaultdict(int), "other": defaultdict(int)}
    charts = {"tick": set(), "other": set()}
    for e in errors:
        f, t = e["figure"], tables[e["figure"]]
        span = t.span
        truth = t.value(e["series"], e["x"])
        for a, b in itertools.combinations(TOOLS, 2):
            if a not in e or b not in e:
                continue
            ra, rb = truth + e[a] * span, truth + e[b] * span
            if abs(ra - rb) > args.agree * span:
                continue
            on_tick = any(abs(ra - v) <= args.snap * span and abs(rb - v) <= args.snap * span for v in ticks[f])
            g = "tick" if on_tick else "other"
            wrong = abs(e[a]) > args.big and abs(e[b]) > args.big
            groups[g]["n"] += 1
            groups[g]["wrong"] += wrong
            if wrong:
                charts[g].add(f)
    rate = {g: groups[g]["wrong"] / max(1, groups[g]["n"]) for g in groups}
    ratio = rate["tick"] / rate["other"] if rate["other"] else float("inf")
    go = ratio >= 3 and len(charts["tick"]) >= 5
    lines = ["# C2: agreement exactly on a tick value (run_log H19)", "",
             f"Calibration charts: {len(tables)}; points: {len(errors)}; agreeing pairs of tools: "
             f"{groups['tick']['n'] + groups['other']['n']}.", "",
             "| Agreement | pairs | both badly wrong | rate | charts where it happens |", "|---|---|---|---|---|",
             f"| on a tick value | {groups['tick']['n']} | {groups['tick']['wrong']} | {rate['tick']:.1%} | {len(charts['tick'])} |",
             f"| elsewhere | {groups['other']['n']} | {groups['other']['wrong']} | {rate['other']:.1%} | {len(charts['other'])} |",
             "", f"Ratio: {ratio:.1f}x. Rule (H19): build a rule only if >= 3x on >= 5 charts. **{'GO' if go else 'NO-GO'}**"]
    text = "\n".join(lines)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
