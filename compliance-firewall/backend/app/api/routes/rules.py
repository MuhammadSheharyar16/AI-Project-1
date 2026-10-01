from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import get_session, require_admin, require_client
from app.rules import repository
from app.rules.repository import VersionConflict
from app.schemas.api import RestoreRequest, RulesResponse, RulesUpdate, RuleVersionInfo

router = APIRouter(prefix="/rules", tags=["rules"], dependencies=[Depends(require_client)])

SessionDep = Annotated[Session, Depends(get_session)]
Admin = Depends(require_admin)


@router.get("", response_model=RulesResponse)
def get_rules(session: SessionDep) -> RulesResponse:
    row = repository.get_latest(session)
    if row is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "no rules have been saved")
    return RulesResponse.from_row(row)


@router.put("", response_model=RulesResponse, status_code=status.HTTP_201_CREATED, dependencies=[Admin])
def save_rules(body: RulesUpdate, session: SessionDep) -> RulesResponse:
    """Validate and save as a NEW version (N+1). Existing versions are never changed."""
    try:
        row = repository.save_new_version(session, body.rules, body.note, body.author)
    except VersionConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{exc}; please retry") from exc
    return RulesResponse.from_row(row)


@router.get("/versions", response_model=list[RuleVersionInfo])
def list_versions(session: SessionDep) -> list[RuleVersionInfo]:
    return [RuleVersionInfo.from_row(row) for row in repository.list_versions(session)]


@router.post("/restore/{version}", response_model=RulesResponse,
             status_code=status.HTTP_201_CREATED, dependencies=[Admin])
def restore(version: int, body: RestoreRequest, session: SessionDep) -> RulesResponse:
    """Copy an old version into a brand new version."""
    try:
        row = repository.restore_version(session, version, body.author)
    except VersionConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{exc}; please retry") from exc
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"rules version {version} not found")
    return RulesResponse.from_row(row)
