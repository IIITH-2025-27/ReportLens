"""The `v3feat` split (results/run_log.md, section H): reports with what the six evaluation splits lack.

Charts: fractions on a 0-1 axis with % claims (A5), log-scale loss curves (B4), error bars and shaded bands (B6),
two-panel figures (B5), dual y-axes (B7), scatter / box / heatmap / histogram / horizontal-bar charts (B7), and pairs of
bar charts that a claim spans (B9).
Sentences: ranges (A6), two numbers in one sentence (B2), peak claims (B3), wrong figure numbers (A1), claims in
captions (A4), series aliases and error-rate claims (B9).
Layout: two columns (A7) and vector figures (B1). Every report also gets two twins with the same truth file:
`v3feat_plain` (one column, raster figures: the reference for A7 and B1) and `v3feat_scanned` (every page an image,
no text layer: C5).

Pages are written with PyMuPDF, so vector figures (matplotlib PDF) can be placed as real vector drawings.
The frozen generator (report_builder.py) is not touched: no existing split changes.
"""
from __future__ import annotations

import io
import json
import math
import random
import re
from dataclasses import asdict, replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pymupdf  # noqa: E402
from matplotlib.ticker import FixedLocator, FormatStrFormatter, NullFormatter, NullLocator  # noqa: E402

from ..claims.tolerance import find_numbers, find_range, is_within  # noqa: E402
from .claims import ClaimRecord, figure_claims, fmt, no_figure_claim, point_sentence, setup_sentences  # noqa: E402
from .plot import MARKERS, PALETTES, sample_style  # noqa: E402
from .tables import DATASETS, MODELS, ChartTable, make_table  # noqa: E402

KINDS = (["plain"] * 2 + ["fraction"] * 2 + ["log"] * 2 + ["errbar", "band"] + ["panels"] * 2 + ["dual"]
         + ["unsupported"] * 2 + ["cross_pair"])
UNSUPPORTED = ["scatter", "box", "heatmap", "histogram", "horizontal_bar"]
ALIASES = {"ResNet-18": "RN18", "ResNet-50": "RN50", "VGG-16": "VGG16", "EfficientNet": "EffNet", "ViT-S": "ViT-Small"}


# ------------------------------------------------------------------ tables
def fraction_of(t: ChartTable) -> ChartTable:
    """The same results drawn as fractions (0-1): what the chart shows. Claims stay in percent."""
    return replace(t, series={k: [round(v / 100, 3) for v in vs] for k, vs in t.series.items()}, percent=False,
                   decimals=3, y_label=t.y_label.replace(" (%)", ""), meta=dict(t.meta))


def loss_table(rng: random.Random, tid: str) -> ChartTable:
    n, step = rng.randint(6, 9), rng.choice([1, 2, 5])
    xs = [step * (i + 1) for i in range(n)]
    names = rng.sample(MODELS, rng.randint(1, 3))
    series = {}
    for name in names:
        start, end = rng.uniform(1.5, 3.0), rng.uniform(0.03, 0.12)
        series[name] = [round(start * (end / start) ** (i / (n - 1)) * math.exp(rng.gauss(0, 0.05)), 3) for i in range(n)]
    return ChartTable(tid, "line", "Training loss (log scale)", "Epoch", "Loss", "loss", [str(x) for x in xs], series,
                      percent=False, decimals=3)


def bar_pair(rng: random.Random, tid: str) -> tuple[ChartTable, ChartTable]:
    """Two grouped-bar tables sharing their models, on different datasets (a claim may span both)."""
    names = rng.sample(MODELS, rng.randint(2, 3))
    ds = rng.sample(DATASETS, 6)
    out = []
    for j, d in enumerate((ds[:3], ds[3:])):
        base = {x: rng.uniform(60, 92) for x in d}
        series = {n: [round(min(99.5, base[x] + rng.uniform(-6, 6)), 1) for x in d] for n in names}
        out.append(ChartTable(f"{tid}_{j}", "grouped_bar", f"Accuracy by dataset ({'vision' if j == 0 else 'text'})",
                              "Dataset", "Accuracy (%)", "accuracy", d, series, percent=True, decimals=1))
    return out[0], out[1]


