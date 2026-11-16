"""v4 (16 Nov): fixes from the real-world review (results/run_log.md, section J). Every switch is off by default, so
each test also checks that the frozen behaviour is unchanged where that matters."""
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pymupdf  # noqa: E402
import pytest  # noqa: E402

from chart_claim_verifier.agent.controller import ClaimController  # noqa: E402
from chart_claim_verifier.agent.memory import ReportMemory  # noqa: E402
from chart_claim_verifier.agent.policies import FixedOrderPolicy  # noqa: E402
from chart_claim_verifier.agent.report_agent import ReportAgent, unsupported  # noqa: E402
from chart_claim_verifier.calibration.store import CalibrationTable  # noqa: E402
from chart_claim_verifier.claims import direction  # noqa: E402
from chart_claim_verifier.claims.finder import figure_hint, is_candidate  # noqa: E402
from chart_claim_verifier.claims.number_words import words_to_digits  # noqa: E402
from chart_claim_verifier.claims.parser import RuleParser  # noqa: E402
from chart_claim_verifier.claims.tolerance import find_numbers, find_range  # noqa: E402
from chart_claim_verifier.decide.rule import RuleConfig  # noqa: E402
from chart_claim_verifier.ingest.pdf_parser import PdfError, parse_pdf, split_sentences  # noqa: E402
from chart_claim_verifier.pipeline import _parse_cache_name, ingest_options  # noqa: E402
from chart_claim_verifier.retrieval.figure_index import FigureIndex  # noqa: E402
from chart_claim_verifier.schemas import ClaimSpec, Figure, Report, Sentence  # noqa: E402
from chart_claim_verifier.tools import base  # noqa: E402
from chart_claim_verifier.tools.base import Tool, ToolError, lookup, match_name, names_conflict, strict_match  # noqa: E402

V4 = RuleParser(True, True, True, more_phrasings=True, directions=True)
FROZEN = RuleParser()


@pytest.fixture(autouse=True)
def loose_names():
    base.STRICT_NAMES = False
    yield
    base.STRICT_NAMES = False


# ------------------------------------------------------------------ numbers as a PDF writes them
@pytest.mark.parametrize("text, value, percent", [
    ("a log-likelihood of −0.35 here", -0.35, False),          # LaTeX minus sign
    ("a loss of 3.5 × 10−4 here", 0.00035, False),             # exponent with the superscript lost
    ("a loss of 3.5×10⁻⁴ here", 0.00035, False),               # exponent in superscripts
    ("a loss of .35 here", 0.35, False),
    ("reaches 91.2 per cent here", 91.2, True),
    ("reaches 91.2%¹ here", 91.2, True),                        # footnote mark, not a number
])
def test_numbers_written_the_pdf_way(text, value, percent):
    n = find_numbers(text)
    assert n and n[0].value == pytest.approx(value) and n[0].percent == percent
    assert len(n) == 1


@pytest.mark.parametrize("text, relation", [("reaches >90% at", "greater"), ("reaches ≥ 90% at", "greater"),
                                            ("an error of <1% at", "less"), ("reaches ~91% at", "approx")])
def test_symbol_relations(text, relation):
    assert find_numbers(text)[0].relation == relation


def test_hedged_large_numbers_allow_five_percent():
    tol = lambda t: find_numbers(t)[0].tolerance
    assert tol("about 80%") == 5 and tol("about 100 runs") == 5 and tol("about 10%") == 5     # unchanged
    assert tol("about 1000 images/s") == 50 and tol("about 2500 steps") == 50 and tol("roughly 50,000 samples") == 2500


def test_dash_range_needs_a_percent_sign():
    r = find_range("VGG-16 reaches 84-86% accuracy", dash=True)
    assert (r.low.value, r.high.value) == (84, 86)
    assert find_range("between epochs 5-10 it reaches 91%", dash=True) is None
    assert find_range("VGG-16 reaches 84-86% accuracy") is None                    # frozen: off


# ------------------------------------------------------------------ finding claims
def test_more_result_words_only_with_the_switch():
    for s in ["The AUC of ResNet-50 is 0.91 at epoch 14.", "ResNet-50 hits 91.2% at epoch 14.",
              "ResNet-50 has a gradient norm of 0.00056 at epoch 10.", "The model has a mAP of 31.2 on COCO."]:
        assert is_candidate(s, extended=True) and not is_candidate(s)
    assert not is_candidate("Error bars show the standard deviation over 5 runs.", extended=True)
    assert figure_hint("as shown in Fig 3", extended=True) == 3 and figure_hint("as shown in Fig 3") is None


