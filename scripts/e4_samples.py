"""E4, reduced: does one model asked several times repeat its own mistakes, compared with tools of different kinds?

    python scripts/e4_samples.py -c configs/exp/local_real.yaml --per-chart 5 --samples 3 --out results/e4_samples.md

On the calibration charts (true values known), up to `--per-chart` points per chart are read `--samples` more times by
the crop reader at temperature 0.7 (`vlm_crop@s1..`). Their errors sit next to the four tools' saved calibration errors
for the same points, and the same statistics as the tool profile are computed for every pair: how often two readings
agree (within 3% of the axis) and, when they agree, how often both are badly wrong (> 5% of the axis). The rule only
decides when readings agree, so this is the number that matters. Readings are cached; a rerun calls no model.
"""
import argparse
import json
import random
from pathlib import Path

from chart_claim_verifier.config import load_config
from chart_claim_verifier.evaluation.correlation import error_correlation
from chart_claim_verifier.evaluation.tool_profile import pair_stats
from chart_claim_verifier.generator.build import report_dirs
from chart_claim_verifier.generator.tables import ChartTable
from chart_claim_verifier.pipeline import Context, calibration_splits, ingest
from chart_claim_verifier.schemas import PointQuery
from chart_claim_verifier.tools.vlm_crop import VlmCropTool

TOOLS = ["ocr_pixel", "deplot", "vlm_table", "vlm_crop"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default="configs/exp/local_real.yaml")
    ap.add_argument("--per-chart", type=int, default=5)
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--out", default="results/e4_samples.md")
    args = ap.parse_args()
    cfg = load_config(args.config)
    ctx = Context(cfg)
    cal = Path(cfg["paths"]["calibration_dir"])
    saved = {(e["figure"], e["series"], e["x"]): e
             for e in json.loads((cal / ("_".join(TOOLS) + ".errors.json")).read_text())}
    samplers = [VlmCropTool(ctx.llm, ctx.cache, temperature=0.7, name=f"vlm_crop@s{i}") for i in range(1, args.samples + 1)]
    names = [t.name for t in samplers]
    errors = []
    for rd in [d for s in calibration_splits(cfg) for d in report_dirs(ctx.data, s)]:
        report, truth = ingest(ctx, rd)
        by_num = {f["number"]: f for f in truth["figures"]}
        for fig in report.figures:
            if fig.number not in by_num:
                continue
            table = ChartTable.from_dict(by_num[fig.number]["table"])
            points = [(s, x) for s in table.series for x in table.x_values]
            for s, x in random.Random(f"e4-{fig.image_path}").sample(points, min(args.per_chart, len(points))):
                e = dict(saved.get((fig.image_path, s, x), {}))
                if not e:
                    continue
                for tool in samplers:
                    r = tool.read(fig, PointQuery(series=s, x=x))
                    if r.ok:
                        e[tool.name] = (r.value - table.value(s, x)) / table.span
                errors.append(e)
        print(f"[e4] {rd.name}: {len(errors)} points", flush=True)

    every = TOOLS + names
    pairs = pair_stats(errors, every)["*"]
    corr = error_correlation(errors, every)["pairs"]
    rows = []
    for key, p in pairs.items():
        a, b = key.split("~")
        kind = ("same model, sampled" if a.startswith("vlm_crop") and b.startswith("vlm_crop")
                else "same model, different prompt" if {a.split("@")[0], b.split("@")[0]} == {"vlm_crop", "vlm_table"}
                else "different kinds")
        rows.append((kind, key, p, corr.get(key, {}).get("corr")))
    rows.sort(key=lambda r: (r[0], -(r[2]["wrong_when_agree"] or 0)))
    lines = ["# E4 (reduced): repeated samples of one model against tools of different kinds", "",
             f"Made by `python scripts/e4_samples.py`: {len(errors)} calibration points (up to {args.per_chart} per chart), "
             f"crop reader sampled {args.samples} more times at temperature 0.7. Agree = within 3% of the axis; "
             "wrong = the two readings' mean is more than 5% of the axis off.", "",
             "| Pair | Kind | Both answered | Agree | Wrong when they agree | Error correlation |", "|---|---|---|---|---|---|"]
    for kind, key, p, r in rows:
        w = "-" if p["wrong_when_agree"] is None else f"{p['wrong_when_agree']:.1%} ({p['agree_wrong']} of {p['agree']})"
        lines.append(f"| {key} | {kind} | {p['both']} | {p['agree'] / max(p['both'], 1):.0%} | {w} | "
                     f"{'-' if r is None or r != r else f'{r:.2f}'} |")
    Path(args.out).write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
