"""The report agent / planner (implementation.md §7.1).

    ingest -> memory -> find number sentences -> parse -> locate figure
    -> order claims so ones sharing a figure run together -> claim loop each

The batch check (BH across a whole assignment) and posting to the LMS happen
afterwards, in `finalize`, because BH needs every report of the batch.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Callable, Literal

from ..claims.number_words import words_to_digits
from ..claims.direction import alternative_values, negation, orient, percent_alternative
from ..claims.finder import is_candidate, strip_figure_refs
from ..ingest.pdf_parser import split_sentences
from ..claims.parser import ParseError
from ..claims.tolerance import find_numbers
from ..decide.rule import batch_check, decide
from ..ingest.pdf_parser import parse_pdf
from ..lms.guard import ActionGuard
from ..retrieval.figure_index import FigureIndex
from ..schemas import ClaimSpec, ClaimTrace, Decision, Figure, Report, Sentence
from .controller import ClaimController
from .events import emit
from .memory import ReportMemory
from .notes import add_conflicts, citation_note, explain_flag

RetrievalMode = Literal["ours", "nearest", "oracle"]
AMBIGUOUS_RULES = ("either", "top", "both", "never")


def ambiguous_accepts(rule: str, verdicts: list[str]) -> bool:
    """Two figures fit the sentence: may the claim be accepted? (Never flagged: one of the figures is the wrong one.)

    verdicts: the claim's verdict on each candidate figure, best-ranked first.
      either  accept if the claim matches either figure
      top     accept only if it matches the best-ranked figure
      both    accept only if it matches both
      never   always hand to the TA
    """
    ok = [v == "CONSISTENT" for v in verdicts]
    return {"either": any(ok), "top": bool(ok) and ok[0], "both": bool(ok) and all(ok), "never": False}[rule]


def _p_or_one(p: float | None) -> float:
    return 1.0 if p is None or p != p else p


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


class ReportAgent:
    """Runs every stage for one report and records WHY each decision was taken.

    Parse:   the rule parser first (cheap, exact); the LLM parser only when there is
             evidence the rules are not enough -- no known phrasing, or the parsed
             names appear in no figure (possible mis-parse).
    Figure:  explicit "Figure N", else best text match that really shows the series;
             two close candidates -> check both, never flag.
    Measure: the controller + policy (P3 decides from the measured tool profile).
    Decide:  the fixed rule.
    """

    def __init__(self, parser, controller: ClaimController, retrieval: RetrievalMode = "ours",
                 oracle: Callable[[str, str], str | None] | None = None, ref_bonus: float = 10.0,
                 vocab_match: int = 80, llm_parser=None, ambiguous_rule: str = "either", legend_reader=None,
                 hand_off_rejected: bool = False, cited_first: bool = False, ambiguity_ratio: float = 0.8,
                 check_captions: bool = False, hand_off_unsupported: bool = False, aliases: dict | None = None,
                 cross_chart: bool = False, equivalent_metrics: bool = False, number_words: bool = False,
                 more_phrasings: bool = False, directions: bool = False, ambiguous_percent: bool = False,
                 strict_names: bool = False, split_aware: bool = False, ambiguous_flag: str = "never"):
        if ambiguous_rule not in AMBIGUOUS_RULES:
            raise ValueError(f"unknown ambiguous_rule {ambiguous_rule!r}")
        if ambiguous_flag not in ("never", "both"):
            raise ValueError(f"unknown ambiguous_flag {ambiguous_flag!r}")
        self.ambiguous_rule = ambiguous_rule
        # v5: two figures fit the sentence and the claim is wrong on BOTH: wrong whichever figure is meant ("both"),
        # the mirror of ambiguous_rule "both" for accepts. "never" (the frozen behaviour): such a claim goes to the TA
        self.ambiguous_flag = ambiguous_flag
        self.parser, self.controller, self.retrieval = parser, controller, retrieval
        self.llm_parser = llm_parser    # escalation target; None = rules only
        self.oracle = oracle            # (report_id, sentence) -> true figure_id; ablation only
        self.ref_bonus, self.vocab_match = ref_bonus, vocab_match
        self.legend_reader = legend_reader  # fig -> legend names read by the VLM (U11b); None = OCR text only
        # v2: a sentence that looks like a claim but that the parser rejects goes to the TA instead of being dropped
        # (a hidden instruction made the LLM parser drop 8 real claims, E8)
        self.hand_off_rejected = hand_off_rejected
        self.cited_first, self.ambiguity_ratio = cited_first, ambiguity_ratio    # retrieval options, see FigureIndex
        # v3 switches (all off in the frozen configs)
        self.check_captions = check_captions              # A4: claims written in captions, checked on their own figure
        self.hand_off_unsupported = hand_off_unsupported  # B7: dual y-axes and chart kinds the tools cannot read -> TA
        self.aliases = {k.lower(): v for k, v in (aliases or {}).items()}   # B9: "RN50" -> "ResNet-50"
        self.cross_chart = cross_chart                    # B9: a difference whose two values sit on two figures
        self.equivalent_metrics = equivalent_metrics      # B9: an error-rate claim may be checked on an accuracy chart
        self.number_words = number_words                  # H23: "ninety-one percent" is read as "91 percent"
        # v4 switches (16 Nov, real-world reports; all off in the frozen configs)
        self.more_phrasings = more_phrasings              # more result words and figure citations ("Fig 3", AUC, ...)
        self.directions = directions                      # "decreases" / "lower than" signs; negated sentences -> TA
        self.ambiguous_percent = ambiguous_percent        # "improves by 12%": flag only if wrong as % AND as points
        self.strict_names, self.split_aware = strict_names, split_aware   # retrieval: see FigureIndex
        self.on_event = None                              # optional live activity feed (web app); see events.py

    def _emit(self, **event) -> None:
        emit(self.on_event, **event)

    def _emit_stages(self, entries: list[dict], sentence: str, detail: dict | None = None) -> None:
        for e in entries:
            self._emit(stage=e.get("stage"), text=str(e.get("decision")), why=e.get("why"), sentence=sentence,
                       detail=detail)

    def _emit_parsed(self, stages: list[dict], claims, used: str, sent) -> None:
        """The parse steps; a successful parse is reported with the claim it understood."""
        if not isinstance(claims, list):
            self._emit_stages(stages, sent.text)
            return
        primary = used == "rule"                  # the first parser succeeded and logged one entry for it
        self._emit_stages(stages[:-1] if primary else stages, sent.text)
        parser = "llm" if (self.parser.name == "llm" or not primary) else "rule"
        for c in claims:
            self._emit(stage="parse", text=f"understood a {c.claim_type} claim", sentence=sent.text,
                       why=stages[-1].get("why") if primary and stages else None,
                       detail={"parser": parser, "claim_type": c.claim_type, "series": c.series, "x": c.x,
                               "series_b": c.series_b, "x_b": c.x_b, "claimed": c.claimed_value,
                               "claimed_high": c.claimed_high, "unit": c.unit, "relation": c.relation,
                               "tolerance": c.tolerance, "figure_hint": c.figure_hint,
                               "operands": [list(o) for o in c.operands()]})

    def ingest(self, pdf_path: str | Path, work_dir: str | Path, report_id: str | None = None) -> Report:
        return parse_pdf(pdf_path, work_dir, report_id)

    # ------------------------------------------------------------------ planning
    def plan(self, mem: ReportMemory) -> dict:
        """Look at every figure once and decide which tools are worth using on it."""
        from .situation import observe
        policy = self.controller.policy
        for f in mem.report.figures:
            sit = observe(f)
            entry = {"situation": sit.key, "looks_like": sit.describe()}
            if hasattr(policy, "assess"):
                a = policy.assess(sit.key, list(self.controller.tools))
                entry["callable_tools"] = a["callable"]
                entry["skipped_tools"] = {t: (None if r is None else round(r, 2)) for t, r in a["skipped"].items()}
                entry["cross_check_pairs"] = a["good_pairs"]
            mem.plan[f.figure_id] = entry
        return mem.plan

    # ------------------------------------------------------------------ parse stage
    def _parse(self, sent, context: str, stages: list) -> tuple[object, str]:
        """Returns (list of claims | None | 'error', parser name). A sentence gives several claims only with the v3
        parser switches (claims.split_multi / claims.extremum); otherwise at most one, exactly as before."""
        multi = getattr(self.parser, "split_multi", False) or getattr(self.parser, "peaks", False)
        if multi:
            claims = self.parser.parse_all(sent.text, sent.sentence_id, context) or None
        else:
            one = self.parser.parse(sent.text, sent.sentence_id, context)
            claims = [one] if one is not None else None
        if claims is not None:
            claim = claims[0]
            if self.parser.name == "llm":
                stages.append({"stage": "parse", "decision": "LLM parser",
                               "why": f"the model read the sentence as a '{claim.claim_type}' claim"})
            else:
                kinds = " + ".join(c.claim_type for c in claims)
                stages.append({"stage": "parse", "decision": "rule parser",
                               "why": f"sentence matches a known '{kinds}' phrasing"
                               + (f" ({len(claims)} claims)" if len(claims) > 1 else "")})
            return claims, "rule"
        if self.llm_parser is None:
            stages.append({"stage": "parse", "decision": "not a chart claim",
                           "why": "the LLM parser found no checkable chart claim" if self.parser.name == "llm"
                           else "no known phrasing and no LLM parser available"})
            return None, self.parser.name
        stages.append({"stage": "parse", "decision": "escalate to LLM parser",
                       "why": "the sentence has a result-like number but no phrasing the rules know"})
        try:
            c = self.llm_parser.parse(sent.text, sent.sentence_id, context)
            return ([c] if c is not None else None), "llm"
        except ParseError:
            return "error", "llm"

    def _alias(self, claim: ClaimSpec, mem: ReportMemory, stages: list) -> ClaimSpec:
        """B9: a series written under another name ("RN50") that no figure shows, while its alias is shown."""
        if not self.aliases:
            return claim
        upd = {}
        for field in ("series", "series_b"):
            v = getattr(claim, field)
            target = self.aliases.get((v or "").lower())
            if target and not mem.index.shows(v) and mem.index.shows(target):
                upd[field] = target
        if upd:
            stages.append({"stage": "parse", "decision": "alias",
                           "why": "; ".join(f"read '{getattr(claim, k)}' as '{v}' (alias table)" for k, v in upd.items())})
            claim = claim.model_copy(update=upd)
        return claim

    def _caption_sentences(self, report: Report) -> list[Sentence]:
        """A4: sentences written in captions; each is about its own figure."""
        out = []
        for f in report.figures:
            for j, text in enumerate(split_sentences(f.caption)):
                out.append(Sentence(sentence_id=f"{report.report_id}_cap_{f.figure_id}_{j}", report_id=report.report_id,
                                    text=text, page=f.page, figure_id=f.figure_id))
        return out

    # ------------------------------------------------------------------ main loop
    def run(self, report: Report) -> tuple[list[ClaimTrace], ReportMemory]:
        mem = ReportMemory(report, FigureIndex(report.figures, self.ref_bonus, self.vocab_match,
                                                  legend_reader=self.legend_reader, cited_first=self.cited_first,
                                                  ambiguity_ratio=self.ambiguity_ratio,
                                                  equivalent_metrics=self.equivalent_metrics,
                                                  strict_names=self.strict_names, split_aware=self.split_aware))
        self.plan(mem)
        for fid, entry in mem.plan.items():
            tools = entry.get("callable_tools")
            f = mem.figure(fid)
            self._emit(stage="plan", text=f"{fid}: looks like {entry.get('looks_like')}",
                       why=("tools worth calling: " + (", ".join(tools) or "none")) if tools is not None else None,
                       detail={"figure": fid, "number": f.number, "panel": f.panel, "chart_type": f.chart_type,
                               "looks_like": entry.get("looks_like"), "callable": tools,
                               "skipped": entry.get("skipped_tools"), "pairs": entry.get("cross_check_pairs")})
        context = mem.context()
        planned, traces = [], []
        sentences = list(report.sentences) + (self._caption_sentences(report) if self.check_captions else [])
        for sent in sentences:
            original = sent.text
            if self.number_words:                          # H23: number words -> digits; the TA still sees the original
                converted = words_to_digits(sent.text)
                if converted != sent.text:
                    sent = sent.model_copy(update={"text": converted})
            if not find_numbers(strip_figure_refs(sent.text, self.more_phrasings)):
                continue                                   # no number: nothing to check
            base = dict(report_id=report.report_id, sentence_id=sent.sentence_id, sentence=original,
                        policy=self.controller.policy.name)
            if not is_candidate(sent.text, self.more_phrasings):
                self._emit(stage="parse", text="skip: not a result claim", sentence=sent.text)
                traces.append(ClaimTrace(**base, decision=Decision(verdict="SKIPPED", reason="not a result claim")))
                continue
            stages: list[dict] = []
            claims, used = self._parse(sent, context, stages)
            if isinstance(claims, list) and original != sent.text:
                claims = [c.model_copy(update={"sentence": original}) for c in claims]
            self._emit_parsed(stages, claims, used, sent)
            if claims == "error":
                traces.append(ClaimTrace(**base, stages=stages,
                                         decision=Decision(verdict="NOT_SURE", reason="could not parse")))
                self._emit(stage="decide", text="NOT_SURE", why="the language model could not parse the sentence",
                           sentence=sent.text, detail={"verdict": "NOT_SURE", "unparsed": True})
                continue
            if isinstance(claims, list) and self.directions:
                neg = negation(original)
                if neg:                                    # v4: only positive statements are verified
                    why = f"the sentence is negated ('{neg}'): the checker only verifies positive statements"
                    traces.append(ClaimTrace(**base, claim=claims[0], stages=stages + [
                        {"stage": "decide", "decision": "NOT_SURE", "why": why}],
                        decision=Decision(verdict="NOT_SURE", reason="handed off: " + why)))
                    self._emit(stage="decide", text="NOT_SURE", why=why, sentence=sent.text,
                               detail={"verdict": "NOT_SURE", "handed_off": True})
                    continue
                oriented = [orient(c, original) for c in claims]
                claims = [c for c, _ in oriented]
                for c, note in oriented:
                    if note:
                        stages.append({"stage": "parse", "decision": "direction", "why": note})
                        self._emit(stage="parse", text="direction read from the sentence", why=note,
                                   sentence=sent.text)
            if claims is None:
                verdict = "NOT_SURE" if self.hand_off_rejected else "SKIPPED"
                traces.append(ClaimTrace(**base, stages=stages,
                                         decision=Decision(verdict=verdict, reason="parser: not a chart claim")))
                self._emit(stage="decide", text=verdict, why="the parser found no chart claim in it", sentence=sent.text,
                           detail={"verdict": verdict, "rejected": True})
                continue
            for atom, claim in enumerate(claims):
                abase = {**base, "atom": atom}
                st = list(stages)
                claim = self._alias(claim, mem, st)
                op_figs = None
                if sent.figure_id:                         # a caption sentence: its own figure
                    figs, cands = [mem.figure(sent.figure_id)], []
                    st.append({"stage": "figure", "decision": sent.figure_id, "why": "the sentence is this figure's caption"})
                else:
                    figs, cands = self._locate(claim, sent, mem)
                if not figs and len(claims) == 1 and used == "rule" and self.llm_parser is not None \
                        and self.retrieval == "ours" and not sent.figure_id:
                    st.append({"stage": "figure", "decision": "re-parse with LLM",
                               "why": f"no figure shows '{claim.series}' at '{claim.x}': possibly a mis-parse"})
                    try:
                        again = self.llm_parser.parse(sent.text, sent.sentence_id, context)
                    except ParseError:
                        again = None
                    if again is not None:
                        figs2, cands2 = self._locate(again, sent, mem)
                        if figs2:
                            claim, figs, cands = again, figs2, cands2
                            self._emit_parsed([], [claim], "llm", sent)
                if not figs and self.cross_chart:
                    figs, op_figs = self._locate_across(claim, mem)
                    if figs:
                        st.append({"stage": "figure", "decision": " + ".join(f.figure_id for f in op_figs),
                                   "why": "each value of the claim is shown on a different figure"})
                if not figs:
                    st.append({"stage": "figure", "decision": "NO_FIGURE",
                               "why": f"no figure shows series '{claim.series}' at x '{claim.x}'"})
                    self._emit_stages(st[len(stages):], sent.text,
                                      {"chosen": [], "hint": claim.figure_hint,
                                       "candidates": [[c, round(float(v), 2)] for c, v in cands[:4]]})
                    note = citation_note(claim, None, report.figures)
                    traces.append(ClaimTrace(**abase, claim=claim, figure_candidates=cands, stages=st,
                                             notes=[note] if note else [],
                                             decision=Decision(verdict="NO_FIGURE", reason="no figure shows this series / x")))
                    continue
                if not sent.figure_id and op_figs is None:
                    st.append(self._figure_note(claim, figs, cands, mem))
                self._emit_stages(st[len(stages):], sent.text,
                                  {"chosen": [f.figure_id for f in (op_figs or figs)], "hint": claim.figure_hint,
                                   "candidates": [[c, round(float(v), 2)] for c, v in cands[:4]]})
                planned.append((figs[0].figure_id, len(planned), abase, claim, figs, cands, st, op_figs))

        mem.pending = Counter(p[0] for p in planned)       # claims waiting on each figure: shares a table tool's cost
        for fid0, _, base, claim, figs, cands, stages, op_figs in sorted(planned, key=lambda p: (p[0], p[1])):
            key = _norm(claim.sentence) + (f"#{base['atom']}" if base.get("atom") else "")
            if key in mem.checked:                         # duplicate sentence: same answer, no calls
                old = mem.checked[key]
                traces.append(old.model_copy(update={"sentence_id": base["sentence_id"], "tool_calls": 0}, deep=True))
                self._emit(stage="decide", text=old.decision.verdict, why="same sentence as an earlier one: answer reused, no calls",
                           sentence=claim.sentence, detail={"verdict": old.decision.verdict, "reused": True,
                                                            "claimed": claim.claimed_value, "estimate": old.decision.estimate})
                mem.pending[fid0] -= 1
                continue
            why_not = unsupported(figs[0]) if self.hand_off_unsupported else None
            if why_not:                                    # B7: the tools cannot read this kind of chart
                mem.pending[fid0] -= 1
                stages = stages + [{"stage": "decide", "decision": "NOT_SURE", "why": why_not}]
                self._emit_stages(stages[-1:], claim.sentence, {"verdict": "NOT_SURE", "handed_off": True,
                                                                 "figure": figs[0].figure_id})
                note = citation_note(claim, figs[0], report.figures)        # A1: also on a handed-off claim
                tr = ClaimTrace(**base, claim=claim, figure_id=figs[0].figure_id, figure_candidates=cands,
                                chart_type=figs[0].chart_type, y_span=figs[0].y_span, stages=stages,
                                notes=[note] if note else [],
                                decision=Decision(verdict="NOT_SURE", reason="handed off: " + why_not))
                mem.checked[key] = tr
                traces.append(tr)
                continue
            self._emit(stage="claim", text=f"check {claim.claim_type} claim on {' and '.join(f.figure_id for f in figs)}",
                       why=f"claimed {claim.claimed_value} for {claim.series} at {claim.x}", sentence=claim.sentence)
            runs = [(f, self.controller.run(claim, f, mem, op_figs if len(figs) == 1 else None)) for f in figs]
            mem.pending[fid0] -= 1
            fig, r = runs[0]
            figure_runs = {}
            if len(runs) > 1:
                # Two figures fit the sentence. Never flag; accept by the configured rule (agent.ambiguous_rule).
                figure_runs = {f.figure_id: {"verdict": x.decision.verdict, "estimate": x.decision.estimate,
                                             "gap": x.decision.gap, "margin_flag": x.decision.margin_flag}
                               for f, x in runs}
                if ambiguous_accepts(self.ambiguous_rule, [x.decision.verdict for _, x in runs]):
                    fig, r = next((f, x) for f, x in runs if x.decision.verdict == "CONSISTENT")
                elif self.ambiguous_flag == "both" and all(x.decision.verdict == "MISMATCH" for _, x in runs):
                    # the weaker of the two flags speaks for both: its p-value goes to the batch check
                    fig, r = max(runs, key=lambda p: _p_or_one(p[1].decision.p_value))
                    r.decision.reason = ("gap > rounding + flag margin on every figure that fits ("
                                         + ", ".join(f.figure_id for f, _ in runs) + ")")
                else:
                    r.decision.verdict = "NOT_SURE"
                    r.decision.reason = "ambiguous figure: " + ", ".join(f.figure_id for f, _ in runs)
                r.calls = sum(x.calls for _, x in runs)
            stages = stages + [{"stage": "measure",
                                "decision": (f"repair {s['action']['tool']} ({s['action']['repair']})"
                                             if s["action"]["action"] == "repair"
                                             else s["action"].get("tool") or s["action"]["action"]),
                                "why": s["action"].get("why", ""), "result": s.get("result")} for s in r.steps]
            alt_note = self._second_reading(claim, fig, r) if self.ambiguous_percent and len(runs) == 1 else None
            stages.append({"stage": "decide", "decision": r.decision.verdict, "why": r.decision.reason})
            d = r.decision
            self._emit_stages(stages[-1:], claim.sentence,
                              {"verdict": d.verdict, "claimed": claim.claimed_value, "claimed_high": claim.claimed_high,
                               "estimate": d.estimate, "gap": d.gap, "tolerance": claim.tolerance,
                               "margin_flag": d.margin_flag, "margin_accept": d.margin_accept,
                               "disagreement": d.disagreement, "n_readings": d.n_readings,
                               "tool_values": {k: round(v, 4) for k, v in r.tool_values.items()},
                               "unit": claim.unit, "claim_type": claim.claim_type, "figure": fig.figure_id})
            notes = list(r.notes) + ([alt_note] if alt_note else [])
            notes += [st["why"] for st in stages if st.get("decision") == "direction"]
            if op_figs is None:
                if (n := citation_note(claim, fig, report.figures)):
                    notes.append(n)
                if not r.notes and (n := explain_flag(claim, fig, r.decision, self.controller.tools, mem.tables_used)):
                    notes.append(n)
            tr = ClaimTrace(**base, claim=claim, figure_id=fig.figure_id, figure_candidates=cands,
                            chart_type=fig.chart_type, y_span=fig.y_span, tool_values=r.tool_values,
                            readings=r.readings, controller_steps=r.steps, decision=r.decision,
                            blocked_actions=r.blocked, tool_calls=r.calls, stages=stages, figure_runs=figure_runs,
                            notes=notes)
            mem.checked[key] = tr
            traces.append(tr)
        add_conflicts(traces)
        order = {s.sentence_id: i for i, s in enumerate(sentences)}
        return sorted(traces, key=lambda t: (order.get(t.sentence_id, len(order)), t.atom)), mem

    def _second_reading(self, claim: ClaimSpec, fig: Figure, r) -> str | None:
        """v4: "accuracy improves by 12%" may mean 12 points, "outperforms B by 3%" may mean 3% relative. A mismatch
        under the reading the parser chose is handed to the TA when the other reading fits (same readings, no calls)."""
        kind = percent_alternative(claim) if r.decision.verdict == "MISMATCH" else None
        if kind is None:
            return None
        ops = claim.operands()
        values = alternative_values(kind, r.readings, ops, list(r.tool_values))
        ctl = self.controller
        if len(values) < ctl.rc.min_readings:
            return None
        if kind == "points":
            alt = claim.model_copy(update={"claim_type": "difference", "unit": "pct_points", "series_b": claim.series,
                                           "x": claim.x_b, "x_b": claim.x})
            if claim.claimed_value < 0:                    # a fall: compare as minus the points
                values = {t: -v for t, v in values.items()}
                alt = alt.model_copy(update={"claimed_value": -claim.claimed_value})
        else:
            alt = claim.model_copy(update={"claim_type": "relative_change", "unit": "percent"})
        status, d = decide(alt, values, fig.chart_type, fig.y_span or 1.0, ctl.table, ctl.rc)
        if status != "CONSISTENT":
            return None
        other = "percentage points" if kind == "points" else "a relative change"
        note = (f"the % is ambiguous: wrong as {'a relative change' if kind == 'points' else 'percentage points'}, "
                f"but it matches as {other} (estimate {d.estimate:.3g})")
        r.decision.verdict = "NOT_SURE"
        r.decision.reason = "handed off: " + note
        return note

    @staticmethod
    def _figure_note(claim, figs, cands, mem) -> dict:
        if len(figs) > 1:
            return {"stage": "figure", "decision": "check both " + " and ".join(f.figure_id for f in figs),
                    "why": "two figures show this series with similar text-match scores"}
        f = figs[0]
        if claim.figure_hint is not None and f.number == claim.figure_hint:
            why = f"the sentence names Figure {claim.figure_hint}"
            if (f.figure_id, claim.series) in mem.index.rescued:
                why += "; " + mem.index.rescued[(f.figure_id, claim.series)] + ", so the tools must find the series"
        else:
            why = f"best text match that shows '{claim.series}' (scores {cands[:3]})"
            if (f.figure_id, claim.series) in mem.index.rescued:
                why = f"{mem.index.rescued[(f.figure_id, claim.series)]} (scores {cands[:3]})"
        plan = mem.plan.get(f.figure_id, {})
        if plan:
            why += f"; chart looks like: {plan.get('looks_like')}"
        return {"stage": "figure", "decision": f.figure_id, "why": why}

    def _locate(self, claim, sent, mem: ReportMemory):
        if self.retrieval == "oracle" and self.oracle:
            fid = self.oracle(sent.report_id, sent.text)
            return ([mem.figure(fid)] if fid else []), []
        if self.retrieval == "nearest":
            f = mem.figure(sent.nearest_figure_id) if sent.nearest_figure_id else None
            return ([f] if f else []), []
        return mem.index.locate(claim)

    def _locate_across(self, claim: ClaimSpec, mem: ReportMemory) -> tuple[list[Figure], list[Figure] | None]:
        """B9: a difference whose two values are on two different figures of the same kind. Each value must have
        exactly one figure, and the two axes must be alike (same chart family, spans within 1.5x)."""
        if claim.claim_type != "difference":
            return [], None
        found = []
        for s, x in claim.operands():
            one = claim.model_copy(update={"claim_type": "point", "series": s, "x": x, "series_b": None,
                                           "x_b": None, "figure_hint": None})
            figs, _ = mem.index.locate(one)
            if len(figs) != 1:
                return [], None
            found.append(figs[0])
        a, b = found
        fam = lambda f: "line" if f.chart_type == "line" else "bar"
        if a.figure_id == b.figure_id or fam(a) != fam(b) or not a.y_span or not b.y_span \
                or max(a.y_span, b.y_span) > 1.5 * min(a.y_span, b.y_span):
            return [], None
        return [a], [a, b]


def unsupported(fig: Figure) -> str | None:
    """B7: why the tools cannot read this chart, or None."""
    if "dual_y" in fig.flags:
        return "the chart has two y-axes, and which series belongs to which axis is not known"
    if "axis_multiplier" in fig.flags:
        # v4: "1e-5" / "+1e3" above the axis; the readers report the tick labels (7.0 for 7e-05)
        return "the y-axis has a multiplier above it (like 1e-5 or +1e3) that the reading tools ignore"
    kinds = [f.split(":", 1)[1] for f in fig.flags if f.startswith("unsupported:")]
    if kinds:
        return f"{kinds[0]} charts are not supported by the reading tools"
    if "scanned" in fig.flags and not fig.y_span:
        # C5: on a scanned page whose chart axis could not be read, the margins have no axis range to scale with
        # (and a % claim cannot be told from a 0-1 axis); on the v3feat scans every wrong flag was on such a chart
        return "the chart comes from a scanned page and its y-axis could not be read, so the reading error has no scale"
    return None


def finalize(traces: list[ClaimTrace], guard: ActionGuard | None, alpha: float = 0.10,
             use_batch_check: bool = True) -> list[ClaimTrace]:
    """Batch check across the assignment, then post MISMATCH / NOT_SURE to the TA review list."""
    out = batch_check(traces, alpha) if use_batch_check else traces
    if guard is not None:
        for t in out:
            for forbidden in t.blocked_actions:              # LLM attempts are routed through the guard
                guard.execute(forbidden, caller="llm_controller", report_id=t.report_id)
            if t.decision.verdict in ("MISMATCH", "NOT_SURE"):
                guard.execute("post_flag", caller="decision_rule", report_id=t.report_id,
                              claim_id=t.sentence_id, verdict=t.decision.verdict, evidence=evidence_card(t))
    return out


def evidence_card(t: ClaimTrace) -> dict:
    """What the TA sees next to a flag."""
    d = t.decision
    return {"sentence": t.sentence, "figure": t.figure_id,
            "claimed": t.claim.claimed_value if t.claim else None,
            "allowed_rounding": t.claim.tolerance if t.claim else None,
            "readings": {k: round(v, 4) for k, v in t.tool_values.items()},
            "estimate": d.estimate, "error_margin": d.margin_flag, "p_value": d.p_value, "why": d.reason,
            "notes": list(t.notes)}
