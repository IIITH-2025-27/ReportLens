"""Numbers written in words (v3, H23): "ninety-one percent" -> "91 percent" before a sentence is checked.

The claim finder, both parsers and the rounding rules (claims.tolerance) read numbers only when they are written in
digits, so a sentence like "ResNet-50 reaches ninety-one percent accuracy at epoch fourteen" was never checked. This
module rewrites number words as digits, and everything downstream stays the same. A number in words is read exactly
as the same number in digits: "ninety-one percent" allows the same +-0.5 as "91%", "ninety-one point two" the same
+-0.05 as "91.2", and "about twelve points" is hedged like "about 12 points".

    ninety-one percent          -> 91 percent
    Ninety one per cent         -> 91 percent
    ninety-one point two        -> 91.2
    zero point nine one         -> 0.91
    point five percent          -> 0.5 percent
    one hundred and five        -> 105
    two thousand five hundred   -> 2500
    at epoch fourteen / five    -> at epoch 14 / 5
    twelve points better        -> 12 points better
    one of the models           -> unchanged (a small number on its own is usually not a value)
    drops by a third            -> unchanged (fractions stay text and go to the TA if they cannot be parsed)

Small numbers (zero to nine, with no decimal part) are rewritten only next to a unit ("percent", "points") or after
an x-axis word ("epoch", "step", ...), because "one", "two", ... are common in ordinary text. A word glued to a name
("ResNet-fifty") is left alone.

v4 (16 Nov), found by feeding real-world sentences:
    at this point five models   -> unchanged (was "at this 0.5 models": a leading "point" needs a unit after it or a
                                   word like "by" / "of" / "to" before it)
    a hundred percent           -> 100 percent
    one point twenty-five       -> 1.25 (was "1 point 25")
    nineteen ninety-eight       -> 1998 (was "19 98"); two numbers side by side that are not a year stay words
    two to three percent        -> 2 to 3 percent
    ninety-one and a half       -> 91.5
    ﬁve (a PDF ligature)        -> five
    seventy point oh five       -> 70.05 ("oh" is read as zero only after "point")
    nought point five           -> 0.5
"""
from __future__ import annotations

import re

UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
         "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
SCALES = {"hundred": 100, "thousand": 1000}
NUMBER_WORDS = set(UNITS) | set(TEENS) | set(TENS) | set(SCALES) | {"point", "and"}

# a run of number words joined by spaces or hyphens ("ninety-one point two", "one hundred and five")
_WORD = r"(?:" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")"
RUN_RE = re.compile(r"\b" + _WORD + r"(?:(?:\s+|-)" + _WORD + r")*\b", re.I)
UNIT_AFTER = re.compile(r"\s*(?:%|per\s?cent\b|percent\b|percentage\b|points?\b|pp\b)", re.I)
X_WORD_BEFORE = re.compile(r"\b(?:epochs?|steps?|iterations?|rounds?|layers?)\s+$", re.I)


def _int_value(words: list[str]) -> int | None:
    """Value of a whole number written in words, or None if the words do not form one ("one two", "twenty thirty")."""
    if not words or words[0] in ("and", "hundred", "thousand"):
        return None
    total, current, last = 0, 0, None        # last: kind of the previous word, to reject impossible orders
    for w in words:
        if w in UNITS:
            if last in ("unit", "teen") or (last == "tens" and UNITS[w] == 0):
                return None
            current += UNITS[w]
            last = "unit"
        elif w in TEENS:
            if last in ("unit", "teen", "tens"):
                return None
            current += TEENS[w]
            last = "teen"
        elif w in TENS:
            if last in ("unit", "teen", "tens") or current % 100:
                return None
            current += TENS[w]
            last = "tens"
        elif w == "hundred":
            if not 0 < current < 10 or last == "hundred":
                return None
            current *= 100
            last = "hundred"
        elif w == "thousand":
            if not 0 < current < 1000 or last == "thousand":
                return None
            total += current * 1000
            current = 0
            last = "thousand"
        elif w == "and":
            if last not in ("hundred", "thousand"):
                return None
            last = "and"
        else:
            return None
    if last == "and":
        return None
    return total + current


def _fraction(frac: list[str]) -> str | None:
    """Digits after "point": "two" -> "2", "zero five" -> "05", v4: "twenty-five" -> "25"."""
    if frac and all(w in UNITS for w in frac):
        return "".join(str(UNITS[w]) for w in frac)
    v = _int_value(frac) if frac else None
    return str(v) if v is not None and 10 <= v < 100 else None


