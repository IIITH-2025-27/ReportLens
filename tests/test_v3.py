"""v3 (results/run_log.md, section H): groups A, B and C of the questions.txt review."""
import random

import numpy as np
import pymupdf
import pytest

from chart_claim_verifier.agent.controller import ClaimController, peak_value
from chart_claim_verifier.agent.notes import add_conflicts, citation_note, explain_flag
from chart_claim_verifier.agent.policies import FixedOrderPolicy
from chart_claim_verifier.agent.report_agent import ReportAgent, unsupported
from chart_claim_verifier.calibration.collect import CalibrationItem
from chart_claim_verifier.calibration.fit import fit_table
from chart_claim_verifier.claims.parser import RuleParser
from chart_claim_verifier.claims.tolerance import find_numbers, find_range, is_within
from chart_claim_verifier.claims.units import log_transform, metric_transform, unit_scale
from chart_claim_verifier.decide.rule import RuleConfig, claim_gap, decide
from chart_claim_verifier.evaluation.metrics import join
from chart_claim_verifier.retrieval.figure_index import FigureIndex
from chart_claim_verifier.schemas import ClaimSpec, ClaimTrace, Decision, Figure, PointQuery, Report, Sentence
from chart_claim_verifier.tools.base import TableTool, Tool, ToolError


# ---------------------------------------------------------------- helpers
class FakeTable(TableTool):
    def __init__(self, name, tab, cache=None):
        super().__init__(cache)
        self.name, self.tab = name, tab

    def extract_table(self, fig):
        return self.tab


class FakePoint(Tool):
    def __init__(self, name, tab, offset=0.0):
        super().__init__(None)
        self.name, self.tab, self.offset = name, tab, offset

    def _read(self, fig, q):
        try:
            return self.tab[q.series][q.x] + self.offset
        except KeyError:
            raise ToolError("x_not_found")


def _table(span=100.0, ctype="point", sd=1.0):
    rng = random.Random(0)
    items = []
    for _ in range(400):
        truth = rng.uniform(0.2, 0.9) * span
        items.append(CalibrationItem("bar", ctype, truth, {t: truth + rng.gauss(0, sd * span / 100) for t in "abcd"},
                                     span=span))
        items.append(CalibrationItem("line", ctype, truth, {t: truth + rng.gauss(0, sd * span / 100) for t in "abcd"},
                                     span=span))
    return fit_table(items, eps=0.005, min_group_size=50)


_IMG_DIR = __import__("tempfile").mkdtemp()


def _fig(fid="fig1", number=1, chart_type="bar", span=100.0, lines=(), **kw):
    """A figure whose image is a blank page (the agent looks at every chart before measuring)."""
    import cv2
    path = f"{_IMG_DIR}/{fid}.png"
    cv2.imwrite(path, np.full((300, 400, 3), 255, np.uint8))
    return Figure(figure_id=fid, report_id="r", image_path=path, number=number, chart_type=chart_type,
                  y_span=span, text_lines=list(lines), **kw)


def _claim(sentence="s", value=50.0, tol=0.05, **kw):
    base = dict(claim_id="c", sentence=sentence, claim_type="point", series="A", x="CIFAR-10", claimed_value=value,
                tolerance=tol)
    base.update(kw)
    return ClaimSpec(**base)


# ---------------------------------------------------------------- A5: numbers and units
@pytest.mark.parametrize("text,value,tol", [
    ("reaches 91,2% accuracy", 91.2, 0.05), ("an F1 of 0,912", 0.912, 0.0005), ("on 1,000 images", 1000.0, 0.5),
    ("a rate of 3e-4", 0.0003, 0.00005), ("after 1.2k steps", 1200.0, 50.0), ("a 2 x 10^-3 loss", 0.002, 0.0005),
    ("reaches 82.4%", 82.4, 0.05)])
def test_number_formats(text, value, tol):
    n = find_numbers(text)[-1]
    assert n.value == pytest.approx(value) and n.tolerance == pytest.approx(tol)


def test_lists_and_names_are_not_numbers():
    assert [n.value for n in find_numbers("epochs 10,20 on CIFAR-10 with ResNet-50")] == [10.0, 20.0]