# ------------------------------------------------------------------ drawing
def _draw(ax, t: ChartTable, style: dict, colors: list[str], extra: str | None = None, rng=None) -> None:
    names = list(t.series)
    if t.kind == "line":
        xs = [float(x) for x in t.x_values]
        for i, n in enumerate(names):
            ys = t.series[n]
            ax.plot(xs, ys, color=colors[i % len(colors)], linewidth=1.8,
                    marker=MARKERS[i] if style.get("markers") else None, markersize=4, label=n)
            if extra == "band":
                e = [0.04 * t.span] * len(ys)
                ax.fill_between(xs, [y - d for y, d in zip(ys, e)], [y + d for y, d in zip(ys, e)],
                                color=colors[i % len(colors)], alpha=0.2, linewidth=0)
        ax.set_xticks(xs)
        ax.set_xticklabels(t.x_values)
    else:
        pos = np.arange(len(t.x_values))
        width = 0.8 / len(names)
        top = max(max(v) for v in t.series.values())
        for i, n in enumerate(names):
            offs = pos - 0.4 + width * (i + 0.5)
            err = [0.03 * top] * len(pos) if extra == "errbar" else None
            ax.bar(offs, t.series[n], width=width * 0.92, color=colors[i % len(colors)], label=n,
                   yerr=err, capsize=3 if err else 0, ecolor="black")
        ax.set_xticks(pos)
        ax.set_xticklabels(t.x_values)
        hi = top * 1.18
        ax.set_ylim(0, min(100.0, hi) if t.percent else (min(1.0, hi) if top <= 1 else hi))
    ax.set_xlabel(t.x_label)
    ax.set_ylabel(t.y_label)
    ax.set_title(t.title, fontsize=style["font_size"])
    if len(names) > 1 or t.kind == "line":
        ax.legend(loc=style["legend_loc"], fontsize=style["font_size"] - 1, framealpha=0.9)
    t.ylim = tuple(float(v) for v in ax.get_ylim())
    t.meta["colors"] = {n: colors[i % len(colors)] for i, n in enumerate(names)}


def _draw_unsupported(ax, t: ChartTable, kind: str, colors: list[str], rng: random.Random) -> None:
    names = list(t.series)
    pos = np.arange(len(t.x_values))
    if kind == "scatter":
        for i, n in enumerate(names):
            ax.scatter(pos + rng.uniform(-0.15, 0.15), t.series[n], color=colors[i % len(colors)], s=22, label=n)
            for _ in range(4):           # several runs per point, as scatter plots of seeds look
                ax.scatter(pos + rng.uniform(-0.25, 0.25), [v + rng.gauss(0, 1.5) for v in t.series[n]],
                           color=colors[i % len(colors)], s=12)
        ax.set_xticks(pos)
        ax.set_xticklabels(t.x_values)
        ax.legend(fontsize=8)
    elif kind == "box":
        data = [[v + rng.gauss(0, 2.0) for _ in range(20)] for v in t.series[names[0]]]
        ax.boxplot(data)
        ax.set_xticks(range(1, len(t.x_values) + 1))
        ax.set_xticklabels(t.x_values)
    elif kind == "heatmap":
        m = np.array([t.series[n] for n in names])
        im = ax.imshow(m, cmap="viridis", aspect="auto")
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names)
        ax.set_xticks(range(len(t.x_values)))
        ax.set_xticklabels(t.x_values)
        plt.colorbar(im, ax=ax)
    elif kind == "histogram":
        data = [rng.gauss(t.series[names[0]][0], 8) for _ in range(400)]
        ax.hist(data, bins=14, color=colors[0])
    elif kind == "horizontal_bar":
        ax.barh(pos, t.series[names[0]], color=colors[0], height=0.6)
        ax.set_yticks(pos)
        ax.set_yticklabels(t.x_values)
    ax.set_title(t.title)
    t.ylim = tuple(float(v) for v in ax.get_ylim())


