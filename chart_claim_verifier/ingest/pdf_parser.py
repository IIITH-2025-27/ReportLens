"""PDF -> Report(figures, sentences) (implementation.md §6.2).

PyMuPDF gives text blocks with positions and the embedded images. A figure's
caption is the text block just below it that starts with "Figure N" / "Fig. N".
Figures are also OCR'd once here (legend, ticks, titles) for retrieval and the
parser, and their axis span is measured for the disagreement floor.
"""
from __future__ import annotations

import re
from pathlib import Path

import pymupdf

from ..schemas import Figure, Report, Sentence
from ..tools.axis import ChartReadError, analyse
from ..tools.chart_ocr import ocr_lines
from .chart_type import detect_chart_type

CAPTION_RE = re.compile(r"^\s*(?:Figure|Fig\.)\s*(\d+)\s*[:.]", re.I)
HEADING_RE = re.compile(r"^\s*\d+(?:\.\d+)*\s+[A-Z][\w ]{0,40}$")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    # do not split after "Fig." / "e.g." / "i.e."
    protected = re.sub(r"\b(Fig|e\.g|i\.e|et al)\.", lambda m: m.group().replace(".", "§"), text)
    return [s.replace("§", ".").strip() for s in SENT_SPLIT.split(protected) if s.strip()]


def merge_continued(blocks: list[tuple]) -> list[tuple]:
    """Join a paragraph that a page break (or a figure) cut in the middle of a sentence.

    Blocks are (page, y0, y1, text, ...) in reading order. A block that is a full line of prose and stops without a full
    stop ("... higher on IMDB than on") continues in the next block ("SVHN (Figure 4)."). Left unjoined, the first
    half parsed as a different claim and was flagged (2 of the 3 wrong flags on holdout2 had this cause, §24.7).
    Short blocks (page numbers, headers), headings and captions are never joined.
    """
    out: list[tuple] = []
    for b in blocks:
        prev = out[-1] if out else None
        if (prev and len(prev[3]) >= 30 and prev[3][-1] not in ".!?:" and not HEADING_RE.match(prev[3])
                and not CAPTION_RE.match(prev[3]) and not CAPTION_RE.match(b[3]) and not HEADING_RE.match(b[3])):
            out[-1] = (prev[0], prev[1], prev[2] if b[0] != prev[0] else b[2], prev[3] + " " + b[3]) + tuple(prev[4:])
        else:
            out.append(b)
    return out


