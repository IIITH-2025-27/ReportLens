"""Score the v3 changes on the v3feat split, feature by feature (run_log section H).

    python scripts/analysis/v3feat_eval.py --runs runs/v3feat --out results/v3feat_eval.md

Reads the runs written by configs/exp/v3feat_sim.yaml (sim_v3feat, sim_v3feat_plain, sim_v3feat_scanned) and
configs/exp/v3feat_sim_off.yaml (simoff_v3feat). Those runs use the real ocr_pixel and three SIMULATED readers, so
verdict numbers test the logic, not how well real VLMs read these charts; ocr_pixel's own errors are real.
"""
import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from chart_claim_verifier.evaluation.metrics import join, summarize  # noqa: E402
from chart_claim_verifier.generator.tables import ChartTable  # noqa: E402
from chart_claim_verifier.pipeline import load_traces  # noqa: E402

GEN = Path("data/local/generated")


def norm(s):
    return re.sub(r"\s+", " ", s.strip().lower())


def load(run: Path):
    traces = load_traces(run / "traces_raw.jsonl")
    ids = json.loads((run / "truths.json").read_text())
    split = ids[0].rsplit("_", 1)[0]
    truths = [json.loads((GEN / ("v3feat" if split.startswith("v3feat") else split) / rid / "truth.json").read_text())
              for rid in ids]
    return traces, truths


def by_claim(traces, truths):
    gold = {(t["report_id"], norm(c["sentence"]), c.get("atom", 0)): c for t in truths for c in t["claims"]}
    out = {}
    for tr in traces:
        g = gold.get((tr.report_id, norm(tr.sentence), tr.atom))
        if g is not None:
            out[(tr.report_id, norm(tr.sentence), tr.atom)] = (g, tr)
    return gold, out