def _save(fig, png: Path, pdf: Path, style: dict) -> None:
    fig.tight_layout()
    fig.savefig(png)
    fig.savefig(pdf)                                # vector version (text stays text)
    plt.close(fig)
    if style.get("jpeg_quality"):
        from PIL import Image
        im = Image.open(png).convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=style["jpeg_quality"])
        Image.open(buf).save(png)


def render_figure(kind: str, tables: list[ChartTable], style: dict, png: Path, pdf: Path, rng: random.Random,
                  sub: str | None = None) -> None:
    colors = style["palette"]
    with plt.style.context("default"):
        plt.rcParams.update({"font.size": style["font_size"], "font.family": "DejaVu Sans"})
        if kind == "panels":
            fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.8), dpi=style["dpi"])
            for ax, t in zip(axes, tables):
                _draw(ax, t, style, colors)
        else:
            fig, ax = plt.subplots(figsize=style["figsize"], dpi=style["dpi"])
            t = tables[0]
            if kind == "unsupported":
                _draw_unsupported(ax, t, sub, colors, rng)
            elif kind == "dual":
                _draw(ax, t, style, colors)
                ax2 = ax.twinx()
                loss = tables[1]
                ax2.plot([float(x) for x in loss.x_values], loss.series[next(iter(loss.series))], "--",
                         color="black", linewidth=1.4, label="loss")
                ax2.set_ylabel("Loss")
                loss.ylim = tuple(float(v) for v in ax2.get_ylim())
            else:
                _draw(ax, t, style, colors, extra=kind if kind in ("errbar", "band") else None, rng=rng)
                if kind == "log":
                    ax.set_yscale("log")
                    lo, hi = min(min(v) for v in t.series.values()), max(max(v) for v in t.series.values())
                    ticks = [v for v in (0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5) if lo / 1.3 <= v <= hi * 1.3]
                    ax.yaxis.set_major_locator(FixedLocator(ticks))
                    ax.yaxis.set_major_formatter(FormatStrFormatter("%g"))
                    ax.yaxis.set_minor_locator(NullLocator())
                    ax.yaxis.set_minor_formatter(NullFormatter())
                    t.ylim = tuple(float(v) for v in ax.get_ylim())
        _save(fig, png, pdf, style)


# ------------------------------------------------------------------ sentences
def number_in(sentence: str, vt: str):
    """The NumberPhrase of the value written as `vt` (not the epoch that may follow it)."""
    i = sentence.find(vt)
    return next(n for n in find_numbers(sentence) if n.start == i)


def _vtxt(c: ClaimRecord, percent: bool) -> str | None:
    """The claimed number as written, for claims written exactly (half a unit of the last digit)."""
    if c.relation != "approx" or c.tolerance is None or c.tolerance <= 0:
        return None
    d = max(0, round(-math.log10(2 * c.tolerance)))
    if abs(0.5 * 10 ** -d - c.tolerance) > 1e-9:
        return None                                 # hedged ("about 80%"): skip
    return fmt(c.claimed_value, d, percent)


def range_variant(rng, c: ClaimRecord, t: ChartTable) -> ClaimRecord | None:
    """'between L and H' instead of the number (A6). Correct ranges hold the truth; wrong ones miss it by a planted gap."""
    if c.claim_type != "point" or c.relation != "approx" or c.true_value is None:
        return None
    vt = _vtxt(c, t.percent)
    if vt is None or vt not in c.sentence:
        return None
    T, span = c.true_value, t.span
    if rng.random() < 0.5:
        lo, hi = math.floor(T - rng.uniform(0.01, 0.04) * span), math.ceil(T + rng.uniform(0.01, 0.04) * span)
        kind = "range_correct"
    else:
        d = rng.choice([0.05, 0.1, 0.2]) * span
        width = max(1, round(rng.uniform(0.02, 0.05) * span))
        lo = math.ceil(T + d) if rng.random() < 0.5 else math.floor(T - d - width)
        hi, kind = lo + width, "range_planted"
    pct = "%" if t.percent else ""
    sentence = c.sentence.replace(vt, f"between {lo}{pct} and {hi}{pct}", 1)
    r = find_range(sentence)
    if r is None:
        return None
    ok = is_within(r.low.value, T, r.tolerance, "between", r.high.value)
    return replace(c, sentence=sentence, kind=kind, gold="correct" if ok else "error", claimed_value=r.low.value,
                   relation="between", tolerance=r.tolerance, delta=None, feature="range", claimed_high=r.high.value)


