from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.ai import mock_assistant
from app.api.deps import get_firewall_context, get_session, get_simulate, rate_limit, require_client
from app.pipeline import firewall
from app.pipeline.firewall import FirewallContext, Simulate
from app.schemas.api import ChatRequest, CheckRequest, CheckResponse

router = APIRouter(tags=["firewall"], dependencies=[Depends(require_client), Depends(rate_limit)])

SessionDep = Annotated[Session, Depends(get_session)]
ContextDep = Annotated[FirewallContext, Depends(get_firewall_context)]


@router.post("/chat", response_model=CheckResponse)
async def chat(body: ChatRequest, session: SessionDep, ctx: ContextDep) -> CheckResponse:
    """The mock assistant drafts an answer, then the firewall checks it."""
    answer = mock_assistant.draft(body.question, body.mode)
    decision = await firewall.run(body.question, answer, session, ctx, source="chat")
    return CheckResponse.from_decision(decision)


@router.post("/check", response_model=CheckResponse)
async def check(
    body: CheckRequest,
    session: SessionDep,
    ctx: ContextDep,
    simulate: Annotated[Simulate | None, Depends(get_simulate)],
) -> CheckResponse:
    """Run the firewall on a given answer."""
    decision = await firewall.run(
        body.question, body.answer, session, ctx, source="scenario", simulate=simulate
    )
    return CheckResponse.from_decision(decision)
