from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import get_firewall_context, get_session, rate_limit, require_admin, require_client
from app.pipeline.firewall import FirewallContext
from app.pipeline.suite import load_items, run_suite
from app.schemas.api import SuiteInfo, SuiteReport

router = APIRouter(prefix="/suite", tags=["suite"])


@router.get("", response_model=SuiteInfo, dependencies=[Depends(require_client)])
def info() -> SuiteInfo:
    """How many labelled answers the suite holds, split by label."""
    items = load_items()
    approve = sum(item.label == "approve" for item in items)
    return SuiteInfo(total=len(items), approve=approve, reject=len(items) - approve)


@router.post("/run", response_model=SuiteReport, dependencies=[Depends(require_admin), Depends(rate_limit)])
async def run(
    session: Annotated[Session, Depends(get_session)],
    ctx: Annotated[FirewallContext, Depends(get_firewall_context)],
) -> SuiteReport:
    """Run all labelled answers on the latest rules. Each run is saved to the audit log."""
    return await run_suite(session, ctx, load_items())
