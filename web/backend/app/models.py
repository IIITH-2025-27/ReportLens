"""Tables.

    users ─< courses ─< assignments ─< submissions ─< report_versions ─< verification_runs ─< claim_results
                 └─< course_members                               └─< reviews

A TA creates a course, adds students to it by email (course_members) and releases assignments in it.
A submission is one student's work for one assignment. Each upload (the first one and every rework) is a
report_version. A TA runs the verifier on a version (verification_run), looks at its claim_results,
and writes a review that goes back to the student.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# Loading: collections are lazy by default; the pages that walk them ask for them up front with loader options
# (app/routes.py, _full_* helpers), so a page costs a fixed number of queries however many students there are.
# Users are joined in. This matters on a remote database, where every query is a network round trip.

Json = JSON().with_variant(JSONB(), "postgresql")

ROLES = ("student", "ta")
# submitted -> verifying -> verified -> accepted | rework_requested -> (new upload) submitted ...
SUBMISSION_STATUS = ("submitted", "verifying", "verified", "rework_requested", "accepted")
RUN_STATUS = ("queued", "running", "done", "failed")
TA_DECISIONS = ("confirmed", "dismissed")
REVIEW_DECISIONS = ("accepted", "rework")


def now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(primary_key=True)
    ta_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)      # the TA who created it
    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(40), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    ta: Mapped[User] = relationship(lazy="joined")
    members: Mapped[list["CourseMember"]] = relationship(back_populates="course", order_by="CourseMember.email",
                                                         cascade="all, delete-orphan")
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="course", order_by="Assignment.id",
                                                           cascade="all, delete-orphan")


class CourseMember(Base):
    """A student on a course, kept by email so a TA can add someone who has not signed up yet."""
    __tablename__ = "course_members"
    __table_args__ = (UniqueConstraint("course_id", "email"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    course: Mapped[Course] = relationship(back_populates="members")


class Assignment(Base):
    __tablename__ = "assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    course: Mapped[Course] = relationship(back_populates="assignments")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="assignment", order_by="Submission.id")


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("assignment_id", "student_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="submitted", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    assignment: Mapped[Assignment] = relationship(back_populates="submissions")
    student: Mapped[User] = relationship(lazy="joined")
    versions: Mapped[list["ReportVersion"]] = relationship(back_populates="submission", order_by="ReportVersion.version",
                                                           cascade="all, delete-orphan")


class ReportVersion(Base):
    __tablename__ = "report_versions"
    __table_args__ = (UniqueConstraint("submission_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    note: Mapped[str] = mapped_column(Text, default="")            # what the student says changed
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    submission: Mapped[Submission] = relationship(back_populates="versions")
    runs: Mapped[list["VerificationRun"]] = relationship(back_populates="version", order_by="VerificationRun.id",
                                                         cascade="all, delete-orphan")
    reviews: Mapped[list["Review"]] = relationship(back_populates="version", order_by="Review.id",
                                                   cascade="all, delete-orphan")


class VerificationRun(Base):
    __tablename__ = "verification_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("report_versions.id"), index=True)
    started_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[dict | None] = mapped_column(Json, nullable=True)    # verdict counts, policy, tools, seconds
    figures: Mapped[dict | None] = mapped_column(Json, nullable=True)    # figure_id -> {path, caption, number, chart_type}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    version: Mapped[ReportVersion] = relationship(back_populates="runs")
    claims: Mapped[list["ClaimResult"]] = relationship(back_populates="run", order_by="ClaimResult.position",
                                                       cascade="all, delete-orphan")


class ClaimResult(Base):
    """One checked sentence. The common fields are columns; the full ClaimTrace is kept as JSON."""
    __tablename__ = "claim_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("verification_runs.id"), index=True)
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
    ta_decision: Mapped[str | None] = mapped_column(String(16), nullable=True)   # confirmed | dismissed
    ta_note: Mapped[str] = mapped_column(Text, default="")

    run: Mapped[VerificationRun] = relationship(back_populates="claims")


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("report_versions.id"), index=True)
    ta_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("verification_runs.id"), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    findings: Mapped[str] = mapped_column(Text, default="")
    decision: Mapped[str] = mapped_column(String(16))                    # accepted | rework
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    version: Mapped[ReportVersion] = relationship(back_populates="reviews")
    ta: Mapped[User] = relationship(lazy="joined")
