"""Real-world-style sample reports for testing (v4, run_log section J): sample_reports/real_world/.

    python scripts/real/make_sample_reports.py            # writes the PDFs, truth.json and expected.json files
    python scripts/real/check_samples.py                  # runs the checker on them (see that script)

Every report is something the generated splits never contain: LaTeX two-column text with vector figures, Word-style
pages with Excel-look charts, negations and decreases, near-identical model names, train / validation / test
charts, hard chart kinds, a scanned report, and a full three-page report built with pgfplots. Each report folder has

    report.pdf      the report
    truth.json      the true value of every plotted point, per figure number (and panel)
    expected.json   every sentence with a number: is it true, which verdicts are acceptable, and why

Verdicts in expected.json:
    "true" claim      acceptable: CONSISTENT, or NOT_SURE when the chart cannot be judged; wrong: MISMATCH
    "false" claim     acceptable: MISMATCH, or NOT_SURE; wrong: CONSISTENT
    "negated"         NOT_SURE (the checker only verifies positive statements); wrong: CONSISTENT / MISMATCH
    "no_figure"       NO_FIGURE (or NOT_SURE); wrong: CONSISTENT / MISMATCH (checked against the wrong chart)
    "setup"           SKIPPED (not a result); wrong: MISMATCH

The two LaTeX reports need pdflatex (TeX Live with IEEEtran and pgfplots); without it they are skipped.
"""
from __future__ import annotations

import io
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pymupdf  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "sample_reports" / "real_world"

EP10 = [str(e) for e in range(1, 11)]
EP20 = [str(e) for e in range(2, 21, 2)]


def rel(a: float, b: float) -> float:
    return (b - a) / abs(a) * 100.0


# ------------------------------------------------------------------ report bookkeeping
class Sample:
    def __init__(self, name: str, title: str, about: str):
        self.name, self.title, self.about = name, title, about
        self.dir = OUT / name
        self.figures: list[dict] = []
        self.expected: list[dict] = []

    def figure(self, number: int, kind: str, x: list[str], series: dict[str, list[float]], panel: str | None = None,
               note: str = "") -> dict:
        f = {"number": number, "panel": panel, "kind": kind, "x_values": x,
             "series": {k: [float(v) for v in vals] for k, vals in series.items()}, "note": note}
        self.figures.append(f)
        return f

    def claim(self, text: str, truth: str, why: str, accept: list[str] | None = None) -> str:
        default = {"true": ["CONSISTENT", "NOT_SURE"], "false": ["MISMATCH", "NOT_SURE"], "negated": ["NOT_SURE"],
                   "no_figure": ["NO_FIGURE", "NOT_SURE"], "setup": ["SKIPPED"]}[truth]
        wrong = {"true": ["MISMATCH"], "false": ["CONSISTENT"], "negated": ["CONSISTENT", "MISMATCH"],
                 "no_figure": ["CONSISTENT", "MISMATCH"], "setup": ["MISMATCH"]}[truth]
        self.expected.append({"sentence": text, "truth": truth, "accept": accept or default, "wrong": wrong,
                              "why": why})
        return text

    def save(self) -> None:
        (self.dir / "truth.json").write_text(json.dumps({"report": self.name, "title": self.title,
                                                         "figures": self.figures}, indent=1))
        (self.dir / "expected.json").write_text(json.dumps({"report": self.name, "about": self.about,
                                                            "claims": self.expected}, indent=1, ensure_ascii=False))


# ------------------------------------------------------------------ charts
def line_chart(x, series, ylabel, title, style="default", excel=False, fmt="png", legend="lower right",
               yscale=None, size=(6.0, 3.8), dpi=130, twin=None, sci=False) -> bytes:
    ctx = plt.style.context(style)
    with ctx:
        fig, ax = plt.subplots(figsize=size, dpi=dpi)
        xs = [float(v) for v in x]
        for i, (name, vals) in enumerate(series.items()):
            ax.plot(xs, vals, marker="os^D"[i % 4], markersize=4, label=name)
        if twin:
            name, vals, label = twin
            ax2 = ax.twinx()
            ax2.plot(xs, vals, "--", color="black", label=name)
            ax2.set_ylabel(label)
        ax.set_xticks(xs)
        ax.set_xticklabels(x)
        ax.set_xlabel("Epoch")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        if yscale:
            ax.set_yscale(yscale)
        if sci:                                    # a multiplier ("1e-4") above the axis, as many students set it
            ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))
        if excel:                                  # Excel / Google Sheets look: no frame, light grid, legend below
            for s in ax.spines.values():
                s.set_visible(False)
            ax.yaxis.grid(True, color="#d9d9d9")
            ax.tick_params(length=0)
            ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=len(series), frameon=False)
        else:
            ax.legend(loc=legend)
        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format=fmt)
        plt.close(fig)
    return buf.getvalue()


def bar_chart(cats, series, ylabel, title, excel=False, fmt="png", horizontal=False, labels=False,
              size=(6.0, 3.8), dpi=130, ylim=None) -> bytes:
    fig, ax = plt.subplots(figsize=size, dpi=dpi)
    pos = np.arange(len(cats))
    w = 0.8 / len(series)
    for i, (name, vals) in enumerate(series.items()):
        off = pos - 0.4 + w * (i + 0.5)
        bars = (ax.barh if horizontal else ax.bar)(off, vals, w * 0.92, label=name)
        if labels:
            ax.bar_label(bars, fmt="%.1f", fontsize=7, padding=1)
    if horizontal:
        ax.set_yticks(pos)
        ax.set_yticklabels(cats)
        ax.set_xlabel(ylabel)
    else:
        ax.set_xticks(pos)
        ax.set_xticklabels(cats)
        ax.set_ylabel(ylabel)
        top = max(max(v) for v in series.values())
        ax.set_ylim(*(ylim or (0, top * 1.18)))
    ax.set_title(title)
    if excel:
        for s in ax.spines.values():
            s.set_visible(False)
        ax.yaxis.grid(True, color="#d9d9d9")
        ax.set_axisbelow(True)
        ax.tick_params(length=0)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=len(series), frameon=False)
    else:
        ax.legend(loc="upper left" if not horizontal else "lower right", fontsize=8)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format=fmt)
    plt.close(fig)
    return buf.getvalue()


