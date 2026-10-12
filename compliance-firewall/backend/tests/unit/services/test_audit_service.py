import asyncio

import pytest
from sqlmodel import Session

from app.core.exceptions import NotFoundError
from app.pipeline.firewall import FirewallContext
from app.services import audit_service, firewall_service


def _saved_entry_id(session: Session, ctx: FirewallContext) -> int:
    decision = asyncio.run(
        firewall_service.check_answer("q", "The Pro plan costs $49 per month.", session, ctx, source="scenario")
    )
    assert decision.audit_id is not None
    return decision.audit_id


def test_get_entry_when_missing_raises_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError, match="audit entry 999 not found"):
        audit_service.get_entry(db_session, 999)


def test_add_review_when_entry_exists_appends_review(db_session: Session, firewall_ctx: FirewallContext) -> None:
    entry_id = _saved_entry_id(db_session, firewall_ctx)

    review = audit_service.add_review(db_session, entry_id, "Ayesha", "agree", "looks right")

    assert review.audit_id == entry_id
    assert [r.verdict for r in audit_service.list_reviews(db_session, entry_id)] == ["agree"]


def test_add_review_when_entry_missing_raises_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        audit_service.add_review(db_session, 999, "Ayesha", "agree", None)


def test_recheck_when_entry_exists_saves_new_linked_entry(db_session: Session, firewall_ctx: FirewallContext) -> None:
    entry_id = _saved_entry_id(db_session, firewall_ctx)

    decision = asyncio.run(audit_service.recheck(db_session, entry_id, firewall_ctx))

    assert decision.audit_id not in (None, entry_id)
    entry = audit_service.get_entry(db_session, decision.audit_id)
    assert entry.recheck_of == entry_id and entry.source == "recheck"


def test_list_entries_when_filtered_by_source_returns_only_matches(
    db_session: Session, firewall_ctx: FirewallContext
) -> None:
    _saved_entry_id(db_session, firewall_ctx)

    total, rows = audit_service.list_entries(
        db_session, decision=None, version=None, source="chat", q=None, limit=10, offset=0
    )

    assert (total, rows) == (0, [])
