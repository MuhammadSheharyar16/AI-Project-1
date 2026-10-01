"""Versioned, append-only storage for rules. There is deliberately no update function."""

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col, select

from app.models.rule_set import RuleSet
from app.schemas.rules import Rules


class VersionConflict(Exception):
    """Another save created the same version number first."""


def latest_version_number(session: Session) -> int | None:
    return session.exec(select(func.max(RuleSet.version))).one()


def get_version(session: Session, version: int) -> RuleSet | None:
    return session.get(RuleSet, version)


def get_latest(session: Session) -> RuleSet | None:
    latest = latest_version_number(session)
    return None if latest is None else get_version(session, latest)


def list_versions(session: Session) -> list[RuleSet]:
    return list(session.exec(select(RuleSet).order_by(col(RuleSet.version).desc())))


def save_new_version(
    session: Session, rules: Rules, note: str | None = None, author: str | None = None
) -> RuleSet:
    """Insert rules as version N+1. Never overwrites an existing version."""
    row = RuleSet(
        version=(latest_version_number(session) or 0) + 1,
        note=note,
        author=author,
        body=rules.model_dump(mode="json"),
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise VersionConflict(f"version {row.version} already exists") from exc
    session.refresh(row)
    return row


def restore_version(session: Session, version: int, author: str | None = None) -> RuleSet | None:
    """Copy an old version into a brand new version. Returns None if it does not exist."""
    old = get_version(session, version)
    if old is None:
        return None
    return save_new_version(
        session, Rules.model_validate(old.body), note=f"restored from v{version}", author=author
    )
