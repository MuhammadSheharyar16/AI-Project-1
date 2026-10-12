import shutil
from pathlib import Path
from typing import Any

import pytest
from conftest import make_settings
from sqlmodel import Session

from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.rules import demo_site
from app.schemas.rules import Rules
from app.services import rules_service


class Recorder:
    """Stands in for BackgroundTasks.add_task: records what would run after the response."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def __call__(self, *args: Any) -> None:
        self.calls.append(args)


def _with_pro_price(rules: Rules, price: str) -> Rules:
    data = rules.model_dump(mode="json")
    next(p for p in data["prices"] if p["product"] == "Pro plan")["price"] = price
    return Rules.model_validate(data)


def test_get_latest_when_no_rules_saved_raises_service_unavailable(empty_session: Session) -> None:
    with pytest.raises(ServiceUnavailableError, match="no rules have been saved"):
        rules_service.get_latest(empty_session)


def test_save_when_demo_site_off_creates_next_version_only(db_session: Session, rules: Rules) -> None:
    defer = Recorder()

    row = rules_service.save(db_session, rules, "note", "Ayesha", make_settings(demo_site_dir=""), defer)

    assert row.version == 2 and rules_service.get_latest(db_session).version == 2
    assert defer.calls == []


def test_save_when_demo_site_set_rewrites_pages_and_defers_publish(
    db_session: Session, rules: Rules, tmp_path: Path
) -> None:
    site = shutil.copytree(demo_site.DEMO_SITE, tmp_path / "site")
    settings = make_settings(demo_site_dir=str(site), demo_site_repo="owner/repo")
    defer = Recorder()

    row = rules_service.save(db_session, _with_pro_price(rules, "USD 59"), None, "Ayesha", settings, defer)

    assert '<p class="price">$59</p>' in (site / demo_site.PRICING_PAGE).read_text(encoding="utf-8")
    assert len(defer.calls) == 1 and defer.calls[0][2:] == ("owner/repo", row.version)


def test_restore_when_version_exists_copies_it_as_new_version(db_session: Session, rules: Rules) -> None:
    settings = make_settings(demo_site_dir="")
    rules_service.save(db_session, _with_pro_price(rules, "USD 59"), None, "Ayesha", settings, Recorder())

    row = rules_service.restore(db_session, 1, "Ayesha", settings, Recorder())

    assert row.version == 3 and Rules.model_validate(row.body) == rules


def test_restore_when_version_missing_raises_not_found(db_session: Session) -> None:
    with pytest.raises(NotFoundError, match="rules version 99 not found"):
        rules_service.restore(db_session, 99, "Ayesha", make_settings(demo_site_dir=""), Recorder())
