"""Orchestrator: rules -> extract (pattern + security scan) -> code checks -> AI extraction ->
code checks on AI facts -> AI promise check -> decide -> audit. Fails closed on anything."""

import asyncio
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import Literal

from sqlmodel import Session

from app.ai.governance import AIGateway, AIPolicy, with_timeout
from app.ai.llm import LLMClient
from app.ai.redact import redact_deep, redact_text
from app.audit import repository as audit_repo
from app.core.logging import get_logger
from app.models.audit_entry import AuditEntry
from app.pipeline import extract_ai
from app.pipeline.checks import (
    banned, dates, links, percents, periods, policy_ai, prices, security, unlimited,
)
from app.pipeline.decide import decide, safe_message
from app.pipeline.extract import extract
from app.rules.cache import RulesCache
from app.schemas.decision import Decision, DecisionStatus, TraceStep
from app.schemas.facts import Fact, FactResult
from app.schemas.rules import Rules

log = get_logger(__name__)

Source = Literal["chat", "scenario", "suite", "recheck"]
Simulate = Literal["crash", "timeout"]


@dataclass
class FirewallContext:
    llm: LLMClient
    cache: RulesCache
    ai: AIPolicy
    redact_audit: bool = True  # privacy: no personal data stored in the audit log

    @property
    def timeout_s(self) -> float:
        return self.ai.timeout_s


def _describe(exc: BaseException) -> str:
    message = str(exc) or "no details"
    return f"{type(exc).__name__}: {message}"


class _Tracer:
    def __init__(self) -> None:
        self.steps: list[TraceStep] = []

    @contextmanager
    def step(self, name: str) -> Iterator[TraceStep]:
        record = TraceStep(step=name)
        started = perf_counter()
        try:
            yield record
        except Exception as exc:
            record.status = "failed"
            record.note = _describe(exc)
            raise
        finally:
            record.ms = round((perf_counter() - started) * 1000, 2)
            self.steps.append(record)

    def skip(self, note: str, *names: str) -> None:
        for name in names:
            self.steps.append(TraceStep(step=name, status="skipped", note=note))


def _code_check(fact: Fact, answer: str, rules: Rules) -> FactResult | None:
    """Cheap deterministic check for one fact. None means 'leave it for the AI'."""
    match fact.type:
        case "price":
            return prices.check(fact, rules)
        case "percent":
            return percents.check(fact, rules)
        case "period":
            return periods.check(fact, answer, rules)
        case "date":
            return dates.check(fact, answer, rules)
        case "link":
            return links.check(fact, rules)
        case "promise":
            return unlimited.check(fact, rules)
    return None


def _run_code_checks(facts: list[Fact], answer: str, rules: Rules,
                     results: list[FactResult]) -> list[Fact]:
    """Append code-check results; return the promises still waiting for the AI."""
    pending = []
    for fact in facts:
        result = _code_check(fact, answer, rules)
        if result is not None:
            results.append(result)
        elif fact.type == "promise":
            pending.append(fact)
    return pending


def _failed(results: list[FactResult]) -> int:
    return sum(not r.ok for r in results)


def _unchecked(facts: list[Fact], results: list[FactResult], status: DecisionStatus) -> list[FactResult]:
    """List every extracted fact that never got a verdict, so compliance sees all facts found.

    These are for display only: they are added after the decision and never pick the safe message.
    """
    judged = {(r.fact.type, r.fact.start, r.fact.end) for r in results}
    reason = (
        "not checked: the check stopped with an error" if status == "Error"
        else "not checked: AI check skipped because a code check already failed"
    )
    return [
        FactResult(fact=fact, ok=False, skipped=True, reason=reason)
        for fact in facts
        if (fact.type, fact.start, fact.end) not in judged
    ]


async def _simulate(kind: Simulate, timeout_s: float) -> None:
    if kind == "crash":
        raise RuntimeError("simulated crash")
    await with_timeout(asyncio.sleep(timeout_s + 5), timeout_s)


def _summary(facts: list[Fact], flagged: list[FactResult]) -> str:
    counts = Counter(f.type for f in facts) + Counter(r.fact.type for r in flagged)
    return ", ".join(f"{kind}={n}" for kind, n in counts.items()) or "no facts"


