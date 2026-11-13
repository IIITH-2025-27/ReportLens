"""Draws the figures of report.tex. The numbers are copied from results/base/summary.md, results/lora/summary.md,
results/run_log.md and runs/local/baselines.log (source noted at each block); nothing here is computed from a model.

    python docs/mid_report/make_figures.py       (run from the repository root; needs matplotlib)
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = Path(__file__).parent / "figures"
OUT.mkdir(exist_ok=True)
BLUE, ORANGE, GREY, RED, GREEN = "#2b6cb0", "#dd7a1f", "#8a8f98", "#c0392b", "#2f855a"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 150})


def box(ax, x, y, w, h, text, fc="#eef3f8", ec=BLUE, bold=False, fs=8.6):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06", fc=fc, ec=ec, lw=1.4))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, fontweight="bold" if bold else "normal")


def arrow(ax, x0, y0, x1, y1):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0), arrowprops=dict(arrowstyle="->", color="#444", lw=1.2))


# ------------------------------------------------------------------ 1. pipeline
# Two rows of four tiles that run the full width; the second row is read right to left (snake order).
fig, ax = plt.subplots(figsize=(10, 2.7))
ax.set_xlim(0, 10.2); ax.set_ylim(0, 2.7); ax.axis("off")
W, H, STEP = 2.3, 1.1, 2.6
top = ["1. Report PDF\ntext and figures", "2. Find the figure\nfigure number, caption,\nlegend names",
       "3. Parse the claim\nseries, x, value,\nrounding", "4. Pick tools\nfrom the measured\ntool profile"]
bottom = ["8. Fixed rule decides\nflag / accept /\nnot sure", "7. Error margin\nfrom charts with\nknown values",
          "6. Combine\nmedian of the\nreadings", "5. Read the value\nwith up to four tools"]
for i, t in enumerate(top):
    box(ax, 0.05 + i * STEP, 1.55, W, H, t, fs=9.5)
    if i:
        arrow(ax, 0.05 + (i - 1) * STEP + W, 1.55 + H / 2, 0.05 + i * STEP, 1.55 + H / 2)
styles = [dict(fc="#e8f5ee", ec=GREEN, bold=True), dict(fc="#fdf3e7", ec=ORANGE), {}, dict(fc="#fdf3e7", ec=ORANGE)]
for i, (t, st) in enumerate(zip(bottom, styles)):
    box(ax, 0.05 + i * STEP, 0.05, W, H, t, fs=9.5, **st)
    if i:
        arrow(ax, 0.05 + i * STEP, 0.05 + H / 2, 0.05 + (i - 1) * STEP + W, 0.05 + H / 2)
x_last = 0.05 + 3 * STEP + W / 2
arrow(ax, x_last, 1.55, x_last, 0.05 + H)
fig.savefig(OUT / "pipeline.png", bbox_inches="tight"); plt.close(fig)

# ------------------------------------------------------------------ 2. per split (informed planner; results/base/summary.md)
splits = ["test", "dev", "holdout", "holdout2", "holdout3", "all\n(1000 claims)"]
cov = [74.1, 80.8, 78.0, 83.7, 76.1, 78.6]
right = [99.3, 97.6, 91.7, 97.7, 97.3, 96.8]
wrong = [1.2, 1.4, 9.4, 1.2, 3.0, 3.0]
fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.6), gridspec_kw={"width_ratios": [1.2, 1]})
xs = range(len(splits)); w = 0.38
a.bar([x - w / 2 for x in xs], cov, w, color=BLUE, label="coverage (decided)")
a.bar([x + w / 2 for x in xs], right, w, color=GREEN, label="right, of those decided")
a.set_ylim(0, 105); a.set_xticks(list(xs)); a.set_xticklabels(splits, fontsize=8); a.set_ylabel("%"); a.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, frameon=False)
a.set_title("How much it decides, and how often it is right", fontsize=10)
cols = [GREY, GREY, RED, GREY, GREY, BLUE]
b.bar(list(xs), wrong, color=cols)
for x, v in zip(xs, wrong):
    b.text(x, v + 0.25, f"{v:.1f}", ha="center", fontsize=8)
b.set_xticks(list(xs)); b.set_xticklabels(splits, fontsize=8); b.set_ylabel("% of flags that were wrong")
b.set_title("Wrong flags (lower is better)", fontsize=10)
fig.tight_layout(); fig.savefig(OUT / "per_split.png"); plt.close(fig)

# ------------------------------------------------------------------ 3. against baselines (test split; runs/local/baselines.log and results/base/summary.md)
names = ["B1\nVLM answers\ndirectly", "B4\ntools, model\njudges", "P0\nall tools\n+ rule", "P1\nfixed order\n+ rule", "P3\ninformed\n+ rule"]
wf = [36.1, 37.2, 2.6, 1.3, 1.2]
ms = [61.0, 0.0, 1.0, 1.0, 0.0]
fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.6))
cs = [RED, RED, GREY, GREY, BLUE]
a.bar(names, wf, color=cs); a.set_ylabel("% of flags that were wrong"); a.set_title("Wrong flags (test split)", fontsize=10)
for i, v in enumerate(wf):
    a.text(i, v + 0.8, f"{v:.1f}", ha="center", fontsize=8)
b.bar(names, ms, color=cs); b.set_ylabel("% of real errors accepted as fine"); b.set_title("Missed errors (test split)", fontsize=10)
for i, v in enumerate(ms):
    b.text(i, v + 0.8, f"{v:.1f}", ha="center", fontsize=8)
for ax_ in (a, b):
    ax_.tick_params(axis="x", labelsize=7.5)
fig.tight_layout(); fig.savefig(OUT / "baselines.png"); plt.close(fig)

# ------------------------------------------------------------------ 4. smallest error caught (test, informed; results/base/summary.md)
size = ["2%", "5%", "10%", "20%", "50%"]
of_all = [70, 86, 72, 86, 94]
of_meas = [87.5, 92.3, 86.7, 100, 100]
fig, ax = plt.subplots(figsize=(6.4, 3.4))
ax.plot(size, of_meas, "o-", color=BLUE, label="of errors the tools could measure")
ax.plot(size, of_all, "s--", color=GREY, label="of all planted errors")
ax.set_ylim(40, 104); ax.set_xlabel("size of the planted error (share of the axis range)"); ax.set_ylabel("% flagged"); ax.legend(fontsize=8, loc="lower right")
fig.tight_layout(); fig.savefig(OUT / "catch_rate.png"); plt.close(fig)

# ------------------------------------------------------------------ 5. fine-tuning (results/run_log.md C6)
labels = ["answers\n(higher is better)", "median error\n(% of axis range)", "90th-percentile error\n(% of axis range)", "badly wrong\n(% of answers, > 5% off)"]
base = [66.2, 1.4, 17.3, 26.0]
lora = [74.0, 0.8, 8.7, 17.3]
fig, axs = plt.subplots(1, 4, figsize=(10, 3.0))
for a, l, b0, b1 in zip(axs, labels, base, lora):
    a.bar(["base", "LoRA"], [b0, b1], color=[GREY, BLUE])
    for i, v in enumerate([b0, b1]):
        a.text(i, v * 1.02, f"{v:g}", ha="center", fontsize=8)
    a.set_title(l, fontsize=8.5); a.set_ylim(0, max(b0, b1) * 1.25)
fig.suptitle("VLM chart-to-table tool on the 51 calibration charts (1,063 readings)", fontsize=10)
fig.tight_layout(); fig.savefig(OUT / "lora.png"); plt.close(fig)
# ------------------------------------------------------------------ 6. calibrated margin against the raw-disagreement margin (B5)
# all five splits pooled, all-tools readings; results/run_log.md D2 (python scratch sweep over `evaluation/sweep.py`)
ours = [(23.1, 86.7), (20.4, 86.3), (17.3, 85.9), (14.2, 84.8), (8.8, 81.5), (4.9, 78.0), (3.9, 75.3), (3.3, 69.6)]
b5 = [(18.6, 81.6), (8.8, 80.3), (4.9, 80.8), (3.8, 75.9), (4.0, 67.4), (3.9, 52.1), (3.4, 35.6)]
fig, ax = plt.subplots(figsize=(6.4, 3.8))
ax.plot(*zip(*ours), "o-", color=BLUE, label="calibrated margin (this project)")
ax.plot(*zip(*b5), "s--", color=ORANGE, label="B5: raw disagreement x fixed factor")
ax.axvline(10, color=GREY, lw=0.8, ls=":"); ax.text(10.2, 38, "10% target", fontsize=8, color=GREY)
ax.set_xlabel("% of flags that were wrong"); ax.set_ylabel("coverage (% of claims decided)"); ax.legend(fontsize=8, loc="lower right")
fig.tight_layout(); fig.savefig(OUT / "calibrated_vs_b5.png"); plt.close(fig)
print("figures written to", OUT)
