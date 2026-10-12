import asyncio
from typing import Any

import pytest
from sqlmodel import Session

from app.audit import repository as audit_repo
from app.pipeline.firewall import FirewallContext
from app.rules.seed import SEED_RULES
from app.services import firewall_service


def test_check_answer_when_answer_is_correct_saves_approved_entry(
    db_session: Session, firewall_ctx: FirewallContext
) -> None:
    answer = "The Pro plan costs $49 per month."
    decision = asyncio.run(firewall_service.check_answer("q", answer, db_session, firewall_ctx, source="scenario"))

    assert decision.status == "Approved" and decision.customer_text == answer
    entry = audit_repo.get(db_session, decision.audit_id)
    assert entry is not None and entry.decision == "Approved" and entry.source == "scenario"
    assert decision.trace[-1].step == "audit" and decision.trace[-1].status == "ran"


def test_check_answer_when_answer_has_personal_data_stores_it_redacted(
    db_session: Session, firewall_ctx: FirewallContext
) -> None:
    answer = "Mail ali@example.com about the Pro plan at $49."
    decision = asyncio.run(firewall_service.check_answer("q", answer, db_session, firewall_ctx, source="scenario"))

    assert decision.raw_answer == answer  # the live response keeps the original text
    entry = audit_repo.get(db_session, decision.audit_id)
    assert entry is not None and "ali@example.com" not in entry.raw_answer


def test_check_answer_when_audit_save_fails_returns_error_with_safe_message(
    db_session: Session, firewall_ctx: FirewallContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_save(*args: Any) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(audit_repo, "save", broken_save)
    decision = asyncio.run(
        firewall_service.check_answer(
            "q", "The Pro plan costs $49 per month.", db_session, firewall_ctx, source="scenario"
        )
    )

    assert decision.status == "Error" and decision.audit_id is None
    assert decision.customer_text == SEED_RULES["safe_messages"]["general"]
    assert decision.error is not None and "audit save failed" in decision.error


def test_draft_and_check_when_mode_is_mistakes_rejects_the_draft(
    db_session: Session, firewall_ctx: FirewallContext
) -> None:
    decision = asyncio.run(firewall_service.draft_and_check("How much is Pro?", "mistakes", db_session, firewall_ctx))

    assert decision.status == "Rejected"
    entry = audit_repo.get(db_session, decision.audit_id)
    assert entry is not None and entry.source == "chat"