def test_percent_claim_on_a_fraction_axis_is_converted():
    c = _claim("ResNet-50 reaches 91.2% accuracy on CIFAR-10.", 91.2, unit="percent")
    assert unit_scale(c, _fig(span=1.0))[0] == 100.0
    assert unit_scale(c, _fig(span=100.0))[0] == 1.0
    frac = _claim("ResNet-50 reaches an accuracy of 0.912 on CIFAR-10.", 0.912, tol=0.0005)
    assert unit_scale(frac, _fig(span=100.0))[0] == 0.01
    loss = _claim("The loss of ResNet-50 is 0.912 at epoch 3.", 0.912, tol=0.0005)
    assert unit_scale(loss, _fig(span=100.0))[0] == 1.0          # not an accuracy-like metric: left alone


def test_controller_compares_in_the_claims_units():
    tab = {"A": {"CIFAR-10": 0.912, "SVHN": 0.80}}
    tools = {"a": FakePoint("a", tab), "b": FakePoint("b", tab, 0.002)}
    c = _claim("A reaches 91.2% accuracy on CIFAR-10.", 91.2, unit="percent")
    fig = _fig(span=1.0)
    from chart_claim_verifier.agent.memory import ReportMemory
    mem = ReportMemory(Report(report_id="r", pdf_path="", figures=[fig], sentences=[]), FigureIndex([fig]))
    off = ClaimController(tools, FixedOrderPolicy(["a", "b"]), _table(), RuleConfig()).run(c, fig, mem)
    on = ClaimController(tools, FixedOrderPolicy(["a", "b"]), _table(), RuleConfig(),
                         options={"unit_convert": True}).run(c, fig, mem)
    assert off.decision.verdict == "MISMATCH" and on.decision.verdict == "CONSISTENT" and on.notes


# ---------------------------------------------------------------- A6: ranges
def test_range_claims():
    r = find_range("ResNet-50 reaches between 85% and 90% accuracy")
    assert (r.low.value, r.high.value, r.tolerance) == (85.0, 90.0, 0.5)
    c = RuleParser(ranges=True).parse("ResNet-50 reaches between 85% and 90% accuracy on CIFAR-10.", "c")
    assert (c.relation, c.claimed_value, c.claimed_high) == ("between", 85.0, 90.0)
    assert RuleParser().parse("ResNet-50 reaches between 85% and 90% accuracy on CIFAR-10.", "c") is None   # frozen
    # a bare number before the next word ("1 at epoch"); the "and" of a range is not two claims
    c = RuleParser(ranges=True, split_multi=True).parse_all("CNN has a loss of between 0 and 1 at epoch 20.", "c")
    assert [(x.series, x.x, x.claimed_value, x.claimed_high) for x in c] == [("CNN", "20", 0.0, 1.0)]
    assert claim_gap(85, 87, "between", 90) == 0 and claim_gap(85, 92, "between", 90) == 2
    assert is_within(85, 90.4, 0.5, "between", 90) and not is_within(85, 91, 0.5, "between", 90)


# ---------------------------------------------------------------- B2, B3: several claims, peaks
def test_two_claims_in_one_sentence():
    p = RuleParser(split_multi=True)
    cs = p.parse_all("ResNet-50 reaches 91.2% accuracy at epoch 10 and 93.4% at epoch 20 (Figure 2).", "c")
    assert [(c.series, c.x, c.claimed_value, c.figure_hint) for c in cs] == [("ResNet-50", "10", 91.2, 2),
                                                                           ("ResNet-50", "20", 93.4, 2)]
    cs = p.parse_all("At epoch 10, ResNet-50 reaches 91.2% accuracy and ViT-S reaches 89.0% accuracy.", "c")
    assert [(c.series, c.x) for c in cs] == [("ResNet-50", "10"), ("ViT-S", "10")]
    assert len(RuleParser().parse_all("ResNet-50 reaches 91.2% accuracy at epoch 10.", "c")) == 1


def test_peak_claims():
    cs = RuleParser(peaks=True).parse_all("GRU peaks at 91.2% accuracy at epoch 14 (Figure 3(b)).", "c")
    assert [c.claim_type for c in cs] == ["point", "peak"] and cs[1].panel_hint == "b" and cs[1].relation == "greater"
    fig = _fig(chart_type="line")
    tool = FakeTable("t", {"GRU": {"10": 88.0, "14": 91.2, "18": 90.5}})
    assert peak_value(tool, fig, "GRU", "14") == pytest.approx(0.7)
    assert peak_value(tool, fig, "GRU", "18") == pytest.approx(-0.7)


