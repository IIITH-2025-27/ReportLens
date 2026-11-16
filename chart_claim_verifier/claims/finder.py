"""Which sentences are candidate chart claims?

A sentence qualifies if it contains a number (figure references removed) and a
result-like word. Setup sentences ("trained for 50 epochs") are skipped.

v4 (`extended=True`, switch claims.more_phrasings): more result words (past tense verbs, "hits", "converges to",
metrics such as AUC, BLEU, mAP, RMSE, perplexity) and more ways of citing a figure ("Fig 3", "FIGURE 3",
"Figs. 2 and 3", "Figure 3 (left)"). Without the switch everything is exactly as before.
"""
from __future__ import annotations

import re

from .tolerance import find_numbers

FIG_REF = re.compile(r"\(?\b(?:Figure|Fig\.)\s*\d+(?:\s*\([a-h]\)|[a-h]\b)?\)?,?", re.I)   # v3: "Figure 3(b)", "Fig. 3b"
RESULT_WORDS = re.compile(
    r"\b(reach\w*|achiev\w*|obtain\w*|attain\w*|scor\w*|outperform\w*|beat\w*|lead\w*|ahead|exceed\w*|surpass\w*|better|worse|higher|lower|"
    r"improv\w*|drop\w*|decreas\w*|increas\w*|accuracy|loss|f1|precision|recall|error rate|peaks?|highest|maximum)\b", re.I)

# v4: "Fig 3", "FIGURE 3", "Figs. 2 and 3", "Figure 3 (left)", "Fig. 3(b)"
FIG_REF_V4 = re.compile(r"\(?\b(?:Figures?|Figs?\.?)\s*\d+(?:\s*\([a-h]\)|[a-h]\b)?"
                        r"(?:\s*(?:and|,|&|-|–)\s*\d+(?:\s*\([a-h]\)|[a-h]\b)?)*"
                        r"(?:\s*\((?:left|right|top|bottom|middle|centre|center|upper|lower)[^)]*\))?\)?,?", re.I)
# verbs only with the preposition that makes them a result ("stands at 91%", not "stands for"), so ordinary setup
# sentences do not become candidates (with agent.hand_off_rejected each candidate the parsers reject goes to the TA)
RESULT_WORDS_V4 = re.compile(
    r"\b(hits?|converg\w*|plateau\w*|(?:stands?|stood|sits?|sat|ends?|ended|settles?|settled|levels? off) at|tops? out|"
    r"topped out|(?:climbs?|climbed|rises?|rose|falls?|fell|goes up|goes down|went up|went down|jumps?|jumped) (?:to|by)|"
    r"declin\w*|trails?|trailed|lags? behind|lagged behind|gains?|gained|yield\w*|record\w*|deliver\w*|"
    r"auc|roc-auc|bleu|rouge(?:-\w+)?|iou|dice|rmse|mae|mse|wer|cer|perplexity|error(?!\s+bars?)|top-?[15]|"
    r"(?:at|after|by) epoch \d+)\b", re.I)                    # "... of 0.00056 at epoch 10": a value read off a curve
CASED_METRICS = re.compile(r"\b(mAP|AP50|AP|mIoU)\b")       # case matters: "map" / "ap" are ordinary words


def strip_figure_refs(text: str, extended: bool = False) -> str:
    return (FIG_REF_V4 if extended else FIG_REF).sub("", text)


def figure_hint(text: str, extended: bool = False) -> int | None:
    pat = r"\b(?:Figures?|Figs?\.?)\s*(\d+)" if extended else r"\b(?:Figure|Fig\.)\s*(\d+)"
    m = re.search(pat, text, re.I)
    return int(m.group(1)) if m else None


def panel_hint(text: str, extended: bool = False) -> str | None:
    """"Figure 3(b)" / "Fig. 3b" -> "b" (v3, B5)."""
    pat = (r"\b(?:Figures?|Figs?\.?)\s*\d+\s*(?:\(([a-h])\)|([a-h])\b)" if extended
           else r"\b(?:Figure|Fig\.)\s*\d+\s*(?:\(([a-h])\)|([a-h])\b)")
    m = re.search(pat, text, re.I)
    return (m.group(1) or m.group(2)).lower() if m else None


def is_candidate(sentence: str, extended: bool = False) -> bool:
    core = strip_figure_refs(sentence, extended)
    if not find_numbers(core):
        return False
    if RESULT_WORDS.search(core):
        return True
    return extended and bool(RESULT_WORDS_V4.search(core) or CASED_METRICS.search(core))
