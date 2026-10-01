from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.api.deps import get_session, get_settings
from app.core.config import Settings
from app.rules import repository

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: str
    rule_version: int | None
    ai_configured: bool
    debug: bool


@router.get("/health", response_model=Health)
def health(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Health:
    return Health(
        status="ok",
        rule_version=repository.latest_version_number(session),
        ai_configured=bool(settings.groq_api_key.get_secret_value()),
        debug=settings.debug,
    )
