"""RuleSet table: one immutable row per rules version."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class RuleSet(SQLModel, table=True):
    __tablename__ = "rule_sets"

    version: int = Field(primary_key=True, sa_column_kwargs={"autoincrement": False})
    created_at: datetime = Field(default_factory=utcnow)
    note: str | None = None
    author: str | None = None  # AI governance: who made this version
    body: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
