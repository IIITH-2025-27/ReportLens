"""v3 image rules on real chart images (run_log H12, H13, H15).

  existing  every figure image of the calibration and evaluation splits: how often does a v3 rule fire where it must
            not (a second panel, an unsupported kind, a second y-axis), and does the log/inverted y fit change any axis
            the ordinary fit already read?
  v3feat    every figure of the v3feat split: are two-panel figures split, dual axes and unsupported kinds flagged,
            and log axes read?

    python scripts/analysis/v3_image_rules.py --out results/v3_image_rules.md
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from chart_claim_verifier.ingest.panels import chart_flags, find_panels  # noqa: E402
from chart_claim_verifier.tools.axis import ChartReadError, analyse  # noqa: E402
from chart_claim_verifier.tools.chart_ocr import load_bgr  # noqa: E402

SPLITS = ["calib", "calib_easy", "test", "dev", "holdout", "holdout2", "holdout3", "final"]
MODES = ("linear", "log", "inverted")


def geo(p, modes=("linear",)):
    try:
        return analyse(p, modes) if modes != ("linear",) else analyse(p)
    except ChartReadError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    lines = ["# v3 image rules (run_log H12, H13, H15)", ""]
    imgs = [f["image_path"] for sp in SPLITS for p in sorted(Path("data/local/work", sp).glob("*/report.json"))
            for f in json.loads(p.read_text())["figures"]]
    fp = Counter()
    for p in imgs:
        g = geo(p)
        fp["panels"] += len(find_panels(load_bgr(p))) >= 2
        for fl in chart_flags(p, g):
            fp[fl] += 1
            print("false flag:", fl, p, flush=True)
        g3 = geo(p, MODES)
        if g is not None and (g3 is None or (g3.yfit.a, g3.yfit.b, g3.yfit.log) != (g.yfit.a, g.yfit.b, False)):
            fp["axis fit changed"] += 1
        if g is None and g3 is not None:
            fp["read only with log/inverted"] += 1
    lines += [f"Existing splits: {len(imgs)} figure images.", "", "| rule fired where it must not | images |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(fp.items())] or ["| (none) | 0 |"]
    lines.append(f"| any v3 flag at all | {sum(v for k, v in fp.items() if k not in ('read only with log/inverted',))} |")
    hit = Counter()
    tot = Counter()
    for t in sorted(Path("data/local/generated/v3feat").glob("*/truth.json")):
        truth = json.loads(t.read_text())
        seen = set()
        for f in truth["figures"]:
            if f["image"] in seen:
                continue
            seen.add(f["image"])
            p = str(t.parent / f["image"])
            k = f["kind"]
            g = geo(p)
            flags = chart_flags(p, g)
            tot[k] += 1
            if k == "panels":
                hit[k] += len(find_panels(load_bgr(p))) == 2
            elif k == "dual":
                hit[k] += "dual_y" in flags
            elif k.startswith("unsupported:"):
                hit[k] += k in flags
            elif k == "log":
                g3 = geo(p, MODES)
                hit[k] += g3 is not None and g3.yfit.log
            else:
                hit["no flag (" + k + ")"] += not flags
                tot["no flag (" + k + ")"] += 1
                tot[k] -= 1
    lines += ["", "v3feat figures (raster):", "", "| kind | found | of |", "|---|---|---|"]
    lines += [f"| {k} | {hit[k]} | {tot[k]} |" for k in sorted(tot) if tot[k]]
    text = "\n".join(lines)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
