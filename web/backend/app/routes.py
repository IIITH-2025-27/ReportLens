from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from . import config, serialize, verifier_service
from .db import get_db
from .models import Assignment, ClaimResult, Course, CourseMember, ReportVersion, Review, Submission, User, VerificationRun
from .schemas import AssignmentIn, ClaimDecision, CourseIn, ReviewIn, SignIn, SignUp, StudentsIn
from .security import check_password, current_user, hash_password, make_token, student_only, ta_only

router = APIRouter(prefix="/api")


# ------------------------------------------------------------------ auth
@router.post("/auth/signup")
def signup(body: SignUp, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    u = User(name=body.name, email=body.email, password_hash=hash_password(body.password), role=body.role)
    db.add(u)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "An account with this email already exists. Sign in instead.") from None
    return {"token": make_token(u), "user": serialize.user(u)}


@router.post("/auth/signin")
def signin(body: SignIn, db: Session = Depends(get_db)):
    """The role is not asked for: it comes from the account the email belongs to."""
    u = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if u is None or not check_password(body.password, u.password_hash):
        raise HTTPException(401, "Email or password is incorrect")
    return {"token": make_token(u), "user": serialize.user(u)}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return serialize.user(user)


# ------------------------------------------------------------------ helpers
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _is_member(db: Session, course_id: int, user: User) -> bool:
    return db.scalar(select(CourseMember.id).where(CourseMember.course_id == course_id, CourseMember.email == user.email)) is not None


def _course(db: Session, cid: int, user: User) -> Course:
    """A TA reaches the courses they created; a student reaches the courses they were added to."""
    c = db.get(Course, cid)
    if c is None or (user.role == "ta" and c.ta_id != user.id) or (user.role == "student" and not _is_member(db, cid, user)):
        raise HTTPException(404, "Course not found")
    return c


def _assignment(db: Session, aid: int, user: User) -> Assignment:
    a = db.get(Assignment, aid)
    if a is None:
        raise HTTPException(404, "Assignment not found")
    try:
        _course(db, a.course_id, user)
    except HTTPException:
        raise HTTPException(404, "Assignment not found") from None
    return a


def _can_see(s: Submission, user: User) -> bool:
    return s.student_id == user.id if user.role == "student" else s.assignment.course.ta_id == user.id


def _submission(db: Session, sid: int, user: User) -> Submission:
    s = db.get(Submission, sid)
    if s is None or not _can_see(s, user):
        raise HTTPException(404, "Report not found")
    return s


def _version(db: Session, vid: int, user: User) -> ReportVersion:
    v = db.get(ReportVersion, vid)
    if v is None or not _can_see(v.submission, user):
        raise HTTPException(404, "Report version not found")
    return v


def _run(db: Session, rid: int, user: User) -> VerificationRun:
    run = db.get(VerificationRun, rid)
    if run is None or not _can_see(run.version.submission, user):
        raise HTTPException(404, "Run not found")
    return run


# Loader options for the pages that walk the tree: one query per level for all rows, not one per row.
_SUB_TREE = (selectinload(Submission.versions).selectinload(ReportVersion.runs),
             selectinload(Submission.versions).selectinload(ReportVersion.reviews))


def _full(db: Session, model, key: int, *opts):
    """Reload one row with its children eager-loaded (the row is already access-checked)."""
    return db.scalar(select(model).where(model.id == key).options(*opts).execution_options(populate_existing=True))


def _full_course(db: Session, cid: int) -> Course:
    subs = selectinload(Course.assignments).selectinload(Assignment.submissions)
    return _full(db, Course, cid, selectinload(Course.members), subs, *(subs.options(o) for o in _SUB_TREE))


def _full_assignment(db: Session, aid: int) -> Assignment:
    subs = selectinload(Assignment.submissions)
    return _full(db, Assignment, aid, selectinload(Assignment.course).selectinload(Course.members), subs,
                 *(subs.options(o) for o in _SUB_TREE))


def _full_submission(db: Session, sid: int) -> Submission:
    return _full(db, Submission, sid, *_SUB_TREE)


def _names(db: Session, c: Course) -> dict[str, str]:
    """email -> name for the course members who already have an account."""
    emails = [m.email for m in c.members]
    return dict(db.execute(select(User.email, User.name).where(User.email.in_(emails))).all()) if emails else {}


