"""Tables (all suffixed _v2; they sit in the same database as the full web app's tables).

    reports_v2 ─< verification_runs_v2 ─< claim_results_v2

No accounts: anyone can upload a report, run the verifier on it, and open any earlier report from the history.
Running the verifier again on a report adds a new run; earlier runs are kept and can still be opened.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

Json = JSON().with_variant(JSONB(), "postgresql")
RUN_STATUS = ("queued", "running", "done", "failed")


def now() -> datetime:
    return datetime.now(timezone.utc)


class Report(Base):
    __tablename__ = "reports_v2"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

    runs: Mapped[list["VerificationRun"]] = relationship(back_populates="report", order_by="VerificationRun.id",
                                                         cascade="all, delete-orphan")


class VerificationRun(Base):
    __tablename__ = "verification_runs_v2"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports_v2.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[dict | None] = mapped_column(Json, nullable=True)    # verdict counts, policy, tools, seconds
    figures: Mapped[dict | None] = mapped_column(Json, nullable=True)    # figure_id -> {path, caption, number, chart_type}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    report: Mapped[Report] = relationship(back_populates="runs")
    claims: Mapped[list["ClaimResult"]] = relationship(back_populates="run", order_by="ClaimResult.position",
                                                       cascade="all, delete-orphan")


class ClaimResult(Base):
    """One checked sentence. The common fields are columns; the full ClaimTrace is kept as JSON."""
    __tablename__ = "claim_results_v2"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("verification_runs_v2.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    page: Mapped[int] = mapped_column(Integer, default=0)
    sentence: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(16), index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    figure_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    claimed_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    tolerance: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    gap: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin_flag: Mapped[float | None] = mapped_column(Float, nullable=True)
    p_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    trace: Mapped[dict] = mapped_column(Json)

    run: Mapped[VerificationRun] = relationship(back_populates="claims")
