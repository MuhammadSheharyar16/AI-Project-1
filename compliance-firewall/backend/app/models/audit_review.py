"""AuditReview table: human-in-the-loop reviews of firewall decisions (append-only)."""

from datetime import datetime

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel

from app.models.rule_set import utcnow


class AuditReview(SQLModel, table=True):
    __tablename__ = "audit_reviews"

    id: int | None = Field(default=None, primary_key=True)
    audit_id: int = Field(foreign_key="audit_entries.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)
    reviewer: str
    verdict: str = Field(index=True)  # agree | disagree
    note: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
