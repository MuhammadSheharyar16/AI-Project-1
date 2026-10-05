"""AI governance: the single gateway every LLM call goes through.

Enforces the kill switch, a per-minute call budget, PII redaction and the timeout, and keeps a
ledger of every call (purpose, model, prompt version, outcome, time) for the audit log.
"""

import asyncio
import threading
import time
from collections import deque
from collections.abc import Awaitable
from dataclasses import dataclass
from time import perf_counter
from typing import Any, TypeVar

from app.ai.llm import LLMClient, LLMError, LLMRateLimited, LLMTimeout
from app.ai.redact import redact
from app.schemas.decision import AICallRecord, Outcome, Purpose

T = TypeVar("T")


class AIDisabled(LLMError):
    """AI_ENABLED=false: the kill switch is on."""


class AIBudgetExceeded(LLMError):
    """More AI calls this minute than AI_MAX_CALLS_PER_MINUTE allows."""


async def with_timeout(call: Awaitable[T], timeout_s: float) -> T:
    """Hard deadline. `asyncio.wait_for` would also wait for the cancelled call to finish cleaning
    up (e.g. closing a stalled connection), which can take far longer than the timeout."""
    task = asyncio.ensure_future(call)
    try:
        done, _ = await asyncio.wait({task}, timeout=timeout_s)
    except asyncio.CancelledError:
        task.cancel()
        raise
    if not done:
        task.cancel()
        task.add_done_callback(lambda t: t.cancelled() or t.exception())  # nothing left unretrieved
        raise LLMTimeout(f"AI call timed out after {timeout_s:g}s")
    return task.result()


class AIBudget:
    """Sliding one-minute window shared by the whole app."""

    def __init__(self, max_per_minute: int) -> None:
        self.max_per_minute = max_per_minute
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        now = time.monotonic()
        with self._lock:
            while self._calls and now - self._calls[0] >= 60:
                self._calls.popleft()
            if len(self._calls) >= self.max_per_minute:
                return False
            self._calls.append(now)
            return True


@dataclass
class AIPolicy:
    """App-wide governance settings for AI calls."""

    enabled: bool
    budget: AIBudget
    timeout_s: float
    model: str
    prompt_version: str


class AIGateway:
    """One per firewall run. Every AI call goes through `ask`."""

    def __init__(self, llm: LLMClient, policy: AIPolicy) -> None:
        self._llm = llm
        self._policy = policy
        self.ledger: list[AICallRecord] = []

    @property
    def calls_made(self) -> int:
        """Calls that actually reached the LLM (not blocked by the kill switch or budget)."""
        return sum(r.outcome not in ("disabled", "budget_exceeded") for r in self.ledger)

    def _record(self, purpose: Purpose, outcome: Outcome, started: float,
                redactions: int = 0, error: str | None = None) -> None:
        self.ledger.append(AICallRecord(
            purpose=purpose, model=self._policy.model, prompt_version=self._policy.prompt_version,
            outcome=outcome, ms=round((perf_counter() - started) * 1000, 2),
            redactions=redactions, error=error,
        ))

    async def ask(self, purpose: Purpose, prompt: str) -> dict[str, Any]:
        started = perf_counter()
        if not self._policy.enabled:
            self._record(purpose, "disabled", started)
            raise AIDisabled("AI checks are disabled by governance (AI_ENABLED=false)")
        if not self._policy.budget.try_acquire():
            self._record(purpose, "budget_exceeded", started)
            raise AIBudgetExceeded(
                f"AI call budget reached ({self._policy.budget.max_per_minute} calls per minute)"
            )
        safe_prompt, redactions = redact(prompt)
        try:
            data = await with_timeout(
                self._llm.llm_json(safe_prompt, self._policy.timeout_s), self._policy.timeout_s
            )
        except LLMTimeout as exc:
            self._record(purpose, "timeout", started, redactions, str(exc))
            raise
        except LLMRateLimited as exc:
            self._record(purpose, "rate_limited", started, redactions, str(exc))
            raise
        except Exception as exc:
            self._record(purpose, "error", started, redactions, f"{type(exc).__name__}: {exc}")
            raise
        self._record(purpose, "ok", started, redactions)
        return data