# ------------------------------------------------------------------ parsing real phrasings
@pytest.mark.parametrize("sentence, ctype, series, x, value", [
    ("ResNet-50 achieved an accuracy of 91.2% at epoch 14.", "point", "ResNet-50", "14", 91.2),
    ("ResNet-50 reached 91.2% at epoch 14.", "point", "ResNet-50", "14", 91.2),
    ("At epoch 14 ResNet-50 reaches 91.2% accuracy.", "point", "ResNet-50", "14", 91.2),
    ("By epoch 14, ResNet-50 reaches 91.2%.", "point", "ResNet-50", "14", 91.2),
    ("ResNet-50's accuracy is 91.2% at epoch 14.", "point", "ResNet-50", "14", 91.2),
    ("The accuracy of ResNet-50 at epoch 14 is 91.2%.", "point", "ResNet-50", "14", 91.2),
    ("ResNet-50 achieves 91.2% accuracy after 14 epochs.", "point", "ResNet-50", "14", 91.2),
    ("ResNet-50 reaches ~91% at epoch 14.", "point", "ResNet-50", "14", 91.0),
    ("ResNet-50 reaches 91.2 ± 0.4% accuracy at epoch 14.", "point", "ResNet-50", "14", 91.2),
    ("ResNet-50 reaches 91.2% at epoch 14 (see Table 2).", "point", "ResNet-50", "14", 91.2),
    ("In Fig. 3, ResNet-50 reaches 91.2% at epoch 14.", "point", "ResNet-50", "14", 91.2),
    ("ResNet-50 achieves 91.2% accuracy at step 1,400.", "point", "ResNet-50", "1400", 91.2),
    ("ResNet-50 has a loss of −0.35 at epoch 14.", "point", "ResNet-50", "14", -0.35),
    ("At epoch 10, ViT-S trails ResNet-50 by 4.0 points.", "difference", "ViT-S", "10", 4.0),
])
def test_v4_phrasings(sentence, ctype, series, x, value):
    c = V4.parse(sentence, "c")
    assert c is not None, sentence
    assert (c.claim_type, c.series, c.x, c.claimed_value) == (ctype, series, x, pytest.approx(value))


def test_decreases_are_parsed_only_with_directions():
    s = "From epoch 1 to epoch 10, the loss of VGG-16 drops by 65%."
    assert RuleParser(more_phrasings=True).parse(s, "c") is None      # without the sign fix it would be read as +65
    assert V4.parse(s, "c").claim_type == "relative_change"
    assert FROZEN.parse(s, "c") is None


# ------------------------------------------------------------------ directions and negation
def _oriented(sentence):
    c = V4.parse(sentence, "c")
    return direction.orient(c, sentence)[0]


def test_falls_are_negative():
    c = _oriented("From epoch 1 to epoch 10, the loss of VGG-16 drops by 65%.")
    assert c.claimed_value == -65
    c = _oriented("From epoch 1 to epoch 10, the loss of ResNet-50 improves by 70%.")      # better loss = lower
    assert c.claimed_value == -70
    c = _oriented("From epoch 5 to epoch 10, the accuracy of ResNet-50 improves by a relative 9.9%.")
    assert c.claimed_value == 9.9
    c = _oriented("From epoch 1 to epoch 10, the loss of VGG-16 drops by more than 60%.")
    assert (c.claimed_value, c.relation) == (-60, "less")                                 # change < -60


@pytest.mark.parametrize("sentence, first, second", [
    ("At epoch 10, VGG-16 is 6.2 points lower than ResNet-50.", "ResNet-50", "VGG-16"),
    ("At epoch 10, ViT-S trails ResNet-50 by 4.0 points.", "ResNet-50", "ViT-S"),
    ("ResNet-50 outperforms VGG-16 by 6.2 points at epoch 10.", "ResNet-50", "VGG-16"),
])
def test_differences_are_first_minus_second(sentence, first, second):
    c = _oriented(sentence)
    assert (c.series, c.series_b, c.claimed_value) == (first, second, 6.2 if "6.2" in sentence else 4.0)


def test_x_position_ignores_the_number_and_the_figure_reference():
    """dev_009 (v4 replay): "about 4 points higher on 4 than on 2 (Figure 2)" was turned around."""
    c = _oriented("As shown in Figure 2, GRU scores about 4 points higher on 4 than on 2.")
    assert (c.x, c.x_b) == ("4", "2")
    c = _oriented("GRU scores 4 points lower on 2 than on 4.")
    assert (c.x, c.x_b) == ("4", "2")