def pct(a, b):
    return f"{a} of {b} ({a / b:.0%})" if b else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default="runs/v3feat")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    R = Path(args.runs)
    v3, truths = load(R / "sim_v3feat")
    off, _ = load(R / "simoff_v3feat")
    gold, m3 = by_claim(v3, truths)
    _, m0 = by_claim(off, truths)
    feats = Counter(c.get("feature") or "plain" for c in gold.values())
    L = ["# v3feat: the v3 changes feature by feature (run_log section H)", "",
         f"{len(truths)} reports, {len(gold)} claims ({dict(feats)}). Readers: real ocr_pixel + simulated DePlot / VLM "
         f"table / VLM crop, so verdicts test the logic, not real VLM reading on these charts.", ""]

    s3, s0 = summarize(join(v3, truths)), summarize(join(off, truths))
    L += ["## Whole split, v2 switches vs v3 switches", "", "| | v2 (switches off) | v3 |", "|---|---|---|"]
    for k, f in (("coverage", "{:.1%}"), ("accuracy_when_decided", "{:.1%}"), ("wrong_flag_rate", "{:.1%}"),
                 ("missed_errors", "{:.1%}"), ("n_flagged", "{}"), ("retrieval_top1", "{:.1%}")):
        L.append(f"| {k} | {f.format(s0[k])} | {f.format(s3[k])} |")

    def rows(feature, pred=None):
        return [(g, t) for (k, (g, t)) in m3.items() if (g.get("feature") == feature if pred is None else pred(g))]

    def verdicts(pairs):
        c = Counter()
        for g, t in pairs:
            v = t.decision.verdict
            right = (v == "CONSISTENT" and g["gold"] == "correct") or (v == "MISMATCH" and g["gold"] == "error") \
                or (v == "NO_FIGURE" and g["gold"] == "no_figure")
            wrongflag = v == "MISMATCH" and g["gold"] != "error"
            c["n"] += 1
            c["decided"] += v in ("CONSISTENT", "MISMATCH", "NO_FIGURE")
            c["right"] += right
            c["wrong_flag"] += wrongflag
            c["missed"] += v == "CONSISTENT" and g["gold"] == "error"
        return c

    def line(name, pairs, rule=""):
        c = verdicts(pairs)
        return (f"| {name} | {c['n']} | {pct(c['decided'], c['n'])} | {pct(c['right'], c['decided'])} | "
                f"{c['wrong_flag']} | {c['missed']} | {rule} |")

    def off_pairs(feature):
        return [(g, t) for (k, (g, t)) in m0.items() if g.get("feature") == feature]

    L += ["", "## Claims by feature (v3; the v2 row is the same claims with the switches off)", "",
          "| feature | claims | decided | right when decided | wrong flags | missed errors | note |",
          "|---|---|---|---|---|---|---|"]
    for f in sorted(feats):
        if f == "plain":
            continue
        L.append(line(f, rows(f)))
        L.append(line(f + " (v2)", off_pairs(f)))

    # A6 / B2 / B3 parse accuracy
    def parsed_right(g, t):
        c = t.claim
        if c is None:
            return False
        ok = norm(c.series) == norm(g.get("series") or "") and norm(c.x) == norm(g.get("x") or "")
        if g.get("relation") == "between":
            ok = ok and c.relation == "between" and abs(c.claimed_value - g["claimed_value"]) < 1e-9 \
                and abs((c.claimed_high or 0) - g["claimed_high"]) < 1e-9
        elif g.get("claim_type") == "peak":
            ok = ok and c.claim_type == "peak"
        else:
            ok = ok and abs(c.claimed_value - (g.get("claimed_value") or math.nan)) < 1e-9
        return ok
    L += ["", "## Parsing (rules H6, H10)", "", "| claims | parsed right (v3) | parsed right (v2) |", "|---|---|---|"]
    for f in ("range", "two_numbers", "peak", "caption"):
        p3 = rows(f)
        all_f = [g for g in gold.values() if g.get("feature") == f]
        r0 = sum(parsed_right(g, t) for g, t in off_pairs(f))
        L.append(f"| {f} | {pct(sum(parsed_right(g, t) for g, t in p3), len(all_f))} | {pct(r0, len(all_f))} |")

    # A1 citation notes
    wrong = [(g, t) for (g, t) in m3.values() if g.get("wrong_citation")]
    right = [(g, t) for (g, t) in m3.values() if g.get("cites_figure") and not g.get("wrong_citation")]
    has = lambda t: any("citation may be wrong" in n or "the report has no Figure" in n for n in t.notes)
    L += ["", "## TA-card notes (rules H1-H3)", "",
          f"- Wrong figure number noted: {pct(sum(has(t) for _, t in wrong), len(wrong))}; note on a right figure number: "
          f"{pct(sum(has(t) for _, t in right), len(right))}."]
    flags = [(g, t) for (g, t) in m3.values() if t.decision.verdict == "MISMATCH"]
    mix = [(g, t) for g, t in flags if g.get("kind") == "mixup"]
    other = [(g, t) for g, t in flags if g.get("kind") != "mixup"]
    mixnote = lambda t: any("possibly a mix-up" in n for n in t.notes)
    L.append(f"- Mix-up explained on flagged mix-ups: {pct(sum(mixnote(t) for _, t in mix), len(mix))}; on other flags: "
             f"{pct(sum(mixnote(t) for _, t in other), len(other))}.")
    L.append(f"- Conflict notes: {sum(any('Another sentence' in n for n in t.notes) for t in v3)}.")

    # B7 hand-offs
    uns = [(g, t) for (g, t) in m3.values() if (g.get("feature") or "").startswith("unsupported") or g.get("feature") == "dual"]
    uns0 = [(g, t) for (g, t) in m0.values() if (g.get("feature") or "").startswith("unsupported") or g.get("feature") == "dual"]
    hand = lambda t: t.decision.verdict == "NOT_SURE"
    L += ["", "## Unsupported charts and dual axes (rule H15)", "",
          f"- Claims on them handed to the TA: v3 {pct(sum(hand(t) for _, t in uns), len(uns))}, "
          f"v2 {pct(sum(hand(t) for _, t in uns0), len(uns0))}; flags on them: v3 "
          f"{sum(t.decision.verdict == 'MISMATCH' for _, t in uns)}, v2 {sum(t.decision.verdict == 'MISMATCH' for _, t in uns0)} "
          f"(wrong: v3 {sum(t.decision.verdict == 'MISMATCH' and g['gold'] != 'error' for g, t in uns)}, "
          f"v2 {sum(t.decision.verdict == 'MISMATCH' and g['gold'] != 'error' for g, t in uns0)})."]

    # ocr_pixel reading on the new chart kinds (real tool)
    tables = {}
    for t in truths:
        for f in t["figures"]:
            tables[(t["report_id"], f["figure_id"])] = (ChartTable.from_dict(f["table"]), f["kind"], t["layout"])
    err = defaultdict(lambda: Counter())
    for g, tr in m3.values():
        if g.get("claim_type") != "point" or not tr.figure_id or g.get("feature") in ("error_rate",):
            continue
        key = (tr.report_id, g["figure_id"])
        if key not in tables or tr.figure_id != g["figure_id"]:
            continue
        tab, kind, layout = tables[key]
        for r in tr.readings:
            if r.tool != "ocr_pixel" or r.query is None:
                continue
            try:
                true = tab.value(r.query.series if r.query.series in tab.series else g["series"], g["x"])
            except (KeyError, ValueError):
                continue
            k = kind + (" (vector)" if layout["vector"] else "")
            err[k]["asked"] += 1
            if r.ok:
                err[k]["answered"] += 1
                if kind == "log" and r.value > 0 and true > 0:
                    lo, hi = tab.ylim
                    bad = abs(math.log10(r.value) - math.log10(true)) > 0.05 * (math.log10(hi) - math.log10(lo))
                else:
                    bad = abs(r.value - true) > 0.05 * tab.span
                err[k]["bad"] += bad
    L += ["", "## ocr_pixel (real) on the new chart kinds (rules H9, H12, H14)", "",
          "| chart kind | asked | answered | badly wrong (> 5% of the axis; log axes in log units) |", "|---|---|---|---|"]
    for k in sorted(err):
        c = err[k]
        L.append(f"| {k} | {c['asked']} | {pct(c['answered'], c['asked'])} | {pct(c['bad'], c['answered'])} |")

    # A7 / B1 / C5: twins
    for twin, label in (("sim_v3feat_plain", "one-column raster twin"), ("sim_v3feat_scanned", "scanned twin")):
        if not (R / twin).exists():
            continue
        tw, _ = load(R / twin)
        _, mt = by_claim(tw, truths)
        same = sum(1 for k in m3 if k in mt and m3[k][1].decision.verdict == mt[k][1].decision.verdict)
        found = len(set(mt))
        sents = defaultdict(set)
        for t in tw:
            sents[t.report_id].add(norm(t.sentence))
        uniq = {(r, s) for (r, s, _) in gold}
        close = sum(max((fuzz.ratio(s, x) for x in sents[r]), default=0) >= 90 for r, s in uniq)
        L += ["", f"## v3feat vs its {label}", "",
              f"- Gold claims found as sentences: v3feat {pct(len(m3), len(gold))}, {label} {pct(found, len(gold))} "
              f"(exact text); gold claim sentences read with at most small OCR differences (similarity >= 90 of 100): "
              f"{pct(close, len(uniq))}.",
              f"- Same verdict on claims found in both: {pct(same, len(set(m3) & set(mt)))}."]
        if twin == "sim_v3feat_plain":
            two = {t["report_id"] for t in truths if t["layout"]["two_column"]}
            vec = {t["report_id"] for t in truths if t["layout"]["vector"]}
            g2 = [k for k in gold if k[0] in two]
            gv = [k for k in gold if k[0] in vec]
            L.append(f"- Two-column reports: claims found {pct(sum(k in m3 for k in g2), len(g2))} (twin "
                     f"{pct(sum(k in mt for k in g2), len(g2))}). Vector-figure reports: {pct(sum(k in m3 for k in gv), len(gv))} "
                     f"(twin {pct(sum(k in mt for k in gv), len(gv))}).")
            fig3 = {(t.report_id, t.figure_id) for t in v3 if t.report_id in vec and t.figure_id}
            figt = {(t.report_id, t.figure_id) for t in tw if t.report_id in vec and t.figure_id}
            L.append(f"- Vector-figure reports, figures measured for at least one claim: v3feat {len(fig3)}, "
                     f"raster twin {len(figt)}.")
    text = "\n".join(L)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
