"""Draws figures/finetune.png (report Figure 3) from results/finetune_v2 (no number is typed in by hand).

    python docs/final_report/make_ft_figure.py        (run from the repository root)

Three small panels on the same 300 test charts: values given, values within 2% of the axis, badly wrong values.
The adapter taken forward is drawn in blue, the others in grey.
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RES = Path("results/finetune_v2")
OUT = Path(__file__).parent / "figures" / "finetune.png"
BLUE, GREY, LIGHT, INK, MUTED = "#2b6cb0", "#8a8f98", "#c9ccd1", "#1f2328", "#57606a"

merge = json.loads((RES / "merge_results.json").read_text())["test"]
models = [  # (label, test measures, colour), top to bottom
    ("Base Qwen3-VL-4B", merge["base"], LIGHT),
    ("Best single adapter", merge["shard_2"], GREY),
    ("Average of seven", merge["merged_avg"], GREY),
    ("Longer training (A)", json.loads((RES / "test_shard7_A.json").read_text())["chart2table"], GREY),
    ("Longer training (B)", json.loads((RES / "test_shard7_B.json").read_text())["chart2table"], BLUE),
]
panels = [("cells_answered", "Values given\n(higher is better)", 100),
          ("within_2pct", "Within 2% of the axis\n(higher is better)", 100),
          ("badly_wrong_over_5pct", "Badly wrong, over 5% off\n(lower is better)", 40)]

plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 200})
fig, axes = plt.subplots(1, 3, figsize=(7.4, 2.05), sharey=True)
ys = range(len(models))[::-1]
for ax, (key, title, xmax) in zip(axes, panels):
    vals = [100 * m[1][key] for m in models]
    ax.barh(list(ys), vals, height=0.62, color=[m[2] for m in models], edgecolor="white", linewidth=1)
    for y, v in zip(ys, vals):
        ax.text(v + xmax * 0.015, y, f"{v:.1f}%", va="center", fontsize=8, color=INK)
    ax.set_title(title, fontsize=8.5, color=INK, loc="left")
    ax.set_xlim(0, xmax * 1.18)
    ax.set_xticks([0, xmax / 2, xmax])
    ax.set_xticklabels([f"{x:g}%" for x in (0, xmax / 2, xmax)])
    ax.tick_params(axis="x", colors=MUTED, labelsize=7.5, length=0)
    ax.tick_params(axis="y", length=0)
    ax.xaxis.grid(True, color="#e6e8eb", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.spines["left"].set_color(LIGHT)
    ax.spines["bottom"].set_visible(False)
axes[0].set_yticks(list(ys))
axes[0].set_yticklabels([m[0] for m in models], fontsize=8, color=INK)
fig.tight_layout(w_pad=1.2)
OUT.parent.mkdir(exist_ok=True)
fig.savefig(OUT, bbox_inches="tight")
print("wrote", OUT)