def test_peak_claim_is_decided_by_the_table_tools():
    tabs = {"GRU": {"10": 88.0, "14": 91.2, "18": 95.5}}
    tools = {"p": FakePoint("p", tabs), "t1": FakeTable("t1", tabs), "t2": FakeTable("t2", tabs)}
    fig = _fig(chart_type="line")
    from chart_claim_verifier.agent.memory import ReportMemory
    mem = ReportMemory(Report(report_id="r", pdf_path="", figures=[fig], sentences=[]), FigureIndex([fig]))
    peak = _claim("GRU peaks at 91.2% accuracy at epoch 14.", 0.0, tol=0.0, claim_type="peak", series="GRU", x="14",
                  relation="greater")
    r = ClaimController(tools, FixedOrderPolicy(["p", "t1", "t2"]), _table(ctype="difference"), RuleConfig()).run(peak, fig, mem)
    assert set(r.tool_values) == {"t1", "t2"} and r.decision.verdict == "MISMATCH"   # 18 is higher than 14


# ---------------------------------------------------------------- B4: log axes
def test_log_axis_claim_in_log_units():
    c = _claim("The loss is 0.20 at epoch 4.", 0.2, tol=0.005)
    lc, note = log_transform(c, _fig(flags=["log_y"]))
    assert lc.claimed_value == pytest.approx(np.log10(0.2)) and note
    assert log_transform(c.model_copy(update={"claim_type": "difference"}), _fig(flags=["log_y"]))[0] is None


def test_log_axis_fit():
    from chart_claim_verifier.tools.axis import ChartReadError, fit_y
    ticks = [(400.0, 0.1), (300.0, 1.0), (200.0, 10.0), (100.0, 100.0)]       # evenly spaced decades
    with pytest.raises(ChartReadError):
        fit_y(ticks)
    f = fit_y(ticks, modes=("linear", "log"))
    assert f.log and f.value(250.0) == pytest.approx(10 ** 0.5)


# ---------------------------------------------------------------- B9: error rate, aliases, two figures
def test_error_rate_on_an_accuracy_chart():
    c = _claim("ResNet-50 has an error rate of 8.8% on CIFAR-10.", 8.8)
    fn, note = metric_transform(c, _fig(lines=["Accuracy (%)", "ResNet-50"]))
    assert fn(91.2) == pytest.approx(8.8) and note
    figs = [_fig(lines=["Accuracy (%)", "ResNet-50", "CIFAR-10"], caption="Accuracy by dataset")]
    c2 = c.model_copy(update={"series": "ResNet-50"})
    assert FigureIndex(figs).locate(c2)[0] and not FigureIndex(figs, equivalent_metrics=True).covers(
        figs[0], c2.model_copy(update={"sentence": "ResNet-50 has a loss of 0.3 on CIFAR-10."}))


def test_alias_and_two_figure_claims():
    f1 = _fig("fig1", 1, lines=["Accuracy (%)", "ResNet-50", "CIFAR-10", "MNIST"], caption="Accuracy (vision)")
    f2 = _fig("fig2", 2, lines=["Accuracy (%)", "ResNet-50", "SST-2", "IMDB"], caption="Accuracy (text)")
    report = Report(report_id="r", pdf_path="", figures=[f1, f2], sentences=[
        Sentence(sentence_id="s1", report_id="r", text="RN50 reaches 91.2% accuracy on CIFAR-10."),
        Sentence(sentence_id="s2", report_id="r", text="ResNet-50 scores 5.0 points higher on CIFAR-10 than on SST-2.")])
    tab1, tab2 = {"ResNet-50": {"CIFAR-10": 91.2, "MNIST": 99.0}}, {"ResNet-50": {"SST-2": 86.2, "IMDB": 88.0}}

    class TwoFig(Tool):
        def __init__(self, name):
            super().__init__(None)
            self.name = name

        def _read(self, fig, q):
            return (tab1 if fig.figure_id == "fig1" else tab2)[q.series][q.x]
    ctl = ClaimController({"a": TwoFig("a"), "b": TwoFig("b")}, FixedOrderPolicy(["a", "b"]), _table(), RuleConfig())
    old = {t.sentence_id: t for t in ReportAgent(RuleParser(), ctl).run(report)[0]}
    new = {t.sentence_id: t for t in ReportAgent(RuleParser(), ctl, aliases={"RN50": "ResNet-50"},
                                                 cross_chart=True).run(report)[0]}
    assert old["s1"].decision.verdict == "NO_FIGURE" and new["s1"].decision.verdict == "CONSISTENT"
    assert old["s2"].decision.verdict == "NO_FIGURE" and new["s2"].decision.verdict == "CONSISTENT"