def two_panel(x, acc, loss) -> bytes:
    fig, (a, b) = plt.subplots(1, 2, figsize=(8, 3.2), dpi=130)
    xs = [float(v) for v in x]
    for name, vals in acc.items():
        a.plot(xs, vals, marker="o", markersize=3, label=name)
    for name, vals in loss.items():
        b.plot(xs, vals, marker="o", markersize=3, label=name)
    for ax, t, yl in ((a, "(a) Accuracy", "Accuracy (%)"), (b, "(b) Loss", "Loss")):
        ax.set_xticks(xs)
        ax.set_xticklabels(x)
        ax.set_title(t)
        ax.set_xlabel("Epoch")
        ax.set_ylabel(yl)
        ax.legend(fontsize=7)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


# ------------------------------------------------------------------ Word-style PDF writer
class Doc:
    """A plain single-column document laid out top to bottom (like a report exported from Word)."""
    W, H, M = 595, 842, 64

    def __init__(self):
        self.doc = pymupdf.open()
        self.page = None
        self.y = 0.0
        self.new_page()

    def new_page(self):
        self.page = self.doc.new_page(width=self.W, height=self.H)
        self.y = self.M

    # TrueType fonts (shipped with matplotlib), embedded like Word does: the PDF base fonts have no "–", "≈" or "±"
    FONTS = {"helv": "DejaVuSans.ttf", "hebo": "DejaVuSans-Bold.ttf", "heit": "DejaVuSans-Oblique.ttf"}

    def text(self, s: str, size: float = 10.5, font: str = "helv", gap: float = 8, width: float | None = None):
        width = width or (self.W - 2 * self.M)
        fontfile = str(Path(matplotlib.get_data_path()) / "fonts" / "ttf" / self.FONTS[font])
        for _ in range(2):
            rect = pymupdf.Rect(self.M, self.y, self.M + width, self.H - self.M)
            left = self.page.insert_textbox(rect, s, fontsize=size, fontname="F" + font, fontfile=fontfile)
            if left >= 0:
                self.y = rect.y1 - left + gap
                return
            self.new_page()
        raise ValueError("paragraph too long for one page")

    def heading(self, s: str):
        self.text(s, size=13, font="hebo", gap=6)

    def image(self, data: bytes, width: float = 330, height: float = 210):
        if self.y + height > self.H - self.M:
            self.new_page()
        x0 = (self.W - width) / 2
        self.page.insert_image(pymupdf.Rect(x0, self.y, x0 + width, self.y + height), stream=data)
        self.y += height + 4

    def vector(self, pdf_bytes: bytes, width: float = 330, height: float = 210):
        if self.y + height > self.H - self.M:
            self.new_page()
        x0 = (self.W - width) / 2
        src = pymupdf.open("pdf", pdf_bytes)
        self.page.show_pdf_page(pymupdf.Rect(x0, self.y, x0 + width, self.y + height), src, 0)
        self.y += height + 4

    def caption(self, s: str):
        self.text(s, size=9, font="heit", gap=10)

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.subset_fonts()
        self.doc.save(str(path), garbage=4, deflate=True, deflate_images=True)


def tex(s: str) -> str:
    return s.replace("%", r"\%").replace("&", r"\&")


def run_latex(folder: Path, name: str = "report") -> bool:
    if shutil.which("pdflatex") is None:
        print(f"  pdflatex not found: {folder.name} skipped", file=sys.stderr)
        return False
    for _ in range(2):                             # twice, for \ref
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", f"{name}.tex"], cwd=folder,
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-3000:], file=sys.stderr)
            raise RuntimeError(f"pdflatex failed in {folder}")
    for ext in ("aux", "log", "out"):
        (folder / f"{name}.{ext}").unlink(missing_ok=True)
    return True