def two_number_sentence(rng, a: ClaimRecord, b: ClaimRecord, t: ChartTable) -> list[ClaimRecord] | None:
    """One sentence, two claims (B2)."""
    va, vb = _vtxt(a, t.percent), _vtxt(b, t.percent)
    if not va or not vb or a.claim_type != "point" or b.claim_type != "point":
        return None
    w = t.metric_word
    if t.kind == "line" and a.series == b.series and a.x != b.x:
        s = f"{a.series} reaches {va} {w} at epoch {a.x} and {vb} at epoch {b.x}."
    elif t.kind == "line" and a.x == b.x and a.series != b.series:
        s = f"At epoch {a.x}, {a.series} reaches {va} {w} and {b.series} reaches {vb} {w}."
    elif t.kind != "line":
        s = f"{a.series} achieves {va} {w} on {a.x}, while {b.series} obtains {vb} {w} on {b.x}."
    else:
        return None
    return [replace(a, sentence=s, atom=0, feature="two_numbers", cites_figure=False),
            replace(b, sentence=s, atom=1, feature="two_numbers", cites_figure=False, claim_id=b.claim_id + "_b")]


def peak_sentences(rng, t: ChartTable, fid: str, prefix: str) -> list[ClaimRecord]:
    """'S peaks at V at epoch X' (B3): the value at X (always right here) and 'X is the highest point'."""
    s = rng.choice(list(t.series))
    vals = t.series[s]
    best = max(range(len(vals)), key=lambda i: vals[i])
    lower = [i for i, v in enumerate(vals) if v <= vals[best] - 0.05 * t.span]
    i = best if (rng.random() < 0.5 or not lower) else rng.choice(lower)
    x, v = t.x_values[i], vals[i]
    vt = fmt(v, t.decimals if not t.percent else 1, t.percent)
    w = t.metric_word
    sentence = rng.choice([f"{s} peaks at {vt} {w} at epoch {x}.",
                           f"The {w} of {s} reaches its highest value of {vt} at epoch {x}.",
                           f"At epoch {x}, {s} reaches its maximum {w} of {vt}."])
    n = number_in(sentence, vt)
    common = dict(sentence=sentence, figure_id=fid, series=s, x=x, span=t.span, feature="peak")
    d = v - max(vv for j, vv in enumerate(vals) if j != i)
    return [ClaimRecord(claim_id=f"{prefix}peak", kind="correct_exact", gold="correct", claim_type="point",
                        true_value=v, claimed_value=n.value, tolerance=n.tolerance, atom=0, **common),
            ClaimRecord(claim_id=f"{prefix}peak_b", kind="peak_correct" if i == best else "peak_planted",
                        gold="correct" if d > 0 else "error", claim_type="peak", true_value=round(d, 6),
                        claimed_value=0.0, tolerance=0.0, relation="greater", atom=1, **common)]


def error_rate_sentence(rng, t: ChartTable, fid: str, prefix: str) -> ClaimRecord:
    """'S has an error rate of E% on X' for an accuracy chart (B9): true value = 100 - accuracy."""
    s, x = rng.choice(list(t.series)), rng.choice(t.x_values)
    T = round(100 - t.value(s, x), 1)
    planted = rng.random() < 0.5
    delta = rng.choice([0.05, 0.1, 0.2]) * rng.choice([-1, 1]) if planted else None
    v = max(0.5, T + (delta or 0) * t.span)
    sentence = f"{s} has an error rate of {v:.1f}% on {x}."
    n = number_in(sentence, f"{v:.1f}%")
    ok = is_within(n.value, T, n.tolerance, "approx")
    return ClaimRecord(claim_id=f"{prefix}err", sentence=sentence, figure_id=fid, kind="planted" if planted else
                       "correct_exact", gold="correct" if ok else "error", claim_type="point", series=s, x=x,
                       true_value=T, claimed_value=n.value, tolerance=n.tolerance, delta=delta, span=t.span,
                       feature="error_rate")


