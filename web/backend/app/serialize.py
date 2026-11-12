"""Database rows -> what the frontend gets. Students never receive verifier output directly:
they see the TA's review and the claims the TA confirmed."""
from __future__ import annotations

from datetime import datetime, timezone

from .models import Assignment, ClaimResult, Course, ReportVersion, Review, Submission, User, VerificationRun

OPEN = ("submitted", "verifying", "verified")          # waiting on the TA


def user(u: User) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role}


def run_brief(r: VerificationRun | None) -> dict | None:
    if r is None:
        return None
    return {"id": r.id, "status": r.status, "error": r.error, "summary": r.summary,
            "created_at": r.created_at, "started_at": r.started_at, "finished_at": r.finished_at}


def claim(c: ClaimResult, full: bool = True) -> dict:
    out = {"id": c.id, "position": c.position, "page": c.page, "sentence": c.sentence, "verdict": c.verdict,
           "figure_id": c.figure_id, "claimed_value": c.claimed_value, "estimate": c.estimate,
           "ta_decision": c.ta_decision, "ta_note": c.ta_note}
    if full:
        t = c.trace or {}
        out.update({"reason": c.reason, "tolerance": c.tolerance, "gap": c.gap, "margin_flag": c.margin_flag,
                    "margin_accept": (t.get("decision") or {}).get("margin_accept"), "p_value": c.p_value,
                    "claim": t.get("claim"), "tool_values": t.get("tool_values") or {},
                    "readings": t.get("readings") or [], "stages": t.get("stages") or [],
                    "figure_candidates": t.get("figure_candidates") or [], "figure_runs": t.get("figure_runs") or {},
                    "calibration_group": (t.get("decision") or {}).get("calibration_group"),
                    "n_readings": (t.get("decision") or {}).get("n_readings"), "tool_calls": t.get("tool_calls", 0)})
    return out


def review(r: Review, shared: list[ClaimResult]) -> dict:
    return {"id": r.id, "decision": r.decision, "score": r.score, "findings": r.findings, "created_at": r.created_at,
            "ta_name": r.ta.name, "run_id": r.run_id,
            "confirmed_claims": [{"sentence": c.sentence, "page": c.page, "figure_id": c.figure_id,
                                  "claimed_value": c.claimed_value, "estimate": c.estimate, "verdict": c.verdict,
                                  "ta_note": c.ta_note} for c in shared]}


def version(v: ReportVersion, for_ta: bool) -> dict:
    runs = {r.id: r for r in v.runs}
    out = {"id": v.id, "version": v.version, "filename": v.filename, "note": v.note, "uploaded_at": v.uploaded_at,
           "reviews": [review(r, [c for c in runs[r.run_id].claims if c.ta_decision == "confirmed"]
                              if r.run_id in runs else []) for r in v.reviews]}
    if for_ta:
        out["runs"] = [run_brief(r) for r in v.runs]
    return out


def _utc(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)      # SQLite gives back naive datetimes


def submission_row(s: Submission, for_ta: bool) -> dict:
    last = s.versions[-1] if s.versions else None
    due = s.assignment.due_at
    out = {"id": s.id, "title": s.assignment.title, "assignment_id": s.assignment_id, "status": s.status,
           "created_at": s.created_at, "updated_at": s.updated_at, "versions": len(s.versions),
           "latest_filename": last.filename if last else None,
           "late": bool(due and s.versions and _utc(s.versions[0].uploaded_at) > _utc(due))}
    rv = last.reviews[-1] if last and last.reviews else None
    out["latest_score"] = rv.score if rv else None
    if for_ta:
        out["student"] = {"name": s.student.name, "email": s.student.email}
        run = last.runs[-1] if last and last.runs else None
        out["latest_run"] = {"status": run.status, "verdicts": (run.summary or {}).get("verdicts")} if run else None
    return out


def submission_detail(s: Submission, for_ta: bool) -> dict:
    out = submission_row(s, for_ta)
    out["versions"] = [version(v, for_ta) for v in s.versions]
    out["student"] = {"name": s.student.name, "email": s.student.email}
    a = s.assignment
    out["assignment"] = {"id": a.id, "title": a.title, "description": a.description, "due_at": a.due_at}
    out["course"] = course_brief(a.course)
    return out


# ------------------------------------------------------------------ courses and assignments
def course_brief(c: Course) -> dict:
    return {"id": c.id, "name": c.name, "code": c.code}


def assignment_row(a: Assignment, u: User) -> dict:
    out = {"id": a.id, "title": a.title, "description": a.description, "due_at": a.due_at, "created_at": a.created_at}
    if u.role == "ta":
        out["submitted"] = len(a.submissions)
        out["students"] = len(a.course.members)
        out["to_review"] = sum(s.status in OPEN for s in a.submissions)
    else:
        mine = next((s for s in a.submissions if s.student_id == u.id), None)
        out["submission"] = submission_row(mine, False) if mine else None
    return out


def course_row(c: Course, u: User) -> dict:
    out = course_brief(c) | {"ta_name": c.ta.name, "created_at": c.created_at, "assignments": len(c.assignments)}
    if u.role == "ta":
        out["students"] = len(c.members)
        out["to_review"] = sum(s.status in OPEN for a in c.assignments for s in a.submissions)
    else:
        mine = [next((s for s in a.submissions if s.student_id == u.id), None) for a in c.assignments]
        out["to_do"] = sum(s is None or s.status == "rework_requested" for s in mine)
    return out


def course_detail(c: Course, u: User, names: dict[str, str] | None = None) -> dict:
    out = course_row(c, u)
    out["assignments"] = [assignment_row(a, u) for a in reversed(c.assignments)]
    if u.role == "ta":
        out["members"] = [{"id": m.id, "email": m.email, "name": (names or {}).get(m.email)} for m in c.members]
    return out


def assignment_detail(a: Assignment, u: User, names: dict[str, str] | None = None) -> dict:
    out = assignment_row(a, u)
    out["course"] = course_brief(a.course)
    if u.role == "ta":
        out["submissions"] = [submission_row(s, True) for s in sorted(a.submissions, key=lambda s: s.updated_at, reverse=True)]
        done = {s.student.email for s in a.submissions}
        out["missing"] = [{"email": m.email, "name": (names or {}).get(m.email)} for m in a.course.members if m.email not in done]
    return out
