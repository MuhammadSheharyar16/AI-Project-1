"""Audit log reads, human reviews and re-checks of past answers."""

from sqlmodel import Session

from app.audit import repository as audit_repo
from app.core.exceptions import NotFoundError
from app.models.audit_entry import AuditEntry
from app.models.audit_review import AuditReview
from app.pipeline.firewall import FirewallContext
from app.schemas.api import Source
from app.schemas.decision import Decision, DecisionStatus
from app.services import firewall_service


def list_entries(
    session: Session,
    *,
    decision: DecisionStatus | None,
    version: int | None,
    source: Source | None,
    q: str | None,
    limit: int,
    offset: int,
) -> tuple[int, list[AuditEntry]]:
    return audit_repo.list_entries(
        session, decision=decision, version=version, source=source, q=q, limit=limit, offset=offset
    )


def get_entry(session: Session, entry_id: int) -> AuditEntry:
    entry = audit_repo.get(session, entry_id)
    if entry is None:
        raise NotFoundError(f"audit entry {entry_id} not found")
    return entry


def list_reviews(session: Session, entry_id: int) -> list[AuditReview]:
    return audit_repo.list_reviews(session, entry_id)


def add_review(session: Session, entry_id: int, reviewer: str, verdict: str, note: str | None) -> AuditReview:
    """Append-only: a review never changes the entry."""
    get_entry(session, entry_id)
    return audit_repo.add_review(
        session,
        AuditReview(
            audit_id=entry_id,
            reviewer=reviewer,
            verdict=verdict,
            note=note,
        ),
    )


async def recheck(session: Session, entry_id: int, ctx: FirewallContext) -> Decision:
    """Re-run a past answer against the LATEST rules. Saves a new entry with recheck_of set."""
    entry = get_entry(session, entry_id)
    return await firewall_service.check_answer(
        entry.question, entry.raw_answer, session, ctx, source="recheck", recheck_of=entry.id
    )
