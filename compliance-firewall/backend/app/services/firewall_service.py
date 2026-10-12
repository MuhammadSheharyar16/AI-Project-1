"""Runs the firewall on an answer and records every decision in the audit log."""

from collections.abc import Callable
from time import perf_counter
from typing import Any

from sqlmodel import Session

from app.ai import mock_assistant
from app.ai.mock_assistant import Mode
from app.ai.redact import redact, redact_deep
from app.audit import repository as audit_repo
from app.core.logging import get_logger
from app.models.audit_entry import AuditEntry
from app.pipeline import firewall
from app.pipeline.decide import safe_message
from app.pipeline.firewall import FirewallContext, Simulate, Source
from app.rules.cache import RulesUnavailable
from app.schemas.decision import Decision, TraceStep
from app.schemas.rules import Rules

log = get_logger(__name__)


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc) or 'no details'}"


async def check_answer(
    question: str,
    answer: str,
    session: Session,
    ctx: FirewallContext,
    *,
    source: Source,
    recheck_of: int | None = None,
    simulate: Simulate | None = None,
) -> Decision:
    decision, rules = await firewall.run(question, answer, session, ctx, source=source, simulate=simulate)
    return _record(session, decision, question, source, recheck_of, rules, ctx.redact_audit)


async def draft_and_check(question: str, mode: Mode, session: Session, ctx: FirewallContext) -> Decision:
    """The mock assistant drafts an answer, then the firewall checks it."""
    try:
        rules = ctx.cache.get_rules(session)[1]
    except RulesUnavailable:
        rules = None  # the firewall reports this itself
    answer = mock_assistant.draft(question, mode, rules)
    return await check_answer(question, answer, session, ctx, source="chat")


def _record(
    session: Session,
    decision: Decision,
    question: str,
    source: Source,
    recheck_of: int | None,
    rules: Rules | None,
    redact_pii: bool = True,
) -> Decision:
    """Save the audit entry. If saving fails, nothing may be shown: downgrade to Error.

    With `redact_pii`, personal data is redacted in everything stored. The live response still
    carries the original text; stored fact offsets refer to the original (unredacted) answer.
    """
    audit_step = TraceStep(step="audit", note="saved" + (" (PII redacted)" if redact_pii else ""))
    decision.trace.append(audit_step)
    started = perf_counter()
    scrub_text: Callable[[str], str] = (lambda t: redact(t)[0]) if redact_pii else (lambda t: t)
    scrub: Callable[[Any], Any] = redact_deep if redact_pii else (lambda v: v)
    try:
        entry = audit_repo.save(
            session,
            AuditEntry(
                question=scrub_text(question),
                raw_answer=scrub_text(decision.raw_answer),
                shown_to_customer=scrub_text(decision.customer_text),
                decision=decision.status,
                rule_version=decision.rule_version,
                results_json=scrub([r.model_dump(mode="json") for r in decision.results]),
                trace_json=[s.model_dump(mode="json") for s in decision.trace],
                ai_used=decision.ai_used,
                latency_ms=decision.latency_ms,
                source=source,
                recheck_of=recheck_of,
                error=decision.error,
                ai_model=decision.ai_model,
                prompt_version=decision.prompt_version,
                ai_calls_json=[c.model_dump(mode="json") for c in decision.ai_ledger],
            ),
        )
    except Exception as exc:
        session.rollback()
        log.error("audit save failed: %s", _describe(exc))
        audit_step.status, audit_step.note = "failed", _describe(exc)
        decision.status = "Error"
        decision.customer_text = safe_message("general", rules)
        decision.error = f"audit save failed: {_describe(exc)}"
        return decision
    audit_step.ms = round((perf_counter() - started) * 1000, 2)
    audit_step.note = f"saved as #{entry.id}" + (" (PII redacted)" if redact_pii else "")
    decision.audit_id = entry.id
    log.info("decision #%s %s (v%s, source=%s)", entry.id, decision.status, decision.rule_version, source)
    return decision
