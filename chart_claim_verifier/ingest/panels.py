"""What is in a figure image, before any reading tool runs (v3). Used only when its `ingest.*` switch is on.

  find_panels    B5: a figure with several plot panels (matplotlib subplots): one box per panel, in reading order
  split_caption  B5: "(a) Accuracy ... (b) Loss ..." -> one caption per panel
  chart_flags    B7: "dual_y" (numbered ticks on the right edge too) and "unsupported:<kind>" for scatter plots, box
                 plots, heatmaps, histograms and horizontal bars, which the tools were never built or calibrated for

All rules are simple pixel counts; each was checked to fire on none of the charts of the six evaluation splits.
"""
from __future__ import annotations

import re

import cv2
import numpy as np

from ..tools.axis import ChartReadError, Geometry, _dark, _num, _ocr_crop, find_plot_area


def find_panels(img: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Plot boxes (x0, y0, x1, y1) drawn with dark spines, in reading order. One box (or none) = not multi-panel."""
    h, w = img.shape[:2]
    dark = _dark(img, 140).astype(np.uint8)
    horiz = cv2.morphologyEx(dark, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, w // 10), 1)))
    vert = cv2.morphologyEx(dark, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(15, h // 8))))
    lines = cv2.dilate(cv2.bitwise_or(horiz, vert), np.ones((3, 3), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(lines, connectivity=8)
    boxes = []
    for i in range(1, n):
        x, y, bw, bh, _ = stats[i]
        if bw >= 0.18 * w and bh >= 0.25 * h:
            # a plot box has spines on (at least) its left and bottom edge
            ex, ey = max(6, bw // 20), max(6, bh // 20)          # tick marks can widen the box a few pixels
            if vert[y:y + bh, x:x + ex].any() and horiz[y + bh - ey:y + bh, x:x + bw].any():
                boxes.append((int(x), int(y), int(x + bw), int(y + bh)))
    boxes = [b for b in boxes if not any(o != b and o[0] <= b[0] and o[1] <= b[1] and o[2] >= b[2] and o[3] >= b[3]
                                         for o in boxes)]                 # drop boxes inside other boxes
    rows: list[list] = []
    for b in sorted(boxes, key=lambda b: b[1]):
        row = next((r for r in rows if abs(r[0][1] - b[1]) < 0.15 * h), None)
        (row.append(b) if row is not None else rows.append([b]))
    return [b for r in rows for b in sorted(r, key=lambda b: b[0])]


def panel_crops(img: np.ndarray, boxes: list[tuple]) -> list[tuple[int, int, int, int]]:
    """Crop windows that keep each panel's tick labels and titles: halfway to the neighbouring panel."""
    h, w = img.shape[:2]
    out = []
    for b in boxes:
        left = max([o[2] for o in boxes if o[2] <= b[0] and _same_row(o, b)], default=None)
        right = min([o[0] for o in boxes if o[0] >= b[2] and _same_row(o, b)], default=None)
        above = max([o[3] for o in boxes if o[3] <= b[1] and _same_col(o, b)], default=None)
        below = min([o[1] for o in boxes if o[1] >= b[3] and _same_col(o, b)], default=None)
        # labels sit left of / below the box, so the cut to the left neighbour goes close to that neighbour's spine
        x0 = 0 if left is None else int(left + 0.15 * (b[0] - left))
        x1 = w if right is None else int(b[2] + 0.15 * (right - b[2]))
        y0 = 0 if above is None else int(above + 0.5 * (b[1] - above))
        y1 = h if below is None else int(b[3] + 0.6 * (below - b[3]))
        out.append((x0, y0, x1, y1))
    return out


def _same_row(a, b) -> bool:
    return min(a[3], b[3]) - max(a[1], b[1]) > 0.5 * min(a[3] - a[1], b[3] - b[1])


def _same_col(a, b) -> bool:
    return min(a[2], b[2]) - max(a[0], b[0]) > 0.5 * min(a[2] - a[0], b[2] - b[0])


def split_caption(caption: str, n: int) -> list[str]:
    """'Results. (a) Accuracy on CIFAR-10. (b) Training loss.' -> per-panel captions (shared text + own part)."""
    parts = re.split(r"\(([a-h])\)\s*", caption)
    if len(parts) < 3:
        return [caption] * n
    shared = parts[0].strip()
    own = {parts[i].lower(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    letters = "abcdefgh"[:n]
    return [" ".join(x for x in (shared, own.get(l, "")) if x) for l in letters]


# ------------------------------------------------------------------ B7: kinds of chart the tools cannot read
def _right_axis_numbers(img: np.ndarray, geo: Geometry) -> int:
    """Numbered tick labels just right of the plot area (a second y-axis)."""
    a, h, w = geo.area, img.shape[0], img.shape[1]
    if w - a.right < 2 * geo.font_px:
        return 0
    dark = _dark(img, 165)
    marks = dark[a.top:a.bottom, a.right + 2:min(w, a.right + 7)].any(axis=1)
    ys = [i + a.top for i in np.where(marks)[0]]
    groups, cur = [], []
    for y in ys:
        if cur and y - cur[-1] > 2:
            groups.append(float(np.mean(cur)))
            cur = []
        cur.append(y)
    if cur:
        groups.append(float(np.mean(cur)))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    f = geo.font_px
    nums = [_num(_ocr_crop(gray, a.right + 5, y - 0.8 * f, min(w, a.right + 7 * f), y + 0.8 * f, True)) for y in groups]
    return sum(v is not None for v in nums)


def _components(region: np.ndarray):
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    sat = ((hsv[..., 1] > 80) & (hsv[..., 2] > 60)).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(sat, connectivity=8)
    return sat, stats[1:], labels


def _stepped_blob(sat: np.ndarray, stats, rh: int, rw: int) -> bool:
    """One wide coloured blob standing on the baseline whose top is a staircase of >= 6 flat steps (a histogram)."""
    for x, y, w, h, a in stats:
        if w < 0.4 * rw or y + h < rh - 4 or a < 0.15 * w * h:
            continue
        tops = []
        for c in range(x, x + w):
            col = np.where(sat[:, c])[0]
            tops.append(int(col[0]) if len(col) else rh)
        steps, run = 0, 1
        for a_, b_ in zip(tops, tops[1:]):
            if abs(a_ - b_) <= 1:
                run += 1
            else:
                steps += run >= 4
                run = 1
        steps += run >= 4
        changes = sum(abs(a_ - b_) > 2 for a_, b_ in zip(tops, tops[1:]))
        if steps >= 6 and changes >= 5:
            return True
    return False


def _hue_bins(region: np.ndarray, mask: np.ndarray) -> int:
    """Distinct hues (12-degree bins) holding at least 3% of the coloured pixels."""
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    h = hsv[..., 0][mask.astype(bool)] // 6
    if len(h) == 0:
        return 0
    counts = np.bincount(h, minlength=30)
    return int((counts >= 0.03 * len(h)).sum())


def chart_kind(img: np.ndarray, area, legend_box=None) -> str | None:
    """'scatter' | 'heatmap' | 'histogram' | 'horizontal_bar' | 'box' | None (a bar or line chart, or unsure)."""
    region = img[area.top + 2:area.bottom - 1, area.left + 2:area.right - 1]
    rh, rw = region.shape[:2]
    if rh < 20 or rw < 20:
        return None
    sat, stats, labels = _components(region)
    total = int(sat.sum())
    # heatmap: colour fills nearly the whole plot area, in many hues (a colour map, not a few series colours)
    if total > 0.85 * rh * rw and _hue_bins(region, sat) >= 5:
        return "heatmap"
    if total >= 50:
        small = [s for s in stats if s[4] >= 4 and s[2] <= 0.04 * rw and s[3] <= 0.06 * rh and 0.4 <= s[2] / max(1, s[3]) <= 2.5]
        long = [s for s in stats if s[2] >= 0.15 * rw]
        if len(small) >= 20 and sum(s[4] for s in small) >= 0.7 * total and not long:
            return "scatter"
        rects = [s for s in stats if s[4] >= 0.002 * rh * rw and s[4] / (s[2] * s[3]) > 0.85 and s[3] > 8 and s[2] > 4]
        if len(rects) >= 2:
            lefts = [s[0] for s in rects]
            bottoms = [s[1] + s[3] for s in rects]
            if max(lefts) - min(lefts) <= 3 and np.std([s[3] for s in rects]) < 0.2 * np.mean([s[3] for s in rects]) \
                    and np.std([s[2] for s in rects]) > 0.1 * np.mean([s[2] for s in rects]):
                return "horizontal_bar"                          # all bars start at the left axis, lengths vary
            hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
            hues = {int(np.median(hsv[..., 0][labels == i + 1])) // 6
                    for i, st in enumerate(stats) if any(st is r for r in rects)}
            if len(rects) >= 6 and max(bottoms) - min(bottoms) <= 3 and len(hues) == 1:
                xs = sorted((s[0], s[0] + s[2]) for s in rects)
                gaps = [b[0] - a[1] for a, b in zip(xs, xs[1:])]
                if sum(g <= 2 for g in gaps) >= 0.7 * len(gaps):
                    return "histogram"                           # bars touching each other
        if _stepped_blob(sat, stats, rh, rw):
            return "histogram"                                   # touching bars of one colour drawn as one blob
    # box plot: >= 2 dark rectangle outlines of similar width standing free inside the plot area (not letters, not
    # the legend frame)
    dark = _dark(region, 120).astype(np.uint8)
    contours, _ = cv2.findContours(dark, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    widths = []
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw < 0.03 * rw or ch < 0.06 * rh or x <= 3 or y <= 3 or x + cw >= rw - 3 or y + ch >= rh - 3:
            continue
        if legend_box is not None:
            gx, gy = x + area.left + 2, y + area.top + 2
            lx0, ly0, lx1, ly1 = legend_box
            if gx < lx1 and gx + cw > lx0 and gy < ly1 and gy + ch > ly0:
                continue
        fill = dark[y:y + ch, x:x + cw].mean()
        if fill < 0.35 and len(cv2.approxPolyDP(c, 0.04 * cv2.arcLength(c, True), True)) == 4:
            widths.append(cw)
    if len(widths) >= 2 and np.std(widths) <= 0.2 * np.mean(widths):
        return "box"
    return None


def chart_flags(path: str, geo: Geometry | None) -> list[str]:
    """Flags for a figure: "dual_y", "unsupported:<kind>", v4: "axis_multiplier"."""
    from ..tools.chart_ocr import load_bgr
    img = load_bgr(path)
    flags = []
    try:
        area = geo.area if geo is not None else find_plot_area(img)
    except ChartReadError:
        return flags
    kind = chart_kind(img, area, geo.legend_box if geo is not None else None)
    if kind:
        flags.append(f"unsupported:{kind}")
    if geo is not None and _right_axis_numbers(img, geo) >= 3:
        flags.append("dual_y")
    from ..tools.axis import axis_multiplier
    if axis_multiplier(img, area):                     # v4: "1e-5" / "+1e3" / "x10^3" above the y-axis
        flags.append("axis_multiplier")
    return flags
