"""E2 done fairly: the calibrated margin against B5 (raw disagreement x a fixed factor), and what the BH batch check adds.

    python scripts/margin_vs_b5.py --choose test=v3_test dev=v3_dev \
        --evaluate holdout=v3_holdout holdout2=v3_holdout2 holdout3=u17old_holdout3 final=final

Re-decides the saved all-tools readings (runs/local/<prefix>_all_tools/traces_raw.jsonl); no model is called.
  1. Each method's setting (our level, B5's factor) is CHOSEN on the --choose splits: the highest coverage whose wrong-flag
     rate is at or below the target. It is then MEASURED on the --evaluate splits, with 95% intervals that resample whole
     reports, and a paired interval for the coverage difference.
  2. BH: with level_flag >= 1 - alpha a flag's p-value is at most 1 - level_flag <= alpha, so BH keeps every flag. Lower
     per-claim levels let BH act; the table shows what it then does on all splits.
The replay skips the two-figure rule (agent.ambiguous_rule), so its numbers differ slightly from full runs.
"""
import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from chart_claim_verifier.calibration.store import CalibrationTable, ConstantTable
from chart_claim_verifier.config import load_config
from chart_claim_verifier.decide.rule import RuleConfig
from chart_claim_verifier.evaluation.metrics import coverage, join, wrong_flag_rate
from chart_claim_verifier.evaluation.sweep import redecide
from chart_claim_verifier.generator.build import load_truth
from chart_claim_verifier.pipeline import load_traces

LEVELS = (0.8, 0.85, 0.9, 0.925, 0.95, 0.975)
FACTORS = (0.5, 1, 1.5, 2, 3, 5)


def load(prefix: str):
    d = Path("runs/local") / f"{prefix}_all_tools"
    ids = json.loads((d / "truths.json").read_text())
    truths = [load_truth(Path("data/local/generated") / r.rsplit("_", 1)[0] / r) for r in ids]
    return load_traces(d / "traces_raw.jsonl"), truths


def interval(vals):
    v = sorted(x for x in vals if x == x)
    return v[int(0.025 * len(v))], v[int(0.975 * len(v)) - 1]


def boot(rows_a, rows_b, n=1000, seed=0):
    by_a, by_b = defaultdict(list), defaultdict(list)
    for r in rows_a:
        by_a[r.report_id].append(r)
    for r in rows_b:
        by_b[r.report_id].append(r)
    ids, rng = list(by_a), random.Random(seed)
    out = defaultdict(list)
    for _ in range(n):
        pick = [rng.choice(ids) for _ in ids]
        a = [r for i in pick for r in by_a[i]]
        b = [r for i in pick for r in by_b[i]]
        out["cov_a"].append(coverage(a))
        out["cov_b"].append(coverage(b))
        out["wfr_a"].append(wrong_flag_rate(a))
        out["wfr_b"].append(wrong_flag_rate(b))
        out["diff"].append(coverage(a) - coverage(b))
    return {k: interval(v) for k, v in out.items()}