def test_negation():
    assert direction.negation("ResNet-50 does not reach 91.2% at epoch 10.") == "not"
    assert direction.negation("ViT-S never reaches 90% at epoch 10.") == "never"
    assert direction.negation("Not only does ResNet-50 reach 91%, it is also fast.") is None
    assert direction.negation("ResNet-50 reaches 91.2% at epoch 10.") is None


def test_percent_alternative():
    c = V4.parse("From epoch 5 to epoch 10, the accuracy of ResNet-50 improves by 8.2%.", "c")
    assert direction.percent_alternative(c) == "points"
    c = V4.parse("From epoch 5 to epoch 10, the accuracy of ResNet-50 improves by a relative 9.9%.", "c")
    assert direction.percent_alternative(c) is None
    c = V4.parse("ResNet-50 outperforms VGG-16 by 3.1% at epoch 14.", "c")
    assert direction.percent_alternative(c) == "relative"


# ------------------------------------------------------------------ number words
@pytest.mark.parametrize("text, expected", [
    ("At this point five models were trained.", "At this point five models were trained."),
    ("ResNet-50 reaches a hundred percent at epoch 14.", "ResNet-50 reaches 100 percent at epoch 14."),
    ("Loss drops to one point twenty-five at epoch ten.", "Loss drops to 1.25 at epoch 10."),
    ("In nineteen ninety-eight LeNet reached 99%.", "In 1998 LeNet reached 99%."),
    ("Accuracy improves by two to three percent.", "Accuracy improves by 2 to 3 percent."),
    ("ResNet-50 reaches ninety-one and a half percent.", "ResNet-50 reaches 91.5 percent."),
    ("ResNet-50 reaches ﬁve percent more.", "ResNet-50 reaches 5 percent more."),
])
def test_number_words_v4(text, expected):
    assert words_to_digits(text) == expected


# ------------------------------------------------------------------ family names
def test_names_conflict():
    assert names_conflict("ResNet-18", "ResNet-50") and names_conflict("CIFAR-100", "CIFAR-10")
    assert names_conflict("BERT-base", "BERT-large") and not names_conflict("VGG16", "VGG-16")
    assert strict_match("ResNet", ["ResNet-18", "ResNet-50"]) == (None, "ambiguous_name")
    assert strict_match("ResNet-18", ["ResNet-50", "VGG-16"])[0] is None
    assert strict_match("ResNet-50", ["ResNet-50 (ours)", "ResNet-18"])[0] == "ResNet-50 (ours)"
    assert match_name("ResNet-18", ["ResNet-50", "VGG-16"]) == "ResNet-50"           # frozen: loose


def test_strict_lookup_never_reads_a_sibling():
    tab = {"ResNet-50": {"CIFAR-10": 94.6, "CIFAR-100": 78.2}}
    base.STRICT_NAMES = True
    with pytest.raises(ToolError):
        lookup(tab, "ResNet-18", "CIFAR-10")                                         # single series: no fallback
    tab2 = {"ResNet-50": {"CIFAR-10": 94.6}}
    with pytest.raises(ToolError):
        lookup(tab2, "ResNet-50", "CIFAR-100")
    assert base.lookup_veto(tab, "ResNet-18", "CIFAR-10") == "series_name_conflict"


def _fig(fid, n, cap, lines, chart="line"):
    return Figure(figure_id=fid, report_id="r", image_path="x.png", caption=cap, number=n, chart_type=chart,
                  text_lines=lines, y_span=40)


def test_strict_and_split_aware_retrieval():
    val = _fig("fig1", 1, "Validation accuracy.", ["ResNet-50", "VGG-16", "Accuracy (%)"])
    loose, strict = FigureIndex([val]), FigureIndex([val], strict_names=True, split_aware=True)
    c18 = V4.parse("ResNet-18 reaches 88.0% accuracy at epoch 10.", "c")
    assert loose.locate(c18)[0] and not strict.locate(c18)[0]
    ctest = V4.parse("ResNet-50 reaches 89.0% test accuracy at epoch 10.", "c")
    assert loose.locate(ctest)[0] and not strict.locate(ctest)[0]
    # OCR ran three labels together: no clean name there, so it is not a conflict (dev_011 in the v4 replay)
    bar = _fig("fig3", 3, "Validation accuracy of BERT-base by dataset.",
               ["SST-2", "CIFAR-1LOFashion-MNISTAG News", "SVHN"], chart="bar")
    c = V4.parse("On CIFAR-10, BERT-base obtains a validation accuracy of about 80%.", "c")
    assert FigureIndex([bar], strict_names=True, split_aware=True).locate(c)[0]


