"""Draws the figures of the final report from the saved runs (no number is typed in by hand; no model is called).

    PYTHONPATH=. python report/final_report/make_figures.py        (run from the repository root)

Reads runs/local/fin_<split>_<policy> (the frozen configuration replayed on every split), the B1-B4 baselines of the
final split (runs/local/final_all_tools/baselines.json) and the calibration readings of the base and LoRA tables.
Also writes figures/numbers.json with every number drawn, so the text can be checked against it.
"""
import json
from pathlib import Path
from statistics import median

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from chart_claim_verifier.calibration.store import CalibrationTable, ConstantTable  # noqa: E402
from chart_claim_verifier.config import load_config  # noqa: E402
from chart_claim_verifier.decide.rule import RuleConfig  # noqa: E402
from chart_claim_verifier.evaluation.metrics import coverage, join, summarize, wrong_flag_rate  # noqa: E402
from chart_claim_verifier.evaluation.sweep import redecide  # noqa: E402
from chart_claim_verifier.generator.build import load_truth  # noqa: E402
from chart_claim_verifier.pipeline import load_traces  # noqa: E402

OUT = Path(__file__).parent / "figures"
OUT.mkdir(exist_ok=True)
RUNS, DATA = Path("runs/local"), Path("data/local/generated")
SPLITS = ["test", "dev", "holdout", "holdout2", "holdout3", "final"]
PREFIX = "fin"
BLUE, ORANGE, GREY, RED, GREEN = "#2b6cb0", "#dd7a1f", "#8a8f98", "#c0392b", "#2f855a"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150})
numbers: dict = {}


def rows_of(run: Path, raw: bool = False):
    ids = json.loads((run / "truths.json").read_text())
    truths = [load_truth(DATA / r.rsplit("_", 1)[0] / r) for r in ids]
    return join(load_traces(run / ("traces_raw.jsonl" if raw else "traces.jsonl")), truths)


def pct(x):
    return round(100 * x, 1)


# ------------------------------------------------------------------ 1. per split, main policy
per = {s: summarize(rows_of(RUNS / f"{PREFIX}_{s}_informed")) for s in SPLITS}
pooled_rows = [r for s in SPLITS[:-1] for r in rows_of(RUNS / f"{PREFIX}_{s}_informed")]
per["five earlier"] = summarize(pooled_rows)
numbers["per_split_informed"] = {s: {k: per[s][k] for k in ("n_claims", "coverage", "accuracy_when_decided",
                                                             "wrong_flag_rate", "missed_errors", "n_flagged")}
                                 for s in per}
labels = ["test", "dev", "holdout", "holdout2", "holdout3", "5 earlier\npooled", "final\nuntouched"]
keys = SPLITS[:-1] + ["five earlier", "final"]
fig, (a, b) = plt.subplots(1, 2, figsize=(10.5, 3.6), gridspec_kw={"width_ratios": [1.25, 1]})
xs, w = range(len(keys)), 0.38
a.bar([x - w / 2 for x in xs], [pct(per[k]["coverage"]) for k in keys], w, color=BLUE, label="coverage (decided)")
a.bar([x + w / 2 for x in xs], [pct(per[k]["accuracy_when_decided"]) for k in keys], w, color=GREEN,
      label="right, of those decided")
a.set_ylim(0, 105); a.set_xticks(list(xs)); a.set_xticklabels(labels, fontsize=7.5); a.set_ylabel("%")
a.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=2, frameon=False)
a.set_title("How much it decides, and how often it is right", fontsize=10)
wf = [pct(per[k]["wrong_flag_rate"]) for k in keys]
b.bar(list(xs), wf, color=[GREY] * 5 + [BLUE, GREEN])
for x, v in zip(xs, wf):
    b.text(x, v + 0.25, f"{v:.1f}", ha="center", fontsize=8)
b.set_xticks(list(xs)); b.set_xticklabels(labels, fontsize=7.5); b.set_ylabel("% of flags that were wrong")
b.set_title("Wrong flags (lower is better)", fontsize=10)
fig.tight_layout(); fig.savefig(OUT / "per_split.png"); plt.close(fig)

# ------------------------------------------------------------------ 2. smallest error caught (main policy, all six splits)
all_rows = pooled_rows + rows_of(RUNS / f"{PREFIX}_final_informed")
sizes = sorted({round(abs(r.delta), 4) for r in all_rows if r.gold == "error" and r.kind == "planted" and r.delta})
of_all, of_meas, counts = [], [], []
for d in sizes:
    errs = [r for r in all_rows if r.gold == "error" and r.kind == "planted" and r.delta and round(abs(r.delta), 4) == d]
    meas = [r for r in errs if r.trace.decision.n_readings >= 2]
    of_all.append(pct(sum(r.verdict == "MISMATCH" for r in errs) / len(errs)))
    of_meas.append(pct(sum(r.verdict == "MISMATCH" for r in meas) / len(meas)))
    counts.append((len(errs), len(meas), sum(r.verdict == "MISMATCH" for r in meas),
                   sum(r.verdict == "CONSISTENT" for r in errs)))
