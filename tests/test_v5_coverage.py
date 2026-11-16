"""v5 (16 Nov): two measured ways to hand fewer claims to the TA (results/run_log.md, section K). Both switches are off
by default; each test also checks that the v4 behaviour is unchanged without them."""
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

from chart_claim_verifier.agent.controller import ClaimController  # noqa: E402
from chart_claim_verifier.agent.memory import ReportMemory  # noqa: E402
from chart_claim_verifier.agent.policies import Policy  # noqa: E402
from chart_claim_verifier.agent.report_agent import ReportAgent  # noqa: E402
from chart_claim_verifier.calibration.store import CalibrationTable  # noqa: E402
from chart_claim_verifier.claims.parser import RuleParser  # noqa: E402
from chart_claim_verifier.decide.rule import RuleConfig  # noqa: E402
from chart_claim_verifier.agent.policies import FixedOrderPolicy  # noqa: E402
from chart_claim_verifier.retrieval.figure_index import FigureIndex  # noqa: E402
from chart_claim_verifier.schemas import ClaimSpec, Figure, Report, Sentence  # noqa: E402
from chart_claim_verifier.tools import base  # noqa: E402
from chart_claim_verifier.tools.base import TableTool, Tool, ToolError, interpolate, lookup  # noqa: E402

TABLE = CalibrationTable({"*|*|*": [0.5] * 50 + [1.0] * 50}, min_group_size=1)


@pytest.fixture(autouse=True)
def loose_names():
    base.STRICT_NAMES = False
    yield
    base.STRICT_NAMES = False


@pytest.fixture
def chart(tmp_path):
    fig, ax = plt.subplots(figsize=(4, 3), dpi=100)
    ax.plot(range(1, 11), [60 + 3 * i for i in range(10)], label="ResNet-50")
    ax.plot(range(1, 11), [55 + 3 * i for i in range(10)], label="VGG-16")
    ax.legend()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    p = tmp_path / "chart.png"
    p.write_bytes(buf.getvalue())
    return str(p)


# ------------------------------------------------------------------ the straight line between two labelled x
def test_interpolate():
    tab = {"ResNet-50": {"1": 60.0, "5": 80.0, "9": 88.0}, "VGG-16": {"1": 50.0, "5": 70.0, "9": 78.0}}
    assert interpolate(tab, "ResNet-50", "7") == (84.0, "5", "9")
    assert interpolate(tab, "VGG-16", "2")[0] == pytest.approx(55.0)
    assert interpolate(tab, "ResNet-50", "10") is None and interpolate(tab, "ResNet-50", "0") is None   # never beyond
    assert interpolate({"A": {"SST-2": 1.0, "IMDB": 2.0}}, "A", "MNIST") is None                     # not numeric
    assert interpolate(tab, "BERT", "7") is None
    base.STRICT_NAMES = True                    # a sibling is never read for another family member
    assert interpolate({"ResNet-50": {"1": 60.0, "9": 88.0}}, "ResNet-18", "5") is None


# ------------------------------------------------------------------ the last step before a hand-off
class HandOff(Policy):
    name = "handoff"

    def next_action(self, state):
        return {"action": "handoff", "why": "no trustworthy pair among the tools still available on this figure"}


class Labelled(TableTool):
    """DePlot as it behaves on these charts: values only at the x values that carry a tick label."""
    name, kind, version = "deplot", "simulated", "t"
    TAB = {"ResNet-50": {"1": 60.0, "5": 80.0, "9": 88.0}, "VGG-16": {"1": 50.0, "5": 70.0, "9": 78.0}}

    def extract_table(self, fig):
        return self.TAB


class Fixed(Tool):
    scope, kind, version = "point", "simulated", "t"

    def __init__(self, name, value):
        super().__init__(None)
        self.name, self.value = name, value

    def _read(self, fig, q):
        if self.value is None:
            raise ToolError("series_not_found")
        return self.value


