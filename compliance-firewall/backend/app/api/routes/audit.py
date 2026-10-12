from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlmodel import Session

from app.api.deps import get_firewall_context, get_session, rate_limit, require_admin, require_client
from app.pipeline.firewall import FirewallContext
from app.schemas.api import AuditOut, AuditPage, CheckResponse, ReviewOut, ReviewRequest, Source
from app.schemas.decision import DecisionStatus
from app.services import audit_service

router = APIRouter(prefix="/audit", tags=["audit"], dependencies=[Depends(require_client)])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("", response_model=AuditPage)
def list_audit(
    session: SessionDep,
    decision: DecisionStatus | None = None,
    version: int | None = None,
    source: Source | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditPage:
    """Newest first."""
    total, rows = audit_service.list_entries(
        session, decision=decision, version=version, source=source, q=q, limit=limit, offset=offset
    )
    return AuditPage(total=total, limit=limit, offset=offset, items=[AuditOut.from_entry(r) for r in rows])


@router.get("/{entry_id}", response_model=AuditOut)
def get_audit(entry_id: int, session: SessionDep) -> AuditOut:
    entry = audit_service.get_entry(session, entry_id)
    return AuditOut.from_entry(entry, audit_service.list_reviews(session, entry_id))


@router.post(
    "/{entry_id}/review",
    response_model=ReviewOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
def review(entry_id: int, body: ReviewRequest, session: SessionDep) -> ReviewOut:
    """Human-in-the-loop: a compliance reviewer agrees or disagrees with a decision (append-only)."""
    row = audit_service.add_review(session, entry_id, body.reviewer, body.verdict, body.note)
    return ReviewOut.from_row(row)


@router.post("/{entry_id}/recheck", response_model=CheckResponse, dependencies=[Depends(rate_limit)])
async def recheck(
    entry_id: int,
    session: SessionDep,
    ctx: Annotated[FirewallContext, Depends(get_firewall_context)],
) -> CheckResponse:
    """Re-run a past answer against the LATEST rules. Saves a new entry with recheck_of set."""
    decision = await audit_service.recheck(session, entry_id, ctx)
    return CheckResponse.from_decision(decision)