numbers["catch_rate"] = {str(d): {"of_all": a_, "of_measured": m_, "errors_measured_caught_accepted": c_}
                         for d, a_, m_, c_ in zip(sizes, of_all, of_meas, counts)}
fig, ax = plt.subplots(figsize=(6.4, 3.3))
xl = [f"{100 * d:g}%" for d in sizes]
ax.plot(xl, of_meas, "o-", color=BLUE, label="of errors at least two tools could measure")
ax.plot(xl, of_all, "s--", color=GREY, label="of all planted errors (hand-offs count as missed)")
ax.set_ylim(40, 104); ax.set_xlabel("size of the planted error (share of the axis range)"); ax.set_ylabel("% flagged")
ax.legend(fontsize=8, loc="lower right")
fig.tight_layout(); fig.savefig(OUT / "catch_rate.png"); plt.close(fig)

# ------------------------------------------------------------------ 3. calibrated margin vs B5 on all-tools readings
cfg = load_config("configs/exp/local_real.yaml")
rc0 = RuleConfig.from_cfg(cfg)
table = CalibrationTable.load(Path(cfg["paths"]["calibration_dir"]) / ("_".join(cfg["tools"]["enabled"]) + ".json"))
p0 = {s: (load_traces(RUNS / f"{PREFIX}_{s}_all_tools" / "traces_raw.jsonl"),
          [load_truth(DATA / r.rsplit("_", 1)[0] / r)
           for r in json.loads((RUNS / f"{PREFIX}_{s}_all_tools" / "truths.json").read_text())]) for s in SPLITS}


def curve_point(tab, rc, splits, bh=False):
    rr = [x for s in splits for x in join(redecide(p0[s][0], tab, rc, bh), p0[s][1])]
    return pct(wrong_flag_rate(rr)), pct(coverage(rr))


ours = [curve_point(table, RuleConfig(**{**rc0.__dict__, "level_flag": lv, "level_accept": min(0.75, lv)}), SPLITS)
        for lv in (0.8, 0.85, 0.9, 0.925, 0.95, 0.975, 0.99)]
b5 = [curve_point(ConstantTable(f, f / 2), rc0, SPLITS) for f in (0.5, 1, 1.5, 2, 3, 5)]
bh = [curve_point(table, RuleConfig(**{**rc0.__dict__, "level_flag": lv, "level_accept": min(0.75, lv)}), SPLITS, True)
      for lv in (0.6, 0.7, 0.8)]
numbers["tradeoff_all_six"] = {"ours_levels_0.8_to_0.99": ours, "b5_factors_0.5_to_5": b5, "ours_lower_level_plus_bh": bh}
fig, ax = plt.subplots(figsize=(6.6, 3.8))
ax.plot(*zip(*ours), "o-", color=BLUE, label="calibrated margin, level 0.8 to 0.99")
ax.plot(*zip(*b5), "s--", color=ORANGE, label="B5: raw disagreement x factor 0.5 to 5")
ax.plot(*zip(*bh), "^", color=GREEN, ms=8, label="level 0.6 / 0.7 / 0.8, then BH at 0.10")
ax.axvline(10, color=GREY, lw=0.8, ls=":"); ax.text(10.2, max(c for _, c in b5 + ours), "10% target", fontsize=8, color=GREY, va="top")
ax.set_xlabel("% of flags that were wrong"); ax.set_ylabel("coverage (% of claims decided)"); ax.legend(fontsize=8, loc="lower right")
fig.tight_layout(); fig.savefig(OUT / "calibrated_vs_b5.png"); plt.close(fig)

# ------------------------------------------------------------------ 4. LoRA: reading quality of vlm_table on the calibration charts
def reading(path):
    errs = json.loads(Path(path).read_text())
    vals = [abs(e["vlm_table"]) for e in errs if "vlm_table" in e]
    v = sorted(vals)
    return [pct(len(vals) / len(errs)), pct(median(v)), pct(v[int(0.9 * len(v))]), pct(sum(x > 0.05 for x in v) / len(v))]


base = reading("calibration_tables/local/ocr_pixel_deplot_vlm_table_vlm_crop.errors.json")
lora = reading("calibration_tables/local_lora/ocr_pixel_deplot_vlm_table_vlm_crop.errors.json")
numbers["lora_reading"] = {"base": base, "lora": lora, "order": ["answers", "median error", "p90 error", "badly wrong"]}
labels4 = ["answers\n(higher is better)", "median error\n(% of axis range)", "90th-percentile error\n(% of axis range)",
           "badly wrong\n(% of answers, > 5% off)"]