# ================================================================== 01: LaTeX, IEEE two-column, vector figures
def report_01() -> Sample:
    s = Sample("01_latex_ieee_two_column", "Comparing CNN Architectures on CIFAR-10",
               "IEEE two-column LaTeX with matplotlib PDF (vector) figures: hyphenation across lines, ligatures, "
               "the LaTeX minus sign, 10^{-4} exponents, 'Fig. N' references and IEEE 'Fig. 1.' captions.")
    acc = {"ResNet-50": [62.0, 71.5, 77.8, 81.9, 84.6, 86.7, 88.2, 89.5, 90.4, 91.2],
           "VGG-16": [58.3, 66.0, 71.2, 75.0, 77.9, 80.2, 81.8, 83.1, 84.0, 84.7]}
    loss = {"ResNet-50": [1.92, 1.41, 1.10, 0.90, 0.76, 0.66, 0.59, 0.53, 0.49, 0.46],
            "VGG-16": [2.05, 1.62, 1.33, 1.12, 0.97, 0.86, 0.78, 0.72, 0.67, 0.63]}
    test = {"ResNet-50": [91.2, 95.4, 78.6], "VGG-16": [84.7, 93.1, 72.3]}
    cats = ["CIFAR-10", "SVHN", "STL-10"]
    s.figure(1, "line", EP20, acc)
    s.figure(2, "line", EP20, loss)
    s.figure(3, "grouped_bar", cats, test)
    s.dir.mkdir(parents=True, exist_ok=True)
    (s.dir / "fig_acc.pdf").write_bytes(line_chart(EP20, acc, "Accuracy (%)", "Validation accuracy", fmt="pdf"))
    (s.dir / "fig_loss.pdf").write_bytes(line_chart(EP20, loss, "Loss", "Training loss", fmt="pdf", legend="upper right"))
    (s.dir / "fig_test.pdf").write_bytes(bar_chart(cats, test, "Accuracy (%)", "Test accuracy", fmt="pdf"))

    d = rel(loss["ResNet-50"][0], loss["ResNet-50"][-1])           # -76.0
    claims = [
        s.claim("Each model was trained for 20 epochs with a batch size of 128 on a single GPU.", "setup",
                "training setup, not a result"),
        s.claim("ResNet-50 reached 91.2% validation accuracy at epoch 20 (Fig. 1).", "true",
                "past tense; ResNet-50 at epoch 20 is 91.2"),
        s.claim("VGG-16 achieved 88.0% validation accuracy at epoch 20.", "false", "VGG-16 at epoch 20 is 84.7"),
        s.claim("At epoch 10, VGG-16 is 6.7 points lower than ResNet-50.", "true",
                "'lower than': ResNet-50 84.6 minus VGG-16 77.9 = 6.7"),
        s.claim(f"From epoch 2 to epoch 20, the training loss of ResNet-50 decreased by {abs(d):.0f}%.", "true",
                f"a fall: 1.92 -> 0.46 is {d:.1f}%"),
        s.claim("The training loss of VGG-16 was 0.63 at epoch 20.", "true", "VGG-16 loss at epoch 20 is 0.63"),
        s.claim("The training loss of ResNet-50 was 0.30 at epoch 20.", "false", "ResNet-50 loss at epoch 20 is 0.46"),
        s.claim("On SVHN, ResNet-50 achieves 95.4% test accuracy (Fig. 3).", "true", "bar chart, SVHN 95.4"),
        s.claim("On STL-10, ResNet-50 is 2.1 points better than VGG-16.", "false", "78.6 - 72.3 = 6.3"),
        s.claim("VGG-16 reaches eighty-four point seven percent validation accuracy at epoch twenty.", "true",
                "number words: 84.7 at epoch 20"),
    ]
    # LaTeX-only wording of some sentences (math minus, exponents); the plain text above is what extraction should give
    exp_claim = s.claim("The training loss of ResNet-50 is 4.6 × 10−1 at epoch 20.", "true",
                        "exponent as LaTeX prints it: 4.6e-1 = 0.46")
    setup2 = s.claim("We used a weight decay of 5 × 10−4 and a learning rate of 10−3.", "setup",
                     "exponents in a setup sentence: must not become a claim")
    body = [tex(c) for c in claims]
    body_exp = r"The training loss of ResNet-50 is $4.6\times10^{-1}$ at epoch 20."
    body_setup2 = r"We used a weight decay of $5\times10^{-4}$ and a learning rate of $10^{-3}$."
    src = rf"""\documentclass[conference]{{IEEEtran}}
\usepackage{{graphicx}}
\begin{{document}}
\title{{{s.title}}}
\author{{\IEEEauthorblockN{{Sample Student}}\IEEEauthorblockA{{Department of Computer Science}}}}
\maketitle
\begin{{abstract}}
This report compares two convolutional neural networks for image classification. The final classifier
architecture, the effective learning rate schedule and the official training split are described below.
\end{{abstract}}
\section{{Introduction}}
Image classification remains a standard benchmark for convolutional architectures. We study how
quickly two well-known networks converge and how their final performance differs across datasets,
following the usual practice of reporting validation curves and test results side by side.
\section{{Experimental Setup}}
{body[0]} {body_setup2} Data augmentation used random crops and horizontal flips, which is the
conventional configuration for this benchmark and keeps the comparison fair across architectures.
\section{{Results}}
Fig.~\ref{{fig:acc}} shows the validation accuracy and Fig.~\ref{{fig:loss}} the training loss.
\begin{{figure}}[t]\centering\includegraphics[width=\columnwidth]{{fig_acc.pdf}}
\caption{{Validation accuracy of ResNet-50 and VGG-16 during training.}}\label{{fig:acc}}\end{{figure}}
{body[1]} {body[2]} {body[3]} The difference between the two architectures is substantial and consistent
throughout training, which suggests that the residual connections help optimisation considerably.
\begin{{figure}}[t]\centering\includegraphics[width=\columnwidth]{{fig_loss.pdf}}
\caption{{Training loss of both models.}}\label{{fig:loss}}\end{{figure}}
{body[4]} {body[5]} {body[6]} {body_exp}
\begin{{figure}}[t]\centering\includegraphics[width=\columnwidth]{{fig_test.pdf}}
\caption{{Test accuracy on three datasets.}}\label{{fig:test}}\end{{figure}}
{body[7]} {body[8]} {body[9]}
\section{{Conclusion}}
Residual networks train faster and generalise better on every dataset considered here. Further
experiments with stronger regularisation are left for future work.
\end{{document}}
"""
    (s.dir / "report.tex").write_text(src)
    if run_latex(s.dir):
        s.save()
    return s


