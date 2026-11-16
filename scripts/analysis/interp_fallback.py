"""v5 (run_log K1): how good is DePlot's table, joined by a straight line, at an x with no tick label?

On the hard line charts most hand-offs are claims at an epoch between two labelled ticks ("epoch 7" on an axis
labelled 1, 5, 9, 13). The table tools return only labelled x values, the OCR+pixel reader often cannot find the
series in a blurry legend, and vlm_crop alone is badly wrong there about half the time, so no two tools answer.

Measured here on the calibration charts only (true values known), from cached tables, without any model call:
  * how often a straight line between the two labelled neighbours gives a value, and how often it is badly wrong
  * the curve-bend error alone: the same straight line drawn through the TRUE values at those neighbours.
    Its 95th percentile is `agent.interpolation_error` in configs/exp/v5.yaml (the flag margin is widened by it)
  * how often the interpolated value and vlm_crop agree on a wrong value

    python scripts/analysis/interp_fallback.py -c configs/exp/v4.yaml --out results/interp_fallback.md
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from chart_claim_verifier.config import load_config  # noqa: E402
from chart_claim_verifier.generator.tables import ChartTable  # noqa: E402
from chart_claim_verifier.pipeline import Context  # noqa: E402
from chart_claim_verifier.tools.base import _float, interpolate, match_name  # noqa: E402

BIG, AGREE = 0.05, 0.03


def true_table(fig: str, data_dir: Path) -> ChartTable:
    rep = Path(fig).parent
    report = json.loads((rep / "report.json").read_text())
    truth = json.loads((data_dir / rep.parent.name / rep.name / "truth.json").read_text())
    num = next(x["number"] for x in report["figures"] if x["image_path"] == fig)
    return ChartTable.from_dict(next(x for x in truth["figures"] if x["number"] == num)["table"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default="configs/exp/v4.yaml")
    ap.add_argument("--cache", default=None, help="reading cache to read the tables from (default: the config's)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    paths = {"cache_db": args.cache} if args.cache else None
    cfg = load_config(args.config, paths=paths) if paths else load_config(args.config)
    ctx = Context(cfg, offline=True)
    deplot = ctx.tools()["deplot"]
    stem = "_".join(cfg["tools"]["enabled"])
    errors = json.loads((Path(cfg["paths"]["calibration_dir"]) / f"{stem}.errors.json").read_text())
    data_dir = Path(cfg["paths"]["data_dir"])

    pts, fails, tables = [], Counter(), {}
    for e in errors:
        if e["_situation"] != "line|hard" or e["_on_tick"] is not False:
            continue
        if e["figure"] not in tables:
            tables[e["figure"]] = true_table(e["figure"], data_dir)
        t = tables[e["figure"]]
        truth, span = t.value(e["series"], e["x"]), t.span
        p = {"fig": e["figure"], "crop": e.get("vlm_crop"), "direct": e.get("deplot")}
        if p["direct"] is None:
            tab = deplot.known_table(SimpleNamespace(image_path=e["figure"]))
            hit = interpolate(tab, e["series"], e["x"]) if tab else None
            if hit is None:
                fails["no table" if not tab else "series not found or x outside the labelled range"] += 1
            else:
                v, x0, x1 = hit
                p["interp"] = (v - truth) / span
                try:
                    bend = t.value(e["series"], x0) + (t.value(e["series"], x1) - t.value(e["series"], x0)) * \
                        (_float(e["x"]) - _float(x0)) / (_float(x1) - _float(x0))
                    p["bend"] = (bend - truth) / span
                except (KeyError, ValueError, TypeError):
                    pass
        pts.append(p)

    n = len(pts)
    got = [p for p in pts if p.get("interp") is not None]
    big = sum(abs(p["interp"]) > BIG for p in got)
    bends = np.array([abs(p["bend"]) for p in got if p.get("bend") is not None])
    q = {k: float(np.percentile(bends, k)) for k in (50, 90, 95, 99)} if len(bends) else {}
    crop_big = sum(p["crop"] is not None and abs(p["crop"]) > BIG for p in pts)
    pair = [p for p in got if p["crop"] is not None]
    agree = [p for p in pair if abs(p["interp"] - p["crop"]) <= AGREE]
    wrong = [p for p in agree if abs((p["interp"] + p["crop"]) / 2) > BIG]
    charts = len({p["fig"] for p in pts})

    lines = [
        "# DePlot interpolated at x values with no tick label (run_log K1)", "",
        f"Calibration charts only: {n} points at an unlabelled x on {charts} hard line charts, where DePlot's table "
        "has no row for that x. Errors are fractions of the y-axis range.", "",
        "| | value |", "|---|---|",
        f"| a straight line between the two labelled neighbours gives a value | {len(got)} of {n} ({len(got) / max(1, n):.0%}) |",
        f"| ... badly wrong (> 5% of the axis) | {big} ({big / max(1, len(got)):.0%}) |",
        f"| vlm_crop badly wrong at the same points (for comparison) | {crop_big} of {n} ({crop_big / max(1, n):.0%}) |",
        f"| interpolated value and vlm_crop agree (within 3%) | {len(agree)} of {len(pair)} |",
        f"| ... and both badly wrong | {len(wrong)} ({len(wrong) / max(1, len(agree)):.1%}) on "
        f"{len({p['fig'] for p in wrong})} of {len({p['fig'] for p in agree})} charts |",
        f"| no value: {', '.join(f'{k} {v}' for k, v in fails.items()) or '-'} | |", "",
        "Curve-bend error alone (the straight line drawn through the TRUE values at the same neighbours):", "",
        "| percentile | 50 | 90 | 95 | 99 |", "|---|---|---|---|---|",
        "| error | " + " | ".join(f"{100 * q[k]:.1f}%" for k in (50, 90, 95, 99)) + " |" if q else "| error | - | - | - | - |", "",
        "Most badly wrong interpolations come from DePlot misreading the labelled neighbours (a few charts), not from",
        "the bend. The pair still agrees on a wrong value more often than the planner's 5% bar, so the interpolated",
        "value is not a profile tool: it is used only as a last step before a hand-off, with the flag margin widened",
        f"by the bend error's 95th percentile ({100 * q.get(95, 0):.1f}% of the axis, halved in the estimate because the",
        "estimate averages the interpolated value with vlm_crop's direct reading). Accepts are not widened.",
    ]
    text = "\n".join(lines)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
