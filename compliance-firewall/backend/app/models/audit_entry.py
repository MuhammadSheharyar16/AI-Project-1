"""AuditEntry table: one row per firewall decision."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, Text
from sqlmodel import Field, SQLModel

from app.models.rule_set import utcnow


class AuditEntry(SQLModel, table=True):
    __tablename__ = "audit_entries"

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    question: str = Field(sa_column=Column(Text, nullable=False))
    raw_answer: str = Field(sa_column=Column(Text, nullable=False))
    shown_to_customer: str = Field(sa_column=Column(Text, nullable=False))
    decision: str = Field(index=True)  # Approved | Rejected | Error
    rule_version: int | None = Field(default=None, index=True)
    results_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    trace_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    ai_used: bool = False
    latency_ms: int = 0
    source: str = Field(index=True)  # chat | scenario | suite | recheck
    recheck_of: int | None = Field(default=None, foreign_key="audit_entries.id")
    error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    # AI governance: which model and prompt version were in force, and every AI call made.
    ai_model: str | None = None
    prompt_version: str | None = None
    ai_calls_json: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
