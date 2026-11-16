"""C1 (run_log H18): can a bar hidden behind the legend be told apart from a tall bar that is visible?

Draws bar charts with the generator's own code (generator/plot.py: same tables, styles, legend positions, JPEG
compression) and records, from matplotlib itself, the legend frame and every bar. A bar's top is hidden when it lies
inside the frame. Then `tools/occlusion.hidden_top` (the pixel-only detector the system would use) is run on every bar.

    python scripts/analysis/c1_hidden_bars.py --charts 300 --out results/c1_hidden_bars.md

Rule written before running it: build the lower-bound decision only if the detector finds >= 80% of hidden tops
with <= 5% false alarms.
"""
import argparse
import random
import sys
import tempfile
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.figure  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from chart_claim_verifier.generator.plot import render, sample_style  # noqa: E402
from chart_claim_verifier.generator.tables import make_table  # noqa: E402
from chart_claim_verifier.schemas import Figure  # noqa: E402
from chart_claim_verifier.tools.occlusion import hidden_top  # noqa: E402

CAPTURED: dict[str, dict] = {}
_save = matplotlib.figure.Figure.savefig


def _capture(self, fname, *a, **k):
    """Record the legend frame and the bars (image pixels, top-left origin) before saving."""
    self.canvas.draw()
    r = self.canvas.get_renderer()
    ax = self.axes[0]
    H = self.get_size_inches()[1] * self.dpi
    leg = ax.get_legend()
    box = None
    if leg is not None:
        e = leg.get_window_extent(r)
        box = (e.x0, H - e.y1, e.x1, H - e.y0)
    bars = [(p.get_window_extent(r), p.get_height()) for p in ax.patches]
    CAPTURED[str(fname)] = {"legend": box, "bars": [((e.x0, H - e.y1, e.x1, H - e.y0), h) for e, h in bars]}
    return _save(self, fname, *a, **k)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--charts", type=int, default=300)
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", default="c1-hidden-bars", help="development runs used other seeds than the measured one")
    args = ap.parse_args()
    matplotlib.figure.Figure.savefig = _capture
    rng = random.Random(args.seed)
    counts = Counter()
    near = Counter()                               # bars whose top is at most 20 px below the frame's lower edge
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(args.charts):
            hard = rng.random() < 0.5
            t = make_table(rng, f"c1_{i}", kind=rng.choice(["bar", "grouped_bar"]), hard=hard)
            style = sample_style(rng, False, hard)
            path = str(Path(tmp) / f"c{i}.png")
            render(t, style, path)
            cap = CAPTURED[path]
            if cap["legend"] is None:
                continue
            from PIL import Image
            w = Image.open(path).size[0]
            s = 2.0 if w < 700 else 1.0                # load_bgr works at 2x on small images
            lx0, ly0, lx1, ly1 = (v * s for v in cap["legend"])
            fig = Figure(figure_id="f", report_id="r", image_path=path, chart_type=t.kind)
            names = list(t.series)
            for k, (ext, _) in enumerate(cap["bars"]):
                series, x = names[k // len(t.x_values)], t.x_values[k % len(t.x_values)]
                bx0, top, bx1, _ = (v * s for v in ext)
                over = min(bx1, lx1) - max(bx0, lx0) >= 0.3 * (bx1 - bx0)
                truth = over and ly0 + 2 <= top <= ly1
                got = hidden_top(fig, series, x)
                key = ("hidden" if truth else "visible") + ":" + ("none" if got is None else str(got))
                counts[key] += 1
                if over and ly1 < top <= ly1 + 20 * s:
                    near["visible_near_edge:" + ("none" if got is None else str(got))] += 1
                if truth:
                    near["hidden:" + ("none" if got is None else str(got))] += 1
    hid = counts["hidden:True"] + counts["hidden:False"] + counts["hidden:none"]
    vis = counts["visible:True"] + counts["visible:False"] + counts["visible:none"]
    found = counts["hidden:True"] / max(1, counts["hidden:True"] + counts["hidden:False"])
    false_alarm = counts["visible:True"] / max(1, counts["visible:True"] + counts["visible:False"])
    near_vis = near["visible_near_edge:True"] + near["visible_near_edge:False"]
    lines = [
        "# C1: hidden bar tops (run_log H18)", "",
        f"{args.charts} bar charts drawn with the generator's code; {hid} bars hidden behind the legend, {vis} visible.", "",
        "| | detector says hidden | says visible | cannot tell |", "|---|---|---|---|",
        f"| hidden (truth) | {counts['hidden:True']} | {counts['hidden:False']} | {counts['hidden:none']} |",
        f"| visible (truth) | {counts['visible:True']} | {counts['visible:False']} | {counts['visible:none']} |",
        f"| visible, top within 20 px below the frame | {near['visible_near_edge:True']} | "
        f"{near['visible_near_edge:False']} | {near['visible_near_edge:none']} |", "",
        f"Found: {found:.0%} of hidden tops (where the detector answered). False alarms: {false_alarm:.1%} of all visible "
        f"bars, {near['visible_near_edge:True'] / max(1, near_vis):.0%} of visible bars just below the frame (the case U18 "
        f"could not separate).", "",
        f"Rule (H18): build only if found >= 80% and false alarms <= 5%. "
        f"**{'GO' if found >= 0.8 and false_alarm <= 0.05 else 'NO-GO'}**",
    ]
    text = "\n".join(lines)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