# ================================================================== 02: Word-style, Excel-look charts
def report_02() -> Sample:
    s = Sample("02_word_excel_charts", "Lab 3: Text Classification with Recurrent Networks",
               "A Word-style report: Excel / Google-Sheets-look charts (no frame, the y-axis cannot be read), "
               "caption styles 'Figure 1 –', 'Fig 2:' and a caption above its figure, a figure without a caption, "
               "past tense, '~' / '>' / '≈', '(see Table 2)' and 'Dr.' in the text.")
    ep = [str(e) for e in range(1, 9)]
    acc = {"LSTM": [71.2, 76.5, 79.8, 81.9, 83.0, 83.8, 84.3, 84.6],
           "GRU": [72.8, 78.1, 81.0, 82.9, 84.1, 84.9, 85.4, 85.7],
           "BERT-base": [85.1, 88.9, 90.6, 91.4, 91.9, 92.2, 92.4, 92.5]}
    f1 = {"LSTM": [80.1, 83.4, 86.0], "GRU": [81.0, 84.2, 86.9], "BERT-base": [90.3, 92.8, 94.1]}
    cats = ["IMDB", "AG News", "SST-2"]
    loss = {"LSTM": [0.92, 0.71, 0.60, 0.53, 0.49, 0.46, 0.44, 0.43]}
    s.figure(1, "line", ep, acc, note="Excel look: axis not readable")
    s.figure(2, "grouped_bar", cats, f1, note="Excel look: axis not readable")
    s.figure(3, "line", ep, loss, note="ordinary matplotlib chart, caption written ABOVE it")
    d = Doc()
    d.text(s.title, size=16, font="hebo", gap=4)
    d.text("Prepared under the supervision of Dr. Mehta for the course on natural language processing.", size=10)
    d.heading("1. Method")
    d.text(s.claim("All three models were trained for 8 epochs with a learning rate of 0.001 and a batch size of 32.",
                   "setup", "training setup"))
    d.heading("2. Results")
    d.image(line_chart(ep, acc, "Accuracy (%)", "Validation accuracy", excel=True), 340, 215)
    d.caption("Figure 1 – Validation accuracy per epoch.")
    d.text(" ".join([
        s.claim("BERT-base achieved 92.5% accuracy at epoch 8.", "true", "past tense; 92.5"),
        s.claim("The GRU reached ~85% accuracy at epoch 6.", "true", "hedged '~85%': 84.9"),
        s.claim("LSTM obtained 88.0% accuracy at epoch 8.", "false", "LSTM at epoch 8 is 84.6"),
        s.claim("At epoch 4, BERT-base is 9.5 points higher than LSTM.", "true", "91.4 - 81.9 = 9.5"),
        s.claim("GRU had >85% accuracy at epoch 3.", "false", "GRU at epoch 3 is 81.0, not above 85"),
    ]))
    d.image(bar_chart(cats, f1, "F1 score (%)", "Test F1 score by dataset", excel=True), 340, 215)
    d.caption("Fig 2: Test F1 score on three datasets.")
    d.text(" ".join([
        s.claim("On SST-2, BERT-base reached an F1 score of 94.1% (see Table 2).", "true", "94.1; a table reference"),
        s.claim("On IMDB, the GRU scored ≈81% F1.", "true", "'≈81%': 81.0"),
        s.claim("On AG News, LSTM obtained an F1 score of 90.0%.", "false", "LSTM on AG News is 83.4"),
    ]))
    # a figure with no caption at all, then a figure whose caption sits ABOVE it
    d.image(line_chart(ep, {"GRU": acc["GRU"]}, "Accuracy (%)", "GRU only (no caption)"), 280, 170)
    d.text("The GRU curve flattens out after the sixth epoch, as the plot above shows.")
    d.new_page()                                   # nothing above the next caption but the page margin
    d.caption("Figure 3: Training loss of the LSTM, written above its chart.")
    d.image(line_chart(ep, loss, "Loss", "Training loss", legend="upper right"), 300, 190)
    d.text(" ".join([
        s.claim("The training loss of the LSTM was 0.43 at epoch 8 (Figure 3).", "true", "0.43, caption above the chart"),
        s.claim("From epoch 1 to epoch 8, the training loss of the LSTM fell by 53%.", "true",
                f"a fall: 0.92 -> 0.43 = {rel(0.92, 0.43):.1f}%"),
    ]))
    d.save(s.dir / "report.pdf")
    s.save()
    return s


