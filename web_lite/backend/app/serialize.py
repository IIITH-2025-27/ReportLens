"""Database rows -> what the frontend gets."""
from __future__ import annotations

from .models import ClaimResult, Report, VerificationRun


def run_brief(r: VerificationRun | None) -> dict | None:
    if r is None:
        return None
    return {"id": r.id, "report_id": r.report_id, "status": r.status, "error": r.error, "summary": r.summary,
            "created_at": r.created_at, "started_at": r.started_at, "finished_at": r.finished_at}


def claim(c: ClaimResult) -> dict:
    t = c.trace or {}
    d = t.get("decision") or {}
    return {"id": c.id, "position": c.position, "page": c.page, "sentence": c.sentence, "verdict": c.verdict,
            "figure_id": c.figure_id, "claimed_value": c.claimed_value, "estimate": c.estimate,
            "reason": c.reason, "tolerance": c.tolerance, "gap": c.gap, "margin_flag": c.margin_flag,
            "margin_accept": d.get("margin_accept"), "p_value": c.p_value,
            "claim": t.get("claim"), "tool_values": t.get("tool_values") or {},
            "readings": t.get("readings") or [], "stages": t.get("stages") or [],
            "calibration_group": d.get("calibration_group"), "n_readings": d.get("n_readings"),
            "tool_calls": t.get("tool_calls", 0)}


def run_full(r: VerificationRun) -> dict:
    out = run_brief(r)
    out["figures"] = {k: {x: v.get(x) for x in ("caption", "number", "chart_type", "page")} for k, v in (r.figures or {}).items()}
    out["claims"] = [claim(c) for c in r.claims]
    return out


def report_row(rp: Report) -> dict:
    last = rp.runs[-1] if rp.runs else None
    return {"id": rp.id, "filename": rp.filename, "size_bytes": rp.size_bytes, "uploaded_at": rp.uploaded_at,
            "runs": len(rp.runs),
            "latest_run": {"id": last.id, "status": last.status, "finished_at": last.finished_at,
                           "verdicts": (last.summary or {}).get("verdicts")} if last else None}


def report_detail(rp: Report) -> dict:
    out = report_row(rp)
    out["runs"] = [run_brief(r) for r in rp.runs]
    return out
