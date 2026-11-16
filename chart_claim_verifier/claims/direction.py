"""Which way a claim points, and whether it is negated (v4, switch claims.directions).

The parsers copy the number exactly as written, and a number is written without a sign: "the loss decreases by 40%"
gave the claim +40, the chart gave -40, and a true sentence was flagged. The LLM's form has no field for the
direction at all, so even a perfect answer lost it. Here the direction is read from the sentence's own words, by
rules, after either parser (the model still never decides a number):

    relative change   increases / grows / rises            -> +       decreases / drops / falls / declines -> -
                      improves (accuracy-like metric)      -> +       improves (loss, error, perplexity)   -> -
    difference        "A is 6.2 points lower than B", "A trails B by 6.2 points"  ->  B - A = 6.2
                      "A outperforms B by 6.2 points"                              ->  A - B = 6.2
                      (for a loss, "A beats B by 0.1" means A's loss is lower: B - A = 0.1)

A negated sentence ("does not reach 91%", "never exceeds 90%") is not checked: the rule only verifies positive
statements, so it goes to the TA (`negation`).

`percent_alternative` covers the other way a % can be meant: "accuracy improves by 12%" is often 12 percentage
points, and "outperforms B by 3%" is sometimes 3% relative. The agent flags such a claim only if it is wrong under
both readings.
"""
from __future__ import annotations

import re

from ..schemas import ClaimSpec

NEGATION = re.compile(r"\b(not|never|no longer|cannot|can't|isn't|wasn't|aren't|weren't|doesn't|didn't|don't|won't|"
                      r"hasn't|haven't|hadn't|fails? to|failed to|neither|nor|hardly|barely)\b", re.I)
NOT_NEGATION = re.compile(r"\b(not only|not surprisingly|whether or not|if not|not shown|not plotted)\b", re.I)

LOWER_IS_BETTER = re.compile(r"\b(loss\w*|error\w*|perplexity|rmse|mae|mse|wer|cer|latency|runtime|inference time|"
                             r"training time|time per epoch)\b", re.I)
_UP = r"increas\w*|grow\w*|grew|ris(?:e|es|ing)|rose|climb\w*|goes up|went up|jump\w*|gain\w*"
_DOWN = r"decreas\w*|drop\w*|falls?|fell|falling|declin\w*|reduc\w*|shrink\w*|shrank|goes down|went down|dips?|dipped"
_GOOD = r"improv\w*|gets? better|got better"
_BAD = r"worsen\w*|degrad\w*|deteriorat\w*|gets? worse|got worse"
CHANGE_WORDS = re.compile(rf"\b(?:(?P<up>{_UP})|(?P<down>{_DOWN})|(?P<good>{_GOOD})|(?P<bad>{_BAD}))\b", re.I)

# comparing two values: of the VALUE ("higher", "lower") or of the QUALITY ("outperforms", "trails")
# ("more than" / "less than" / "above" are left out: they usually bound the number, "more than 3 points higher")
COMPARE_WORDS = re.compile(
    r"\b(?:(?P<vup>higher|greater|larger)|(?P<vdown>lower|smaller)|"
    r"(?P<qup>outperform\w*|beats?|beat|surpass\w*|exceed\w*|leads?|led|ahead of|better|wins? over)|"
    r"(?P<qdown>trails?|trailed|lags?|lagged|behind|worse|underperform\w*|falls? short of|fell short of))\b", re.I)


def negation(sentence: str) -> str | None:
    """The negation word if the sentence is negated, else None."""
    text = NOT_NEGATION.sub(" ", sentence)
    m = NEGATION.search(text)
    return m.group(0) if m else None


def lower_is_better(sentence: str) -> bool:
    return bool(LOWER_IS_BETTER.search(sentence)) and not re.search(r"\b(accurac\w*|f1|precision|recall|bleu|auc)\b",
                                                                   sentence, re.I)


def _negated_claim(claim: ClaimSpec) -> ClaimSpec:
    """The same claim with its value(s) negated: "drops by more than 40%" = change < -40."""
    flip = {"greater": "less", "less": "greater"}.get(claim.relation, claim.relation)
    if claim.claimed_high is not None:
        return claim.model_copy(update={"claimed_value": -claim.claimed_high, "claimed_high": -claim.claimed_value,
                                        "relation": flip})
    return claim.model_copy(update={"claimed_value": -claim.claimed_value, "relation": flip})


