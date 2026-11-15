"""The bridge to the verifier, built the same way as web/backend/app/verifier_service.py. Nothing here
re-implements a stage: the agent is built by `chart_claim_verifier.pipeline.build_agent` (the function the CLI's
`run` uses) and a report is checked by `pipeline.verify_pdf`.

Verification is slow (models), so a run is a background job. One worker thread, so the models are loaded once
and reports are checked one at a time.
"""
from __future__ import annotations

import math
import threading
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import config
from .db import SessionLocal
from .models import ClaimResult, RunEvent, VerificationRun, now

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="verifier")
_lock = threading.Lock()
_runtime: dict | None = None


def _load_runtime() -> dict:
    """Config, calibration table, tools and agent. Built on first use, then kept (the models stay loaded)."""
    global _runtime
    with _lock:
        if _runtime is None:
            from chart_claim_verifier.config import load_config
            from chart_claim_verifier.pipeline import Context, build_agent, load_profile, load_table

            cfg = load_config(config.VERIFIER_CONFIG)
            for key, value in list(cfg["paths"].items()):          # config paths are relative to the repository root
                if not Path(value).is_absolute():
                    cfg["paths"][key] = str(config.REPO_ROOT / value)
            ctx = Context(cfg)
            table = load_table(ctx)
            policy = config.VERIFIER_POLICY or cfg["agent"]["policy"]
            if policy == "informed":
                try:
                    load_profile(ctx)
                except FileNotFoundError:                           # no tool profile next to the table
                    policy = "fixed_order"
            agent, rc, pol = build_agent(ctx, table, policy, config.VERIFIER_PARSER)
            _runtime = {"ctx": ctx, "agent": agent, "rc": rc, "policy": pol.name,
                        "tools": list(cfg["tools"]["enabled"]), "parser": config.VERIFIER_PARSER}
        return _runtime


def jsonable(o):
    """NaN / inf (an unbounded margin) are not valid JSON for Postgres."""
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    return o


def _num(v):
    return None if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else float(v)


def enqueue(run_id: int) -> None:
    _executor.submit(_run_job, run_id)


def _warm(rt: dict) -> None:
    """The tools load their models on first use; load the local ones now. Models on a remote server (CCV_REMOTE_URL)
    and offline replays have nothing to load."""
    seen = set()
    for tool in rt["agent"].controller.tools.values():
        if hasattr(tool, "_load") and getattr(tool, "server", None) is None and not getattr(tool, "offline", False):
            tool._load()                                           # DePlot
        llm = getattr(tool, "llm", None)
        if hasattr(llm, "load") and id(llm) not in seen:           # Qwen3-VL, shared by the table and crop tools
            seen.add(id(llm))
            llm.load()


# "idle" (not asked to load yet), "loading", "ready" or "failed: <reason>"; shown by /api/health
models_state = "idle"


def preload() -> None:
    """Load the verifier and its models at start-up, on the worker thread, so the first report does not wait for
    them and a loading problem shows at once rather than on someone's first upload. A run started meanwhile waits
    behind it in the same queue."""
    def job():
        global models_state
        models_state = "loading"
        try:
            _warm(_load_runtime())
            models_state = "ready"
        except Exception as e:                                     # the first run will try again and report it
            models_state = f"failed: {type(e).__name__}: {e}"[:300]
            traceback.print_exc()
    _executor.submit(job)


class _Feed:
    """Writes the agent's activity events for one run, each committed at once so the page sees it while the run
    goes on. Its own session, so a failed run's rollback does not take the feed with it."""

    def __init__(self, run_id: int):
        self.run_id, self.seq, self.db = run_id, 0, SessionLocal()

    def __call__(self, e: dict) -> None:
        self.seq += 1
        self.db.add(RunEvent(run_id=self.run_id, seq=self.seq, stage=str(e.get("stage", ""))[:16],
                             status=e.get("status"), text=str(e.get("text", "")), why=e.get("why"),
                             tool=e.get("tool"), sentence=e.get("sentence")))
        try:
            self.db.commit()
        except Exception:                                          # the feed must never stop a run
            self.db.rollback()

    def close(self) -> None:
        self.db.close()


def _run_job(run_id: int) -> None:
    db = SessionLocal()
    try:
        run = db.get(VerificationRun, run_id)
        if run is None or run.status != "queued":
            return
        run.status, run.started_at = "running", now()
        db.commit()
        report_row = run.report
        t0 = time.perf_counter()
        feed = _Feed(run_id)
        try:
            from chart_claim_verifier.pipeline import verify_pdf

            if _runtime is None:
                feed({"stage": "run", "status": "start", "text": "load the verifier and its models (first run only)"})
            rt = _load_runtime()
            global models_state
            models_state = "ready"
            feed({"stage": "run", "status": "ok", "text": "verifier ready",
                  "why": f"policy {rt['policy']}, parser {rt['parser']}, tools {', '.join(rt['tools'])}"})
            work = config.STORAGE_DIR / "work" / f"run_{run.id}"
            report, traces = verify_pdf(rt["ctx"], rt["agent"], rt["rc"], report_row.file_path, work,
                                        report_id=f"lite{report_row.id}", on_event=feed)
            pages = {s.sentence_id: s.page for s in report.sentences}
            run.figures = {f.figure_id: {"path": f.image_path, "caption": f.caption, "number": f.number,
                                         "chart_type": f.chart_type, "page": f.page} for f in report.figures}
            for i, t in enumerate(traces):
                d, c = t.decision, t.claim
                db.add(ClaimResult(
                    run_id=run.id, position=i, page=pages.get(t.sentence_id, 0), sentence=t.sentence,
                    verdict=d.verdict, reason=d.reason, figure_id=t.figure_id,
                    claimed_value=_num(c.claimed_value) if c else None, tolerance=_num(c.tolerance) if c else None,
                    estimate=_num(d.estimate), gap=_num(d.gap), margin_flag=_num(d.margin_flag), p_value=_num(d.p_value),
                    trace=jsonable(t.model_dump(mode="json"))))
            counts = Counter(t.decision.verdict for t in traces)
            run.summary = {"verdicts": dict(counts), "sentences": len(report.sentences), "figures": len(report.figures),
                           "tool_calls": sum(t.tool_calls for t in traces), "seconds": round(time.perf_counter() - t0, 1),
                           "policy": rt["policy"], "parser": rt["parser"], "tools": rt["tools"]}
            run.status = "done"
            feed({"stage": "run", "status": "ok", "text": "finished",
                  "why": ", ".join(f"{n} {v}" for v, n in counts.most_common()) + f" in {run.summary['seconds']}s"})
        except Exception as e:                                     # models missing, unreadable PDF, ...
            db.rollback()
            run = db.get(VerificationRun, run_id)
            run.status = "failed"
            run.error = f"{type(e).__name__}: {e}"[:2000]
            feed({"stage": "run", "status": "error", "text": "the verifier could not finish", "why": run.error})
            traceback.print_exc()
        run.finished_at = now()
        db.commit()
        feed.close()
    finally:
        db.close()


def fail_interrupted() -> None:
    """Runs that were queued or running when the server stopped can never finish: mark them failed."""
    db = SessionLocal()
    try:
        for run in db.query(VerificationRun).filter(VerificationRun.status.in_(("queued", "running"))):
            run.status, run.error, run.finished_at = "failed", "The server restarted before this run finished.", now()
        db.commit()
    finally:
        db.close()