# ---------------------------------------------------------------- A1-A3: notes for the TA
def test_citation_note():
    figs = [_fig("fig1", 1), _fig("fig2", 2)]
    assert citation_note(_claim(figure_hint=1), figs[0], figs) is None
    assert "cites Figure 1" in citation_note(_claim(figure_hint=1), figs[1], figs)
    assert "no Figure 7" in citation_note(_claim(figure_hint=7), None, figs)
    no_fig = citation_note(_claim(figure_hint=1), None, figs)       # cited figure exists, OCR found nothing
    assert "Check Figure 1" in no_fig and "citation may be wrong" not in no_fig


def test_conflicting_sentences_are_noted():
    def tr(sid, v):
        return ClaimTrace(report_id="r", sentence_id=sid, sentence=f"A reaches {v}% on CIFAR-10.", figure_id="fig1",
                          claim=_claim(f"A reaches {v}% on CIFAR-10.", v), decision=Decision(verdict="CONSISTENT"))
    ts = [tr("s1", 91.2), tr("s2", 93.4), tr("s3", 91.2)]
    add_conflicts(ts)
    assert len(ts[0].notes) == 1 and len(ts[1].notes) == 2 and ts[0].decision.verdict == "CONSISTENT"


def test_a_flag_names_the_series_the_number_belongs_to():
    tab = {"A": {"CIFAR-10": 91.2}, "B": {"CIFAR-10": 85.0}}
    tool = FakeTable("t", tab)
    fig = _fig()
    tool.table(fig)
    d = Decision(verdict="MISMATCH", gap=6.2, margin_accept=0.5)
    note = explain_flag(_claim(value=85.0, tol=0.05), fig, d, {"t": tool}, {("t", "fig1")})
    assert "B at CIFAR-10" in note and "series" in note
    assert explain_flag(_claim(value=85.0), fig, d, {"t": tool}, set()) is None          # table not read: no note
    one = FakeTable("t", {"Accuracy (%)": {"CIFAR-10": 91.2, "SVHN": 85.0}})   # DePlot names a lone series by its axis
    one.table(fig)
    note = explain_flag(_claim(value=85.0, tol=0.05), fig, d, {"t": one}, {("t", "fig1")})
    assert "matches A at SVHN" in note and "mix-up of x value" in note


def test_mix_up_note_uses_a_cached_table(tmp_path):
    """In a replay the table comes from the reading cache, not memory: the note must still find it (and not read)."""
    from chart_claim_verifier.tools.cache import ReadingCache
    cache = ReadingCache(str(tmp_path / "c.sqlite"))
    fig = _fig()
    FakeTable("t", {"A": {"CIFAR-10": 91.2}, "B": {"CIFAR-10": 85.0}}, cache=cache).table(fig)   # an earlier run
    fresh = FakeTable("t", {}, cache=cache)                         # this run: nothing in memory, empty if read
    d = Decision(verdict="MISMATCH", gap=6.2, margin_accept=0.5)
    assert "B at CIFAR-10" in explain_flag(_claim(value=85.0, tol=0.05), fig, d, {"t": fresh}, {("t", "fig1")})


# ---------------------------------------------------------------- A4, B7: captions, unsupported charts
def test_caption_claims_and_unsupported_charts():
    f1 = _fig(caption="Accuracy by dataset. A reaches 91.2% accuracy on CIFAR-10.", lines=["A", "CIFAR-10"])
    tab = {"A": {"CIFAR-10": 91.2}}
    ctl = ClaimController({"a": FakePoint("a", tab), "b": FakePoint("b", tab)}, FixedOrderPolicy(["a", "b"]),
                          _table(), RuleConfig())
    report = Report(report_id="r", pdf_path="", figures=[f1], sentences=[])
    assert ReportAgent(RuleParser(), ctl).run(report)[0] == []
    tr = ReportAgent(RuleParser(), ctl, check_captions=True).run(report)[0]
    assert [t.decision.verdict for t in tr] == ["CONSISTENT"] and tr[0].figure_id == "fig1"
    f1.flags = ["dual_y"]
    tr = ReportAgent(RuleParser(), ctl, check_captions=True, hand_off_unsupported=True).run(report)[0]
    assert tr[0].decision.verdict == "NOT_SURE" and unsupported(f1)


