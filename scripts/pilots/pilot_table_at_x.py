"""B8 pilot (run_log H16): can the table model read values at x positions that have no tick label?

On the hard line calibration charts, the table tools answer at an unlabelled x only 23 of 279 times (they return
the labelled x values), and `vlm_crop` alone is badly wrong there about half the time, so those claims go to the TA.
Here the same model is asked, once per chart, for every series' value at exactly the x values that are missing.

    python scripts/pilots/pilot_table_at_x.py -c configs/exp/v2.yaml --out results/b8_table_at_x.md

Live model calls: one per chart (20). Answers are cached in the reading cache under the tool name "vlm_table_x".
Rule written before running it: keep as a new tool version only if, at unlabelled x, it answers >= 50%, is badly wrong
(> 5% of the axis) <= 10%, and agrees with vlm_crop on a wrong value <= 5% of its agreements.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from chart_claim_verifier.config import load_config  # noqa: E402
from chart_claim_verifier.generator.tables import ChartTable  # noqa: E402
from chart_claim_verifier.models.vlm import extract_json  # noqa: E402
from chart_claim_verifier.pipeline import Context  # noqa: E402
from chart_claim_verifier.tools.base import image_key, lookup, ToolError  # noqa: E402
from chart_claim_verifier.tools.vlm_table import parse_table  # noqa: E402

PROMPT = ("This line chart has x-axis tick labels at only some positions. For each series (legend entry), read the "
          "value of the line at each of these x positions, including those without a tick label: {xs}. "
          "Return only a JSON object mapping each series to an object mapping each of these x values to its value, "
          'read as precisely as you can from the y-axis. Example: {{"ResNet-50": {{"3": 61.2, "5": 70.4}}}}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default="configs/exp/v2.yaml")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    cfg = load_config(args.config)
    ctx = Context(cfg)
    errors = json.loads((Path(cfg["paths"]["calibration_dir"]) / "ocr_pixel_deplot_vlm_table_vlm_crop.errors.json").read_text())
    by_fig: dict[str, list] = {}
    for e in errors:
        if e["_situation"] == "line|hard" and e["_on_tick"] is False:
            by_fig.setdefault(e["figure"], []).append(e)
    n = answered = big = agree = agree_wrong = 0
    crop_big = 0
    t0 = time.time()
    for f, pts in sorted(by_fig.items()):
        rep = Path(f).parent
        report = json.loads((rep / "report.json").read_text())
        truth = json.loads((Path("data/local/generated") / rep.parent.name / rep.name / "truth.json").read_text())
        num = next(x["number"] for x in report["figures"] if x["image_path"] == f)
        t = ChartTable.from_dict(next(x for x in truth["figures"] if x["number"] == num)["table"])
        xs = sorted({p["x"] for p in pts}, key=float)
        key = ("vlm_table_x", f"v1:{ctx.llm.name}", image_key(f), "__table__", ",".join(xs))
        hit = ctx.cache.get(key)
        if hit is None:
            ans = ctx.llm.generate(PROMPT.format(xs=", ".join(xs)), [f], max_new_tokens=768)[0]
            try:
                tab = parse_table(ans)
            except ToolError:
                tab = {}
            ctx.cache.put(key, {"table": tab})
        else:
            tab = hit["table"] or {}
        print(f"[{time.time() - t0:.0f}s] {f}: {len(xs)} x values, {len(tab)} series read", file=sys.stderr, flush=True)
        for p in pts:
            n += 1
            truth_v = t.value(p["series"], p["x"])
            crop = p.get("vlm_crop")
            crop_big += crop is not None and abs(crop) > 0.05
            try:
                v = lookup(tab, p["series"], p["x"]) if tab else None
            except ToolError:
                v = None
            if v is None:
                continue
            answered += 1
            err = (v - truth_v) / t.span
            big += abs(err) > 0.05
            if crop is not None:
                crop_v = truth_v + crop * t.span
                if abs(crop_v - v) <= 0.03 * t.span:
                    agree += 1
                    agree_wrong += abs(err) > 0.05 and abs(crop) > 0.05
    a_rate, b_rate = answered / max(1, n), big / max(1, answered)
    w_rate = agree_wrong / max(1, agree)
    go = a_rate >= 0.5 and b_rate <= 0.10 and w_rate <= 0.05
    lines = ["# B8 pilot: the table model asked for values at unlabelled x (run_log H16)", "",
             f"{len(by_fig)} hard line calibration charts, {n} points at an x with no tick label, one model call per chart.", "",
             "| | value |", "|---|---|",
             f"| answered | {answered} of {n} ({a_rate:.0%}) |",
             f"| badly wrong (> 5% of the axis) when answered | {big} ({b_rate:.0%}) |",
             f"| agrees with vlm_crop (within 3%) | {agree} |",
             f"| ... and both badly wrong | {agree_wrong} ({w_rate:.0%} of agreements) |",
             f"| vlm_crop badly wrong on these points (for reference) | {crop_big} of {n} ({crop_big / max(1, n):.0%}) |", "",
             f"Rule (H16): answers >= 50%, badly wrong <= 10%, wrong agreement with vlm_crop <= 5%. "
             f"**{'GO' if go else 'NO-GO'}**"]
    text = "\n".join(lines)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
