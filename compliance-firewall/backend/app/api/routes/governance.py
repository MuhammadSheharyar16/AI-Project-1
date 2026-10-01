from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.ai.governance import AIPolicy
from app.api.deps import get_ai_policy, get_session, get_settings, require_client
from app.audit import report
from app.core.config import Settings
from app.schemas.api import GovernanceReport

router = APIRouter(tags=["governance"], dependencies=[Depends(require_client)])


@router.get("/governance", response_model=GovernanceReport)
def governance(
    session: Annotated[Session, Depends(get_session)],
    ai: Annotated[AIPolicy, Depends(get_ai_policy)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GovernanceReport:
    """AI governance and security posture plus live usage numbers."""
    return report.build(
        session, ai,
        admin_token_set=bool(settings.admin_token.get_secret_value()),
        api_token_set=bool(settings.api_token.get_secret_value()),
        redact_pii=settings.audit_redact_pii,
    )
