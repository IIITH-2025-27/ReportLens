"""C4 (run_log H21): a real report + two WebPlotDigitizer reading sessions -> truth.json (implementation.md §9.3).

Lay a report out like a generated one, under data/local/generated/<split>/<report_id>/:

    report.pdf
    figures.json   [{"number": 1, "panel": null, "kind": "line" | "bar" | "grouped_bar", "title": "...",
                     "y_label": "Accuracy (%)", "metric_word": "accuracy", "percent": true,
                     "x_values": ["1", "2", ...], "sessions": ["fig1_s1", "fig1_s2"]}, ...]
    claims.json    [{"sentence": "...", "figure": 1, "gold": null | "correct" | "error" | "no_figure"}, ...]
    fig1_s1/ ...   one session's readings, either
                     long.csv     with columns series,x,value   (any chart), or
                     <series>.csv with rows x,y as WebPlotDigitizer exports one dataset (line charts; x is snapped
                                  to the nearest value of x_values)

    python scripts/real/import_wpd.py data/local/generated/real/real_000 [--min-agree 0.01]

The chart's table is the mean of the two sessions. A claim with no human label is labelled by comparing it with that
table. With slack = the two sessions' disagreement at that point (at least `--min-agree` of the axis range): correct
within rounding + slack, error beyond rounding + 3 x slack, "unknown" in between. Note that the metrics count a
flag on an "unknown" claim as a wrong flag (as for any unlabelled sentence), so the real-set wrong-flag rate is
conservative. Prints how well
the two sessions agree, which is the label noise of the real set and must be reported with it.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from chart_claim_verifier.claims.parser import RuleParser  # noqa: E402
from chart_claim_verifier.claims.tolerance import is_within  # noqa: E402
from chart_claim_verifier.generator.tables import ChartTable  # noqa: E402


def read_session(folder: Path, x_values: list[str]) -> dict[str, dict[str, float]]:
    """series -> x -> value, from long.csv or from one WebPlotDigitizer x,y file per series."""
    out: dict[str, dict[str, float]] = {}
    long = folder / "long.csv"
    if long.exists():
        for row in csv.DictReader(long.open()):
            out.setdefault(row["series"].strip(), {})[row["x"].strip()] = float(row["value"])
        return out
    xs = [(float(x), x) for x in x_values]
    for f in sorted(folder.glob("*.csv")):
        for row in csv.reader(f.open()):
            try:
                x, y = float(row[0]), float(row[1])
            except (ValueError, IndexError):
                continue                                 # header or blank line
            near = min(xs, key=lambda p: abs(p[0] - x))[1]
            out.setdefault(f.stem, {})[near] = y
    return out


def import_report(rdir: Path, min_agree: float = 0.01) -> dict:
    figs_in = json.loads((rdir / "figures.json").read_text())
    figures, noise, spans = [], {}, {}
    agreement = []
    for f in figs_in:
        s1, s2 = (read_session(rdir / s, f["x_values"]) for s in f["sessions"])
        series = sorted(set(s1) & set(s2))
        values = {s: [(s1[s][x] + s2[s][x]) / 2 for x in f["x_values"]] for s in series}
        lo = min(min(v) for v in values.values())
        hi = max(max(v) for v in values.values())
        span = f.get("y_span") or (hi - min(0.0, lo))
        t = ChartTable(f"{rdir.name}_fig{f['number']}", f["kind"], f.get("title", ""), f.get("x_label", ""),
                       f.get("y_label", ""), f.get("metric_word", ""), f["x_values"], values,
                       percent=f.get("percent", False), decimals=f.get("decimals", 2), ylim=(min(0.0, lo), lo + span))
        key = (f["number"], f.get("panel"))
        spans[key] = span
        for s in series:
            for x in f["x_values"]:
                d = abs(s1[s][x] - s2[s][x])
                noise[(key, s, x)] = d
                agreement.append(d / span)
        figures.append({"figure_id": f"fig{f['number']}{f.get('panel') or ''}", "number": f["number"],
                        "panel": f.get("panel"), "image": None, "caption": f.get("title", ""), "table": t.to_dict(),
                        "kind": "real", "sessions": f["sessions"]})
    tables = {(g["number"], g["panel"]): ChartTable.from_dict(g["table"]) for g in figures}
    parser = RuleParser(ranges=True, split_multi=True, peaks=True)
    claims = []
    for j, c in enumerate(json.loads((rdir / "claims.json").read_text())):
        parsed = parser.parse_all(c["sentence"], f"{rdir.name}_c{j}") if c.get("figure") else []
        for atom, p in enumerate(parsed or [None]):
            rec = {"claim_id": f"{rdir.name}_c{j}_{atom}", "sentence": c["sentence"], "atom": atom,
                   "figure_id": f"fig{c['figure']}{c.get('panel') or ''}" if c.get("figure") else None,
                   "kind": "real", "gold": c.get("gold") or "unknown", "feature": "real"}
            key = (c.get("figure"), c.get("panel"))
            if p is not None and key in tables and c.get("gold") is None and p.claim_type == "point":
                t = tables[key]
                try:
                    truth = t.value(p.series, p.x)
                except (KeyError, ValueError):
                    truth = None
                if truth is not None:
                    slack = max(noise.get((key, p.series, p.x), 0.0), min_agree * spans[key])
                    if is_within(p.claimed_value, truth, p.tolerance + slack, p.relation, p.claimed_high):
                        rec["gold"] = "correct"          # consistent with what both readers saw
                    elif not is_within(p.claimed_value, truth, p.tolerance + 3 * slack, p.relation, p.claimed_high):
                        rec["gold"] = "error"            # clearly off, beyond three times the readers' disagreement
                    rec.update(claim_type=p.claim_type, series=p.series, x=p.x, true_value=truth,
                               claimed_value=p.claimed_value, tolerance=p.tolerance, relation=p.relation)
            claims.append(rec)
    truth = {"report_id": rdir.name, "real": True, "figures": figures, "claims": claims,
             "session_agreement": {"points": len(agreement),
                                   "median_gap_share_of_axis": median(agreement) if agreement else None,
                                   "share_over_1pct": sum(a > 0.01 for a in agreement) / max(1, len(agreement))}}
    (rdir / "truth.json").write_text(json.dumps(truth, indent=1))
    return truth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report_dirs", nargs="+")
    ap.add_argument("--min-agree", type=float, default=0.01)
    args = ap.parse_args()
    for d in args.report_dirs:
        t = import_report(Path(d), args.min_agree)
        a = t["session_agreement"]
        golds = {g: sum(c["gold"] == g for c in t["claims"]) for g in ("correct", "error", "no_figure", "unknown")}
        print(f"{t['report_id']}: {len(t['figures'])} figures, {len(t['claims'])} claims {golds}; two sessions: "
              f"median gap {a['median_gap_share_of_axis']:.2%} of the axis, {a['share_over_1pct']:.0%} of points > 1%")


if __name__ == "__main__":
    main()
