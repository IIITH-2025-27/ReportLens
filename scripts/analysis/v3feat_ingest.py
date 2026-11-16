"""v3feat as the PDF reader sees it (run_log H9, H13, H15): figures found, panels split, kinds flagged, per layout.

    python scripts/analysis/v3feat_ingest.py -c configs/exp/v3.yaml --out results/v3feat_ingest.md

Parses every v3feat report with the config's ingest switches (cached as report_<hash>.json) and compares the
figures with truth.json: each truth figure is matched by its number (and panel letter).
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from chart_claim_verifier.config import load_config  # noqa: E402
from chart_claim_verifier.pipeline import _parse_cache_name, ingest_options  # noqa: E402
from chart_claim_verifier.ingest.pdf_parser import parse_pdf  # noqa: E402
from chart_claim_verifier.schemas import Report  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default="configs/exp/v3.yaml")
    ap.add_argument("--split", default="v3feat")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    cfg = load_config(args.config)
    opts = ingest_options(cfg)
    data = Path(cfg["paths"]["data_dir"])                 # .../generated; parses go to .../work, as in pipeline.ingest
    gen, work = data / args.split, data.parent / "work" / args.split
    found, total, extra = Counter(), Counter(), Counter()
    for rd in sorted(p for p in gen.iterdir() if (p / "report.pdf").exists()):
        truth = json.loads((data / "v3feat" / rd.name / "truth.json").read_text())
        w = work / rd.name
        w.mkdir(parents=True, exist_ok=True)
        cached = w / _parse_cache_name(opts)
        if cached.exists():
            rep = Report.model_validate_json(cached.read_text())
        else:
            rep = parse_pdf(rd / "report.pdf", w, rd.name, **opts)
            cached.write_text(rep.model_dump_json())
        lay = ("two-column" if truth["layout"]["two_column"] else "one-column") + \
              (", vector" if truth["layout"]["vector"] else ", raster")
        if args.split.endswith("_plain"):
            lay = "one-column raster twin"
        elif args.split.endswith("_scanned"):
            lay = "scanned twin"
        parsed = {(f.number, f.panel): f for f in rep.figures}
        for g in truth["figures"]:
            kind = g["kind"]
            total[(lay, "figure found")] += 1
            f = parsed.get((g["number"], g.get("panel")))
            found[(lay, "figure found")] += f is not None
            total[(lay, "figure number found (a panel may be unsplit)")] += 1
            found[(lay, "figure number found (a panel may be unsplit)")] += any(n == g["number"] for n, _ in parsed)
            if kind == "panels":
                total[(lay, "panel split (a/b found)")] += 1
                found[(lay, "panel split (a/b found)")] += f is not None and f.panel is not None
            if kind == "dual" or kind.startswith("unsupported:"):
                total[(lay, "dual / unsupported flagged")] += 1
                want = "dual_y" if kind == "dual" else kind
                found[(lay, "dual / unsupported flagged")] += f is not None and want in f.flags
            if kind == "log":
                total[(lay, "log axis flagged")] += 1
                found[(lay, "log axis flagged")] += f is not None and "log_y" in f.flags
            if kind not in ("dual", "log") and not kind.startswith("unsupported:") and f is not None:
                total[(lay, "readable chart with no kind flag")] += 1
                found[(lay, "readable chart with no kind flag")] += not any(
                    fl == "dual_y" or fl.startswith("unsupported:") for fl in f.flags)
        known = {(g["number"], g.get("panel")) for g in truth["figures"]}
        extra[lay] += sum(1 for k in parsed if k not in known)
    lines = [f"# {args.split} as the PDF reader sees it (ingest switches of {args.config})", "",
             "| layout | check | found | of |", "|---|---|---|---|"]
    for k in sorted(total):
        lines.append(f"| {k[0]} | {k[1]} | {found[k]} | {total[k]} |")
    lines += ["", "Figures read that are not in the truth file (stray images, wrong numbers): " +
              ", ".join(f"{k}: {v}" for k, v in sorted(extra.items()))]
    text = "\n".join(lines)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
