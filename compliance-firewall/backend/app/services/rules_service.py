"""Versioned rules: read, save, restore, and keep the demo site in step with each new version."""

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

from sqlmodel import Session

from app.core.config import Settings
from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.models.rule_set import RuleSet
from app.rules import demo_site, repository
from app.schemas.rules import Rules

log = logging.getLogger(__name__)

# Runs a slow task after the response, e.g. FastAPI's BackgroundTasks.add_task.
Defer = Callable[..., object]


def get_latest(session: Session) -> RuleSet:
    row = repository.get_latest(session)
    if row is None:
        raise ServiceUnavailableError("no rules have been saved")
    return row


def latest_version_number(session: Session) -> int | None:
    return repository.latest_version_number(session)


def list_versions(session: Session) -> list[RuleSet]:
    return repository.list_versions(session)


def save(
    session: Session, rules: Rules, note: str | None, author: str | None, settings: Settings, defer: Defer
) -> RuleSet:
    """Save as a NEW version (N+1). Existing versions are never changed. Raises VersionConflictError."""
    row = repository.save_new_version(session, rules, note, author)
    _sync_demo_site(settings, row, defer)
    return row


def restore(session: Session, version: int, author: str | None, settings: Settings, defer: Defer) -> RuleSet:
    """Copy an old version into a brand new version. Raises NotFoundError or VersionConflictError."""
    row = repository.restore_version(session, version, author)
    if row is None:
        raise NotFoundError(f"rules version {version} not found")
    _sync_demo_site(settings, row, defer)
    return row


def _publish_demo_site(folder: str, repo: str, version: int) -> None:
    try:
        pushed = demo_site.publish(Path(folder), repo, f"Sync demo site to rules v{version}")
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        log.warning("demo site not published for rules v%s: %s", version, exc)
        return
    log.info(
        "demo site published to %s for rules v%s: %s",
        repo,
        version,
        ", ".join(p.as_posix() for p in pushed) or "already live",
    )


def _sync_demo_site(settings: Settings, row: RuleSet, defer: Defer) -> None:
    """Best effort: the rules are already saved, so a site problem is logged, never raised."""
    folder = settings.demo_site_dir
    if not folder:
        return
    try:
        changed, warnings = demo_site.sync(Path(folder), Rules.model_validate(row.body))
    except OSError as exc:
        log.warning("demo site not updated for rules v%s: %s", row.version, exc)
        return
    log.info("demo site synced to rules v%s: %s", row.version, ", ".join(p.as_posix() for p in changed) or "no change")
    for warning in warnings:
        log.warning("demo site: %s", warning)
    if settings.demo_site_repo:  # after the response: the push takes a few seconds
        defer(_publish_demo_site, folder, settings.demo_site_repo, row.version)