def cross_sentence(rng, ta: ChartTable, tb: ChartTable, fa: str, prefix: str) -> ClaimRecord | None:
    """'S scores D points higher on X1 than on X2', with X1 on one chart and X2 on the other (B9)."""
    common = [n for n in ta.series if n in tb.series]
    if not common:
        return None
    s = rng.choice(common)
    x1, x2 = rng.choice(ta.x_values), rng.choice(tb.x_values)
    if ta.value(s, x1) < tb.value(s, x2):
        (ta, x1), (tb, x2) = (tb, x2), (ta, x1)
    T = round(ta.value(s, x1) - tb.value(s, x2), 1)
    if T < 1.0:
        return None
    planted = rng.random() < 0.5
    v = T + (rng.choice([3.0, 6.0, 12.0]) if planted else 0.0)
    sentence = f"{s} scores {v:.1f} points higher on {x1} than on {x2}."
    n = number_in(sentence, f"{v:.1f}")
    ok = is_within(n.value, T, n.tolerance, "approx")
    return ClaimRecord(claim_id=f"{prefix}cross", sentence=sentence, figure_id=fa, kind="planted" if planted else
                       "correct_exact", gold="correct" if ok else "error", claim_type="difference", series=s, x=x1,
                       series_b=s, x_b=x2, true_value=T, claimed_value=n.value, tolerance=n.tolerance,
                       span=ta.span, feature="cross_chart")


# ------------------------------------------------------------------ page writer
class Writer:
    """Places paragraphs, figures and captions on A4 pages, in one or two columns."""

    def __init__(self, two_column: bool):
        self.doc = pymupdf.open()
        self.two = two_column
        self.W, self.H, self.m, self.gut = 595.0, 842.0, 50.0, 18.0
        self.cw = (self.W - 2 * self.m - self.gut) / 2 if two_column else self.W - 2 * self.m
        self._new_page()

    def _new_page(self):
        self.page = self.doc.new_page(width=self.W, height=self.H)
        self.col, self.y = 0, self.m

    def _advance(self, h: float):
        if self.y + h <= self.H - self.m:
            return
        if self.two and self.col == 0:
            self.col, self.y = 1, self.m
        else:
            self._new_page()

    def _x0(self) -> float:
        return self.m + self.col * (self.cw + self.gut)

    def _height(self, text: str, size: float) -> float:
        lines, cur = 1, 0.0
        space = pymupdf.get_text_length(" ", fontsize=size)
        for word in text.split():
            w = pymupdf.get_text_length(word, fontsize=size)
            if cur and cur + space + w > self.cw - 4:
                lines, cur = lines + 1, w
            else:
                cur += (space if cur else 0) + w
        return lines * size * 1.25 + size

    def text(self, text: str, size: float = 10, gap: float = 8):
        h = self._height(text, size)
        self._advance(h)
        rect = pymupdf.Rect(self._x0(), self.y, self._x0() + self.cw, self.y + h + size)
        self.page.insert_textbox(rect, text, fontsize=size, fontname="helv")
        self.y += h + gap

    def figure(self, png: Path, pdf: Path | None, wide: bool = False, caption: str | None = None):
        """The figure, then its caption; both go in the same column (a caption is never split from its figure)."""
        from PIL import Image
        iw, ih = Image.open(png).size
        width = self.cw if self.two else min(self.cw, 380 if not wide else self.cw)
        h = width * ih / iw
        cap_h = self._height(caption, 9) + 8 if caption else 0.0
        self._advance(h + 4 + cap_h)
        x0 = self._x0() + (self.cw - width) / 2
        rect = pymupdf.Rect(x0, self.y, x0 + width, self.y + h)
        if pdf is not None:
            src = pymupdf.open(str(pdf))
            self.page.show_pdf_page(rect, src, 0)
        else:
            self.page.insert_image(rect, filename=str(png))
        self.y += h + 4
        if caption:
            self.text(caption, size=9)

    def save(self, path: Path):
        self.doc.save(str(path))


