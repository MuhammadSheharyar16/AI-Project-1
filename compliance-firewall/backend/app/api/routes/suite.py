from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import get_firewall_context, get_session, rate_limit, require_admin
from app.pipeline.firewall import FirewallContext
from app.pipeline.suite import load_items, run_suite
from app.schemas.api import SuiteReport

router = APIRouter(prefix="/suite", tags=["suite"])


@router.post("/run", response_model=SuiteReport, dependencies=[Depends(require_admin), Depends(rate_limit)])
async def run(
    session: Annotated[Session, Depends(get_session)],
    ctx: Annotated[FirewallContext, Depends(get_firewall_context)],
) -> SuiteReport:
    """Run all labelled answers on the latest rules. Each run is saved to the audit log."""
    return await run_suite(session, ctx, load_items())