# ---------------------------------------------------------------- metrics: one gold label per claim of a sentence
def test_metrics_join_by_atom():
    s = "A reaches 91.2% accuracy on CIFAR-10, while B obtains 80.0% accuracy on SVHN."
    truths = [{"report_id": "r", "claims": [{"sentence": s, "gold": "correct", "kind": "correct_exact", "atom": 0},
                                            {"sentence": s, "gold": "error", "kind": "planted", "atom": 1}]}]
    ts = [ClaimTrace(report_id="r", sentence_id="s", sentence=s, atom=a, decision=Decision(verdict=v))
          for a, v in ((0, "CONSISTENT"), (1, "MISMATCH"))]
    assert [r.gold for r in join(ts, truths)] == ["correct", "error"]


# ---------------------------------------------------------------- A7, B1, C5: reading PDFs
def _two_column_pdf(path, vector_png=None):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    left = ["Left column first paragraph about the models we trained and the data we used here.",
            "Left column second paragraph: ResNet-50 reaches 91.2% accuracy on CIFAR-10 in our runs."]
    right = ["Right column first paragraph: ViT-S reaches 88.0% accuracy on CIFAR-10 after tuning.",
             "Right column second paragraph with the final remarks about the whole experiment here."]
    for i, t in enumerate(left):
        page.insert_textbox(pymupdf.Rect(50, 60 + 80 * i, 285, 130 + 80 * i), t, fontsize=10)
    for i, t in enumerate(right):
        page.insert_textbox(pymupdf.Rect(310, 60 + 80 * i, 545, 130 + 80 * i), t, fontsize=10)
    doc.save(str(path))


def test_two_column_reading_order(tmp_path):
    from chart_claim_verifier.ingest.pdf_parser import parse_pdf
    _two_column_pdf(tmp_path / "r.pdf")
    old = [s.text for s in parse_pdf(tmp_path / "r.pdf", tmp_path / "w1", "r", analyse_figures=False).sentences]
    new = [s.text for s in parse_pdf(tmp_path / "r.pdf", tmp_path / "w2", "r", analyse_figures=False,
                                     two_column=True).sentences]
    assert new[0].startswith("Left column first") and new[2].startswith("Right column first")
    assert old[1].startswith("Right column first")          # the old reader interleaved the columns


