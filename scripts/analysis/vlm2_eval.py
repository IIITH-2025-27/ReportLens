"""A second model family (run_log section I): the go / no-go measurement (I1) and the six-split comparison (I2).

    python scripts/analysis/vlm2_eval.py --out results/vlm2.md
    python scripts/analysis/vlm2_eval.py --profile-only          # I1 only, before the six-split run exists

I1 reads the tool profile that `chart-claim-verifier calibrate -c configs/exp/v3_vlm2.yaml` wrote. I2 pools the six
splits of runs/v3 (v3.yaml) and runs/v3_vlm2 (v3_vlm2.yaml) and compares them claim by claim.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from chart_claim_verifier.evaluation.metrics import join, summarize  # noqa: E402
from chart_claim_verifier.pipeline import load_traces  # noqa: E402

GEN = Path("data/local/generated")
SPLITS = ["test", "dev", "holdout", "holdout2", "holdout3", "final"]
OLD = ["ocr_pixel", "deplot", "vlm_table", "vlm_crop"]
NEW = ["vlm2_crop", "vlm2_table"]
PROFILE = Path("calibration_tables/local/" + "_".join(OLD + NEW) + ".profile.json")


def pct(a, b):
    return f"{a} of {b} ({a / b:.1%})" if b else "-"


def f(x, nd=1):
    return "-" if x is None else f"{100 * x:.{nd}f}%"


def profile_section(p: dict) -> tuple[list[str], bool]:
    L = ["## I1: the new tools on the calibration charts (live calls to the new model, the rest from the cache)", "",
         "| situation | tool | points (charts) | answers | answers at x without a tick label | badly wrong (> 5% of the axis) | median error |",
         "|---|---|---|---|---|---|---|"]
    for sit in ("line|hard", "bar|hard", "line|easy", "bar|easy", "*"):
        for t in OLD + NEW:
            d = (p["situations"].get(sit) or {}).get(t)
            if d:
                L.append(f"| {sit} | {t} | {d['n']} ({d.get('n_figures', '?')}) | {f(d['success'])} | "
                         f"{f(d.get('success_off_tick'))} | {f(d.get('big_error'))} | {f(d.get('median_error'), 2)} |")
    L += ["", "Pairs: of the points where both tools answered and agreed (within 3% of the axis), the share where both were "
          "badly wrong. The planner trusts a pair at <= 5% with >= 20 agreements on >= 5 charts.", "",
          "| situation | pair | agreements | wrong when agreeing | charts (with a wrong agreement) | passes the gate |",
          "|---|---|---|---|---|---|"]
    passed = False
    for sit in ("line|hard", "bar|hard", "*"):
        for key, d in sorted((p["pairs"].get(sit) or {}).items()):
            if not any(n in key.split("~") for n in NEW):
                continue
            ok = d["wrong_when_agree"] <= 0.05 and d["agree"] >= 20 and d.get("figures", 0) >= 5
            if sit == "line|hard" and ok and any(o in key.split("~") for o in OLD):
                passed = True
            L.append(f"| {sit} | {key} | {d['agree']} | {f(d['wrong_when_agree'])} ({d['agree_wrong']}) | "
                     f"{d.get('figures', '?')} ({d.get('figures_wrong', '?')}) | {'yes' if ok else 'no'} |")
    lh = (p["situations"].get("line|hard") or {}).get("vlm2_crop") or {}
    off = lh.get("success_off_tick")
    go = passed and off is not None and off >= 0.5
    L += ["", f"Cost per call (seconds, measured): " + ", ".join(
        f"{t} {c.get('seconds_per_read', 0):.2f} per read, {c.get('seconds_per_figure', 0):.1f} per figure"
        for t, c in p["cost"].items() if t in NEW), "",
          f"**Rule I1** (vlm2_crop answers >= 50% at x without a tick label on line|hard, and a new-old pair passes the gate "
          f"there): answers {f(off)}, a pair passes: {'yes' if passed else 'no'}. **{'GO' if go else 'NO-GO'}**"]
    return L, go


def pooled(run_dir: Path, prefix: str):
    rows, by_split = [], {}
    for s in SPLITS:
        d = run_dir / f"{prefix}_{s}_informed"
        if not d.exists():
            continue
        ids = json.loads((d / "truths.json").read_text())
        truths = [json.loads((GEN / i.rsplit("_", 1)[0] / i / "truth.json").read_text()) for i in ids]
        r = join(load_traces(d / "traces_raw.jsonl"), truths)
        by_split[s] = (r, json.loads((d / "metrics.json").read_text()))
        rows += r
    return rows, by_split


def counts(rows):
    cl = [r for r in rows if r.gold in ("correct", "error", "no_figure")]
    fl = [r for r in cl if r.verdict == "MISMATCH"]
    s = summarize(rows)
    return {"claims": len(cl), "coverage": s["coverage"], "flags": len(fl),
            "wrong_flags": sum(r.gold != "error" for r in fl),
            "missed": sum(r.gold == "error" and r.verdict == "CONSISTENT" for r in cl),
            "accuracy": s["accuracy_when_decided"], "not_sure": sum(r.verdict == "NOT_SURE" for r in cl)}


def bucket(reason: str) -> str:
    r = reason or ""
    if r.startswith("handed off: no trustworthy pair"):
        return "no trustworthy pair of tools for this point"
    if r.startswith("ambiguous"):
        return "two figures fit the sentence"
    if "no usable tool left" in r:
        return "still unclear, no usable tool left"
    if any(k in r for k in ("between the two margins", "too spread", "successful reading")):
        return "readings too spread out, or too few"
    return re.sub(r"\d+(\.\d+)?", "N", r)[:60]


def compare_section(old_dir: Path, new_dir: Path) -> list[str]:
    a_rows, a_split = pooled(old_dir, "v3")
    b_rows, b_split = pooled(new_dir, "v3_vlm2")
    a, b = counts(a_rows), counts(b_rows)
    L = ["## I2: six splits, v3 against v3 plus the second model family (P3 informed)", "",
         "| | v3 | v3 + Granite | change |", "|---|---|---|---|"]
    for k, lab in (("claims", "claims"), ("coverage", "coverage (decided)"), ("flags", "flags"),
                   ("wrong_flags", "wrong flags (a correct claim flagged)"), ("missed", "missed errors (an error accepted)"),
                   ("accuracy", "right when decided"), ("not_sure", "sent to the TA")):
        va, vb = a[k], b[k]
        if isinstance(va, float):
            L.append(f"| {lab} | {f(va)} | {f(vb)} | {100 * (vb - va):+.1f} points |")
        else:
            L.append(f"| {lab} | {va} | {vb} | {vb - va:+d} |")
    L += ["", "| split | coverage v3 | coverage v3 + Granite | wrong flags v3 / new | missed errors v3 / new | offline misses |",
          "|---|---|---|---|---|---|"]
    for s in SPLITS:
        if s in a_split and s in b_split:
            ca, cb = counts(a_split[s][0]), counts(b_split[s][0])
            L.append(f"| {s} | {f(ca['coverage'])} | {f(cb['coverage'])} | {ca['wrong_flags']} / {cb['wrong_flags']} | "
                     f"{ca['missed']} / {cb['missed']} | {b_split[s][1]['run'].get('offline_misses', 0)} |")
    key = lambda r: (r.report_id, r.sentence, r.trace.atom if r.trace else 0)
    va = {key(r): r for r in a_rows if r.gold in ("correct", "error", "no_figure")}
    vb = {key(r): r for r in b_rows if r.gold in ("correct", "error", "no_figure")}
    moves = Counter((va[k].verdict, vb[k].verdict, va[k].gold) for k in va if k in vb and va[k].verdict != vb[k].verdict)
    L += ["", "Verdict changes, claim by claim (old -> new, gold label):", ""]
    L += [f"- {o} -> {n} ({g}): {c}" for (o, n, g), c in moves.most_common()] or ["- none"]
    why = Counter(bucket(r.trace.decision.reason) for r in vb.values() if r.verdict == "NOT_SURE")
    why_a = Counter(bucket(r.trace.decision.reason) for r in va.values() if r.verdict == "NOT_SURE")
    L += ["", "| why a claim still goes to the TA | v3 | v3 + Granite |", "|---|---|---|"]
    L += [f"| {k} | {why_a.get(k, 0)} | {why.get(k, 0)} |" for k in sorted(set(why) | set(why_a), key=lambda k: -why_a.get(k, 0))]
    calls_a, calls_b, sec = Counter(), Counter(), Counter()
    for s, (_, m) in a_split.items():
        calls_a.update(m["run"].get("calls_by_tool", {}))
    for s, (_, m) in b_split.items():
        calls_b.update(m["run"].get("calls_by_tool", {}))
        for name, u in m["run"].get("model_usage", {}).items():
            sec[name] += u.get("seconds", 0)
    L += ["", "Tool calls (pooled): " + ", ".join(f"{t} {calls_a.get(t, 0)} -> {calls_b.get(t, 0)}"
                                                  for t in OLD + NEW),
          "", "Model seconds spent in the v3 + Granite runs (cached readings cost nothing): " +
          ", ".join(f"{k} {v / 60:.0f} min" for k, v in sec.items() if v)]
    unsafe = sum(m["run"].get("lms_unsafe_executed", 0) or 0 for _, m in b_split.values())
    keep = (b["wrong_flags"] <= a["wrong_flags"] and b["missed"] <= a["missed"]
            and b["coverage"] - a["coverage"] >= 0.02 and unsafe == 0)
    L += ["", f"**Rule I2** (pooled: wrong flags do not rise, missed errors do not rise, coverage +2 points or more, "
          f"0 unsafe LMS actions): wrong flags {a['wrong_flags']} -> {b['wrong_flags']}, missed errors {a['missed']} -> "
          f"{b['missed']}, coverage {100 * (b['coverage'] - a['coverage']):+.1f} points, unsafe actions {unsafe}. "
          f"**{'KEEP' if keep else 'NOT KEPT'}**"]
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default=str(PROFILE))
    ap.add_argument("--profile-only", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    L = ["# A reader from a second model family (run_log section I)", "",
         "Model: IBM Granite Vision 4.1 4B (`ibm-granite/granite-vision-4.1-4b`), run locally (Apple M4, MPS, bfloat16). "
         "`vlm2_crop` asks it the same crop question as `vlm_crop`; `vlm2_table` uses its chart-to-CSV task.", ""]
    sec, go = profile_section(json.loads(Path(args.profile).read_text()))
    L += sec
    if not args.profile_only and Path("runs/v3_vlm2").exists():
        L += [""] + compare_section(Path("runs/v3"), Path("runs/v3_vlm2"))
    text = "\n".join(L) + "\n"
    if args.out:
        Path(args.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
