from collections import Counter

from fastapi.testclient import TestClient

from app.pipeline.suite import load_items
from conftest import FakeLLM


def test_dataset_is_balanced_and_covers_every_check() -> None:
    items = load_items()
    assert len(items) == 50
    assert len({i.id for i in items}) == 50
    assert Counter(i.label for i in items) == {"approve": 25, "reject": 25}
    categories = {i.category for i in items}
    for needed in ("price_format", "multi_price", "link_format", "discount", "period", "date", "policy_promise",
                   "tricky_clean", "price_mismatch", "currency_mismatch", "unknown_product", "link",
                   "banned_phrase", "unlimited", "promise_not_covered", "promise_contradicted", "security"):
        assert needed in categories, needed


def test_suite_meets_targets(client: TestClient, fake_llm: FakeLLM) -> None:
    response = client.post("/suite/run")
    assert response.status_code == 200
    report = response.json()
    wrong = [(r["id"], r["decision"], r["reasons"]) for r in report["rows"] if not r["correct"]]

    assert report["total"] == 50
    assert report["leaked"] == 0, wrong
    assert report["caught_rate"] >= 0.95, wrong
    assert report["false_block_rate"] <= 0.10, wrong
    assert report["rule_version"] == 1
    assert report["ai_calls"] == fake_llm.calls > 0
    # Every run is audited with source "suite".
    assert client.get("/audit", params={"source": "suite"}).json()["total"] == 50