def _convert(words: list[str]) -> tuple[str, int] | None:
    """Digits for the longest prefix of `words` that is one number, and how many words it used."""
    for n in range(len(words), 0, -1):
        part = words[:n]
        if "point" in part:
            k = part.index("point")
            whole, frac = part[:k], part[k + 1:]
            digits = _fraction(frac)
            if digits is None:
                continue
            int_part = _int_value(whole) if whole else 0
            if int_part is None:
                continue
            return f"{int_part}." + digits, n
        value = _int_value(part)
        if value is not None:
            return str(value), n
    return None


LIGATURES = {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl"}
VALUE_WORD_BEFORE = re.compile(r"\b(?:by|of|to|is|was|at|reaches|reached|about|around|roughly|nearly|only|just|"
                               r"from|than|under|over|below|above)\s+$", re.I)
YEAR_FIRST = {"nineteen", "twenty"}


def words_to_digits(text: str) -> str:
    """The sentence with its number words rewritten as digits (see the module docstring for what is and is not)."""
    for lig, plain in LIGATURES.items():
        text = text.replace(lig, plain)
    text = re.sub(r"\ba (hundred|thousand)\b", r"one \1", text, flags=re.I)
    # spoken zero: "seventy point oh five" -> 70.05, "nought point five" -> 0.5 ("oh" counts only after "point")
    text = re.sub(r"\bn(?:ou|au)ght(?=\s+point\b)", "zero", text, flags=re.I)
    digit = r"(?:zero|one|two|three|four|five|six|seven|eight|nine)"
    while True:
        new = re.sub(rf"(\bpoint(?:\s+{digit})*)\s+(?:oh|n(?:ou|au)ght)\b", r"\1 zero", text, flags=re.I)
        if new == text:
            break
        text = new
    out, pos = [], 0
    for m in RUN_RE.finditer(text):
        span_words = re.split(r"\s+|-", m.group(0))
        lower = [w.lower() for w in span_words]
        # inside a name ("ResNet-fifty"): leave it
        if m.start() >= 2 and text[m.start() - 1] == "-" and text[m.start() - 2].isalnum():
            continue
        i, cursor, pieces = 0, m.start(), []
        spans = [(w.start() + m.start(), w.end() + m.start()) for w in re.finditer(r"[A-Za-z]+", m.group(0))]
        while i < len(lower):
            conv = _convert(lower[i:])
            if conv is None:
                i += 1
                continue
            digits, used = conv
            # character span of words i .. i+used-1 inside the match
            start, end = spans[i][0], spans[i + used - 1][1]
            small = "." not in digits and int(digits) < 10
            if small and not (UNIT_AFTER.match(text, end) or X_WORD_BEFORE.search(text[:start])):
                i += used
                continue
            # v4: "at this point five models": a number that starts with "point" needs a unit after it or a word
            # like "by" / "of" before it
            if lower[i] == "point" and not (UNIT_AFTER.match(text, end) or VALUE_WORD_BEFORE.search(text[:start])):
                i += used
                continue
            pieces.append((start, end, digits, lower[i]))
            i += used
        pieces = _join_or_drop_neighbours(text, pieces)
        for start, end, digits, _ in pieces:
            out.append(text[pos:start])
            out.append(digits)
            pos = end
    out.append(text[pos:])
    result = "".join(out)
    result = re.sub(r"\b(\d+(?:\.\d+)?)(\s*)per\s+cent\b", r"\1\2percent", result, flags=re.I)
    # v4: "91 and a half percent" -> 91.5; "two to 3 percent" -> "2 to 3 percent"
    result = re.sub(r"\b(\d+) and a half\b", r"\1.5", result)
    small = "|".join(k for k in UNITS)
    return re.sub(rf"\b({small})(\s+(?:to|or|-)\s+\d+(?:\.\d+)?\s*(?:%|percent|points?)\b)",
                  lambda mm: str(UNITS[mm.group(1).lower()]) + mm.group(2), result, flags=re.I)


def _join_or_drop_neighbours(text: str, pieces: list) -> list:
    """Two numbers side by side ("nineteen ninety-eight") are one year, or else not a value: never "19 98"."""
    out, k = [], 0
    while k < len(pieces):
        cur = pieces[k]
        nxt = pieces[k + 1] if k + 1 < len(pieces) else None
        if nxt is not None and re.fullmatch(r"[\s-]*", text[cur[1]:nxt[0]]) and "." not in cur[2] + nxt[2]:
            if cur[3] in YEAR_FIRST and 10 <= int(cur[2]) <= 20 and 0 <= int(nxt[2]) <= 99:
                out.append((cur[0], nxt[1], f"{int(cur[2])}{int(nxt[2]):02d}", cur[3]))
            k += 2                                         # not a year: leave both as words
            continue
        out.append(cur)
        k += 1
    return out