def test_vector_figure_is_found(tmp_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from chart_claim_verifier.ingest.pdf_parser import parse_pdf
    fig, ax = plt.subplots(figsize=(5, 3.4), dpi=100)
    ax.bar(["CIFAR-10", "MNIST", "SVHN"], [80.0, 95.0, 70.0], color="#1f77b4")
    ax.set_ylabel("Accuracy (%)")
    fig.savefig(tmp_path / "f.pdf")
    plt.close(fig)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_textbox(pymupdf.Rect(50, 50, 545, 90), "The results are shown below in a figure.", fontsize=10)
    page.show_pdf_page(pymupdf.Rect(100, 100, 450, 340), pymupdf.open(str(tmp_path / "f.pdf")), 0)
    page.insert_textbox(pymupdf.Rect(50, 350, 545, 380), "Figure 1: Accuracy by dataset.", fontsize=9)
    doc.save(str(tmp_path / "r.pdf"))
    assert parse_pdf(tmp_path / "r.pdf", tmp_path / "w1", "r", analyse_figures=False).figures == []
    rep = parse_pdf(tmp_path / "r.pdf", tmp_path / "w2", "r", vector_figures=True)
    assert [f.number for f in rep.figures] == [1] and "vector" in rep.figures[0].flags
    assert not any("CIFAR" in s.text for s in rep.sentences)       # tick labels are not prose
    from chart_claim_verifier.tools.ocr_pixel import OcrPixelTool
    r = OcrPixelTool().read(rep.figures[0].model_copy(update={"chart_type": "bar"}), PointQuery(series="x", x="MNIST"))
    assert r.ok and r.value == pytest.approx(95.0, abs=1.0)


def test_heatmap_cells_inside_vector_axes_are_one_figure(tmp_path):
    """matplotlib writes a heatmap's cells (and colour bar) as raster images inside vector axes: one figure, not three."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from chart_claim_verifier.ingest.pdf_parser import parse_pdf
    fig, ax = plt.subplots(figsize=(5, 3.4), dpi=100)
    im = ax.imshow(np.arange(20).reshape(4, 5), cmap="viridis", aspect="auto")
    ax.set_xticks(range(5), ["a", "b", "c", "d", "e"])
    ax.set_yticks(range(4), ["CNN", "MLP", "GRU", "ViT"])
    fig.colorbar(im)
    fig.savefig(tmp_path / "f.pdf")
    plt.close(fig)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_textbox(pymupdf.Rect(50, 50, 545, 90), "The results are shown below in a figure.", fontsize=10)
    page.show_pdf_page(pymupdf.Rect(100, 100, 450, 340), pymupdf.open(str(tmp_path / "f.pdf")), 0)
    page.insert_textbox(pymupdf.Rect(50, 350, 545, 380), "Figure 1: Accuracy by model and dataset.", fontsize=9)
    doc.save(str(tmp_path / "r.pdf"))
    rep = parse_pdf(tmp_path / "r.pdf", tmp_path / "w", "r", analyse_figures=False, vector_figures=True)
    assert [(f.number, "vector" in f.flags) for f in rep.figures] == [(1, True)]


def test_a_figure_with_no_text_shows_no_name():
    from chart_claim_verifier.retrieval.figure_index import FigureIndex
    idx = FigureIndex([_fig("blank", None)])         # e.g. a colour bar extracted as its own image (used to crash)
    assert not idx.shows("ResNet-50")
    figs, _ = idx.locate(_claim("ResNet-50 reaches 91.2% on CIFAR-10.", 91.2, series="ResNet-50"))
    assert figs == []


def test_model_usage_is_counted():
    from chart_claim_verifier.models.vlm import new_usage, record_usage
    u = new_usage()
    record_usage(u, 1200, 40, 1.5)
    record_usage(u, 800, 10, 0.5)
    assert (u["calls"], u["input_tokens"], u["output_tokens"], u["seconds"]) == (2, 2000, 50, 2.0)


def test_a_cited_unsupported_chart_is_handed_off_not_no_figure():
    """A histogram's text shows no datasets, so 'no figure' would be a guess: the cited chart is returned instead."""
    hist = _fig("fig1", 1, chart_type="line", caption="Validation accuracy of MLP by dataset",
                flags=["unsupported:histogram"])
    claim = _claim("MLP reaches 72.7% validation accuracy on IMDB (Figure 1).", 72.7, series="MLP", x="IMDB",
                   figure_hint=1)
    figs, _ = FigureIndex([hist]).locate(claim)
    assert [f.figure_id for f in figs] == ["fig1"] and unsupported(figs[0])
    plain = hist.model_copy(update={"flags": []})               # without the flag (switch off): unchanged
    assert FigureIndex([plain]).locate(claim)[0] == []


def test_scanned_page_is_read(tmp_path):
    from chart_claim_verifier.generator.v3feat import scanned_copy
    from chart_claim_verifier.ingest.pdf_parser import parse_pdf
    _two_column_pdf(tmp_path / "r.pdf")
    scanned_copy(tmp_path / "r.pdf", tmp_path / "s.pdf", random.Random(0), dpi=150)
    assert parse_pdf(tmp_path / "s.pdf", tmp_path / "w1", "r", analyse_figures=False).sentences == []
    rep = parse_pdf(tmp_path / "s.pdf", tmp_path / "w2", "r", analyse_figures=False, ocr_scanned=True, two_column=True)
    text = " ".join(s.text for s in rep.sentences)
    assert "91.2% accuracy on CIFAR-10" in text and "88.0% accuracy" in text


# ---------------------------------------------------------------- B5, B7: panels and chart kinds
def _render(tmp_path, draw, name="c.png", size=(5.5, 3.6)):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = draw(plt, size)
    fig.tight_layout()
    fig.savefig(tmp_path / name, dpi=100)
    plt.close(fig)
    return str(tmp_path / name)


def test_two_panels_are_found(tmp_path):
    from chart_claim_verifier.ingest.panels import find_panels, split_caption
    from chart_claim_verifier.tools.chart_ocr import load_bgr

    def two(plt, size):
        fig, axes = plt.subplots(1, 2, figsize=(9, 3.6))
        axes[0].plot([1, 2, 3], [50, 60, 70], color="#d62728")
        axes[1].bar(["a", "b"], [3, 4], color="#1f77b4")
        return fig, axes

    def one(plt, size):
        fig, ax = plt.subplots(figsize=size)
        ax.plot([1, 2, 3], [50, 60, 70], color="#d62728")
        return fig, ax
    assert len(find_panels(load_bgr(_render(tmp_path, two, "two.png")))) == 2
    assert len(find_panels(load_bgr(_render(tmp_path, one, "one.png")))) == 1
    assert split_caption("Results. (a) Accuracy. (b) Loss.", 2) == ["Results. Accuracy.", "Results. Loss."]


@pytest.mark.parametrize("kind", ["scatter", "heatmap", "histogram", "horizontal_bar"])
def test_unsupported_kinds_are_flagged(tmp_path, kind):
    from chart_claim_verifier.ingest.panels import chart_flags
    rng = np.random.default_rng(0)

    def draw(plt, size):
        fig, ax = plt.subplots(figsize=size)
        if kind == "scatter":
            for c in ("#1f77b4", "#d62728"):
                ax.scatter(rng.uniform(0, 10, 30), rng.uniform(40, 90, 30), color=c, s=18)
        elif kind == "heatmap":
            ax.imshow(rng.uniform(0, 1, (5, 6)), cmap="viridis", aspect="auto")
        elif kind == "histogram":
            ax.hist(rng.normal(50, 10, 400), bins=14, color="#1f77b4")
        else:
            ax.barh(range(4), [80, 60, 90, 70], color="#1f77b4", height=0.6)
            ax.set_yticks(range(4))
            ax.set_yticklabels(["CIFAR-10", "MNIST", "SVHN", "IMDB"])
        return fig, ax
    assert f"unsupported:{kind}" in chart_flags(_render(tmp_path, draw), None)


def test_dual_axis_is_flagged(tmp_path):
    from chart_claim_verifier.ingest.panels import chart_flags
    from chart_claim_verifier.tools.axis import analyse

    def draw(plt, size):
        fig, ax = plt.subplots(figsize=size)
        ax.plot([1, 2, 3, 4], [50, 60, 70, 75], color="#1f77b4")
        ax2 = ax.twinx()
        ax2.plot([1, 2, 3, 4], [2.0, 1.2, 0.8, 0.6], "--", color="black")
        return fig, ax
    p = _render(tmp_path, draw)
    assert "dual_y" in chart_flags(p, analyse(p))


# ---------------------------------------------------------------- C4: real charts from two WebPlotDigitizer sessions
def test_import_two_wpd_sessions(tmp_path):
    import importlib.util
    import json
    spec = importlib.util.spec_from_file_location("import_wpd", "scripts/real/import_wpd.py")
    wpd = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wpd)
    (tmp_path / "fig1_s1").mkdir()
    (tmp_path / "fig1_s1" / "long.csv").write_text("series,x,value\nGRU,1,50.0\nGRU,2,60.0\nGRU,3,70.0\n")
    (tmp_path / "fig1_s2").mkdir()                      # WebPlotDigitizer's own x,y export, x slightly off
    (tmp_path / "fig1_s2" / "GRU.csv").write_text("1.02,50.4\n1.98,59.8\n3.01,70.2\n")
    (tmp_path / "figures.json").write_text(json.dumps([{"number": 1, "kind": "line", "y_label": "Accuracy (%)",
                                                        "metric_word": "accuracy", "percent": True, "x_values": ["1", "2", "3"],
                                                        "sessions": ["fig1_s1", "fig1_s2"], "y_span": 100}]))
    (tmp_path / "claims.json").write_text(json.dumps([
        {"sentence": "GRU reaches 60.0% accuracy at epoch 2.", "figure": 1, "gold": None},
        {"sentence": "GRU reaches 75.0% accuracy at epoch 3.", "figure": 1, "gold": None},
        {"sentence": "GRU reaches 52.5% accuracy at epoch 1.", "figure": 1, "gold": None},
        {"sentence": "SVM reaches 40% accuracy on MNIST.", "figure": None, "gold": "no_figure"}]))
    t = wpd.import_report(tmp_path)
    assert t["figures"][0]["table"]["series"]["GRU"] == [50.2, 59.9, 70.1]
    assert [c["gold"] for c in t["claims"]] == ["correct", "error", "unknown", "no_figure"]
    assert t["session_agreement"]["points"] == 3