def scanned_copy(src: Path, dst: Path, rng: random.Random, dpi: int = 150) -> None:
    """Every page as one image, no text layer (C5): what a scanner or a 'print to image' gives."""
    from PIL import Image
    doc, out = pymupdf.open(str(src)), pymupdf.open()
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        arr = np.asarray(im).astype(np.int16)
        arr = np.clip(arr + np.random.default_rng(rng.randrange(10 ** 6)).normal(0, 3, arr.shape), 0, 255).astype(np.uint8)
        buf = io.BytesIO()
        Image.fromarray(arr).save(buf, "JPEG", quality=80)
        p = out.new_page(width=page.rect.width, height=page.rect.height)
        p.insert_image(p.rect, stream=buf.getvalue())
    out.save(str(dst))


# ------------------------------------------------------------------ report
def build_v3feat_report(rid: str, rng: random.Random, root: Path, gen_cfg: dict) -> dict:
    out = root / "v3feat" / rid
    out.mkdir(parents=True, exist_ok=True)
    two_column, vector = rng.random() < 0.5, rng.random() < 0.5
    n_figs = rng.randint(2, 3)
    deltas = gen_cfg["planted_deltas"]
    figs, claims, number = [], [], 0
    kinds = [rng.choice(KINDS) for _ in range(n_figs)]
    for kind in kinds:
        number += 1
        hard = rng.random() < 0.25
        style = sample_style(rng, False, hard)
        if vector:
            style.pop("jpeg_quality", None)
        sub = rng.choice(UNSUPPORTED) if kind == "unsupported" else None
        fid = f"fig{number}"
        entries, tables = [], []                      # (figure_id, panel, chart table, claim table, chart kind)
        if kind == "fraction":
            t = make_table(rng, f"{rid}_{fid}", kind=rng.choice(["line", "bar", "grouped_bar"]))
            while not t.percent:
                t = make_table(rng, f"{rid}_{fid}", kind="bar")
            ct = fraction_of(t)
            tables = [ct]
            entries = [(fid, None, ct, t)]
        elif kind == "log":
            t = loss_table(rng, f"{rid}_{fid}")
            tables, entries = [t], [(fid, None, t, t)]
        elif kind == "panels":
            a, b = make_table(rng, f"{rid}_{fid}a"), make_table(rng, f"{rid}_{fid}b")
            tables, entries = [a, b], [(fid + "a", "a", a, a), (fid + "b", "b", b, b)]
        elif kind == "dual":
            t = make_table(rng, f"{rid}_{fid}", kind="line")
            while not t.percent:
                t = make_table(rng, f"{rid}_{fid}", kind="line")
            n_x, start, end = len(t.x_values), rng.uniform(1.5, 2.5), rng.uniform(0.1, 0.4)
            loss = ChartTable(f"{rid}_{fid}_loss", "line", "Loss", "Epoch", "Loss", "loss", list(t.x_values),
                              {next(iter(t.series)): [round(end + (start - end) * math.exp(-3 * i / n_x), 3)
                                                      for i in range(n_x)]}, percent=False, decimals=3)
            tables, entries = [t, loss], [(fid, None, t, t)]
        elif kind == "unsupported":
            t = make_table(rng, f"{rid}_{fid}", kind="grouped_bar" if sub in ("scatter", "heatmap") else "bar")
            tables, entries = [t], [(fid, None, t, t)]
        elif kind == "cross_pair":
            a, b = bar_pair(rng, f"{rid}_{fid}")
            for j, t in enumerate((a, b)):
                if j == 1:
                    number += 1
                    fid = f"fig{number}"
                png, pdf = out / f"{fid}.png", out / f"{fid}.pdf"
                render_figure("plain", [t], style, png, pdf, rng)
                figs.append({"figure_id": fid, "number": number, "panel": None, "image": png.name,
                             "vector": pdf.name, "caption": f"{t.title} for the models in this experiment.",
                             "table": t.to_dict(), "kind": "cross_pair"})
                claims += figure_claims(rng, t, fid, number, rng.randint(1, 2), deltas, f"{rid}_{fid}_")
            if (c := cross_sentence(rng, a, b, f"fig{number - 1}", f"{rid}_fig{number}_")) is not None:
                claims.append(c)
            continue
        else:                                          # plain, errbar, band
            t = make_table(rng, f"{rid}_{fid}", kind="line" if kind == "band" else ("bar" if kind == "errbar" else None))
            tables, entries = [t], [(fid, None, t, t)]
        png, pdf = out / f"{fid}.png", out / f"{fid}.pdf"
        render_figure(kind, tables, style, png, pdf, rng, sub)
        for e_fid, panel, ct, cl in entries:
            if kind == "fraction":                    # claims in percent on the 0-1 chart
                cl.ylim = (ct.ylim[0] * 100, ct.ylim[1] * 100)
            title = f"({panel}) {ct.title}" if panel else ct.title
            figs.append({"figure_id": e_fid, "number": number, "panel": panel, "image": png.name, "vector": pdf.name,
                         "caption": title, "table": ct.to_dict(), "kind": kind if not sub else f"unsupported:{sub}"})
            mine = figure_claims(rng, cl, e_fid, number, rng.randint(2, 3), deltas, f"{rid}_{e_fid}_")
            if panel:                                   # cite the panel, sometimes
                mine = [replace(c, sentence=c.sentence.replace(f"Figure {number}", f"Figure {number}({panel})"))
                        if rng.random() < 0.6 else c for c in mine]
            if kind == "log":                           # a planted value below zero cannot be drawn on a log axis
                mine = [c for c in mine if c.claim_type != "point" or c.claimed_value > 0]
            for c in mine:
                c.feature = kind if kind != "unsupported" else f"unsupported:{sub}"
            supported = kind in ("plain", "fraction", "log", "errbar", "band", "panels")
            if supported:
                mine = _sentence_variants(rng, mine, cl, e_fid, f"{rid}_{e_fid}_")
            claims += mine
        if kind == "dual":                               # a claim about the right-hand axis too
            loss = tables[1]
            x = rng.choice(loss.x_values)
            s = next(iter(loss.series))
            v = loss.value(s, x)
            sentence = f"At epoch {x}, the loss of {s} is {v:.3f}."
            n = number_in(sentence, f"{v:.3f}")
            claims.append(ClaimRecord(claim_id=f"{rid}_{fid}_dual", sentence=sentence, figure_id=fid,
                                      kind="correct_exact", gold="correct", claim_type="point", series=s, x=x,
                                      true_value=v, claimed_value=n.value, tolerance=n.tolerance, feature="dual"))
    # caption claims (A4): one supported figure gets a claim in its caption
    cap_fig = next((f for f in figs if f["kind"] in ("plain", "errbar", "band") and rng.random() < 0.6), None)
    if cap_fig is not None:
        t = ChartTable.from_dict(cap_fig["table"])
        s, x = rng.choice(list(t.series)), rng.choice(t.x_values)
        v = t.value(s, x) + (rng.choice([0.1, 0.2]) * t.span if rng.random() < 0.4 else 0.0)
        vt = fmt(v, t.decimals, t.percent)
        sent = point_sentence(rng, t, s, x, vt)
        n = number_in(sent, vt)
        ok = is_within(n.value, t.value(s, x), n.tolerance, "approx")
        cap_fig["caption"] = cap_fig["caption"] + ". " + sent
        claims.append(ClaimRecord(claim_id=f"{rid}_{cap_fig['figure_id']}_cap", sentence=sent,
                                  figure_id=cap_fig["figure_id"], kind="correct_exact" if ok else "planted",
                                  gold="correct" if ok else "error", claim_type="point", series=s, x=x,
                                  true_value=t.value(s, x), claimed_value=n.value, tolerance=n.tolerance,
                                  span=t.span, feature="caption"))
    # wrong figure numbers (A1)
    for c in claims:
        if c.cites_figure and c.feature not in ("caption",) and rng.random() < 0.15:
            m = re.search(r"Figure (\d+)(\([a-h]\))?", c.sentence)
            if m:
                wrong = rng.choice([k for k in range(1, number + 3) if k != int(m.group(1))])
                c.sentence = c.sentence.replace(m.group(0), f"Figure {wrong}", 1)
                c.wrong_citation = wrong
    extra = [no_figure_claim(rng, f"{rid}_nofig")] if rng.random() < 0.6 else []
    setup = setup_sentences(rng)

    truth = {"report_id": rid, "layout": {"two_column": two_column, "vector": vector}, "figures": figs,
             "claims": [asdict(c) for c in claims + extra]}
    _write_pdf(out / "report.pdf", truth, out, setup, two_column, vector, rng)
    (out / "truth.json").write_text(json.dumps(truth, indent=1))
    # twins with the same truth: one column + raster figures, and a scanned copy
    plain = root / "v3feat_plain" / rid
    plain.mkdir(parents=True, exist_ok=True)
    for f in figs:
        (plain / f["image"]).write_bytes((out / f["image"]).read_bytes())
    _write_pdf(plain / "report.pdf", truth, plain, setup, False, False, rng)
    (plain / "truth.json").write_text(json.dumps(truth, indent=1))
    scan = root / "v3feat_scanned" / rid
    scan.mkdir(parents=True, exist_ok=True)
    scanned_copy(out / "report.pdf", scan / "report.pdf", random.Random(rid))
    (scan / "truth.json").write_text(json.dumps(truth, indent=1))
    return truth