# ================================================================== 03: tricky language on readable charts
def report_03() -> Sample:
    s = Sample("03_tricky_language", "Training Dynamics of Three Image Classifiers",
               "Ordinary matplotlib charts with sentences that are hard to read: negations, decreases, 'lower than' / "
               "'trails', 'improves by 8.2%' (points or relative?), hedges on large numbers ('about 1000'), ranges "
               "'84-86%' and 'between', '±', number words, 'after 5 epochs', \"X's accuracy\".")
    acc = {"ResNet-50": [60.0, 70.0, 76.0, 80.0, 83.0, 85.5, 87.5, 89.0, 90.2, 91.2],
           "VGG-16": [55.0, 64.0, 70.0, 74.0, 77.0, 79.5, 81.5, 83.0, 84.1, 84.7],
           "ViT-S": [50.0, 61.0, 68.0, 73.5, 77.5, 80.5, 83.0, 85.0, 86.3, 87.2]}
    loss = {"ResNet-50": [2.00, 1.60, 1.30, 1.10, 0.96, 0.85, 0.76, 0.69, 0.64, 0.60],
            "VGG-16": [2.20, 1.80, 1.50, 1.28, 1.12, 0.99, 0.90, 0.83, 0.79, 0.77]}
    tput = {"ResNet-50": [42, 1040], "VGG-16": [35, 870], "ViT-S": [28, 760]}
    s.figure(1, "line", EP10, acc)
    s.figure(2, "line", EP10, loss)
    s.figure(3, "grouped_bar", ["CPU", "GPU"], tput)
    vgg_drop = rel(loss["VGG-16"][0], loss["VGG-16"][-1])           # -65.0
    rn_pts = acc["ResNet-50"][9] - acc["ResNet-50"][4]              # 8.2 points, 9.9% relative
    rn_rel = rel(acc["ResNet-50"][4], acc["ResNet-50"][9])
    loss_impr = -rel(loss["ResNet-50"][0], loss["ResNet-50"][-1])   # 70
    d = Doc()
    d.text(s.title, size=16, font="hebo", gap=10)
    d.heading("1 Setup")
    d.text(" ".join([
        s.claim("We trained each network for 10 epochs and repeated every run 3 times.", "setup", "setup"),
        "At this point five models had been trained in total, and three of them are compared here.",
    ]))
    d.heading("2 Accuracy")
    d.image(line_chart(EP10, acc, "Accuracy (%)", "Validation accuracy"), 330, 210)
    d.caption("Figure 1: Validation accuracy of the three models.")
    d.text(" ".join([
        s.claim("ResNet-50 does not exceed 92% accuracy at epoch 10.", "negated", "negated (true, but not checked)"),
        s.claim("ViT-S never reaches 90% accuracy at epoch 10.", "negated", "negated"),
        s.claim("At epoch 10, ViT-S trails ResNet-50 by 4.0 points.", "true", "91.2 - 87.2 = 4.0"),
        s.claim("At epoch 10, ViT-S trails ResNet-50 by 9.0 points.", "false", "the gap is 4.0"),
        s.claim(f"From epoch 5 to epoch 10, the accuracy of ResNet-50 improves by {rn_pts:.1f}%.", "true",
                f"ambiguous %: {rn_pts:.1f} points (true) but {rn_rel:.1f}% relative; never a flag",
                accept=["NOT_SURE", "CONSISTENT"]),
        s.claim(f"From epoch 5 to epoch 10, the accuracy of ResNet-50 improves by a relative {rn_rel:.1f}%.", "true",
                "explicitly relative"),
        s.claim("ResNet-50 reaches 83.0% accuracy after 5 epochs.", "true", "'after 5 epochs' = epoch 5"),
        s.claim("VGG-16's accuracy is 70.0% at epoch 3.", "true", "possessive phrasing"),
        s.claim("At epoch 10, VGG-16 reaches 84-86% accuracy.", "true", "range with a dash: 84.7"),
        s.claim("At epoch 10, ResNet-50 reaches between 90% and 92% accuracy.", "true", "range: 91.2"),
        s.claim("ResNet-50 reaches 91.2 ± 0.4% accuracy at epoch 10.", "true", "mean ± sd"),
        s.claim("ViT-S reaches eighty-seven point two percent accuracy at epoch ten.", "true", "number words: 87.2"),
    ]))
    d.heading("3 Loss")
    d.image(line_chart(EP10, loss, "Loss", "Training loss", legend="upper right"), 330, 210)
    d.caption("Figure 2: Training loss.")
    d.text(" ".join([
        s.claim(f"From epoch 1 to epoch 10, the loss of VGG-16 drops by {abs(vgg_drop):.0f}%.", "true",
                f"a fall: 2.20 -> 0.77 = {vgg_drop:.1f}%"),
        s.claim("From epoch 1 to epoch 10, the loss of ResNet-50 drops by 30%.", "false", "it drops by 70%"),
        s.claim(f"From epoch 1 to epoch 10, the loss of ResNet-50 improves by {loss_impr:.0f}%.", "true",
                "'improves' on a loss means it falls by 70%"),
        s.claim("The loss of VGG-16 is 0.77 at epoch 10.", "true", "0.77"),
    ]))
    d.heading("4 Speed")
    d.image(bar_chart(["CPU", "GPU"], tput, "Images per second", "Inference throughput"), 320, 205)
    d.caption("Figure 3: Inference throughput on CPU and GPU.")
    d.text(" ".join([
        s.claim("On GPU, ResNet-50 reaches about 1000 images per second.", "true",
                "hedged large number: 1040 is within 5% of 'about 1000' (the old rule allowed only ±5)"),
        s.claim("On CPU, VGG-16 reaches ~35 images per second.", "true", "35"),
        s.claim("On GPU, ViT-S reaches >700 images per second.", "true", "760 > 700"),
        s.claim("On GPU, VGG-16 reaches about 600 images per second.", "false", "870 is far from 600"),
    ]))
    d.save(s.dir / "report.pdf")
    s.save()
    return s


