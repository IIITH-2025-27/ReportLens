"""Which sentences are candidate chart claims?

A sentence qualifies if it contains a number (figure references removed) and a
result-like word. Setup sentences ("trained for 50 epochs") are skipped.
"""
from __future__ import annotations

import re

from .tolerance import find_numbers

FIG_REF = re.compile(r"\(?\b(?:Figure|Fig\.)\s*\d+(?:\s*\([a-h]\)|[a-h]\b)?\)?,?", re.I)   # v3: "Figure 3(b)", "Fig. 3b"
RESULT_WORDS = re.compile(
    r"\b(reach\w*|achiev\w*|obtain\w*|attain\w*|scor\w*|outperform\w*|beat\w*|lead\w*|ahead|exceed\w*|surpass\w*|better|worse|higher|lower|"
    r"improv\w*|drop\w*|decreas\w*|increas\w*|accuracy|loss|f1|precision|recall|error rate|peaks?|highest|maximum)\b", re.I)


def strip_figure_refs(text: str) -> str:
    return FIG_REF.sub("", text)


def figure_hint(text: str) -> int | None:
    m = re.search(r"\b(?:Figure|Fig\.)\s*(\d+)", text, re.I)
    return int(m.group(1)) if m else None


def panel_hint(text: str) -> str | None:
    """"Figure 3(b)" / "Fig. 3b" -> "b" (v3, B5)."""
    m = re.search(r"\b(?:Figure|Fig\.)\s*\d+\s*(?:\(([a-h])\)|([a-h])\b)", text, re.I)
    return (m.group(1) or m.group(2)).lower() if m else None


def is_candidate(sentence: str) -> bool:
    core = strip_figure_refs(sentence)
    return bool(find_numbers(core)) and bool(RESULT_WORDS.search(core))
