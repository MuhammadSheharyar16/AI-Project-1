"""The firewall's output: decision, customer text, per-fact results and a step trace."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.facts import FactResult

DecisionStatus = Literal["Approved", "Rejected", "Error"]
StepStatus = Literal["ran", "skipped", "failed"]
Purpose = Literal["extract", "verify"]
Outcome = Literal["ok", "error", "timeout", "rate_limited", "disabled", "budget_exceeded"]


class TraceStep(BaseModel):
    step: str
    status: StepStatus = "ran"
    note: str = ""
    ms: float = 0.0


class AICallRecord(BaseModel):
    """AI governance ledger: one row per AI call attempt."""

    purpose: Purpose
    model: str
    prompt_version: str
    outcome: Outcome
    ms: float
    redactions: int = 0
    error: str | None = None


class Decision(BaseModel):
    status: DecisionStatus
    customer_text: str
    raw_answer: str
    rule_version: int | None
    results: list[FactResult]
    ai_used: bool
    ai_calls: int = 0
    ai_ledger: list[AICallRecord] = []
    ai_model: str | None = None
    prompt_version: str | None = None
    latency_ms: int
    trace: list[TraceStep]
    error: str | None = None
    audit_id: int | None = None