async def _save_pdf(file: UploadFile, submission_id: int, version: int) -> tuple[str, str]:
    data = await file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"The file is larger than {config.MAX_UPLOAD_MB} MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Upload a PDF file")
    folder = config.STORAGE_DIR / "reports" / str(submission_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"v{version}.pdf"                               # the name on disk never comes from the user
    path.write_bytes(data)
    shown = re.sub(r"[^\w.\- ]", "_", Path(file.filename or "report.pdf").name)[:200] or "report.pdf"
    return shown, str(path)


# ------------------------------------------------------------------ courses
@router.get("/courses")
def list_courses(user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Course).order_by(Course.created_at.desc()).options(
        selectinload(Course.members), selectinload(Course.assignments).selectinload(Assignment.submissions))
    if user.role == "ta":
        q = q.where(Course.ta_id == user.id)
    else:
        q = q.join(CourseMember).where(CourseMember.email == user.email)
    return [serialize.course_row(c, user) for c in db.scalars(q)]


@router.post("/courses")
def create_course(body: CourseIn, user: User = Depends(ta_only), db: Session = Depends(get_db)):
    if not body.name.strip():
        raise HTTPException(400, "Give the course a name")
    c = Course(ta_id=user.id, name=body.name.strip(), code=body.code.strip())
    db.add(c)
    db.commit()
    return serialize.course_detail(c, user)


@router.get("/courses/{cid}")
def get_course(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = _full_course(db, _course(db, cid, user).id)
    return serialize.course_detail(c, user, _names(db, c) if user.role == "ta" else None)


@router.post("/courses/{cid}/students")
def add_students(cid: int, body: StudentsIn, user: User = Depends(ta_only), db: Session = Depends(get_db)):
    """Students are added by email. An email with no account yet is kept; the course shows up when they sign up."""
    c = _course(db, cid, user)
    have = {m.email for m in c.members}
    wanted = list(dict.fromkeys(e.strip().lower() for e in body.emails if e.strip()))
    tas = set(db.scalars(select(User.email).where(User.email.in_(wanted), User.role == "ta"))) if wanted else set()
    added, already, rejected = [], [], []
    for e in wanted:
        if not EMAIL.match(e) or len(e) > 255:
            rejected.append({"email": e, "why": "not an email address"})
        elif e in tas:
            rejected.append({"email": e, "why": "this is a TA account"})
        elif e in have:
            already.append(e)
        else:
            c.members.append(CourseMember(email=e))
            added.append(e)
    db.commit()
    c = _full_course(db, cid)
    return {"added": added, "already": already, "rejected": rejected, "course": serialize.course_detail(c, user, _names(db, c))}


@router.delete("/courses/{cid}/students/{mid}")
def remove_student(cid: int, mid: int, user: User = Depends(ta_only), db: Session = Depends(get_db)):
    """Takes the student off the course. Reports they already submitted are kept."""
    c = _course(db, cid, user)
    m = db.get(CourseMember, mid)
    if m is None or m.course_id != c.id:
        raise HTTPException(404, "Student not found on this course")
    db.delete(m)
    db.commit()
    c = _full_course(db, cid)
    return serialize.course_detail(c, user, _names(db, c))


# ------------------------------------------------------------------ assignments
@router.post("/courses/{cid}/assignments")
def create_assignment(cid: int, body: AssignmentIn, user: User = Depends(ta_only), db: Session = Depends(get_db)):
    c = _course(db, cid, user)
    if not body.title.strip():
        raise HTTPException(400, "Give the assignment a title")
    a = Assignment(course_id=c.id, title=body.title.strip(), description=body.description.strip(), due_at=body.due_at)
    db.add(a)
    db.commit()
    return serialize.assignment_detail(a, user, _names(db, c))


@router.get("/assignments/{aid}")
def get_assignment(aid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _full_assignment(db, _assignment(db, aid, user).id)
    return serialize.assignment_detail(a, user, _names(db, a.course) if user.role == "ta" else None)


# ------------------------------------------------------------------ submissions
@router.post("/assignments/{aid}/submissions")
async def create_submission(aid: int, file: UploadFile = File(...),
                            user: User = Depends(student_only), db: Session = Depends(get_db)):
    """A student's first upload for an assignment. Later uploads go to /submissions/{id}/versions."""
    a = _assignment(db, aid, user)
    if db.scalar(select(Submission.id).where(Submission.assignment_id == a.id, Submission.student_id == user.id)):
        raise HTTPException(409, "You have already submitted a report for this assignment")
    s = Submission(assignment_id=a.id, student_id=user.id, status="submitted")
    db.add(s)
    try:
        db.flush()
        name, path = await _save_pdf(file, s.id, 1)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "You have already submitted a report for this assignment") from None
    except HTTPException:
        db.rollback()
        raise
    db.add(ReportVersion(submission_id=s.id, version=1, filename=name, file_path=path))
    db.commit()
    db.refresh(s)
    return serialize.submission_detail(s, False)


@router.get("/submissions/{sid}")
def get_submission(sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return serialize.submission_detail(_full_submission(db, _submission(db, sid, user).id), user.role == "ta")


@router.post("/submissions/{sid}/versions")
async def upload_new_version(sid: int, note: str = Form(""), file: UploadFile = File(...),
                             user: User = Depends(student_only), db: Session = Depends(get_db)):
    s = _submission(db, sid, user)
    if s.status not in ("submitted", "rework_requested"):
        raise HTTPException(409, {"verifying": "The TA is checking this report right now. Try again once the review is back.",
                                  "verified": "The TA is reviewing this report. Wait for the review before uploading again.",
                                  "accepted": "This report has been accepted and is closed."}[s.status])
    n = s.versions[-1].version + 1
    name, path = await _save_pdf(file, s.id, n)
    db.add(ReportVersion(submission_id=s.id, version=n, filename=name, file_path=path, note=note.strip()[:2000]))
    s.status = "submitted"
    db.commit()
    db.refresh(s)
    return serialize.submission_detail(s, False)


@router.get("/versions/{vid}/pdf")
def download_pdf(vid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    v = _version(db, vid, user)
    if not Path(v.file_path).exists():
        raise HTTPException(404, "The file is no longer on the server")
    return FileResponse(v.file_path, media_type="application/pdf", filename=v.filename,
                        content_disposition_type="inline")


# ------------------------------------------------------------------ TA: verify
@router.post("/versions/{vid}/verify")
def start_verification(vid: int, user: User = Depends(ta_only), db: Session = Depends(get_db)):
    v = _version(db, vid, user)
    s = v.submission
    if v.id != s.versions[-1].id:
        raise HTTPException(409, "Only the latest upload can be verified")
    if s.status == "accepted":
        raise HTTPException(409, "This report has already been accepted")
    if any(r.status in ("queued", "running") for r in v.runs):
        raise HTTPException(409, "A verification is already running for this report")
    run = VerificationRun(version_id=v.id, started_by=user.id, status="queued")
    db.add(run)
    s.status = "verifying"
    db.commit()
    verifier_service.enqueue(run.id)
    return serialize.run_brief(run)


@router.get("/runs/{rid}")
def get_run(rid: int, user: User = Depends(ta_only), db: Session = Depends(get_db)):
    run = _run(db, rid, user)
    out = serialize.run_brief(run)
    out["version_id"] = run.version_id
    out["figures"] = {k: {x: v[x] for x in ("caption", "number", "chart_type", "page")} for k, v in (run.figures or {}).items()}
    out["claims"] = [serialize.claim(c) for c in run.claims]
    return out


@router.get("/runs/{rid}/figures/{figure_id}")
def get_figure(rid: int, figure_id: str, user: User = Depends(ta_only), db: Session = Depends(get_db)):
    fig = (_run(db, rid, user).figures or {}).get(figure_id)
    if fig is None:
        raise HTTPException(404, "Figure not found")
    path = Path(fig["path"]).resolve()
    if config.STORAGE_DIR.resolve() not in path.parents or not path.exists():
        raise HTTPException(404, "Figure not found")
    return FileResponse(path)


@router.patch("/claims/{cid}")
def decide_claim(cid: int, body: ClaimDecision, user: User = Depends(ta_only), db: Session = Depends(get_db)):
    """The TA's own judgement on one finding. Only confirmed findings are shown to the student."""
    c = db.get(ClaimResult, cid)
    if c is None or not _can_see(c.run.version.submission, user):
        raise HTTPException(404, "Claim not found")
    c.ta_decision, c.ta_note = body.ta_decision, body.ta_note.strip()
    db.commit()
    return serialize.claim(c)


# ------------------------------------------------------------------ TA: review
@router.post("/versions/{vid}/review")
def send_review(vid: int, body: ReviewIn, user: User = Depends(ta_only), db: Session = Depends(get_db)):
    v = _version(db, vid, user)
    s = v.submission
    if v.id != s.versions[-1].id:
        raise HTTPException(409, "Only the latest upload can be reviewed")
    if s.status == "verifying":
        raise HTTPException(409, "Wait for the verification to finish")
    if s.status in ("accepted", "rework_requested"):
        raise HTTPException(409, "A review has already been sent for this upload")
    if body.decision == "rework" and not body.findings.strip():
        raise HTTPException(400, "Tell the student what to change")
    done = [r for r in v.runs if r.status == "done"]
    db.add(Review(version_id=v.id, ta_id=user.id, run_id=done[-1].id if done else None, score=body.score,
                  findings=body.findings.strip(), decision=body.decision))
    s.status = "accepted" if body.decision == "accepted" else "rework_requested"
    db.commit()
    db.refresh(s)
    return serialize.submission_detail(s, True)
