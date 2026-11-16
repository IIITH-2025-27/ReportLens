"""Page layout helpers for the PDF reader (v3). Each is used only when its `ingest.*` switch is on.

  reading_order      A7: two-column pages read column by column (full-width blocks split a page into bands)
  vector_figures     B1: a chart drawn with vector paths (matplotlib PDF, pgfplots) is rendered to an image
  scanned_page       C5: a page that is one big image and has no text layer is OCR'd with Tesseract

Blocks are tuples (page, y0, y1, text, x0, x1) and images (page, y0, y1, path, x0, x1), in PDF points.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

CAPTION_RE = re.compile(r"^\s*(?:Figure|Fig\.)\s*(\d+)\s*[:.]", re.I)


# ------------------------------------------------------------------ A7: two columns
def is_two_column(page_blocks: list[tuple], width: float) -> bool:
    """At least two prose blocks entirely in each half of the page."""
    mid = width / 2
    left = [b for b in page_blocks if b[5] <= mid + 0.02 * width and len(b[3]) >= 30]
    right = [b for b in page_blocks if b[4] >= mid - 0.02 * width and len(b[3]) >= 30]
    return len(left) >= 2 and len(right) >= 2


def reading_order(blocks: list[tuple], widths: dict[int, float]) -> list[tuple]:
    """Single-column pages: by height, as before. Two-column pages: bands separated by full-width blocks (title,
    wide figures' captions); inside a band the left column top to bottom, then the right column."""
    out = []
    for pno in sorted({b[0] for b in blocks}):
        pb = sorted(b for b in blocks if b[0] == pno)
        w = widths.get(pno, 595.0)
        if not is_two_column(pb, w):
            out += pb
            continue
        mid = w / 2
        left, right = [], []

        def flush():
            out.extend(sorted(left, key=lambda b: b[1]))
            out.extend(sorted(right, key=lambda b: b[1]))
            left.clear()
            right.clear()
        for b in pb:
            if b[5] <= mid + 0.02 * w:
                left.append(b)
            elif b[4] >= mid - 0.02 * w:
                right.append(b)
            else:                                   # spans both columns
                flush()
                out.append(b)
        flush()
    return out


def overlaps_x(a0: float, a1: float, b0: float, b1: float, share: float = 0.3) -> bool:
    inter = min(a1, b1) - max(a0, b0)
    return inter >= share * min(a1 - a0, b1 - b0)


# ------------------------------------------------------------------ B1: vector figures
def _clusters(rects: list, gap: float) -> list[list]:
    """Union of rectangles that touch once each is grown by `gap` points."""
    groups: list[list] = []
    for r in rects:
        grown = (r[0] - gap, r[1] - gap, r[2] + gap, r[3] + gap)
        hit = [g for g in groups if any(not (grown[2] < q[0] or grown[0] > q[2] or grown[3] < q[1] or grown[1] > q[3])
                                        for q in g)]
        merged = [r] + [q for g in hit for q in g]
        groups = [g for g in groups if g not in hit] + [merged]
    return groups


def vector_figures(page, pno: int, page_blocks: list[tuple], raster: list[tuple], out_dir: Path,
                   dpi: int = 200, caption_re: re.Pattern = CAPTION_RE
                   ) -> tuple[list[tuple], set[int], dict[int, list[str]], set[int]]:
    """Charts drawn as vector paths on this page.

    Returns (images, indices of the page's text blocks that belong to a figure, {image index: those blocks' text},
    indices of `raster` images that are part of a vector figure).
    A figure is a cluster of at least 15 drawing items covering at least 25% of the page width and 10% of its height.
    A cluster that partly overlaps a raster image is skipped (the raster is the figure); one that encloses raster
    images (a heatmap's cells and colour bar inside vector axes) is one figure with them. Short text blocks touching
    it (tick labels, legend, axis titles) are part of it.
    """
    W, H = page.rect.width, page.rect.height
    rects = []
    for d in page.get_drawings():
        r = d.get("rect")
        if r is None or (r.width > 0.8 * W and r.height < 2):          # page-wide rules are not charts
            continue
        rects.append((r.x0, r.y0, r.x1, r.y1))
    images, used, texts, inside = [], set(), {}, set()
    for g in _clusters(rects, 8.0):
        x0, y0 = min(q[0] for q in g), min(q[1] for q in g)
        x1, y1 = max(q[2] for q in g), max(q[3] for q in g)
        # v4: a simple chart (a few bars) has fewer than 15 paths; it still counts when a caption opens right below it
        caps = [b[1] for b in page_blocks if caption_re is not CAPTION_RE and caption_re.match(b[3])
                and 0 <= b[1] - y1 < 60 and b[4] < x1 and b[5] > x0]
        captioned = bool(caps)
        reach = max(y1 + 25, min(caps) - 1) if caps else y1 + 25    # a legend placed under the plot belongs to it
        if len(g) < (4 if captioned else 15):
            continue
        if x1 - x0 < 0.25 * W or y1 - y0 < 0.10 * H:
            continue
        touch = [k for k, im in enumerate(raster)
                 if im[0] == pno and not (x1 < im[4] or x0 > im[5] or y1 < im[1] or y0 > im[2])]
        enclosed = [k for k in touch if raster[k][4] >= x0 - 4 and raster[k][5] <= x1 + 4
                    and raster[k][1] >= y0 - 4 and raster[k][2] <= y1 + 4]
        if touch and len(enclosed) < len(touch):
            continue
        inside.update(enclosed)
        gy1 = y1                                   # bottom of the drawing cluster itself
        mine = []
        for i, b in enumerate(page_blocks):
            if caption_re.match(b[3]) or len(b[3]) > 60:
                continue
            if b[4] >= x0 - 25 and b[5] <= x1 + 25 and b[1] >= y0 - 25 and b[2] <= reach:
                mine.append(i)
        for i in mine:
            b = page_blocks[i]
            x0, y0, x1, y1 = min(x0, b[4]), min(y0, b[1]), max(x1, b[5]), max(y1, b[2])
        if captioned:                              # and so do the legend swatches drawn there
            for q in rects:
                if q[1] >= gy1 - 2 and q[3] <= reach and q[0] >= x0 - 25 and q[2] <= x1 + 25:
                    x0, y0, x1, y1 = min(x0, q[0]), min(y0, q[1]), max(x1, q[2]), max(y1, q[3])
        import pymupdf
        clip = pymupdf.Rect(x0 - 2, y0 - 2, x1 + 2, y1 + 2)
        path = Path(out_dir) / f"p{pno}_vec{len(images)}.png"
        page.get_pixmap(clip=clip, dpi=dpi).save(str(path))
        texts[len(images)] = [page_blocks[i][3] for i in mine]
        images.append((pno, clip.y0, clip.y1, str(path), clip.x0, clip.x1))
        used.update(mine)
    return images, used, texts, inside


# ------------------------------------------------------------------ C5: scanned pages
def looks_scanned(page, page_blocks: list[tuple]) -> bool:
    """No text layer, and one image covers most of the page."""
    if page_blocks:
        return False
    area = page.rect.width * page.rect.height
    for img in page.get_images(full=True):
        for r in page.get_image_rects(img[0]):
            if r.width * r.height >= 0.6 * area:
                return True
    return False


def scanned_page(page, pno: int, out_dir: Path, dpi: int = 200) -> tuple[list[tuple], list[tuple]]:
    """OCR a scanned page: (text blocks, figure images), both in PDF points.

    Text: Tesseract words, split into columns and printed lines by their positions (`_ocr_blocks`). Figures: large
    regions that stay dark after
    the words are blanked out (axes, bars, lines), cropped from the page render; words inside a figure are dropped.
    """
    import cv2
    import pytesseract
    pix = page.get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, pix.n)[..., :3].copy()
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    k = 72.0 / dpi
    data = pytesseract.image_to_data(gray, config="--psm 3", output_type=pytesseract.Output.DICT)
    words = []
    for i, t in enumerate(data["text"]):
        if t.strip() and float(data["conf"][i]) > 30:
            words.append((data["block_num"][i], data["par_num"][i], data["line_num"][i], data["left"][i],
                          data["top"][i], data["width"][i], data["height"][i], t.strip()))
    # figures: ink left after blanking the words, joined into big regions
    ink = (gray < 200).astype(np.uint8)
    for w in words:
        ink[max(0, w[4] - 2):w[4] + w[6] + 2, max(0, w[3] - 2):w[3] + w[5] + 2] = 0
    joined = cv2.dilate(ink, np.ones((25, 25), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    H, W = gray.shape
    figs = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if w >= 0.25 * W and h >= 0.08 * H and ink[y:y + h, x:x + w].sum() > 0.01 * w * h:
            figs.append((x, y, x + w, y + h))
    # chart text (ticks, legend) lies inside a figure region (grown a little): keep it out of the prose
    def inside(w, box, pad=30):
        return box[0] - pad <= w[3] and w[3] + w[5] <= box[2] + pad and box[1] - pad <= w[4] and w[4] + w[6] <= box[3] + pad
    prose = [w for w in words if not any(inside(w, f) for f in figs)]
    blocks = [(pno, y0 * k, y1 * k, text, x0 * k, x1 * k) for y0, y1, text, x0, x1 in _ocr_blocks(prose, W)]
    images = []
    for j, (x0, y0, x1, y1) in enumerate(figs):
        path = Path(out_dir) / f"p{pno}_scan{j}.png"
        cv2.imwrite(str(path), cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_RGB2BGR))
        images.append((pno, y0 * k, y1 * k, str(path), x0 * k, x1 * k))
    return blocks, images


def _ocr_blocks(words: list[tuple], width: int) -> list[tuple]:
    """Tesseract words -> text blocks (y0, y1, text, x0, x1) in pixels.

    Tesseract may run a line across both columns of a two-column page, so columns are found here: a vertical band in
    the middle fifth of the page, at least 1.5% of its width, that at most 3% of the words cross and almost none of
    the lines near it run across. Lines are rebuilt per column from the words' heights, and consecutive lines closer
    than 0.8 line heights form one block (a paragraph)."""
    if not words:
        return []
    gutter = None
    lo, hi = int(0.4 * width), int(0.6 * width)
    cross = np.zeros(width + 1, int)
    for w in words:
        cross[w[3]:w[3] + w[5] + 1] += 1
    # the widest band that at most 3% of the words cross; a gutter is at least 1.5% of the page wide (a one-column
    # page has narrow "rivers" of aligned spaces that a single x position can fall into)
    low = list(cross[lo:hi] <= 0.03 * len(words)) + [False]
    best, start = (0, 0), None
    for i, v in enumerate(low):
        if v and start is None:
            start = i
        elif not v and start is not None:
            best, start = max(best, (i - start, start)), None
    if best[0] >= 0.015 * width:
        x = lo + best[1] + best[0] // 2
        left = sum(w[3] + w[5] < x for w in words)
        # and it must separate two columns: of the printed lines with text near it, almost none run across it (a
        # one-column page can have a band like that when only a few lines reach the middle, but those lines cross it)
        hs = float(np.median([w[6] for w in words]))
        near, across = set(), set()
        for w in words:
            r = int((w[4] + w[6] / 2) // hs)
            if w[3] <= x <= w[3] + w[5]:
                across.add(r)
            elif x - 0.2 * width < w[3] + w[5] < x or x < w[3] < x + 0.2 * width:
                near.add(r)
        if left >= 0.2 * len(words) and len(words) - left - cross[x] >= 0.2 * len(words) \
                and len(near) >= 4 and len(across) <= 0.15 * len(near | across):
            gutter = x

    def col(w):
        if gutter is None:
            return 0
        return 0 if w[3] + w[5] < gutter else (1 if w[3] > gutter else 2)
    out = []
    for c in sorted({col(w) for w in words}):
        # printed lines from the words' own heights, not Tesseract's line numbers (it cuts a line into pieces and
        # sometimes joins the end of one line to the next): sort by vertical centre, start a line at each jump
        ws = sorted((w for w in words if col(w) == c), key=lambda w: w[4] + w[6] / 2)
        hs = float(np.median([w[6] for w in ws]))
        groups: list[list] = []
        for w in ws:
            if groups and (w[4] + w[6] / 2) - (groups[-1][-1][4] + groups[-1][-1][6] / 2) <= 0.5 * hs:
                groups[-1].append(w)
            else:
                groups.append([w])
        rs = []
        for g in groups:
            g.sort(key=lambda w: w[3])
            rs.append((c, min(w[4] for w in g), max(w[4] + w[6] for w in g), " ".join(w[7] for w in g),
                       min(w[3] for w in g), max(w[3] + w[5] for w in g)))
        lh = float(np.median([r[2] - r[1] for r in rs]))
        rs.sort(key=lambda r: r[1])
        cur = None
        for r in rs:
            if cur is not None and r[1] - cur[1] <= 0.8 * lh:
                cur = [cur[0], r[2], cur[2] + " " + r[3], min(cur[3], r[4]), max(cur[4], r[5])]
            else:
                if cur is not None:
                    out.append(tuple(cur))
                cur = [r[1], r[2], r[3], r[4], r[5]]
        out.append(tuple(cur))
    return out