# ------------------------------------------------------------------ deciding without a readable axis
@pytest.fixture
def chart(tmp_path):
    p = tmp_path / "chart.png"
    p.write_bytes(_chart_png())
    return str(p)


class Fixed(Tool):
    scope, kind, version = "point", "simulated", "t"

    def __init__(self, name, value):
        super().__init__(None)
        self.name, self.value = name, value

    def _read(self, fig, q):
        return self.value


def _run(span, options, image):
    tools = {"a": Fixed("a", 91.0), "b": Fixed("b", 91.0)}
    table = CalibrationTable({"*|*|*": [0.5] * 50 + [1.0] * 50}, min_group_size=1)
    ctl = ClaimController(tools, FixedOrderPolicy(list(tools)), table, RuleConfig(), options=options)
    fig = Figure(figure_id="f", report_id="r", image_path=image, chart_type="line", y_span=span)
    claim = ClaimSpec(claim_id="c", sentence="s", claim_type="point", series="A", x="1", claimed_value=95.0,
                      tolerance=0.05)
    rep = Report(report_id="r", pdf_path="r.pdf", figures=[fig], sentences=[])
    return ctl.run(claim, fig, ReportMemory(rep, FigureIndex([fig])))


def test_no_flag_without_a_readable_axis(chart):
    assert _run(None, {}, chart).decision.verdict == "MISMATCH"                                # frozen
    r = _run(None, {"no_flag_without_axis": True}, chart)
    assert r.decision.verdict == "NOT_SURE" and "y-axis could not be read" in r.decision.reason
    assert _run(40.0, {"no_flag_without_axis": True}, chart).decision.verdict == "MISMATCH"   # readable axis: flags


def test_multiplier_and_dual_axis_charts_are_handed_off():
    f = Figure(figure_id="f", report_id="r", image_path="x.png", flags=["axis_multiplier"])
    assert "multiplier" in unsupported(f)


# ------------------------------------------------------------------ the agent: negation and the second reading
class TrueReader(Tool):
    scope, kind, version = "point", "simulated", "t"
    TAB = {"ResNet-50": {str(e): v for e, v in zip(range(1, 11), [60, 70, 76, 80, 83, 85.5, 87.5, 89, 90.2, 91.2])},
           "VGG-16": {str(e): v for e, v in zip(range(1, 11), [55, 64, 70, 74, 77, 79.5, 81.5, 83, 84.1, 85.0])}}

    def __init__(self, name):
        super().__init__(None)
        self.name = name

    def _read(self, fig, q):
        return lookup(self.TAB, q.series, q.x)


def _agent_verdicts(image, sentences, **switches):
    fig = _fig("fig1", 1, "Validation accuracy.", ["ResNet-50", "VGG-16", "Accuracy (%)", "Epoch"])
    fig.image_path = image
    report = Report(report_id="r", pdf_path="r.pdf", figures=[fig],
                    sentences=[Sentence(sentence_id=f"s{i}", report_id="r", text=s) for i, s in enumerate(sentences)])
    tools = {"a": TrueReader("a"), "b": TrueReader("b")}
    table = CalibrationTable({"*|*|*": [0.5] * 50 + [1.0] * 50}, min_group_size=1)
    ctl = ClaimController(tools, FixedOrderPolicy(list(tools)), table, RuleConfig())
    agent = ReportAgent(V4 if switches else FROZEN, ctl, **switches)
    return {t.sentence: t.decision.verdict for t in agent.run(report)[0]}


def test_agent_v4_end_to_end(chart):
    s = ["ResNet-50 does not reach 95% accuracy at epoch 10.",
         "From epoch 5 to epoch 10, the accuracy of ResNet-50 improves by 8.2%.",
         "At epoch 10, VGG-16 is 6.2 points lower than ResNet-50.",
         "ResNet-50 never reaches 91.2% accuracy at epoch 10."]
    v4 = _agent_verdicts(chart, s, more_phrasings=True, directions=True, ambiguous_percent=True, strict_names=True,
                         split_aware=True)
    assert v4[s[0]] in ("NOT_SURE", "SKIPPED") and v4[s[3]] == "NOT_SURE"   # negated: never judged
    assert v4[s[1]] == "NOT_SURE"                                       # 8.2 points is right, 9.9% relative is not
    assert v4[s[2]] == "CONSISTENT"                                     # 91.2 - 85.0 = 6.2
    frozen = _agent_verdicts(chart, s)
    assert frozen[s[3]] == "CONSISTENT" and frozen[s[1]] == "MISMATCH"  # the two v3 failures this fixes