def pct(x):
    return f"{100 * x:.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default="configs/exp/local_real.yaml")
    ap.add_argument("--choose", nargs="+", default=["test=v3_test", "dev=v3_dev"])
    ap.add_argument("--evaluate", nargs="+",
                    default=["holdout=v3_holdout", "holdout2=v3_holdout2", "holdout3=u17old_holdout3"])
    ap.add_argument("--out", default="results/margin_vs_b5.md")
    args = ap.parse_args()
    cfg = load_config(args.config)
    rc0 = RuleConfig.from_cfg(cfg)
    table = CalibrationTable.load(Path(cfg["paths"]["calibration_dir"]) / ("_".join(cfg["tools"]["enabled"]) + ".json"))
    choose = dict(a.split("=") for a in args.choose)
    evaluate = dict(a.split("=") for a in args.evaluate)
    data = {s: load(p) for s, p in {**choose, **evaluate}.items()}

    def rc_with(**kw):
        return RuleConfig(**{**rc0.__dict__, **kw})

    def rows(splits, tab, rc, bh=False):
        out = []
        for s in splits:
            tr, truths = data[s]
            out += join(redecide(tr, tab, rc, bh), truths)
        return out

    settings = [(f"ours, level {lv}", table, rc_with(level_flag=lv, level_accept=min(rc0.level_accept, lv)))
                for lv in LEVELS] + [(f"B5, factor {f}", ConstantTable(f, f / 2), rc0) for f in FACTORS]
    lines = ["# Calibrated margin against B5, and the BH batch check", "",
             f"Made by `python scripts/margin_vs_b5.py`; settings chosen on {', '.join(choose)}, measured on "
             f"{', '.join(evaluate)}. All-tools readings re-decided offline; the two-figure rule is not applied.", "",
             "## Every setting", "",
             "| Setting | Coverage (choose) | Wrong flags (choose) | Coverage (evaluate) | Wrong flags (evaluate) |",
             "|---|---|---|---|---|"]
    res = {}
    for name, tab, rc in settings:
        a, b = rows(choose, tab, rc), rows(evaluate, tab, rc)
        res[name] = (coverage(a), wrong_flag_rate(a), (tab, rc))
        lines.append(f"| {name} | {pct(coverage(a))} | {pct(wrong_flag_rate(a))} | {pct(coverage(b))} | {pct(wrong_flag_rate(b))} |")
    lines += ["", "## Setting chosen on the first splits, measured on the others", "",
              "| Target | Chosen (ours / B5) | Ours: coverage, wrong flags | B5: coverage, wrong flags | Coverage ours - B5 |",
              "|---|---|---|---|---|"]
    for target in (0.05, 0.10):
        pick = {}
        for prefix in ("ours", "B5"):
            ok = [(v[0], k) for k, v in res.items() if k.startswith(prefix) and v[1] <= target]
            pick[prefix] = max(ok)[1] if ok else None
        ra, rb = rows(evaluate, *res[pick["ours"]][2]), rows(evaluate, *res[pick["B5"]][2])
        ci = boot(ra, rb)
        lines.append(
            f"| {target:.0%} | {pick['ours']} / {pick['B5']} | {pct(coverage(ra))} [{pct(ci['cov_a'][0])}, {pct(ci['cov_a'][1])}], "
            f"{pct(wrong_flag_rate(ra))} [{pct(ci['wfr_a'][0])}, {pct(ci['wfr_a'][1])}] | {pct(coverage(rb))} "
            f"[{pct(ci['cov_b'][0])}, {pct(ci['cov_b'][1])}], {pct(wrong_flag_rate(rb))} [{pct(ci['wfr_b'][0])}, "
            f"{pct(ci['wfr_b'][1])}] | {100 * (coverage(ra) - coverage(rb)):+.1f} points [{100 * ci['diff'][0]:+.1f}, "
            f"{100 * ci['diff'][1]:+.1f}] |")
    every = list(data)
    lines += ["", f"## The BH batch check (alpha {rc0.alpha}) on all splits", "",
              "| Per-claim flag level | Rule alone: coverage, wrong flags | Rule + BH: coverage, wrong flags | Verdicts BH changed |",
              "|---|---|---|---|"]
    for lv in (0.6, 0.7, 0.8, 0.9, 0.95):
        rc = rc_with(level_flag=lv, level_accept=min(rc0.level_accept, lv))
        plain, bh = rows(every, table, rc), rows(every, table, rc, True)
        changed = sum(x.verdict != y.verdict for x, y in zip(plain, bh))
        lines.append(f"| {lv} | {pct(coverage(plain))}, {pct(wrong_flag_rate(plain))} | {pct(coverage(bh))}, "
                     f"{pct(wrong_flag_rate(bh))} | {changed} |")
    Path(args.out).write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
