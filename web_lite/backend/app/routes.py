"""Open API: no accounts. Upload a report, run the verifier on it, look at any earlier report and its runs."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import config, serialize, verifier_service
from .db import get_db
from .models import Report, VerificationRun

router = APIRouter(prefix="/api")
ACTIVE = ("queued", "running")


def _report(db: Session, rid: int) -> Report:
    rp = db.scalar(select(Report).where(Report.id == rid).options(selectinload(Report.runs)))
    if rp is None:
        raise HTTPException(404, "Report not found")
    return rp


def _run(db: Session, rid: int) -> VerificationRun:
    run = db.get(VerificationRun, rid)
    if run is None:
        raise HTTPException(404, "Run not found")
    return run


@router.post("/reports")
async def upload_report(file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await file.read(config.MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"The file is larger than {config.MAX_UPLOAD_MB} MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Upload a PDF file")
    shown = re.sub(r"[^\w.\- ]", "_", Path(file.filename or "report.pdf").name)[:200] or "report.pdf"
    rp = Report(filename=shown, file_path="", size_bytes=len(data))
    db.add(rp)
    db.flush()
    folder = config.STORAGE_DIR / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{rp.id}.pdf"                                  # the name on disk never comes from the user
    try:
        path.write_bytes(data)
    except OSError:
        db.rollback()
        raise HTTPException(500, "Could not save the file") from None
    rp.file_path = str(path)
    db.commit()
    return serialize.report_detail(_report(db, rp.id))


@router.get("/reports")
def list_reports(q: str = "", limit: int = 100, db: Session = Depends(get_db)):
    """Newest first. `q` filters by file name."""
    stmt = select(Report).order_by(Report.uploaded_at.desc(), Report.id.desc()).limit(max(1, min(limit, 500)))
    if q.strip():
        stmt = stmt.where(Report.filename.ilike(f"%{q.strip()}%"))
    return [serialize.report_row(rp) for rp in db.scalars(stmt.options(selectinload(Report.runs)))]


@router.get("/reports/{rid}")
def get_report(rid: int, db: Session = Depends(get_db)):
    return serialize.report_detail(_report(db, rid))


@router.get("/reports/{rid}/pdf")
def report_pdf(rid: int, db: Session = Depends(get_db)):
    rp = _report(db, rid)
    if not Path(rp.file_path).exists():
        raise HTTPException(404, "The file is no longer on the server")
    return FileResponse(rp.file_path, media_type="application/pdf", filename=rp.filename,
                        content_disposition_type="inline")


@router.delete("/reports/{rid}")
def delete_report(rid: int, db: Session = Depends(get_db)):
    """Removes the report, all its runs and claims, the PDF and the extracted figures."""
    rp = _report(db, rid)
    if any(r.status in ACTIVE for r in rp.runs):
        raise HTTPException(409, "The verifier is running on this report. Delete it once the run has finished.")
    files = [Path(rp.file_path)]
    folders = [config.STORAGE_DIR / "work" / f"run_{r.id}" for r in rp.runs]
    db.delete(rp)                                                   # runs and claims go with it (cascade)
    db.commit()
    for f in files:
        f.unlink(missing_ok=True)
    for d in folders:
        shutil.rmtree(d, ignore_errors=True)
    return {"deleted": rid}


@router.post("/reports/{rid}/verify")
def start_verification(rid: int, db: Session = Depends(get_db)):
    """A new run every time; earlier runs of the same report are kept."""
    rp = _report(db, rid)
    if any(r.status in ACTIVE for r in rp.runs):
        raise HTTPException(409, "The verifier is already running on this report")
    waiting = db.scalar(select(func.count()).select_from(VerificationRun).where(VerificationRun.status.in_(ACTIVE)))
    if waiting >= config.MAX_QUEUED_RUNS:
        raise HTTPException(429, "The verifier is busy with other reports. Try again in a few minutes.")
    run = VerificationRun(report_id=rp.id, status="queued")
    db.add(run)
    db.commit()
    verifier_service.enqueue(run.id)
    out = serialize.run_brief(run)
    out["queue_position"] = waiting + 1
    return out


@router.get("/runs/{rid}")
def get_run(rid: int, db: Session = Depends(get_db)):
    run = _run(db, rid)
    out = serialize.run_full(run)
    if run.status == "queued":
        out["queue_position"] = db.scalar(select(func.count()).select_from(VerificationRun).where(
            VerificationRun.status.in_(ACTIVE), VerificationRun.id <= run.id))
    return out


@router.get("/runs/{rid}/figures/{figure_id}")
def get_figure(rid: int, figure_id: str, db: Session = Depends(get_db)):
    fig = (_run(db, rid).figures or {}).get(figure_id)
    if fig is None:
        raise HTTPException(404, "Figure not found")
    path = Path(fig["path"]).resolve()
    if config.STORAGE_DIR.resolve() not in path.parents or not path.exists():
        raise HTTPException(404, "Figure not found")
    return FileResponse(path)