# ------------------------------------------------------------------ reading the PDF
def _chart_png(**kw):
    fig, ax = plt.subplots(figsize=(5, 3.2), dpi=110)
    ax.plot(range(1, 11), [v * kw.get("scale", 1) for v in [60, 70, 76, 80, 83, 85.5, 87.5, 89, 90.2, 91.2]],
            marker="o", label="ResNet-50")
    ax.legend(loc="lower right")
    if kw.get("sci"):
        ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))
    if kw.get("inward"):
        ax.tick_params(direction="in")
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def _pdf(tmp_path, items, name="r.pdf"):
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for kind, y, payload in items:
        if kind == "text":
            page.insert_textbox(pymupdf.Rect(72, y, 523, y + 60), payload, fontsize=10, fontname="helv")
        else:
            page.insert_image(pymupdf.Rect(150, y, 450, y + 190), stream=payload)
    path = tmp_path / name
    doc.save(str(path))
    return path


@pytest.mark.parametrize("caption", ["Fig 1: Validation accuracy.", "FIGURE 1 - Validation accuracy.",
                                     "Figure 1 Validation accuracy.", "Figure 1(a): Validation accuracy."])
def test_caption_formats(tmp_path, caption):
    pdf = _pdf(tmp_path, [("image", 80, _chart_png()), ("text", 275, caption)])
    assert parse_pdf(pdf, tmp_path / "w1", "r", caption_formats=True).figures[0].number == 1
    assert parse_pdf(pdf, tmp_path / "w0", "r").figures[0].number is None               # frozen


def test_caption_above_and_no_stealing(tmp_path):
    # two different images (a PDF stores identical images once)
    pdf = _pdf(tmp_path, [("image", 60, _chart_png()), ("text", 255, "The curve flattens out after epoch six."),
                          ("text", 330, "Figure 2: Accuracy, caption above."), ("image", 350, _chart_png(scale=0.5))])
    figs = parse_pdf(pdf, tmp_path / "w", "r", caption_formats=True).figures
    assert [f.number for f in figs] == [None, 2]


def test_clean_text_and_sentence_splitting(tmp_path):
    assert split_sentences("As Dr. Rao noted, ResNet-50 reaches 91%. VGG-16 reaches 85% vs. 80%.", True) == \
        ["As Dr. Rao noted, ResNet-50 reaches 91%.", "VGG-16 reaches 85% vs. 80%."]
    assert len(split_sentences("As Dr. Rao noted, ResNet-50 reaches 91%.")) == 2         # frozen
    assert split_sentences("The loss drops. 91% of runs converge.", True) == ["The loss drops.", "91% of runs converge."]


def test_password_and_broken_pdfs(tmp_path):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "ResNet-50 reaches 91.2% accuracy at epoch 10.")
    locked = tmp_path / "locked.pdf"
    doc.save(str(locked), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")
    with pytest.raises(PdfError, match="password"):
        parse_pdf(locked, tmp_path / "w", "r")
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.7\n" + b"\x00" * 200)
    with pytest.raises(PdfError, match="could not be opened"):
        parse_pdf(broken, tmp_path / "w2", "r")


def test_axis_multiplier_flag(tmp_path):
    from chart_claim_verifier.ingest.panels import chart_flags
    from chart_claim_verifier.tools.axis import analyse
    for name, kw, flagged in (("sci.png", {"scale": 1e-5, "sci": True}, True), ("plain.png", {}, False)):
        p = tmp_path / name
        p.write_bytes(_chart_png(**kw))
        assert ("axis_multiplier" in chart_flags(str(p), analyse(str(p)))) == flagged


def test_inward_ticks_are_read_only_with_the_mode(tmp_path):
    from chart_claim_verifier.tools.axis import ChartReadError, analyse
    p = tmp_path / "inward.png"
    p.write_bytes(_chart_png(inward=True))
    geo = analyse(str(p), ("linear", "inward"))
    assert geo.y_span == pytest.approx(33.6, abs=3)
    with pytest.raises(ChartReadError):
        analyse(str(p))


def test_v3_parse_cache_names_do_not_move():
    v3 = {"two_column": True, "vector_figures": True, "split_panels": True, "detect_kinds": True, "ocr_scanned": True,
          "axis_modes": ("linear", "log", "inverted")}
    assert _parse_cache_name({**v3, "clean_text": False, "caption_formats": False}) == _parse_cache_name(v3)
    assert _parse_cache_name(ingest_options({})) == "report.json"