# ================================================================== 04: similar names, train / val / test
def report_04() -> Sample:
    s = Sample("04_similar_names_and_splits", "ResNet Depth Study",
               "Model and dataset names that differ by a number (ResNet-18 / ResNet-34 / ResNet-50 / ResNet-101, "
               "CIFAR-10 / CIFAR-100, VGG-16 / VGG-19) and separate training, validation and test charts.")
    train = {"ResNet-18": [55.0, 68.0, 76.0, 81.5, 85.0, 88.0, 90.0, 91.8, 93.0, 94.1],
             "ResNet-50": [58.0, 72.0, 80.0, 85.0, 88.5, 91.0, 93.0, 94.5, 95.6, 96.4]}
    val = {"ResNet-18": [52.0, 63.0, 70.0, 74.5, 77.5, 79.8, 81.5, 82.7, 83.5, 84.0],
           "ResNet-50": [55.0, 67.0, 74.0, 78.5, 81.5, 84.0, 85.8, 87.0, 87.9, 88.5],
           "VGG-16": [50.0, 60.0, 66.0, 70.0, 73.0, 75.2, 76.8, 78.0, 78.9, 79.5]}
    test = {"ResNet-18": [92.1, 70.3], "ResNet-50": [94.6, 78.2], "ResNet-101": [95.3, 80.1]}
    cats = ["CIFAR-10", "CIFAR-100"]
    s.figure(1, "line", EP10, train)
    s.figure(2, "line", EP10, val)
    s.figure(3, "grouped_bar", cats, test)
    d = Doc()
    d.text(s.title, size=16, font="hebo", gap=10)
    d.text("We compare residual networks of different depth. Training and validation curves are shown separately, "
           "and the final test accuracy is reported on CIFAR-10 and CIFAR-100.")
    d.image(line_chart(EP10, train, "Accuracy (%)", "Training accuracy"), 320, 200)
    d.caption("Figure 1: Training accuracy.")
    d.image(line_chart(EP10, val, "Accuracy (%)", "Validation accuracy"), 320, 200)
    d.caption("Figure 2: Validation accuracy.")
    d.text(" ".join([
        s.claim("ResNet-18 reaches 94.1% training accuracy at epoch 10.", "true", "Figure 1, not Figure 2"),
        s.claim("ResNet-18 reaches 84.0% validation accuracy at epoch 10.", "true", "Figure 2, not Figure 1"),
        s.claim("ResNet-50 reaches 96.4% validation accuracy at epoch 10.", "false",
                "96.4 is the TRAINING value; validation is 88.5"),
        s.claim("ResNet-34 reaches 86.0% validation accuracy at epoch 10.", "no_figure",
                "ResNet-34 is not plotted (the old matching read ResNet-18 or ResNet-50 instead)"),
        s.claim("VGG-19 reaches 79.5% validation accuracy at epoch 10.", "no_figure",
                "VGG-19 is not plotted, only VGG-16 (whose value is 79.5)"),
        s.claim("ResNet-50 reaches 89.0% test accuracy at epoch 10.", "no_figure",
                "no test curve: the curves are training and validation"),
    ]))
    d.image(bar_chart(cats, test, "Accuracy (%)", "Test accuracy", labels=True), 320, 200)
    d.caption("Figure 3: Test accuracy on CIFAR-10 and CIFAR-100.")
    d.text(" ".join([
        s.claim("On CIFAR-100, ResNet-50 achieves 78.2% test accuracy.", "true", "CIFAR-100 bar"),
        s.claim("On CIFAR-100, ResNet-18 achieves 92.1% test accuracy.", "false",
                "92.1 is CIFAR-10; CIFAR-100 is 70.3 (the old matching read the CIFAR-10 bar)"),
        s.claim("On CIFAR-10, ResNet-101 is 0.7 points better than ResNet-50.", "true", "95.3 - 94.6 = 0.7"),
        s.claim("On CIFAR-10, ResNet-152 achieves 96.0% test accuracy.", "no_figure", "ResNet-152 is not plotted"),
    ]))
    d.save(s.dir / "report.pdf")
    s.save()
    return s


