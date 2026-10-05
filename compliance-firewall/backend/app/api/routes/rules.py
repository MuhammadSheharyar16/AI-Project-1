import logging
import subprocess
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlmodel import Session

from app.api.deps import get_session, get_settings, require_admin, require_client
from app.models.rule_set import RuleSet
from app.rules import demo_site, repository
from app.rules.repository import VersionConflict
from app.schemas.api import RestoreRequest, RulesResponse, RulesUpdate, RuleVersionInfo
from app.schemas.rules import Rules

log = logging.getLogger(__name__)

router = APIRouter(prefix="/rules", tags=["rules"], dependencies=[Depends(require_client)])

SessionDep = Annotated[Session, Depends(get_session)]
Admin = Depends(require_admin)


def _publish_demo_site(folder: str, repo: str, version: int) -> None:
    try:
        pushed = demo_site.publish(Path(folder), repo, f"Sync demo site to rules v{version}")
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        log.warning("demo site not published for rules v%s: %s", version, exc)
        return
    log.info("demo site published to %s for rules v%s: %s", repo, version,
             ", ".join(p.as_posix() for p in pushed) or "already live")


def _sync_demo_site(request: Request, row: RuleSet, background: BackgroundTasks) -> None:
    """Best effort: the rules are already saved, so a site problem is logged, never raised."""
    settings = get_settings(request)
    folder = settings.demo_site_dir
    if not folder:
        return
    try:
        changed, warnings = demo_site.sync(Path(folder), Rules.model_validate(row.body))
    except OSError as exc:
        log.warning("demo site not updated for rules v%s: %s", row.version, exc)
        return
    log.info("demo site synced to rules v%s: %s", row.version,
             ", ".join(p.as_posix() for p in changed) or "no change")
    for warning in warnings:
        log.warning("demo site: %s", warning)
    if settings.demo_site_repo:  # after the response: the push takes a few seconds
        background.add_task(_publish_demo_site, folder, settings.demo_site_repo, row.version)


@router.get("", response_model=RulesResponse)
def get_rules(session: SessionDep) -> RulesResponse:
    row = repository.get_latest(session)
    if row is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "no rules have been saved")
    return RulesResponse.from_row(row)


@router.put("", response_model=RulesResponse, status_code=status.HTTP_201_CREATED, dependencies=[Admin])
def save_rules(body: RulesUpdate, session: SessionDep, request: Request,
               background: BackgroundTasks) -> RulesResponse:
    """Validate and save as a NEW version (N+1). Existing versions are never changed."""
    try:
        row = repository.save_new_version(session, body.rules, body.note, body.author)
    except VersionConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{exc}; please retry") from exc
    _sync_demo_site(request, row, background)
    return RulesResponse.from_row(row)


@router.get("/versions", response_model=list[RuleVersionInfo])
def list_versions(session: SessionDep) -> list[RuleVersionInfo]:
    return [RuleVersionInfo.from_row(row) for row in repository.list_versions(session)]


@router.post("/restore/{version}", response_model=RulesResponse,
             status_code=status.HTTP_201_CREATED, dependencies=[Admin])
def restore(version: int, body: RestoreRequest, session: SessionDep, request: Request,
            background: BackgroundTasks) -> RulesResponse:
    """Copy an old version into a brand new version."""
    try:
        row = repository.restore_version(session, version, body.author)
    except VersionConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{exc}; please retry") from exc
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"rules version {version} not found")
    _sync_demo_site(request, row, background)
    return RulesResponse.from_row(row)
