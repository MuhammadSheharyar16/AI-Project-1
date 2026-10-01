"""Audit log storage: save, filtered listing (newest first), get, human reviews, stats."""

from collections import Counter

from sqlalchemy import func, or_
from sqlmodel import Session, col, select

from app.models.audit_entry import AuditEntry
from app.models.audit_review import AuditReview


def save(session: Session, entry: AuditEntry) -> AuditEntry:
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def get(session: Session, entry_id: int) -> AuditEntry | None:
    return session.get(AuditEntry, entry_id)


def list_entries(
    session: Session,
    *,
    decision: str | None = None,
    version: int | None = None,
    source: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[AuditEntry]]:
    filters = []
    if decision:
        filters.append(col(AuditEntry.decision) == decision)
    if version is not None:
        filters.append(col(AuditEntry.rule_version) == version)
    if source:
        filters.append(col(AuditEntry.source) == source)
    if q:
        needle = q.lower()
        filters.append(or_(
            func.lower(col(AuditEntry.question)).contains(needle, autoescape=True),
            func.lower(col(AuditEntry.raw_answer)).contains(needle, autoescape=True),
        ))
    total = session.exec(select(func.count()).select_from(AuditEntry).where(*filters)).one()
    rows = session.exec(
        select(AuditEntry).where(*filters)
        .order_by(col(AuditEntry.created_at).desc(), col(AuditEntry.id).desc())
        .offset(offset).limit(limit)
    ).all()
    return total, list(rows)


def add_review(session: Session, review: AuditReview) -> AuditReview:
    session.add(review)
    session.commit()
    session.refresh(review)
    return review


def list_reviews(session: Session, audit_id: int) -> list[AuditReview]:
    query = select(AuditReview).where(col(AuditReview.audit_id) == audit_id).order_by(col(AuditReview.id))
    return list(session.exec(query))


def decision_counts(session: Session) -> dict[str, int]:
    rows = session.exec(select(AuditEntry.decision, func.count()).group_by(AuditEntry.decision)).all()
    return {decision: count for decision, count in rows}


def review_counts(session: Session) -> dict[str, int]:
    rows = session.exec(select(AuditReview.verdict, func.count()).group_by(AuditReview.verdict)).all()
    return {verdict: count for verdict, count in rows}


def ai_call_stats(session: Session, limit: int = 1000) -> tuple[Counter[str], Counter[str], float]:
    """Over the latest `limit` entries: (calls by outcome, calls by purpose, avg AI call ms)."""
    ledgers = session.exec(
        select(AuditEntry.ai_calls_json).order_by(col(AuditEntry.id).desc()).limit(limit)
    ).all()
    outcomes: Counter[str] = Counter()
    purposes: Counter[str] = Counter()
    times: list[float] = []
    for ledger in ledgers:
        for call in ledger or []:
            outcomes[call.get("outcome", "unknown")] += 1
            purposes[call.get("purpose", "unknown")] += 1
            if call.get("outcome") not in ("disabled", "budget_exceeded"):
                times.append(float(call.get("ms", 0)))
    return outcomes, purposes, round(sum(times) / len(times), 2) if times else 0.0