def _sentence_variants(rng, mine: list[ClaimRecord], t: ChartTable, fid: str, prefix: str) -> list[ClaimRecord]:
    out = []
    for c in mine:
        r = rng.random()
        if r < 0.15 and (v := range_variant(rng, c, t)) is not None:
            out.append(v)
            continue
        if r < 0.30 and c.series in ALIASES and c.series in c.sentence:
            c = replace(c, sentence=c.sentence.replace(c.series, ALIASES[c.series], 1), feature="alias")
        out.append(c)
    # two numbers in one sentence
    singles = [c for c in out if c.claim_type == "point" and c.feature not in ("range", "alias") and c.relation == "approx"]
    if len(singles) >= 2 and rng.random() < 0.5:
        a, b = singles[0], singles[1]
        pair = two_number_sentence(rng, a, b, t)
        if pair:
            out = [c for c in out if c is not a and c is not b] + pair
    if t.kind == "line" and rng.random() < 0.6:
        out += peak_sentences(rng, t, fid, prefix)
    if t.percent and t.metric_word in ("accuracy", "test accuracy") and t.kind != "line" and rng.random() < 0.5:
        out.append(error_rate_sentence(rng, t, fid, prefix))
    return out


def _write_pdf(path: Path, truth: dict, img_dir: Path, setup: list[str], two_column: bool, vector: bool,
               rng: random.Random) -> None:
    w = Writer(two_column)
    w.text("Lab Report: Model comparison", size=15, gap=10)
    w.text("1 Introduction", size=12, gap=4)
    w.text("In this report we compare several models on standard benchmarks. " + " ".join(setup))
    w.text("2 Results", size=12, gap=4)
    claims = truth["claims"]
    done = set()
    seen_numbers = set()
    for f in truth["figures"]:
        if f["number"] in seen_numbers:
            continue                                  # the second panel shares the image
        seen_numbers.add(f["number"])
        same = [g for g in truth["figures"] if g["number"] == f["number"]]
        w.text(f"Figure {f['number']} shows the results of this experiment.")
        cap = " ".join(g["caption"] for g in same) if len(same) > 1 else f["caption"]
        w.figure(img_dir / f["image"], (img_dir / f["vector"]) if vector else None, wide=f["kind"] == "panels",
                 caption=f"Figure {f['number']}: {cap}")
        body = []
        for c in claims:
            if c["figure_id"] in {g["figure_id"] for g in same} and c["feature"] != "caption" \
                    and c["sentence"] not in done:
                done.add(c["sentence"])
                body.append(c["sentence"])
        if body:
            w.text(" ".join(body))
    w.text("3 Discussion", size=12, gap=4)
    rest = [c["sentence"] for c in claims if c["figure_id"] is None and c["kind"] == "no_figure"]
    w.text(" ".join(rest + ["Overall, the results are in line with what we expected from the literature."]))
    w.save(path)

