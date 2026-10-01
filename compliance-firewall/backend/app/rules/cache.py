"""In-memory rules cache. Reloads only when the latest version number changes."""

import threading

from sqlmodel import Session

from app.rules import repository
from app.schemas.rules import Rules


class RulesUnavailable(Exception):
    """No rules exist in the database."""


class RulesCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._version: int | None = None
        self._rules: Rules | None = None

    def get_rules(self, session: Session) -> tuple[int, Rules, str]:
        """Return (version, rules, cache_note)."""
        latest = repository.latest_version_number(session)
        if latest is None:
            raise RulesUnavailable("no rules have been saved")
        with self._lock:
            if self._version == latest and self._rules is not None:
                return latest, self._rules, f"cache hit (v{latest})"
            row = repository.get_version(session, latest)
            if row is None:
                raise RulesUnavailable(f"rules v{latest} disappeared")
            self._rules = Rules.model_validate(row.body)
            self._version = latest
            return latest, self._rules, f"reloaded (v{latest})"
