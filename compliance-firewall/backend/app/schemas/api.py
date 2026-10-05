"""Request and response bodies for the HTTP API."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.models.audit_entry import AuditEntry
from app.models.audit_review import AuditReview
from app.models.rule_set import RuleSet
from app.schemas.decision import AICallRecord, Decision, DecisionStatus, TraceStep
from app.schemas.facts import FactResult
from app.schemas.rules import Rules

Source = Literal["chat", "scenario", "suite", "recheck"]


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    mode: Literal["accurate", "mistakes"] = "accurate"


class CheckRequest(BaseModel):
    question: str = Field(default="", max_length=2000)
    answer: str = Field(min_length=1, max_length=5000)


class CustomerView(BaseModel):
    text: str


class ComplianceView(BaseModel):
    audit_id: int | None
    decision: DecisionStatus
    rule_version: int | None
    raw_answer: str
    results: list[FactResult]
    ai_used: bool
    latency_ms: int
    trace: list[TraceStep]
    error: str | None
    governance: "AIGovernanceInfo"


class AIGovernanceInfo(BaseModel):
    """Which AI configuration made this decision, and every AI call made."""

    ai_model: str | None
    prompt_version: str | None
    ai_calls: list[AICallRecord]


class CheckResponse(BaseModel):
    customer: CustomerView
    compliance: ComplianceView

    @classmethod
    def from_decision(cls, d: Decision) -> "CheckResponse":
        return cls(
            customer=CustomerView(text=d.customer_text),
            compliance=ComplianceView(
                audit_id=d.audit_id, decision=d.status, rule_version=d.rule_version,
                raw_answer=d.raw_answer, results=d.results, ai_used=d.ai_used,
                latency_ms=d.latency_ms, trace=d.trace, error=d.error,
                governance=AIGovernanceInfo(
                    ai_model=d.ai_model, prompt_version=d.prompt_version, ai_calls=d.ai_ledger,
                ),
            ),
        )


Name = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[^\x00-\x1f]+$")]


class RulesUpdate(BaseModel):
    rules: Rules
    note: str | None = Field(default=None, max_length=500)
    author: Name


class RestoreRequest(BaseModel):
    author: Name


class RulesResponse(BaseModel):
    version: int
    created_at: datetime
    note: str | None
    author: str | None
    rules: Rules

    @classmethod
    def from_row(cls, row: RuleSet) -> "RulesResponse":
        return cls(version=row.version, created_at=row.created_at, note=row.note,
                   author=row.author, rules=Rules.model_validate(row.body))


class RuleVersionInfo(BaseModel):
    version: int
    created_at: datetime
    note: str | None
    author: str | None

    @classmethod
    def from_row(cls, row: RuleSet) -> "RuleVersionInfo":
        return cls(version=row.version, created_at=row.created_at, note=row.note, author=row.author)


class ReviewRequest(BaseModel):
    reviewer: Name
    verdict: Literal["agree", "disagree"]
    note: str | None = Field(default=None, max_length=1000)


class ReviewOut(BaseModel):
    id: int
    audit_id: int
    created_at: datetime
    reviewer: str
    verdict: Literal["agree", "disagree"]
    note: str | None

    @classmethod
    def from_row(cls, r: AuditReview) -> "ReviewOut":
        return cls(id=r.id or 0, audit_id=r.audit_id, created_at=r.created_at, reviewer=r.reviewer,
                   verdict=r.verdict, note=r.note)  # type: ignore[arg-type]


class AuditOut(BaseModel):
    id: int
    created_at: datetime
    question: str
    raw_answer: str
    shown_to_customer: str
    decision: DecisionStatus
    rule_version: int | None
    results: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    ai_used: bool
    latency_ms: int
    source: Source
    recheck_of: int | None
    error: str | None
    ai_model: str | None
    prompt_version: str | None
    ai_calls: list[dict[str, Any]]
    reviews: list[ReviewOut] = []

    @classmethod
    def from_entry(cls, e: AuditEntry, reviews: list[AuditReview] | None = None) -> "AuditOut":
        return cls(
            id=e.id or 0, created_at=e.created_at, question=e.question, raw_answer=e.raw_answer,
            shown_to_customer=e.shown_to_customer, decision=e.decision,  # type: ignore[arg-type]
            rule_version=e.rule_version, results=e.results_json, trace=e.trace_json,
            ai_used=e.ai_used, latency_ms=e.latency_ms, source=e.source,  # type: ignore[arg-type]
            recheck_of=e.recheck_of, error=e.error, ai_model=e.ai_model,
            prompt_version=e.prompt_version, ai_calls=e.ai_calls_json or [],
            reviews=[ReviewOut.from_row(r) for r in reviews or []],
        )


class AuditPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AuditOut]


class SuiteItem(BaseModel):
    id: str
    question: str
    answer: str
    label: Literal["approve", "reject"]
    category: str


class SuiteInfo(BaseModel):
    """Size of the labelled dataset, so the UI never hardcodes it."""

    total: int
    approve: int
    reject: int


class SuiteRow(BaseModel):
    id: str
    category: str
    label: Literal["approve", "reject"]
    decision: DecisionStatus
    shown_raw_answer: bool
    correct: bool
    reasons: list[str]
    ai_used: bool
    audit_id: int | None


class SuiteReport(BaseModel):
    total: int
    leaked: int
    caught_rate: float
    false_block_rate: float
    ai_calls: int
    rule_version: int | None
    rows: list[SuiteRow]


class GovernanceReport(BaseModel):
    """AI governance and security posture, plus live usage numbers (for the demo slide)."""

    ai: dict[str, Any]
    security_controls: list[str]
    rules: dict[str, Any]
    decisions: dict[str, int]
    ai_usage: dict[str, Any]
    human_review: dict[str, Any]
