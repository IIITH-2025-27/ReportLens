"""Put a claim and its chart on the same footing before deciding (v3).

Each function looks at the claim and the figure and returns how to transform the TOOLS' values (and, for log axes,
the claim) so both speak the same units. Nothing is guessed silently: every transform returns a note for the TA.

  unit_scale         A5: a % claim on a 0-1 axis (readings x100), a fraction on a 0-100 axis (readings /100)
  metric_transform   B9: an error-rate claim on an accuracy chart (readings -> 100 - reading)
  log_transform      B4: a point claim on a log axis is compared in log10 units, where reading error is constant
"""
from __future__ import annotations

import math
import re

from ..schemas import ClaimSpec, Figure

ACCURACY_LIKE = re.compile(r"\b(?:accurac\w*|precision|recall|f1|score)\b", re.I)
ERROR_WORDS = re.compile(r"\berror(?: rate)?\b", re.I)


def unit_scale(claim: ClaimSpec, fig: Figure) -> tuple[float, str | None]:
    """Factor that turns the chart's numbers into the claim's units (1.0 = same units)."""
    span = fig.y_span
    if not span or claim.claim_type not in ("point", "difference"):
        return 1.0, None
    pct = claim.unit in ("percent", "pct_points")
    v = abs(claim.claimed_value if claim.claimed_high is None else claim.claimed_high)
    if pct and span <= 1.5 and v > 1.5:
        return 100.0, "the chart's axis is in fractions (0-1) and the claim in percent: readings x100 before comparing"
    if (not pct and claim.claim_type == "point" and 0 < v <= 1.0 and span >= 10
            and ACCURACY_LIKE.search(claim.sentence)):
        return 0.01, "the chart's axis is in percent and the claim is a fraction: readings /100 before comparing"
    return 1.0, None


def says_error(claim: ClaimSpec) -> bool:
    return bool(ERROR_WORDS.search(claim.sentence)) and not ACCURACY_LIKE.search(claim.sentence)


def metric_transform(claim: ClaimSpec, fig: Figure, scale: float = 1.0):
    """(function on a tool value, note) when the claim is about the error rate and the chart shows accuracy."""
    shown = " ".join([fig.caption] + fig.text_lines).lower()
    if not says_error(claim) or "error" in shown or "accurac" not in shown:
        return None, None
    if claim.claim_type == "point":
        full = 100.0 if (fig.y_span or 0) * scale > 1.5 else 1.0
        return (lambda v: full - v), f"the claim is an error rate and the chart shows accuracy: compared as {full:g} - accuracy"
    if claim.claim_type == "difference":
        return (lambda v: -v), "the claim is an error-rate difference and the chart shows accuracy: compared as minus the accuracy difference"
    return None, None


def log_transform(claim: ClaimSpec, fig: Figure) -> tuple[ClaimSpec | None, str | None]:
    """The claim in log10 units for a log-scale axis; (None, reason) when it cannot be compared there."""
    if "log_y" not in fig.flags:
        return claim, None
    if claim.claim_type != "point" or claim.claimed_value <= 0:
        return None, "log-scale axis: only a positive value at one point can be checked there"

    def lg(v: float) -> float:
        return math.log10(v)
    c, tol = claim.claimed_value, claim.tolerance
    tol_log = max(lg(c + tol) - lg(c), lg(c) - lg(c - tol)) if 0 < tol < c else (0.0 if tol == 0 else lg(c + tol) - lg(c))
    new = claim.model_copy(update={"claimed_value": lg(c), "tolerance": tol_log,
                                   "claimed_high": lg(claim.claimed_high) if claim.claimed_high else None})
    return new, "log-scale axis: claim and readings compared in log10 units"