def parse_pdf(pdf_path: str | Path, out_dir: str | Path, report_id: str | None = None,
              analyse_figures: bool = True, two_column: bool = False, vector_figures: bool = False,
              split_panels: bool = False, detect_kinds: bool = False, ocr_scanned: bool = False,
              axis_modes: tuple = ("linear",)) -> Report:
    """With every v3 option off this is the frozen reader. The options (configs: `ingest:`):
    two_column (A7), vector_figures (B1), split_panels (B5), detect_kinds (B7), ocr_scanned (C5), axis_modes (B4)."""
    from . import layout
    pdf_path, out_dir = Path(pdf_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_id = report_id or pdf_path.parent.name
    doc = pymupdf.open(str(pdf_path))

    images, blocks = [], []      # (page, y0, y1, path, x0, x1) / (page, y0, y1, text, x0, x1)
    widths, vector_text, flags_by_path = {}, {}, {}
    for pno, page in enumerate(doc):
        widths[pno] = page.rect.width
        page_blocks = [(pno, b[1], b[3], " ".join(b[4].split()), b[0], b[2])
                       for b in page.get_text("blocks") if b[6] == 0 and b[4].strip()]
        if ocr_scanned and layout.looks_scanned(page, page_blocks):
            page_blocks, scanned = layout.scanned_page(page, pno, out_dir)
            images += scanned
            flags_by_path.update({im[3]: ["scanned"] for im in scanned})
            blocks += page_blocks
            continue
        page_images = []
        for img in page.get_images(full=True):
            xref = img[0]
            rects = page.get_image_rects(xref)
            if not rects:
                continue
            data = doc.extract_image(xref)
            path = out_dir / f"p{pno}_x{xref}.{data['ext']}"
            path.write_bytes(data["image"])
            page_images.append((pno, rects[0].y0, rects[0].y1, str(path), rects[0].x0, rects[0].x1))
        if vector_figures:
            vec, used, texts, inside = layout.vector_figures(page, pno, page_blocks, page_images, out_dir)
            for j, im in enumerate(vec):
                vector_text[im[3]] = texts.get(j, [])
                flags_by_path[im[3]] = ["vector"]
            page_images = [im for k, im in enumerate(page_images) if k not in inside] + vec
            page_blocks = [b for i, b in enumerate(page_blocks) if i not in used]   # tick labels are not prose
        images += page_images
        blocks += page_blocks
    images.sort()
    blocks = merge_continued(layout.reading_order(blocks, widths) if two_column else sorted(blocks))

    figures: list[Figure] = []
    caption_ids = set()
    for k, (pno, y0, y1, path, ix0, ix1) in enumerate(images):
        cap, number = "", None
        # two-column pages (A7): a caption belongs to the figure above it in the same column
        same_col = (lambda b: layout.overlaps_x(b[4], b[5], ix0, ix1)) if two_column else (lambda b: True)
        below = [(b, i) for i, b in enumerate(blocks) if b[0] == pno and b[1] >= y1 - 5 and CAPTION_RE.match(b[3])
                 and i not in caption_ids and same_col(b)]
        if not below:
            # figure at the bottom of a page: its caption may open the next page
            first_img_next = min((im[1] for im in images if im[0] == pno + 1), default=1e9)
            below = [(b, i) for i, b in enumerate(blocks) if b[0] == pno + 1 and b[2] <= first_img_next
                     and CAPTION_RE.match(b[3]) and i not in caption_ids]
        if below:
            b, i = min(below, key=lambda bi: bi[0][1])
            caption_ids.add(i)
            number = int(CAPTION_RE.match(b[3]).group(1))
            cap = CAPTION_RE.sub("", b[3]).strip()
        fid = f"fig{number}" if number else f"img{k + 1}"
        parts = [(path, cap, None)]
        if split_panels:
            parts = _split_into_panels(path, cap, out_dir)
        for ppath, pcap, panel in parts:
            fig = Figure(figure_id=fid + (panel or ""), report_id=report_id, image_path=ppath, caption=pcap,
                         number=number, page=pno, panel=panel, flags=list(flags_by_path.get(path, [])))
            if analyse_figures:
                _analyse(fig, axis_modes, detect_kinds, vector_text.get(path, []))
            figures.append(fig)

    sentences: list[Sentence] = []
    fig_pos = [(im[0], im[2]) for im in images]
    for i, b in enumerate(blocks):
        pno, y0, y1, text = b[:4]
        if i in caption_ids or HEADING_RE.match(text):
            continue
        # the last figure before this block in reading order (used by the "nearest figure" ablation)
        before = [(pos[0], pos[1], f) for f, pos in zip(_first_per_image(figures, images), fig_pos) if pos <= (pno, y0 + 1)]
        nearest = max(before, key=lambda t: (t[0], t[1]))[2].figure_id if before else None
        for s in split_sentences(text):
            sentences.append(Sentence(sentence_id=f"{report_id}_s{len(sentences)}", report_id=report_id,
                                      text=s, page=pno, nearest_figure_id=nearest))
    return Report(report_id=report_id, pdf_path=str(pdf_path), figures=figures, sentences=sentences)


def _first_per_image(figures: list[Figure], images: list[tuple]) -> list[Figure]:
    """One figure per extracted image (the first panel of a split figure), aligned with `images`."""
    out, seen = [], set()
    for f in figures:
        key = (f.page, f.number, f.figure_id.rstrip("abcdefgh") if f.panel else f.figure_id)
        if f.panel and key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out[:len(images)]


def _analyse(fig: Figure, axis_modes: tuple, detect_kinds: bool, pdf_text: list[str]) -> None:
    """Chart type, OCR'd chart text, axis span (and, v3: log axis, y range, kind flags, the PDF's own chart text)."""
    path = fig.image_path
    fig.chart_type = detect_chart_type(path)
    fig.text_lines = [ln.text for ln in ocr_lines(path)] + list(pdf_text)
    geo = None
    try:
        geo = analyse(path, axis_modes) if axis_modes != ("linear",) else analyse(path)
        fig.y_span = geo.y_span
        # legend entries found via their colour handles are more reliable than full-image OCR
        fig.text_lines += list(geo.legend) + [t for _, t in geo.xticks]
        if axis_modes != ("linear",):
            fig.y_range = [geo.yfit.value(geo.area.bottom), geo.yfit.value(geo.area.top)]
            if geo.yfit.log:
                fig.flags.append("log_y")
    except ChartReadError:
        fig.y_span = None
    if detect_kinds:
        from .panels import chart_flags
        fig.flags += chart_flags(path, geo)


def _split_into_panels(path: str, caption: str, out_dir: Path) -> list[tuple[str, str, str | None]]:
    """B5: [(image path, caption, panel letter)]; the figure itself (panel None) when it has one plot box."""
    import cv2
    from ..tools.chart_ocr import load_bgr
    from .panels import find_panels, panel_crops, split_caption
    img = load_bgr(path)
    boxes = find_panels(img)
    if len(boxes) < 2:
        return [(path, caption, None)]
    caps = split_caption(caption, len(boxes))
    out = []
    for j, (x0, y0, x1, y1) in enumerate(panel_crops(img, boxes)):
        letter = "abcdefgh"[j]
        ppath = str(Path(out_dir) / (Path(path).stem + f"_{letter}.png"))
        cv2.imwrite(ppath, img[y0:y1, x0:x1])
        out.append((ppath, caps[j], letter))
    return out
