"""Is a bar's top hidden behind the legend? (v3, C1)

A legend frame is drawn semi-transparent (matplotlib: 80% opaque by default, 90% in our generator), so a bar that
runs on behind it tints the frame faintly in the bar's colour. A bar whose top is visible just below the legend does
not. U18 (rejected) could only see that the bar *reaches* the legend's lower edge, and so could not tell a hidden
top from a tall visible one; this measures the tint inside the frame instead.

`hidden_top` returns True / False, or None when the geometry cannot be read (then nothing is concluded).
"""
from __future__ import annotations

import numpy as np

from ..schemas import Figure
from .axis import ChartReadError, analyse, mix_mask, series_colour
from .chart_ocr import load_bgr

MIN_SHARE = 0.04          # tint share that counts as "bar behind the frame" (half the 10% bleed of a 90% frame)


def tint_share(img: np.ndarray, box: tuple, x0: int, x1: int, colour, frame) -> float | None:
    """Median share of `colour` in the near-white pixels of the legend frame over columns x0..x1, against the frame's
    own face colour `frame` (the chart background). Neighbouring columns are no reference: other bars of the same
    series can sit behind them too."""
    lx0, ly0, lx1, ly1 = box
    rows = slice(max(0, ly0 + 2), max(0, ly1 - 2))
    cols = slice(max(lx0, x0), min(lx1, x1))
    if rows.stop - rows.start < 3 or cols.stop - cols.start < 2:
        return None
    region = img[rows, cols].astype(float)
    light = region.min(axis=2) > 190           # the frame is near-white in every channel; text, handles and bars are not
    px = region[light]
    if len(px) < 5:
        return None
    ref = np.asarray(frame, float)
    d = np.asarray(colour, float) - ref
    return float((np.median(px, axis=0) - ref) @ d / max(float(d @ d), 1e-6))


def hidden_top(fig: Figure, series: str, x: str) -> bool | None:
    """True when the bar of (series, x) runs on behind the legend frame and does not come out above it."""
    try:
        geo = analyse(fig.image_path)
        img = load_bgr(fig.image_path)
        colour = series_colour(img, geo, series)
    except (ChartReadError, FileNotFoundError):
        return None
    if not geo.legend_box:
        return False
    xc = geo.x_for(x)
    if xc is None:
        return None
    half = 0.5 * geo.tick_spacing() if len(geo.xticks) > 1 else 0.25 * (geo.area.right - geo.area.left)
    a = geo.area
    c0, c1 = int(max(a.left + 1, xc - half)), int(min(a.right, xc + half))
    m = mix_mask(img[a.top + 1:a.bottom, c0:c1], colour, geo.background)
    cols = [c0 + i for i in range(m.shape[1]) if m[:, i].sum() >= 3]
    if not cols:
        return None
    runs, cur = [], [cols[0]]
    for c in cols[1:]:
        if c - cur[-1] <= 1:
            cur.append(c)
        else:
            runs.append(cur)
            cur = [c]
    runs.append(cur)
    run = max(runs, key=len)
    k = max(1, int(len(run) * 0.2))
    mid = run[k:-k] or run
    bx0, bx1 = mid[0], mid[-1] + 1
    lx0, ly0, lx1, ly1 = geo.legend_box
    if bx1 < lx0 or bx0 > lx1:
        return False                                   # the legend is not over this bar
    above = m[:max(0, ly0 - 3 - a.top - 1), bx0 - c0:bx1 - c0]
    if above.size and above.any(axis=0).mean() > 0.5:
        return False                                   # the bar shows above the legend: its top is visible
    share = tint_share(img, geo.legend_box, bx0, bx1, colour, geo.background)
    return None if share is None else share >= MIN_SHARE
