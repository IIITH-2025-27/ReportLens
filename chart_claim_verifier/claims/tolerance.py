"""Allowed rounding, computed from how a number is written (implementation.md §6.4).

The tolerance is never left to the LLM: it is a deterministic function of the
text, and the data generator labels claims with this same function.

    0.82                  -> ±0.005  (half of the last digit)
    82.4%                 -> ±0.05
    82%                   -> ±0.5
    about 80% / ~80%      -> ±5      (hedged, ends in 0)
    about 82%             -> ±1      (hedged: one unit of the last digit)
    over 80% / above 80%  -> one-sided, true value must be > 80
    between 85% and 90%   -> range (v3): 85 - 0.5 <= true <= 90 + 0.5
    0,912 / 1,000 / 3e-4 / 1.2k  -> read as 0.912 / 1000 / 0.0003 / 1200; the rounding scales with the exponent

v4 (16 Nov, real-world text; none of it occurs in the generated reports, so their labels do not change):
    −0.35 (LaTeX minus), 3.5 × 10−4 (exponent copied from a PDF), .35, 91.2 per cent, >90% / ≥ 90% / <1%
    about 1000 / about 50,000  -> up to 5% of the value (was ±5 whatever the size); "about 100" and below unchanged
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

HEDGES = ("approximately", "roughly", "around", "about", "nearly", "almost", "close to", "~", "≈", "≃", "circa")
GREATER = ("more than", "greater than", "at least", "over", "above", "exceeds", "exceeding", "no less than",
           ">", ">=", "≥", "in excess of")
LESS = ("less than", "fewer than", "at most", "under", "below", "up to", "not exceeding", "no more than",
        "<", "<=", "≤")

SUPERSCRIPT = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-"))
SPACES = "    "


def clean_chars(text: str) -> str:
    """Characters a PDF puts in numbers, mapped one-for-one (so every character position stays the same):
    the minus sign "−" (LaTeX math), non-breaking hyphens and spaces, an en dash used as a minus ("of –0.35"), and
    superscripts: after "10" they are an exponent ("10⁻⁴" -> "10-4"), elsewhere a footnote mark (-> space)."""
    out = list(text)
    for i, ch in enumerate(text):
        if ch == "−" or ch in "‐‑":
            out[i] = "-"
        elif ch in SPACES:
            out[i] = " "
        elif ch == "–" and i + 1 < len(text) and text[i + 1].isdigit() and (i == 0 or text[i - 1] in " (=:"):
            out[i] = "-"
        elif ch in SUPERSCRIPT:
            j = i
            while j > 0 and text[j - 1] in SUPERSCRIPT:
                j -= 1
            out[i] = SUPERSCRIPT[ch] if text[max(0, j - 2):j] == "10" else " "
    return "".join(out)

# How a number may be written (v3, A5). Alternatives in order:
#   0,912         decimal comma (a thousands group never starts with 0)
#   91,2%         decimal comma right before a percent sign
#   1,000 / 12,500.5   thousands separators
#   82 / 0.82     plain
# then an optional exponent (3e-4, 3 x 10^-4) and a multiplier glued to the number (1.2k, 25M, 7B).
# "10,20" stays two numbers, as before.
#   .35           v4: no leading zero
_MANTISSA = r"(?:0,\d+|\d+,\d{1,2}(?=\s*%)|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
# v4: "3.5 × 10-4" (a PDF loses the superscript but keeps the minus) and "3.5 · 10^-4"; "2 × 105" stays ambiguous
_EXPONENT = r"(?:[eE][-+]?\d+|\s?[x×·]\s?10(?:\^[-−]?\d+|[-−]\d+))"
NUM_TEXT = r"[-−]?" + _MANTISSA + _EXPONENT + "?" + r"[kKMB]?"
MULTIPLIER = {"": 1.0, "k": 1e3, "K": 1e3, "M": 1e6, "B": 1e9}

# The look-behind skips digits that belong to names: "ResNet-50", "CIFAR-10", "F1".
NUMBER_RE = re.compile(r"(?<![\w.\-])(?P<num>-?" + _MANTISSA + r")(?P<exp>" + _EXPONENT + r")?(?P<mult>[kKMB])?"
                       r"(?![\w\-])\s*(?P<pct>%|percent\b|per\s?cent\b)?")
RANGE_RE = re.compile(r"\bbetween\s+(?P<a>" + NUM_TEXT + r"\s*%?)\s+and\s+(?P<b>" + NUM_TEXT + r"\s*%?)", re.I)


@dataclass(frozen=True)
class NumberPhrase:
    value: float
    tolerance: float
    percent: bool
    relation: str          # "approx" | "greater" | "less"
    decimals: int
    hedged: bool
    start: int             # character span of the number in the sentence
    end: int


def normalise(num: str) -> str:
    """Mantissa as Python reads it: "0,912" -> "0.912", "91,2" -> "91.2", "1,000.5" -> "1000.5"."""
    neg = num.startswith("-")
    m = num.lstrip("-")
    if re.fullmatch(r"0,\d+|\d+,\d{1,2}", m):
        m = m.replace(",", ".")
    else:
        m = m.replace(",", "")
    return ("-" if neg else "") + m


def exponent_of(exp: str | None) -> int:
    return int(re.search(r"[-−+]?\d+$", exp.replace("^", "")).group().replace("−", "-")) if exp else 0


def scaled(num: str, e: int, mult: str | None) -> float:
    """num x 10^e x multiplier, computed from the written digits (3e-4 is 0.0003, not 0.00030000000000000003)."""
    return float(Decimal(num).scaleb(e) * Decimal(MULTIPLIER[mult or ""]))


def rounding_tolerance(num_str: str, hedged: bool) -> float:
    num_str = normalise(num_str)
    decimals = len(num_str.split(".")[1]) if "." in num_str else 0
    unit = 10.0 ** -decimals
    if not hedged:
        return 0.5 * unit
    integer = abs(int(float(num_str)))
    if decimals == 0 and integer >= 10 and integer % 10 == 0:
        if integer > 100:
            # v4: "about 1000 images/s" allowed only ±5 (0.5%), so 1040 was flagged. A hedged round number allows half
            # of its rounding unit, up to 5% of the value: about 1000 -> ±50, about 2500 -> ±50, about 50,000 -> ±2500.
            # 100 and below keep ±5 (every hedged claim of the generated reports is in this range).
            zeros = len(str(integer)) - len(str(integer).rstrip("0"))
            return max(5.0, min(0.5 * 10 ** zeros, 0.05 * integer))
        return 5.0
    return 1.0 * unit


_SYMBOLS = re.compile(r"(>=|<=|[~≈≃><≥≤])")


def _context_before(text: str, start: int, n_words: int = 3) -> str:
    words = _SYMBOLS.sub(r" \1 ", text[:start].lower()).split()
    return " " + " ".join(words[-n_words:]) + " "


def phrase_at(text: str, match: re.Match) -> NumberPhrase:
    num = normalise(match.group("num"))
    e, mult = exponent_of(match.group("exp")), match.group("mult")
    before = _context_before(text, match.start())
    hedged = any(f" {h} " in before for h in HEDGES)
    if any(f" {g} " in before for g in GREATER):
        relation = "greater"
    elif any(f" {l} " in before for l in LESS):
        relation = "less"
    else:
        relation = "approx"
    tol = 0.0 if relation != "approx" else scaled(str(rounding_tolerance(num, hedged)), e, mult)
    return NumberPhrase(
        value=scaled(num, e, mult),
        tolerance=tol,
        percent=bool(match.group("pct")),
        relation=relation,
        decimals=len(num.split(".")[1]) if "." in num else 0,
        hedged=hedged,
        start=match.start(),
        end=match.end(),
    )


def find_numbers(text: str) -> list[NumberPhrase]:
    text = clean_chars(text)              # one-for-one, so the spans still index the text as given
    return [phrase_at(text, m) for m in NUMBER_RE.finditer(text)]


@dataclass(frozen=True)
class RangePhrase:
    low: NumberPhrase
    high: NumberPhrase
    start: int
    end: int

    @property
    def percent(self) -> bool:
        return self.low.percent or self.high.percent

    @property
    def tolerance(self) -> float:          # the rounding of the bounds as written ("between 85 and 90" -> 0.5)
        return max(0.5 * 10.0 ** -self.low.decimals, 0.5 * 10.0 ** -self.high.decimals)


RANGE_DASH_RE = re.compile(r"(?<![\w.\-])(?P<a>\d+(?:\.\d+)?)\s?[-–]\s?(?P<b>\d+(?:\.\d+)?)\s?(?P<pct>%|percent\b)")


def _plain(text: str, m: re.Match, g: str, pct: bool) -> NumberPhrase:
    num = m.group(g)
    dec = len(num.split(".")[1]) if "." in num else 0
    return NumberPhrase(float(num), 0.5 * 10.0 ** -dec, pct, "approx", dec, False, m.start(g), m.end(g))


def find_range(text: str, dash: bool = False) -> RangePhrase | None:
    """'between 85% and 90%' (v3, A6): one claim with two bounds. v4 (`dash`): also "90-92%" / "90–92%" (the
    percent sign is required, so "epochs 5-10" is not a range)."""
    text = clean_chars(text)
    m = RANGE_RE.search(text)
    if not m and dash and (d := RANGE_DASH_RE.search(text)):
        low, high = sorted([_plain(text, d, "a", True), _plain(text, d, "b", True)], key=lambda n: n.value)
        return RangePhrase(low, high, d.start(), d.end())
    if not m:
        return None
    nums = [n for n in find_numbers(text) if m.start() <= n.start < m.end()]
    if len(nums) != 2:
        return None
    low, high = sorted(nums, key=lambda n: n.value)
    return RangePhrase(low, high, m.start(), m.end())


def is_within(claimed: float, true: float, tolerance: float, relation: str, high: float | None = None) -> bool:
    """Ground-truth check: is the claim correct given its allowed rounding?"""
    if relation == "greater":
        return true > claimed
    if relation == "less":
        return true < claimed
    if relation == "between":
        return claimed - tolerance - 1e-9 <= true <= (high if high is not None else claimed) + tolerance + 1e-9
    return abs(claimed - true) <= tolerance + 1e-9
