"""The claim loop (implementation.md §5.2, §7.1).

    Measure -> Combine -> Decide -> (clear: stop) / (unclear: controller picks next tool)

At least `min_readings` readings before any decision; at most `max_tool_calls`
logical tool calls per claim. A table tool costs one call per figure per
report (later lookups come from memory); a point tool costs one call per value.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..calibration.store import CalibrationTable
from ..decide.rule import RuleConfig, decide
from ..measure.aggregate import tool_value
from ..claims.units import log_transform, metric_transform, unit_scale
from ..schemas import ClaimSpec, Decision, Figure, PointQuery, Reading
from ..models.vlm import OfflineMiss
from ..tools.base import TableTool, Tool, ToolError, interpolate, lookup, match_name
from .events import emit
from .memory import ReportMemory
from .policies import Policy


@dataclass
class ClaimResult:
    status: str
    decision: Decision
    tool_values: dict[str, float] = field(default_factory=dict)
    readings: list[Reading] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    calls: int = 0
    blocked: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)       # tool -> failure code seen on THIS claim
    notes: list[str] = field(default_factory=list)             # v3: unit / metric / log transforms, for the TA card


class ClaimController:
    def __init__(self, tools: dict[str, Tool], policy: Policy, table: CalibrationTable, rc: RuleConfig,
                 max_tool_calls: int = 8, profile: dict | None = None, repairs: dict | None = None,
                 options: dict | None = None):
        self.tools, self.policy, self.table, self.rc, self.max_calls = tools, policy, table, rc, max_tool_calls
        # v3 switches, all off in the frozen configs: unit_convert (A5), equivalent_metrics (B9), log_values (B4)
        self.options = options or {}
        self.profile = profile            # measured tool performance (evaluation/tool_profile.py)
        self.repairs = repairs or {}      # name -> fn(fig, tool) -> truthy if the cause of a failure was fixed (U7)
        self.on_event = None              # optional live activity feed (web app); never changes a decision

    def _emit(self, **event) -> None:
        emit(self.on_event, **event)

    def _seconds(self, name: str, n_operands: int) -> float:
        """Measured cost of one call (falls back to the tool's own estimate)."""
        c = (self.profile or {}).get("cost", {}).get(name) or {}
        if isinstance(self.tools[name], TableTool):
            return c.get("seconds_per_figure") or self.tools[name].cost
        return (c.get("seconds_per_read") or self.tools[name].cost) * n_operands

    def _state(self, claim: ClaimSpec, fig: Figure, res: ClaimResult, mem: ReportMemory, tried: set[str],
               last: Decision | None, situation=None) -> dict:
        series = [s for s, _ in claim.operands()]
        scopes = (self.profile or {}).get("failure_scope") or {}
        blocked = {t: c for t in self.tools if t not in tried
                   and (c := mem.blocked(t, fig.figure_id, series, scopes.get(t) or {})) is not None}
        available = [t for t in self.tools if t not in tried and t not in blocked]
        if claim.claim_type == "peak":          # "x is the highest point" needs the whole series: table tools only
            available = [t for t in available if isinstance(self.tools[t], TableTool)]
        free = [t for t in available if (t, fig.figure_id) in mem.tables_used]
        n_ops = len(claim.operands())
        # a table tool is paid once per figure: share its cost among the claims still waiting on this figure
        waiting = max(1, mem.pending.get(fig.figure_id, 1))
        shared = {t: waiting for t in available if isinstance(self.tools[t], TableTool) and t not in free and waiting > 1}
        state = {
            "claim": claim.sentence, "chart_type": fig.chart_type,
            "readings": [{"tool": t, "value": round(v, 4)} for t, v in res.tool_values.items()],
            "failed_here": sorted({t for (t, f, _, _) in mem.failures if f == fig.figure_id}),
            "blocked": blocked, "shared_by": shared,
            "failed_now": dict(res.failed), "can_repair": list(self.repairs),
            "repairs": (self.profile or {}).get("repairs") or {},
            "repaired": sorted(f"{t}:{r}" for (t, f, r) in mem.repaired if f == fig.figure_id),
            "available": available, "all_tools": list(self.tools), "cached_for_free": free,
            "costs": {t: (0.0 if t in free else round(self._seconds(t, n_ops) / shared.get(t, 1), 2)) for t in available},
            "calls_left": self.max_calls - res.calls,
        }
        from .situation import x_on_tick
        state["x_on_tick"] = x_on_tick(fig, [x for _, x in claim.operands()])
        if situation is not None:
            state["situation"] = situation.key
            state["situation_text"] = situation.describe()
            if self.profile:
                sit = self.profile["situations"].get(situation.key) or self.profile["situations"].get("*", {})
                state["evidence"] = {t: {k: (round(v, 4) if isinstance(v, float) else v)
                                         for k, v in (sit.get(t) or {}).items() if k != "top_failures"}
                                     for t in available}
        if last is not None and last.gap is not None:
            state["gap_vs_margins"] = (f"{last.verdict.lower()} (gap {last.gap:.3g}, rounding {claim.tolerance:.3g}, "
                                       f"accept <= {claim.tolerance + last.margin_accept:.3g}, "
                                       f"flag > {claim.tolerance + last.margin_flag:.3g})")
        return state

    def _cost(self, name: str, fig: Figure, n_operands: int, mem: ReportMemory, op_figs: list[Figure] | None = None) -> int:
        tool = self.tools[name]
        if isinstance(tool, TableTool):
            figs = {f.figure_id for f in (op_figs or [fig])}
            return sum((name, f) not in mem.tables_used for f in figs)
        return n_operands

    def _transforms(self, claim: ClaimSpec, fig: Figure):
        """(claim to decide on, value function, span, notes) -- or (None, reason) when the claim cannot be compared."""
        notes, scale, fn, dclaim, span = [], 1.0, None, claim, fig.y_span or 1.0
        if self.options.get("unit_convert"):
            scale, note = unit_scale(claim, fig)
            notes += [note] if note else []
        if self.options.get("equivalent_metrics"):
            fn, note = metric_transform(claim, fig, scale)
            notes += [note] if note else []
        log = bool(self.options.get("log_values") and "log_y" in fig.flags)
        if log:
            dclaim, note = log_transform(claim, fig)
            if dclaim is None:
                return None, note
            notes.append(note)
            lo, hi = (fig.y_range or [None, None])
            span = math.log10(hi) - math.log10(lo) if lo and hi and lo > 0 and hi > lo else 1.0
        else:
            span *= scale

        def value(v: float) -> float | None:
            v = v * scale
            v = fn(v) if fn else v
            if log:
                return math.log10(v) if v > 0 else None
            return v
        return (dclaim, value, span, notes), None

    def run(self, claim: ClaimSpec, fig: Figure, mem: ReportMemory, op_figs: list[Figure] | None = None) -> ClaimResult:
        """Measure one claim on `fig`. `op_figs` (v3, B9): one figure per operand, for a claim across two figures."""
        from .situation import observe
        res = ClaimResult(status="TOO_FEW", decision=Decision(verdict="NOT_SURE", reason="no readings"))
        tried: set[str] = set()
        last: Decision | None = None
        ops = claim.operands()
        op_figs = op_figs or [fig] * len(ops)
        situation = observe(fig)
        prepared, why_not = self._transforms(claim, fig)
        if prepared is None:
            res.decision.reason = "handed off: " + why_not
            res.notes.append(why_not)
            self._emit(stage="stop", text="hand off to the TA", why=why_not, sentence=claim.sentence)
            return res
        dclaim, convert, span, res.notes = prepared

        while True:
            state = self._state(claim, fig, res, mem, tried, last, situation)
            if not state["available"]:
                break
            action = self.policy.next_action(state)
            step = {"available": state["available"], "readings_so_far": len(res.tool_values), "action": action}
            res.steps.append(step)
            if action.get("forbidden"):
                res.blocked.append(action["forbidden"])
            if action["action"] == "repair":
                tool_name, rep = action["tool"], action["repair"]
                if (tool_name, fig.figure_id, rep) in mem.repaired or rep not in self.repairs or res.calls + 1 > self.max_calls:
                    step["skipped"] = "repair not possible"
                    self._emit(stage="stop", text="stop: repair not possible", sentence=claim.sentence)
                    break
                mem.repaired.add((tool_name, fig.figure_id, rep))
                res.calls += 1
                mem.calls["repair:" + rep] += 1
                label = f"repair {tool_name} with {rep} on {fig.figure_id}"
                self._emit(stage="repair", status="start", text=label, why=action.get("why"), tool=tool_name,
                           sentence=claim.sentence)
                fixed = self.repairs[rep](fig, self.tools[tool_name])
                step["result"] = "repaired" if fixed else "error: repair gave nothing"
                self._emit(stage="repair", status="ok" if fixed else "error", text=label, tool=tool_name,
                           why=step["result"], sentence=claim.sentence)
                if fixed:
                    codes = {k.split(":", 1)[1] for k, v in ((self.profile or {}).get("repairs") or {}).items()
                             if k.startswith(tool_name + ":") and v.get("repair") == rep}
                    mem.lift(tool_name, fig.figure_id, codes)
                    tried.discard(tool_name)
                    res.failed.pop(tool_name, None)
                continue
            if action["action"] != "read":
                if action.get("why"):
                    res.decision.reason = "handed off: " + action["why"]
                if (self.options.get("interpolation_error") and self.policy.stops_early
                        and len({f.figure_id for f in op_figs}) == 1
                        and self._interpolated_pair(claim, fig, dclaim, convert, span, res, mem)):
                    break
                self._emit(stage="stop", text=f"stop reading ({action['action']})", why=action.get("why"),
                           sentence=claim.sentence)
                break
            name = action["tool"]
            cost = self._cost(name, fig, len(ops), mem, op_figs)
            if res.calls + cost > self.max_calls:
                step["skipped"] = "over budget"
                self._emit(stage="stop", text=f"stop: {name} would go over the call budget",
                           why=f"{res.calls} of {self.max_calls} calls used, {name} costs {cost}", sentence=claim.sentence)
                break
            tried.add(name)
            tool = self.tools[name]
            label = f"{name} on {' + '.join(sorted({f.figure_id for f in op_figs}))}: " + \
                ", ".join(f"{s} @ {x}" for s, x in ops)
            self._emit(stage="tool", status="start", text=label, why=action.get("why"), tool=name,
                       sentence=claim.sentence,
                       detail={"figures": sorted({f.figure_id for f in op_figs}), "operands": [list(o) for o in ops],
                               "cost": cost, "calls_used": res.calls, "budget": self.max_calls,
                               "claim_type": claim.claim_type})
            reads = [tool.read(f, PointQuery(series=s, x=x)) for (s, x), f in zip(ops, op_figs)]

            def finished(status: str, label=label, name=name, step=step, reads=reads) -> None:
                r = step.get("result")
                shown = f"read {r}" if isinstance(r, (int, float)) else str(r)
                if step.get("status"):
                    shown += f" -> {step['status']} after {len(res.tool_values)} reading(s)"
                self._emit(stage="tool", status=status, text=label, why=shown, tool=name, sentence=claim.sentence,
                           detail={"value": r if isinstance(r, (int, float)) else None,
                                   "raw": [x.value for x in reads], "cached": all(x.cached for x in reads),
                                   "seconds": round(sum(x.latency_s for x in reads), 2),
                                   "error": None if isinstance(r, (int, float)) else str(r).removeprefix("error: "),
                                   "readings": len(res.tool_values), "status": step.get("status"),
                                   "claim_type": claim.claim_type})

            res.readings.extend(reads)
            res.calls += cost
            mem.calls[name] += cost
            if isinstance(tool, TableTool):
                for f in {f.figure_id for f in op_figs}:
                    if (name, f) in mem.tables_used:
                        mem.calls_saved += 1
                    mem.tables_used.add((name, f))
            bad = [r for r in reads if not r.ok]
            if bad:
                for r in bad:
                    mem.note_failure(name, fig.figure_id, r.query.series if r.query else "", r.error or "error")
                res.failed[name] = bad[0].error or "error"
                step["result"] = f"error: {bad[0].error}"
                finished("error")
                continue
            if claim.claim_type == "peak":
                try:
                    v = peak_value(tool, fig, claim.series, claim.x)
                except ToolError as e:
                    mem.note_failure(name, fig.figure_id, claim.series, e.code)
                    res.failed[name] = e.code
                    step["result"] = f"error: {e.code}"
                    finished("error")
                    continue
            else:
                v = tool_value(claim.claim_type, [r.value for r in reads], self.rc.drop_tied_legs)
            if v is None:
                tied = len(reads) == 2 and reads[0].value == reads[1].value
                step["result"] = "error: tied legs (both legs read as the same number)" if tied \
                    else "error: derived value undefined"
                finished("error")
                continue
            v = convert(v)
            if v is None:
                step["result"] = "error: not a positive value on a log axis"
                finished("error")
                continue
            res.tool_values[name] = v
            step["result"] = round(v, 4)
            if len(res.tool_values) >= self.rc.min_readings:
                res.status, last = decide(dclaim, res.tool_values, fig.chart_type, span, self.table, self.rc)
                res.decision = last
                step["status"] = res.status
            finished("ok")
            if len(res.tool_values) >= self.rc.min_readings:
                if self.policy.stops_early and res.status in ("CONSISTENT", "MISMATCH_CANDIDATE"):
                    break

        if not self.policy.stops_early and len(res.tool_values) >= self.rc.min_readings:
            res.status, res.decision = decide(dclaim, res.tool_values, fig.chart_type, span, self.table, self.rc)
        if (self.options.get("no_flag_without_axis") and res.status == "MISMATCH_CANDIDATE"
                and not all(f.y_span for f in op_figs)):
            # v4: without a readable y-axis the margin has no scale (span falls back to 1.0, so two tools that agree
            # on a rounded value flag a true claim). In every run so far, 31 of 231 such flags were wrong (13%, vs
            # 2.8% with a readable axis), so a mismatch there goes to the TA; an accept still stands.
            why = "the chart's y-axis could not be read, so a mismatch has no scale to be judged against"
            res.status = "UNCLEAR"
            res.decision.verdict = "NOT_SURE"
            res.decision.reason = "handed off: " + why
            res.notes.append(why)
            self._emit(stage="stop", text="hand off to the TA", why=why, sentence=claim.sentence)
        if res.status in ("UNCLEAR", "TOO_FEW"):
            res.decision.verdict = "NOT_SURE"
            if res.status == "TOO_FEW" and not res.decision.reason.startswith("handed off"):
                res.decision.reason = f"only {len(res.tool_values)} successful reading(s)"
        return res


    def _interpolated_pair(self, claim: ClaimSpec, fig: Figure, dclaim: ClaimSpec, convert, span: float,
                           res: ClaimResult, mem: ReportMemory) -> bool:
        """v5 (agent.interpolation_error): the last step before a hand-off on a line chart, when no tool has given a
        value. If an x has no tick label, DePlot's values at the labelled x on either side are joined by a straight line
        and paired with vlm_crop's direct reading. Measured on the calibration charts (scripts/analysis/
        interp_fallback.py): the bend of the curve between two ticks puts the straight line off by up to
        `interpolation_error` of the axis (95th percentile), so a mismatch must clear the flag margin by that much too
        (half of it after averaging with vlm_crop). Accepts use the ordinary rule. True if a decision was made."""
        frac = float(self.options["interpolation_error"])
        dp, crop = self.tools.get("deplot"), self.tools.get("vlm_crop")
        if (dp is None or crop is None or fig.chart_type != "line" or res.tool_values or claim.claim_type == "peak"
                or not isinstance(dp, TableTool)):
            return False
        ops = claim.operands()
        table_cost = self._cost("deplot", fig, len(ops), mem)
        if res.calls + table_cost + len(ops) > self.max_calls:
            return False
        try:
            tab = dp.table(fig)
        except ToolError:
            return False
        except OfflineMiss:                    # replay without the model: counted like any other offline miss
            res.readings.append(Reading(tool=dp.name, value=None, ok=False, error="offline_miss", latency_s=0.0,
                                        cached=False, query=PointQuery(series=ops[0][0], x=ops[0][1])))
            return False
        values, joined = [], []
        for s, x in ops:
            try:
                values.append(lookup(tab, s, x))
                joined.append(None)
            except ToolError as e:
                hit = interpolate(tab, s, x) if e.code == "x_not_found" else None
                if hit is None:
                    return False
                values.append(hit[0])
                joined.append(hit)
        if all(j is None for j in joined):     # nothing to interpolate: the planner had its reasons for this pair
            return False
        res.calls += table_cost
        mem.calls["deplot"] += table_cost
        mem.tables_used.add(("deplot", fig.figure_id))
        how = "; ".join(f"x = {x} has no tick label, so DePlot's values at {j[1]} and {j[2]} were joined by a straight "
                        f"line ({j[0]:.4g})" for (_, x), j in zip(ops, joined) if j)
        start = {"figures": [fig.figure_id], "operands": [list(o) for o in ops], "calls_used": res.calls,
                 "budget": self.max_calls, "claim_type": claim.claim_type}
        self._emit(stage="tool", status="start", text=f"deplot on {fig.figure_id} (interpolated)", tool="deplot",
                   why=how, sentence=claim.sentence, detail={**start, "cost": table_cost})
        d_val = tool_value(claim.claim_type, values, self.rc.drop_tied_legs)
        d_val = convert(d_val) if d_val is not None else None
        self._emit(stage="tool", status="ok" if d_val is not None else "error", tool="deplot",
                   text=f"deplot on {fig.figure_id} (interpolated)", sentence=claim.sentence,
                   why=f"read {round(d_val, 4)}" if d_val is not None else "derived value undefined",
                   detail={"value": d_val, "raw": values, "cached": True, "interpolated": True,
                           "claim_type": claim.claim_type})
        res.steps.append({"available": ["deplot", "vlm_crop"], "readings_so_far": 0,
                          "action": {"action": "read", "tool": "deplot", "why": "last step before a hand-off: " + how},
                          "result": round(d_val, 4) if d_val is not None else "error: derived value undefined"})
        if d_val is None:
            return False

        self._emit(stage="tool", status="start", text=f"vlm_crop on {fig.figure_id}", tool="vlm_crop",
                   why="the cross-check for the interpolated DePlot value", sentence=claim.sentence,
                   detail={**start, "cost": len(ops), "calls_used": res.calls})
        reads = [crop.read(fig, PointQuery(series=s, x=x)) for s, x in ops]
        res.readings.extend(reads)
        res.calls += len(ops)
        mem.calls["vlm_crop"] += len(ops)
        c_val = None
        if all(r.ok for r in reads):
            c_val = tool_value(claim.claim_type, [r.value for r in reads], self.rc.drop_tied_legs)
            c_val = convert(c_val) if c_val is not None else None
        res.steps.append({"available": ["vlm_crop"], "readings_so_far": 1,
                          "action": {"action": "read", "tool": "vlm_crop",
                                     "why": "the cross-check for the interpolated DePlot value"},
                          "result": round(c_val, 4) if c_val is not None else
                          f"error: {next((r.error for r in reads if not r.ok), 'derived value undefined')}"})
        if c_val is None:
            self._emit(stage="tool", status="error", text=f"vlm_crop on {fig.figure_id}", tool="vlm_crop",
                       why=res.steps[-1]["result"], sentence=claim.sentence)
            return False

        res.tool_values = {"deplot": d_val, "vlm_crop": c_val}
        status, dec = decide(dclaim, res.tool_values, fig.chart_type, span, self.table, self.rc)
        allow, unit = 0.0, (fig.y_span or 1.0) * frac
        for i, j in enumerate(joined):         # how far the bend could move this claim's value, then halved by averaging
            if j is None:
                continue
            for sign in (-1, 1):
                moved = list(values)
                moved[i] += sign * unit
                v = tool_value(claim.claim_type, moved, self.rc.drop_tied_legs)
                v = convert(v) if v is not None else None
                if v is not None:
                    allow = max(allow, abs(v - d_val) / 2)
        if status == "MISMATCH_CANDIDATE" and dec.gap <= dclaim.tolerance + dec.margin_flag + allow:
            status = "UNCLEAR"
            dec.verdict = "NOT_SURE"
            dec.reason = (f"between the margins once the interpolation error is allowed for (flag only beyond "
                          f"{dclaim.tolerance + dec.margin_flag + allow:.3g})")
        elif status == "MISMATCH_CANDIDATE":
            dec.reason += f" (also beyond the interpolation allowance of {allow:.3g})"
        res.status, res.decision = status, dec
        res.steps[-1]["status"] = status
        res.notes.append(how + "; checked against vlm_crop")
        self._emit(stage="tool", status="ok", text=f"vlm_crop on {fig.figure_id}", tool="vlm_crop",
                   why=f"read {round(c_val, 4)} -> {status} after 2 reading(s)", sentence=claim.sentence,
                   detail={"value": c_val, "raw": [r.value for r in reads], "cached": all(r.cached for r in reads),
                           "seconds": round(sum(r.latency_s for r in reads), 2), "readings": 2, "status": status,
                           "claim_type": claim.claim_type})
        return True


def _same_x(a: str, b: str) -> bool:
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return a.strip().lower() == b.strip().lower()


def peak_value(tool, fig: Figure, series: str, x: str) -> float:
    """One table tool's value at x minus its highest value elsewhere in the series (v3, B3). Positive: x is the peak.
    Uses the tool's table, already read for the value at x, so it costs no new call."""
    tab = tool.table(fig)
    at = lookup(tab, series, x)
    name = match_name(series, list(tab)) or (next(iter(tab)) if len(tab) == 1 else None)
    others = [v for k, v in tab[name].items() if not _same_x(k, x)]
    if len(others) < 2:
        raise ToolError("too_few_points")
    return at - max(others)