# ================================================================== 05: hard chart kinds
def report_05() -> Sample:
    s = Sample("05_hard_charts", "Hard Charts",
               "Chart kinds the reading tools cannot judge safely: two y-axes, an axis multiplier (1e-5), a log "
               "scale, a seaborn style, horizontal bars, and a two-panel figure. Claims here should be handed to "
               "the TA (NOT_SURE) unless they can be measured properly; none may be flagged wrongly.")
    acc = [60.0, 70.0, 76.0, 80.0, 83.0, 85.5, 87.5, 89.0, 90.2, 91.2]
    loss = [2.00, 1.60, 1.30, 1.10, 0.96, 0.85, 0.76, 0.69, 0.64, 0.60]
    small = [round(v * 1e-4, 6) for v in [9.0, 8.1, 7.4, 6.9, 6.5, 6.2, 6.0, 5.8, 5.7, 5.6]]
    logl = [2.0, 0.9, 0.42, 0.2, 0.1, 0.05, 0.026, 0.014, 0.008, 0.005]
    vgg = [55.0, 64.0, 70.0, 74.0, 77.0, 79.5, 81.5, 83.0, 84.1, 84.7]
    s.figure(1, "line", EP10, {"ResNet-50": acc}, note="dual y-axis: accuracy left, loss right")
    s.figure(2, "line", EP10, {"ResNet-50": small}, note="axis multiplier 1e-4 above the axis")
    s.figure(3, "line", EP10, {"ResNet-50": logl}, note="log scale, default tick labels")
    s.figure(4, "line", EP10, {"ResNet-50": acc, "VGG-16": vgg}, note="seaborn whitegrid style")
    s.figure(5, "grouped_bar", ["CIFAR-10", "SVHN"], {"ResNet-50": [91.2, 95.4], "VGG-16": [84.7, 93.1]},
             note="horizontal bars")
    s.figure(6, "line", EP10, {"ResNet-50": acc}, panel="a")
    s.figure(6, "line", EP10, {"ResNet-50": loss}, panel="b")
    d = Doc()
    d.text(s.title, size=16, font="hebo", gap=10)
    d.image(line_chart(EP10, {"ResNet-50": acc}, "Accuracy (%)", "Accuracy and loss",
                       twin=("loss", loss, "Loss"), legend="center right"), 320, 200)
    d.caption("Figure 1: Accuracy (left axis) and loss (right axis) of ResNet-50.")
    d.text(" ".join([
        s.claim("ResNet-50 reaches 91.2% accuracy at epoch 10 (Figure 1).", "true", "two y-axes: hand to the TA"),
        s.claim("ResNet-50 reaches 70.0% accuracy at epoch 10 (Figure 1).", "false", "91.2; two y-axes"),
    ]))
    d.image(line_chart(EP10, {"ResNet-50": small}, "Gradient norm", "Gradient norm", sci=True,
                       legend="upper right"), 300, 190)
    d.caption("Figure 2: Gradient norm of ResNet-50.")
    d.text(" ".join([
        s.claim("ResNet-50 has a gradient norm of 0.00056 at epoch 10 (Figure 2).", "true",
                "the axis shows 5.6 with '1e-4' above it: readers report 5.6"),
    ]))
    d.image(line_chart(EP10, {"ResNet-50": logl}, "Loss", "Training loss (log scale)", yscale="log",
                       legend="upper right"), 300, 190)
    d.caption("Figure 3: Training loss on a log scale.")
    d.text(s.claim("ResNet-50 has a training loss of 0.005 at epoch 10 (Figure 3).", "true", "log scale"))
    d.image(line_chart(EP10, {"ResNet-50": acc, "VGG-16": vgg}, "Accuracy (%)", "Validation accuracy",
                       style="seaborn-v0_8-whitegrid"), 300, 190)
    d.caption("Figure 4: Validation accuracy (seaborn style).")
    d.text(" ".join([
        s.claim("VGG-16 reaches 84.7% validation accuracy at epoch 10 (Figure 4).", "true", "seaborn style"),
        s.claim("VGG-16 reaches 89.0% validation accuracy at epoch 10 (Figure 4).", "false",
                "84.7; the axis cannot be read, so this must not be flagged by guesswork"),
    ]))
    d.image(bar_chart(["CIFAR-10", "SVHN"], {"ResNet-50": [91.2, 95.4], "VGG-16": [84.7, 93.1]},
                      "Accuracy (%)", "Test accuracy", horizontal=True), 300, 180)
    d.caption("Figure 5: Test accuracy (horizontal bars).")
    d.text(s.claim("On SVHN, VGG-16 achieves 93.1% test accuracy (Figure 5).", "true", "horizontal bars"))
    d.image(two_panel(EP10, {"ResNet-50": acc}, {"ResNet-50": loss}), 420, 170)
    d.caption("Figure 6: (a) Accuracy and (b) loss of ResNet-50.")
    d.text(" ".join([
        s.claim("In Figure 6(b), the loss of ResNet-50 is 0.60 at epoch 10.", "true", "panel b"),
        s.claim("In Figure 6(a), ResNet-50 reaches 80.0% accuracy at epoch 10.", "false", "91.2 in panel a"),
    ]))
    d.save(s.dir / "report.pdf")
    s.save()
    return s


# ================================================================== 06: a scanned copy of report 03
def report_06(src: Sample) -> Sample:
    s = Sample("06_scanned_copy", "Training Dynamics of Three Image Classifiers (scanned)",
               "Report 03 printed and scanned: every page is one greyscale image, slightly rotated and JPEG "
               "compressed, with no text layer. The old web config found 0 sentences and showed an empty, "
               "clean-looking result. OCR errors may change words, so sentences are matched loosely.")
    s.figures = src.figures
    for c in src.expected:                       # scanned charts cannot be measured reliably: never a wrong verdict
        accept = sorted(set(c["accept"]) | {"NOT_SURE", "NO_FIGURE", "SKIPPED"})
        s.expected.append({**c, "accept": accept})
    doc = pymupdf.open(src.dir / "report.pdf")
    out = pymupdf.open()
    for page in doc:
        pix = page.get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
        im = Image.open(io.BytesIO(pix.tobytes("png"))).rotate(0.4, fillcolor=255, expand=False)
        buf = io.BytesIO()
        im.convert("L").save(buf, "JPEG", quality=75)
        p = out.new_page(width=page.rect.width, height=page.rect.height)
        p.insert_image(p.rect, stream=buf.getvalue())
    s.dir.mkdir(parents=True, exist_ok=True)
    out.save(str(s.dir / "report.pdf"), garbage=4, deflate=True)
    s.save()
    return s