def _position(sentence: str, name: str | None, is_x: bool = False) -> int:
    """Where a series name (or, `is_x`, an x value) is mentioned. Figure references are blanked first, and an x value
    must follow "on / at / epoch / for / in / than", so the "4" of "about 4 points" or "Figure 2" is not taken for x."""
    if not name:
        return -1
    from .finder import FIG_REF_V4
    text = FIG_REF_V4.sub(lambda m: " " * len(m.group(0)), sentence).lower()
    key = re.escape(name.lower())
    pat = (rf"\b(?:on|at|epoch|for|in|to|from|than)\s+(?:epoch\s+)?(?:the\s+)?{key}(?![\w\-])" if is_x
           else rf"(?<![\w\-]){key}(?![\w\-])")
    m = re.search(pat, text)
    if m:
        return m.start()
    if is_x:
        return -1
    from rapidfuzz import fuzz
    al = fuzz.partial_ratio_alignment(name.lower(), text)
    return al.dest_start if al is not None and al.score >= 80 else -1


def orient(claim: ClaimSpec, sentence: str) -> tuple[ClaimSpec, str | None]:
    """The claim with its direction taken from the sentence's words, and a note for the TA when it changed."""
    s = sentence
    if claim.claim_type == "relative_change":
        if claim.claimed_value < 0:                       # the sign was written ("changes by -12%"): keep it
            return claim, None
        m = None
        for m in CHANGE_WORDS.finditer(s):                 # the last change word wins ("rises, then drops by 5%")
            pass
        if m is None:
            return claim, None
        down = bool(m.group("down")) or (bool(m.group("good")) and lower_is_better(s)) or \
            (bool(m.group("bad")) and not lower_is_better(s))
        if not down:
            return claim, None
        word = m.group(0)
        return _negated_claim(claim), f"'{word}' read as a fall: the claim is a change of {-claim.claimed_value:g}%"
    if claim.claim_type == "difference":
        m = COMPARE_WORDS.search(s)
        if m is None:
            return claim, None
        down = bool(m.group("vdown")) or (bool(m.group("qup")) and lower_is_better(s)) or \
            (bool(m.group("qdown")) and not lower_is_better(s))
        if claim.series_b and claim.series_b != claim.series:
            a, b, field_a, field_b = claim.series, claim.series_b, "series", "series_b"
        elif claim.x_b and claim.x_b != claim.x:
            a, b, field_a, field_b = claim.x, claim.x_b, "x", "x_b"
        else:
            return claim, None
        pa, pb = _position(s, a, field_a == "x"), _position(s, b, field_a == "x")
        if pa < 0 or pb < 0:
            return claim, None
        subject, other = (a, b) if pa <= pb else (b, a)
        # the claim is always "first minus second = the number as written (positive)"
        first, second = (other, subject) if down else (subject, other)
        if (first, second) == (a, b):
            return claim, None
        note = f"'{m.group(0)}': compared as {first} minus {second}"
        return claim.model_copy(update={field_a: first, field_b: second}), note
    return claim, None


def percent_alternative(claim: ClaimSpec) -> str | None:
    """The other reading of a % in a change claim: "points" for a relative change written without "relative",
    "relative" for a difference written with % instead of "points". None when the sentence is unambiguous."""
    s = claim.sentence.lower()
    if claim.claim_type == "relative_change" and claim.unit == "percent" and not re.search(r"relativ|times\b", s):
        return "points"
    if claim.claim_type == "difference" and re.search(r"%|\bper ?cent\b", s) \
            and not re.search(r"\bpoints?\b|\bpp\b|percentage", s):
        return "relative"
    return None


def alternative_values(kind: str, readings: list, operands: list[tuple[str, str]], tools: list[str]) -> dict:
    """Each tool's value for the other reading, from the readings it already made (no new calls)."""
    out = {}
    for t in tools:
        vals = []
        for s, x in operands:
            got = [r.value for r in readings if r.tool == t and r.ok and r.query and r.query.series == s
                   and r.query.x == x]
            if not got:
                break
            vals.append(got[-1])
        if len(vals) != 2:
            continue
        a, b = vals
        if kind == "points":                              # relative change claim: a at x, b at x_b -> b - a
            out[t] = b - a
        elif kind == "relative" and abs(b) > 1e-9:        # difference claim: (a - b) / |b| in %
            out[t] = (a - b) / abs(b) * 100.0
    return out
