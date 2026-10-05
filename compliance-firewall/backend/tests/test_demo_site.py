import base64
import copy
import hashlib
import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.rules import demo_site
from app.rules.seed import SEED_RULES
from app.schemas.rules import Rules
from tests.conftest import make_settings


def site_copy(tmp_path: Path) -> Path:
    """A copy of the real site, set to the seed rules (rule saves keep rewriting the real one)."""
    site = Path(shutil.copytree(demo_site.DEMO_SITE, tmp_path / "site"))
    demo_site.sync(site, Rules.model_validate(SEED_RULES))
    return site


def test_syncing_the_same_rules_again_changes_nothing(tmp_path: Path) -> None:
    assert demo_site.sync(site_copy(tmp_path), Rules.model_validate(SEED_RULES)) == ([], [])


def test_edited_rules_are_written_to_the_pages(tmp_path: Path) -> None:
    edited = copy.deepcopy(SEED_RULES)
    edited["prices"][0]["price"] = "Rs 499"
    edited["prices"][1]["price"] = "USD 59"
    edited["discounts"][0]["percent"] = 25
    edited["policies"][0]["text"] = "Refunds are available within 30 days of purchase."
    site = site_copy(tmp_path)

    changed, warnings = demo_site.sync(site, Rules.model_validate(edited))

    assert changed == [demo_site.PRICING_PAGE, demo_site.POLICIES_PAGE] and warnings == []
    pricing = (site / demo_site.PRICING_PAGE).read_text(encoding="utf-8")
    assert '<p class="price">Rs 499</p>' in pricing and '<p class="alt-price">or $18</p>' in pricing
    assert '<p class="price">Rs 13,999</p>' in pricing and '<p class="alt-price">or $59</p>' in pricing
    assert "save 25% when you pay" in pricing
    policies = (site / demo_site.POLICIES_PAGE).read_text(encoding="utf-8")
    assert "<p>Refunds are available within 30 days of purchase.</p>" in policies
    assert "7-day free trial. No card" in policies  # untouched policies keep their wording


def test_rules_without_a_matching_block_are_reported(tmp_path: Path) -> None:
    edited = copy.deepcopy(SEED_RULES)
    edited["prices"].append({"product": "Enterprise plan", "aliases": [], "price": "USD 499", "other_prices": []})
    changed, warnings = demo_site.sync(site_copy(tmp_path), Rules.model_validate(edited))
    assert changed == [] and warnings == ["pricing page has no card for plan 'Enterprise plan'"]


def test_publish_pushes_only_pages_that_differ_from_the_live_site(tmp_path: Path) -> None:
    site = site_copy(tmp_path)
    policies = (site / demo_site.POLICIES_PAGE).read_bytes().replace(b"\r\n", b"\n")
    live = {"repos/o/r/contents/pricing/index.html": "stale",
            "repos/o/r/contents/help/policies/index.html":
                hashlib.sha1(b"blob %d\0" % len(policies) + policies).hexdigest()}
    puts: list[dict[str, str]] = []

    def fake_gh(args: list[str], body: str | None = None) -> str:
        if body is None:
            return live[args[0]]
        puts.append(json.loads(body) | {"endpoint": args[-1]})
        return ""

    assert demo_site.publish(site, "o/r", "msg", fake_gh) == [demo_site.PRICING_PAGE]
    assert [(p["endpoint"], p["sha"], p["message"]) for p in puts] == [
        ("repos/o/r/contents/pricing/index.html", "stale", "msg")]
    assert b"Plans and prices" in base64.b64decode(puts[0]["content"])


def test_saving_rules_updates_the_configured_site(tmp_path: Path) -> None:
    site = site_copy(tmp_path)
    settings = make_settings(database_url=f"sqlite:///{tmp_path.as_posix()}/test.db", debug=True,
                             demo_site_dir=str(site))
    edited = copy.deepcopy(SEED_RULES)
    edited["prices"][0]["price"] = "Rs 499"
    with TestClient(create_app(settings)) as client:
        assert client.put("/rules", json={"author": "tester", "rules": edited}).status_code == 201
        assert '<p class="price">Rs 499</p>' in (site / demo_site.PRICING_PAGE).read_text(encoding="utf-8")
        assert client.post("/rules/restore/1", json={"author": "tester"}).status_code == 201
        assert '<p class="price">Rs 4,999</p>' in (site / demo_site.PRICING_PAGE).read_text(encoding="utf-8")