# ================================================================== 07: full LaTeX report with pgfplots
def report_07() -> Sample:
    s = Sample("07_latex_pgfplots_full_report", "Image Classification: A Complete Lab Report",
               "A three-page LaTeX article whose charts are drawn by pgfplots (vector graphics with real text "
               "labels), with setup numbers that must be skipped, 'Figs. 1 and 2' citations, a repeated sentence, "
               "claims in captions and a mix of true and false statements.")
    acc = {"ResNet-50": [62.0, 71.5, 77.8, 81.9, 84.6, 86.7, 88.2, 89.5, 90.4, 91.2],
           "ViT-S": [55.0, 65.2, 72.0, 76.9, 80.3, 82.8, 84.6, 85.9, 86.8, 87.4]}
    loss = {"ResNet-50": [1.92, 1.41, 1.10, 0.90, 0.76, 0.66, 0.59, 0.53, 0.49, 0.46],
            "ViT-S": [2.20, 1.70, 1.38, 1.16, 1.00, 0.88, 0.79, 0.72, 0.67, 0.64]}
    bars = {"ResNet-50": [91.2, 95.4], "ViT-S": [87.4, 93.8]}
    s.figure(1, "line", EP20, acc)
    s.figure(2, "line", EP20, loss)
    s.figure(3, "grouped_bar", ["CIFAR-10", "SVHN"], bars)
    s.dir.mkdir(parents=True, exist_ok=True)

    def coords(vals):
        return " ".join(f"({x},{v})" for x, v in zip(EP20, vals))
    marks = ["*", "square*"]

    def plot(series, ylabel, title, legend_pos):
        lines = "\n".join(rf"\addplot+[mark={marks[i]}] coordinates {{{coords(v)}}}; \addlegendentry{{{k}}}"
                          for i, (k, v) in enumerate(series.items()))
        return (rf"\begin{{tikzpicture}}\begin{{axis}}[width=0.8\textwidth,height=6cm,xlabel={{Epoch}},"
                rf"ylabel={{{ylabel}}},title={{{title}}},xtick={{{','.join(EP20)}}},legend pos={legend_pos},"
                rf"grid=major]" + "\n" + lines + r"\end{axis}\end{tikzpicture}")
    bar_tex = (r"\begin{tikzpicture}\begin{axis}[ybar,width=0.7\textwidth,height=6cm,ymin=0,ymax=110,bar width=22pt,"
               r"enlarge x limits=0.5,symbolic x coords={CIFAR-10,SVHN},xtick=data,ylabel={Accuracy (\%)},"
               r"title={Test accuracy},legend style={at={(0.5,-0.18)},anchor=north,legend columns=-1},"
               r"nodes near coords,every node near coord/.append style={font=\tiny}]"
               "\n" + "\n".join(rf"\addplot coordinates {{(CIFAR-10,{v[0]}) (SVHN,{v[1]})}}; \addlegendentry{{{k}}}"
                                for k, v in bars.items()) + r"\end{axis}\end{tikzpicture}")
    c = {
        "setup1": s.claim("All models were trained for 20 epochs on 4 GPUs with a batch size of 256.", "setup", "setup"),
        "setup2": s.claim("The learning rate was reduced by 10% every 5 epochs.", "setup",
                          "setup with 'reduced by 10%': not a chart claim", accept=["SKIPPED", "NOT_SURE"]),
        "p1": s.claim("ResNet-50 achieved 91.2% validation accuracy at epoch 20.", "true", "91.2"),
        "p2": s.claim("ViT-S reached 90.0% validation accuracy at epoch 20.", "false", "87.4"),
        "d1": s.claim("At epoch 10, ViT-S is 4.3 points lower than ResNet-50.", "true", "84.6 - 80.3 = 4.3"),
        "r1": s.claim("From epoch 2 to epoch 20, the training loss of ViT-S fell by 71%.", "true",
                      f"2.20 -> 0.64 = {rel(2.20, 0.64):.1f}%"),
        "l1": s.claim("The training loss of ResNet-50 is 0.46 at epoch 20.", "true", "0.46"),
        "b1": s.claim("On SVHN, ViT-S achieves 93.8% test accuracy.", "true", "93.8"),
        "b2": s.claim("On CIFAR-10, ResNet-50 is 6.0 points better than ViT-S.", "false", "91.2 - 87.4 = 3.8"),
        "neg": s.claim("ViT-S does not reach the accuracy of ResNet-50 at any epoch, staying below 88%.", "negated",
                       "negated"),
        "cap": s.claim("ResNet-50 reaches 91.2% at epoch 20.", "true", "a claim inside a caption (v3 A4)"),
    }
    src = rf"""\documentclass[11pt]{{article}}
\usepackage[margin=2.5cm]{{geometry}}
\usepackage{{pgfplots}}\pgfplotsset{{compat=1.17}}
\begin{{document}}
\begin{{center}}{{\Large\bfseries {s.title}}}\\[4pt]Sample Student\end{{center}}
\section{{Introduction}}
Convolutional networks and vision transformers are the two families most often compared in
introductory deep learning courses. This report follows the official lab handout and compares one
model of each family on two datasets.
\section{{Setup}}
{tex(c["setup1"])} {tex(c["setup2"])} Images were normalised with the usual channel statistics.
\section{{Results}}
Figs.~\ref{{fig:acc}} and~\ref{{fig:loss}} summarise training.
\begin{{figure}}[h]\centering
{plot(acc, "Accuracy (\\%)", "Validation accuracy", "south east")}
\caption{{Validation accuracy. {tex(c["cap"])}}}\label{{fig:acc}}\end{{figure}}
{tex(c["p1"])} {tex(c["p2"])} {tex(c["d1"])}
\begin{{figure}}[h]\centering
{plot(loss, "Loss", "Training loss", "north east")}
\caption{{Training loss.}}\label{{fig:loss}}\end{{figure}}
{tex(c["r1"])} {tex(c["l1"])}
\begin{{figure}}[h]\centering
{bar_tex}
\caption{{Test accuracy on CIFAR-10 and SVHN.}}\label{{fig:bar}}\end{{figure}}
{tex(c["b1"])} {tex(c["b2"])}
\section{{Discussion}}
{tex(c["neg"])} {tex(c["p1"])} Overall the convolutional network remains the stronger choice
for small datasets, in line with the literature.
\end{{document}}
"""
    (s.dir / "report.tex").write_text(src)
    if run_latex(s.dir):
        s.save()
    return s


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    for build in (report_01, report_02, report_03, report_04, report_05):
        r = build()
        made.append(r)
        print(f"  {r.name}: {len(r.expected)} sentences")
    r6 = report_06(next(r for r in made if r.name.startswith("03")))
    print(f"  {r6.name}: {len(r6.expected)} sentences")
    r7 = report_07()
    print(f"  {r7.name}: {len(r7.expected)} sentences")
    print(f"written to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