fig, axs = plt.subplots(1, 4, figsize=(10, 2.9))
for a_, l_, b0, b1 in zip(axs, labels4, base, lora):
    a_.bar(["base", "LoRA"], [b0, b1], color=[GREY, BLUE])
    for i, v in enumerate([b0, b1]):
        a_.text(i, v * 1.02, f"{v:g}", ha="center", fontsize=8)
    a_.set_title(l_, fontsize=8.5); a_.set_ylim(0, max(b0, b1) * 1.25)
fig.suptitle("VLM chart-to-table tool on the 51 calibration charts (1,063 points)", fontsize=10)
fig.tight_layout(); fig.savefig(OUT / "lora.png"); plt.close(fig)

# ------------------------------------------------------------------ 5. one wrong flag, as the TA would see it (holdout_017)
ex = next(t for t in load_traces(RUNS / f"{PREFIX}_holdout_informed" / "traces.jsonl")
          if t.report_id == "holdout_017" and t.decision.verdict == "MISMATCH" and "CNN reaches over 85%" in t.sentence)
img = plt.imread(str(next(f for f in json.loads((DATA.parent / "work/holdout/holdout_017/report.json").read_text())["figures"]
                          if f["figure_id"] == ex.figure_id)["image_path"]))
true = next(c for c in load_truth(DATA / "holdout" / "holdout_017")["claims"] if c["sentence"] == ex.sentence)["true_value"]
fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.2), gridspec_kw={"width_ratios": [1.3, 1]})
a.imshow(img); a.axis("off")
card = (f"Sentence: \"{ex.sentence}\"\n\n"
        + "\n".join(f"{t:>10s} reads {v:.1f}" for t, v in ex.tool_values.items())
        + f"\n\nestimate {ex.decision.estimate:.1f}, flag margin {ex.decision.margin_flag:.1f}\n"
        f"verdict: {ex.decision.verdict} (wrong)\ntrue value: {true:.1f}\n\n"
        "The legend box hides the tops of the CIFAR-10 bars.\nTwo tools of different kinds both read about 50,\nso they agree and the claim is flagged.")
b.text(0, 0.5, card, va="center", fontsize=8.5, family="monospace"); b.axis("off")
fig.tight_layout(); fig.savefig(OUT / "example.png", bbox_inches="tight"); plt.close(fig)
numbers["example_holdout_017"] = {"tool_values": ex.tool_values, "true": true, "estimate": ex.decision.estimate}

# ------------------------------------------------------------------ 6. numbers for the text: capabilities, failures, policies
def run_stats(prefix_policy: str, splits) -> dict:
    out = {"calls_saved_by_memory": 0, "policy_invalid_actions": 0, "lms_unsafe_executed": 0, "lms_blocked": 0,
           "calls_by_tool": {}}
    for s in splits:
        m = json.loads((RUNS / f"{PREFIX}_{s}_{prefix_policy}" / "metrics.json").read_text())["run"]
        for k in ("calls_saved_by_memory", "policy_invalid_actions", "lms_unsafe_executed", "lms_blocked"):
            out[k] += m.get(k, 0)
        for t, c in (m.get("calls_by_tool") or {}).items():
            out["calls_by_tool"][t] = out["calls_by_tool"].get(t, 0) + c
    return out


profile = json.loads(Path("calibration_tables/local/ocr_pixel_deplot_vlm_table_vlm_crop.profile.json").read_text())
sec = {t: (c.get("seconds_per_figure") if t in ("deplot", "vlm_table") else c.get("seconds_per_read")) or 0.0
       for t, c in profile["cost"].items()}
for scope, splits in (("all_six", SPLITS), ("final", ["final"]), ("five_earlier", SPLITS[:-1])):
    block = {}
    for pol in ("all_tools", "fixed_order", "informed"):
        rr = [r for s in splits for r in rows_of(RUNS / f"{PREFIX}_{s}_{pol}")]
        m = summarize(rr)
        st = run_stats(pol, splits)
        block[pol] = {k: m[k] for k in ("n_claims", "coverage", "accuracy_when_decided", "wrong_flag_rate", "missed_errors",
                                        "n_flagged", "handoff_rate", "retrieval_top1", "no_figure_accuracy",
                                        "parse_accuracy", "tool_success_rate", "recovery_rate", "tool_calls_per_claim",
                                        "error_attribution", "handoff_reasons", "margin_check", "early_handoffs",
                                        "blocked_action_attempts", "flags_on_non_claims", "measured_on_wrong_figure")}
        block[pol].update(st)
        block[pol]["model_minutes"] = round(sum(sec.get(t, 0) * c for t, c in st["calls_by_tool"].items()) / 60, 1)
        block[pol]["model_minutes_per_200_claims"] = round(block[pol]["model_minutes"] * 200 / max(1, m["n_claims"]), 1)
    numbers[f"policies_{scope}"] = block

(OUT / "numbers.json").write_text(json.dumps(numbers, indent=1, default=str))
print("figures and numbers.json written to", OUT)