def _run(claimed, image, x="7", chart_type="line", options=None, crop=85.0):
    tools = {"ocr_pixel": Fixed("ocr_pixel", None), "deplot": Labelled(None), "vlm_crop": Fixed("vlm_crop", crop)}
    ctl = ClaimController(tools, HandOff(), TABLE, RuleConfig(),
                          options={"interpolation_error": 0.048} if options is None else options)
    fig = Figure(figure_id="f", report_id="r", image_path=image, chart_type=chart_type, y_span=40.0)
    claim = ClaimSpec(claim_id="c", sentence="s", claim_type="point", series="ResNet-50", x=x, claimed_value=claimed,
                      tolerance=0.05)
    rep = Report(report_id="r", pdf_path="r.pdf", figures=[fig], sentences=[])
    return ctl.run(claim, fig, ReportMemory(rep, FigureIndex([fig])))


def test_interpolated_pair_decides_what_was_handed_off(chart):
    # straight line at epoch 7: 84.0; vlm_crop 85.0 -> estimate 84.5, margins 0.7 (disagreement 0.5 + 0.5% of 40)
    r = _run(85.0, chart)
    assert r.decision.verdict == "CONSISTENT" and set(r.tool_values) == {"deplot", "vlm_crop"}
    assert "joined by a straight line" in r.notes[0]
    assert _run(95.0, chart).decision.verdict == "MISMATCH"
    # gap 1.5 clears the flag margin (0.75) but not the bend allowance (0.048 x 40 / 2 = 0.96): to the TA
    r = _run(86.0, chart)
    assert r.decision.verdict == "NOT_SURE" and "interpolation error" in r.decision.reason


def test_interpolated_pair_only_where_it_was_measured(chart):
    assert _run(85.0, chart, options={}).decision.reason.startswith("handed off")          # switch off: v4
    assert _run(85.0, chart, chart_type="bar").decision.verdict == "NOT_SURE"            # line charts only
    assert _run(80.0, chart, x="5").decision.verdict == "NOT_SURE"                       # x is labelled: no line drawn
    assert _run(85.0, chart, x="12").decision.verdict == "NOT_SURE"                      # never beyond the last label
    assert _run(85.0, chart, crop=None).decision.verdict == "NOT_SURE"                   # no cross-check


# ------------------------------------------------------------------ wrong on every figure that fits
class PerFigure(Tool):
    scope, kind, version = "point", "simulated", "t"

    def __init__(self, name, tables):
        super().__init__(None)
        self.name, self.tables = name, tables

    def cache_key(self, fig, q):
        return (self.name, fig.figure_id, q.series, q.x)

    def _read(self, fig, q):
        return lookup(self.tables[fig.figure_id], q.series, q.x)


def _ambiguous(image, tables, sentence, **switches):
    figs = []
    for n in (1, 2):
        figs.append(Figure(figure_id=f"fig{n}", report_id="r", image_path=image, caption="Validation accuracy.", number=n,
                           chart_type="line", text_lines=["ResNet-50", "VGG-16", "Accuracy (%)", "Epoch"], y_span=40))
    report = Report(report_id="r", pdf_path="r.pdf", figures=figs,
                    sentences=[Sentence(sentence_id="s0", report_id="r", text=sentence)])
    tools = {"a": PerFigure("a", tables), "b": PerFigure("b", tables)}
    ctl = ClaimController(tools, FixedOrderPolicy(list(tools)), TABLE, RuleConfig())
    agent = ReportAgent(RuleParser(True, True, True), ctl, ambiguous_rule="both", **switches)
    return agent.run(report)[0][0]


def test_flag_when_wrong_on_both_figures(chart):
    s = "ResNet-50 reaches 95.0% accuracy at epoch 10."
    both = {"fig1": {"ResNet-50": {"10": 91.2}}, "fig2": {"ResNet-50": {"10": 89.0}}}
    assert _ambiguous(chart, both, s).decision.verdict == "NOT_SURE"                          # v4: never flagged
    t = _ambiguous(chart, both, s, ambiguous_flag="both")
    assert t.decision.verdict == "MISMATCH" and "every figure that fits" in t.decision.reason
    one = {"fig1": {"ResNet-50": {"10": 95.0}}, "fig2": {"ResNet-50": {"10": 89.0}}}
    assert _ambiguous(chart, one, s, ambiguous_flag="both").decision.verdict == "NOT_SURE"   # right on one of them
    with pytest.raises(ValueError):
        _ambiguous(chart, both, s, ambiguous_flag="either")