async def run(
    question: str,
    answer: str,
    session: Session,
    ctx: FirewallContext,
    *,
    source: Source,
    recheck_of: int | None = None,
    simulate: Simulate | None = None,
) -> Decision:
    started = perf_counter()
    tracer = _Tracer()
    gateway = AIGateway(ctx.llm, ctx.ai)
    rules: Rules | None = None
    version: int | None = None
    facts: list[Fact] = []
    results: list[FactResult] = []
    error: str | None = None
    status: DecisionStatus

    try:
        with tracer.step("load_rules") as step:
            version, rules, step.note = ctx.cache.get_rules(session)

        with tracer.step("extract") as step:
            facts = extract(answer, rules)
            flagged = security.scan(answer) + banned.find(answer, rules)
            ai_needed = extract_ai.needs_ai(answer, facts)
            step.note = _summary(facts, flagged) + ("; cues left for AI" if ai_needed else "")

        if simulate:
            with tracer.step("simulate") as step:
                step.note = f"simulating {simulate}"
                await _simulate(simulate, ctx.timeout_s)

        if not facts and not flagged and not ai_needed:
            tracer.skip("no facts: approved instantly", "code_checks", "ai_extract", "ai_check")
        else:
            with tracer.step("code_checks") as step:
                results = list(flagged)
                pending = _run_code_checks(facts, answer, rules, results)
                failed = _failed(results)
                step.note = f"{len(results)} checked, {failed} failed"

            if failed:
                tracer.skip("a code check failed", "ai_extract", "ai_check")
            else:
                if ai_needed:
                    with tracer.step("ai_extract") as step:
                        found = await extract_ai.extract(answer, rules, gateway, facts)
                        facts += found.facts
                        pending += _run_code_checks(found.facts, answer, rules, results)
                        failed = _failed(results)
                        step.note = (f"{len(found.facts)} new fact(s), {found.discarded} discarded "
                                     f"(ungrounded/invalid), {found.duplicates} already found, "
                                     f"{found.cadence} cadence ignored"
                                     + (f", {failed} failed code checks" if failed else ""))
                else:
                    tracer.skip("pattern rules explained every cue", "ai_extract")

                if failed:
                    tracer.skip("a code check failed", "ai_check")
                elif not pending:
                    tracer.skip("no promises to verify", "ai_check")
                else:
                    with tracer.step("ai_check") as step:
                        for fact in pending:
                            results.append(await policy_ai.check(fact, rules, gateway))
                        step.note = f"{len(pending)} promise(s) verified, {_failed(results)} failed"

        with tracer.step("decide") as step:
            status, key = decide(results)
            customer_text = answer if status == "Approved" else safe_message(key or "general", rules)
            step.note = status if key is None else f"{status}: {key} safe message"
    except Exception as exc:  # fail closed on anything
        status, error = "Error", _describe(exc)
        customer_text = safe_message("general", rules)
        tracer.steps.append(TraceStep(step="decide", note="Error: general safe message"))
        log.warning("firewall error (source=%s): %s", source, error)

    results += _unchecked(facts, results, status)
    results.sort(key=lambda r: (r.fact.start, r.fact.end))
    decision = Decision(
        status=status, customer_text=customer_text, raw_answer=answer, rule_version=version,
        results=results, ai_used=gateway.calls_made > 0, ai_calls=gateway.calls_made,
        ai_ledger=gateway.ledger, ai_model=ctx.ai.model, prompt_version=ctx.ai.prompt_version,
        latency_ms=round((perf_counter() - started) * 1000), trace=tracer.steps, error=error,
    )
    return _record(session, decision, question, source, recheck_of, rules, ctx.redact_audit)


def _record(
    session: Session, decision: Decision, question: str, source: Source,
    recheck_of: int | None, rules: Rules | None, redact_pii: bool = True,
) -> Decision:
    """Save the audit entry. If saving fails, nothing may be shown: downgrade to Error.

    With `redact_pii`, personal data is redacted in everything stored. The live response still
    carries the original text; stored fact offsets refer to the original (unredacted) answer.
    """
    audit_step = TraceStep(step="audit", note="saved" + (" (PII redacted)" if redact_pii else ""))
    decision.trace.append(audit_step)
    started = perf_counter()
    scrub_text = redact_text if redact_pii else (lambda t: t)
    scrub = redact_deep if redact_pii else (lambda v: v)
    try:
        entry = audit_repo.save(session, AuditEntry(
            question=scrub_text(question), raw_answer=scrub_text(decision.raw_answer),
            shown_to_customer=scrub_text(decision.customer_text), decision=decision.status,
            rule_version=decision.rule_version,
            results_json=scrub([r.model_dump(mode="json") for r in decision.results]),
            trace_json=[s.model_dump(mode="json") for s in decision.trace],
            ai_used=decision.ai_used, latency_ms=decision.latency_ms, source=source,
            recheck_of=recheck_of, error=decision.error,
            ai_model=decision.ai_model, prompt_version=decision.prompt_version,
            ai_calls_json=[c.model_dump(mode="json") for c in decision.ai_ledger],
        ))
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
