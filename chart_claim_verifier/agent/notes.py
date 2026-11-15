"""Extra lines for the TA's evidence card (v3, A1-A3). They explain a verdict; they never change one.

  citation_note    A1: the sentence cites "Figure N" but the claim was measured on another figure (or N does not exist)
  explain_flag     A3: a flagged value matches another series / x in a table the tools already read (a likely mix-up)
  add_conflicts    A2: two sentences give different values for the same point of the same figure
"""
from __future__ import annotations

import re
from collections import defaultdict
from itertools import combinations

from ..schemas import ClaimSpec, ClaimTrace, Decision, Figure
from ..tools.base import TableTool, match_name


def _same_x(a: str, b: str) -> bool:
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return a.strip().lower() == b.strip().lower()


def _name(f: Figure) -> str:
    return f"Figure {f.number}{f.panel or ''}" if f.number else f.figure_id


def citation_note(claim: ClaimSpec, fig: Figure | None, figures: list[Figure]) -> str | None:
    """The sentence names a figure other than the one the claim was checked on."""
    hint = claim.figure_hint
    if hint is None:
        return None
    cited = [f for f in figures if f.number == hint]
    if fig is None:
        if not cited:
            return f"The sentence cites Figure {hint}, but the report has no Figure {hint}."
        # not "the citation is wrong": on the six splits every such case was an OCR misread of the cited figure
        return (f"No figure was found for this claim, but the sentence names Figure {hint}: the text read from it does "
                f"not show '{claim.series}' at '{claim.x}' (its legend or labels may be misread). Check Figure {hint}.")
    if fig.number == hint and (claim.panel_hint is None or fig.panel in (None, claim.panel_hint)):
        return None
    where = (f"the report has no Figure {hint}" if not cited else f"Figure {hint} does not show '{claim.series}'")
    return (f"The sentence cites Figure {hint}{claim.panel_hint or ''}, but the claim was checked on {_name(fig)}, "
            f"the figure that shows '{claim.series}' ({where}). The citation may be wrong.")


def explain_flag(claim: ClaimSpec, fig: Figure, decision: Decision, tools: dict, paid: set) -> str | None:
    """For a flagged point claim: does the claimed number match another series or x in a table already read?

    Uses only tables the tools have already read for this figure (`paid` = mem.tables_used), so it costs no call.
    A match needs to be within the claim's rounding plus the accept margin, and closer than the claim's own point.
    """
    if claim.claim_type != "point" or decision.verdict != "MISMATCH" or decision.gap is None:
        return None
    tol = claim.tolerance + (decision.margin_accept or 0.0)
    found: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    owns: set = set()                         # each table's name for the claim's own series ("Accuracy (%)" if only one)
    for name, tool in tools.items():
        if not isinstance(tool, TableTool) or (name, fig.figure_id) not in paid:
            continue
        tab = tool.known_table(fig)                  # already read: from memory or the reading cache, no new call
        if tab is None:
            continue
        own = match_name(claim.series, list(tab)) or (next(iter(tab)) if len(tab) == 1 else None)
        owns.add(own)
        for s, row in tab.items():
            for x, v in row.items():
                if s == own and _same_x(x, claim.x):
                    continue
                d = abs(v - claim.claimed_value)
                if d <= tol and d < decision.gap:
                    found[(s, x)].append((name, v))
    if not found:
        return None
    (s, x), hits = max(found.items(), key=lambda kv: (len(kv[1]), -min(abs(v - claim.claimed_value) for _, v in kv[1])))
    own_s = s in owns or s.lower() == claim.series.lower() or match_name(claim.series, [s]) is not None
    kind = "x value" if own_s else "series"
    reads = ", ".join(f"{t} reads {v:g}" for t, v in hits)
    return (f"The claimed {claim.claimed_value:g} matches {claim.series if own_s else s} at {x} ({reads}): "
            f"possibly a mix-up of {kind}.")


def _ops_key(c: ClaimSpec) -> tuple:
    norm = lambda s: re.sub(r"\s+", " ", (s or "").strip().lower())
    return (c.claim_type,) + tuple((norm(s), norm(x)) for s, x in c.operands())


def add_conflicts(traces: list[ClaimTrace]) -> None:
    """Two sentences state different values for the same point of the same figure: at most one can be right."""
    groups: dict[tuple, list[ClaimTrace]] = defaultdict(list)
    for t in traces:
        c = t.claim
        if c is None or not t.figure_id or c.relation != "approx" or c.claim_type == "peak" \
                or t.decision.verdict in ("NO_FIGURE", "SKIPPED"):
            continue
        groups[(t.figure_id,) + _ops_key(c)].append(t)
    for ts in groups.values():
        for a, b in combinations(ts, 2):
            if abs(a.claim.claimed_value - b.claim.claimed_value) > a.claim.tolerance + b.claim.tolerance + 1e-9:
                a.notes.append(f"Another sentence gives {b.claim.claimed_value:g} for the same point: \"{b.sentence[:90]}\"")
                b.notes.append(f"Another sentence gives {a.claim.claimed_value:g} for the same point: \"{a.sentence[:90]}\"")
