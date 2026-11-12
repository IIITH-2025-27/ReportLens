from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SignUp(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["student", "ta"]

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        local, _, domain = v.partition("@")
        if not local or "." not in domain or " " in v:
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return v.strip()


class SignIn(BaseModel):
    email: str
    password: str


class ClaimDecision(BaseModel):
    ta_decision: Literal["confirmed", "dismissed"] | None = None
    ta_note: str = Field(default="", max_length=2000)


class ReviewIn(BaseModel):
    decision: Literal["accepted", "rework"]
    score: float | None = Field(default=None, ge=0, le=100)
    findings: str = Field(default="", max_length=10000)


class CourseIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(default="", max_length=40)


class StudentsIn(BaseModel):
    emails: list[str] = Field(min_length=1, max_length=500)


class AssignmentIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    due_at: datetime | None = None
