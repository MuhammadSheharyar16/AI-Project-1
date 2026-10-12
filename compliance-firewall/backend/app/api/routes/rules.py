from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlmodel import Session

from app.api.deps import get_session, get_settings, require_admin, require_client
from app.core.config import Settings
from app.schemas.api import RestoreRequest, RulesResponse, RulesUpdate, RuleVersionInfo
from app.services import rules_service

router = APIRouter(prefix="/rules", tags=["rules"], dependencies=[Depends(require_client)])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
Admin = Depends(require_admin)


@router.get("", response_model=RulesResponse)
def get_rules(session: SessionDep) -> RulesResponse:
    return RulesResponse.from_row(rules_service.get_latest(session))


@router.put("", response_model=RulesResponse, status_code=status.HTTP_201_CREATED, dependencies=[Admin])
def save_rules(
    body: RulesUpdate, session: SessionDep, settings: SettingsDep, background: BackgroundTasks
) -> RulesResponse:
    """Validate and save as a NEW version (N+1). Existing versions are never changed."""
    row = rules_service.save(session, body.rules, body.note, body.author, settings, background.add_task)
    return RulesResponse.from_row(row)


@router.get("/versions", response_model=list[RuleVersionInfo])
def list_versions(session: SessionDep) -> list[RuleVersionInfo]:
    return [RuleVersionInfo.from_row(row) for row in rules_service.list_versions(session)]


@router.post(
    "/restore/{version}", response_model=RulesResponse, status_code=status.HTTP_201_CREATED, dependencies=[Admin]
)
def restore(
    version: int, body: RestoreRequest, session: SessionDep, settings: SettingsDep, background: BackgroundTasks
) -> RulesResponse:
    """Copy an old version into a brand new version."""
    row = rules_service.restore(session, version, body.author, settings, background.add_task)
    return RulesResponse.from_row(row)
