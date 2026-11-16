"""H23: numbers written in words are read like the same numbers written in digits."""
import pytest

from chart_claim_verifier.agent.controller import ClaimController
from chart_claim_verifier.agent.policies import FixedOrderPolicy
from chart_claim_verifier.agent.report_agent import ReportAgent
from chart_claim_verifier.calibration.store import CalibrationTable
from chart_claim_verifier.claims.finder import is_candidate
from chart_claim_verifier.claims.number_words import words_to_digits
from chart_claim_verifier.claims.parser import RuleParser
from chart_claim_verifier.decide.rule import RuleConfig
from chart_claim_verifier.schemas import Report, Sentence


@pytest.mark.parametrize("text, expected", [
    ("ResNet-50 reaches ninety-one percent accuracy at epoch fourteen.", "ResNet-50 reaches 91 percent accuracy at epoch 14."),
    ("It reaches ninety-one point two percent.", "It reaches 91.2 percent."),
    ("Accuracy of seventy-eight point zero five percent.", "Accuracy of 78.05 percent."),
    ("The loss falls to zero point nine one at step fifty.", "The loss falls to 0.91 at step 50."),
    ("Accuracy improves by point five percent.", "Accuracy improves by 0.5 percent."),
    ("Ninety one per cent accuracy at epoch twenty.", "91 percent accuracy at epoch 20."),
    ("It is about twelve points better than VGG-16.", "It is about 12 points better than VGG-16."),
    ("One hundred and five runs reach 91%.", "105 runs reach 91%."),
    ("Two thousand five hundred steps.", "2500 steps."),
    ("The error rate is two percent lower at round seven.", "The error rate is 2 percent lower at round 7."),
    # decimals
    ("Accuracy reaches ninety-one point two five percent.", "Accuracy reaches 91.25 percent."),
    ("The loss falls to zero point zero five at epoch ten.", "The loss falls to 0.05 at epoch 10."),
    ("It gains three point five points over VGG-16.", "It gains 3.5 points over VGG-16."),
    ("Recall is point nine two at step two hundred.", "Recall is 0.92 at step 200."),
    ("Accuracy goes from eighty-five point five to ninety point two percent.",
     "Accuracy goes from 85.5 to 90.2 percent."),
    ("It improves by zero point three percentage points.", "It improves by 0.3 percentage points."),
    ("Precision reaches one point twenty-five times the baseline.", "Precision reaches 1.25 times the baseline."),
    ("Accuracy is seventy point oh five percent.", "Accuracy is 70.05 percent."),
    ("The loss is nought point five at epoch three.", "The loss is 0.5 at epoch 3."),
    # v4 cases
    ("It reaches a hundred percent at epoch thirty.", "It reaches 100 percent at epoch 30."),
    ("Accuracy rises from two to three percent.", "Accuracy rises from 2 to 3 percent."),
    ("Accuracy is ninety-one and a half percent.", "Accuracy is 91.5 percent."),
    ("The model, released in nineteen ninety-eight, reaches 91%.", "The model, released in 1998, reaches 91%."),
    ("It reaches ninety-one percent after ﬁve epochs.", "It reaches 91 percent after five epochs."),
])
def test_number_words_become_digits(text, expected):
    assert words_to_digits(text) == expected


@pytest.mark.parametrize("text", [
    "One of the models reaches 91% at epoch 3.",          # "one" is not a value here
    "Two models reach higher accuracy than BERT.",
    "Accuracy drops by roughly a third after epoch 10.",   # fractions stay text
    "ResNet-fifty reaches 91%.",                           # part of a name
    "It scores one two three on the benchmark.",           # not one number
    "At this point the loss is 0.57.",
    "At this point five models reach 91%.",                # "point five" here is not 0.5
    "Oh, the loss is 0.57 at epoch 3.",                    # "oh" is zero only after "point"
])
def test_ordinary_words_are_left_alone(text):
    assert words_to_digits(text) == text


@pytest.mark.parametrize("words, digits", [
    ("ResNet-50 reaches ninety-one percent accuracy at epoch fourteen.", "ResNet-50 reaches 91% accuracy at epoch 14."),
    ("ResNet-50 reaches ninety-one point two percent accuracy at epoch 14.", "ResNet-50 reaches 91.2% accuracy at epoch 14."),
    ("At epoch 14, ResNet-50 is about twelve points better than VGG-16.", "At epoch 14, ResNet-50 is about 12 points better than VGG-16."),
])
def test_same_claim_and_rounding_as_the_digit_version(words, digits):
    rp = RuleParser()
    a, b = rp.parse(words_to_digits(words), "w"), rp.parse(digits, "d")
    assert a is not None and b is not None
    for field in ("claim_type", "series", "x", "series_b", "claimed_value", "tolerance", "relation"):
        assert getattr(a, field) == getattr(b, field), field


def test_agent_reads_number_words_only_with_the_switch():
    text = "ResNet-50 reaches ninety-one percent accuracy at epoch fourteen."
    assert not is_candidate(text) and is_candidate(words_to_digits(text))
    report = Report(report_id="r", pdf_path="r.pdf", figures=[],
                    sentences=[Sentence(sentence_id="s1", report_id="r", text=text)])
    ctl = ClaimController({}, FixedOrderPolicy([]), CalibrationTable({}), RuleConfig())
    assert ReportAgent(RuleParser(), ctl).run(report)[0] == []               # off: no digit, so nothing to check
    traces = ReportAgent(RuleParser(), ctl, number_words=True).run(report)[0]
    assert len(traces) == 1
    assert traces[0].sentence == text                                         # the TA sees the original sentence
    assert traces[0].claim is not None and traces[0].claim.claimed_value == 91.0
    assert traces[0].claim.sentence == text
