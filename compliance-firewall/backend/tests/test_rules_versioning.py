import copy
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.ai import mock_assistant
from app.rules import repository
from app.rules.seed import SEED_RULES
from app.schemas.rules import Rules


def seed() -> dict[str, Any]:
    return copy.deepcopy(SEED_RULES)


def set_price(rules: dict[str, Any], product: str, price: str) -> dict[str, Any]:
    next(p for p in rules["prices"] if p["product"] == product)["price"] = price
    return rules


def trace_note(body: dict[str, Any], step: str) -> str:
    return next(s["note"] for s in body["compliance"]["trace"] if s["step"] == step)


def check(client: TestClient, answer: str, question: str = "q") -> dict[str, Any]:
    return client.post("/check", json={"question": question, "answer": answer}).json()


def test_health_reports_seeded_v1(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body == {"status": "ok", "rule_version": 1, "ai_configured": True, "debug": True}


def test_get_rules_returns_seed(client: TestClient) -> None:
    body = client.get("/rules").json()
    assert body["version"] == 1 and body["note"] == "seed"
    assert [p["product"] for p in body["rules"]["prices"]] == ["Basic plan", "Pro plan", "Business plan"]


def test_put_creates_new_version_and_never_overwrites(client: TestClient) -> None:
    saved = client.put("/rules", json={"author": "tester", "rules": set_price(seed(), "Pro plan", "USD 59"), "note": "raise"})
    assert saved.status_code == 201
    assert saved.json()["version"] == 2

    versions = client.get("/rules/versions").json()
    assert [(v["version"], v["note"]) for v in versions] == [(2, "raise"), (1, "seed")]
    assert client.get("/rules").json()["version"] == 2
    with Session(client.app.state.engine) as session:
        assert repository.get_version(session, 1).body["prices"][1]["price"] == "USD 49"
        assert repository.get_version(session, 2).body["prices"][1]["price"] == "USD 59"


def test_restore_copies_old_version_into_new_one(client: TestClient) -> None:
    client.put("/rules", json={"author": "tester", "rules": set_price(seed(), "Pro plan", "USD 59")})
    restored = client.post("/rules/restore/1", json={"author": "tester"})
    assert restored.status_code == 201
    body = restored.json()
    assert body["version"] == 3 and body["note"] == "restored from v1"
    assert body["rules"] == client.get("/rules").json()["rules"]
    pro = next(p for p in body["rules"]["prices"] if p["product"] == "Pro plan")
    assert pro["price"] == "USD 49"
    assert len(client.get("/rules/versions").json()) == 3


def test_restore_missing_version_is_404(client: TestClient) -> None:
    assert client.post("/rules/restore/99", json={"author": "tester"}).status_code == 404


def _bad_rules() -> list[dict[str, Any]]:
    bad_price = set_price(seed(), "Pro plan", "forty-nine")
    unknown_field = seed() | {"surprise": True}
    dup_policy = seed()
    dup_policy["policies"].append(dict(dup_policy["policies"][0]))
    bad_link = seed()
    bad_link["allowed_links"].append("muhammadsheharyar16.github.io/hisaabpro/nope")
    unsafe_message = seed()
    unsafe_message["safe_messages"]["link"] = "Go to https://evil.example.com now."
    banned_in_message = seed()
    banned_in_message["safe_messages"]["policy"] = "Guaranteed refund for everyone."
    missing = seed()
    del missing["safe_messages"]
    return [bad_price, unknown_field, dup_policy, bad_link, unsafe_message, banned_in_message, missing]


@pytest.mark.parametrize("rules", _bad_rules())
def test_invalid_rules_are_rejected_without_new_version(client: TestClient, rules: dict[str, Any]) -> None:
    assert client.put("/rules", json={"author": "tester", "rules": rules}).status_code == 422
    assert [v["version"] for v in client.get("/rules/versions").json()] == [1]


def test_repository_has_no_way_to_overwrite() -> None:
    assert not any(hasattr(repository, n) for n in ("update", "update_version", "overwrite", "delete"))


def test_cache_reloads_only_when_version_changes(client: TestClient) -> None:
    answer = "The Pro plan costs $49 per month."
    assert trace_note(check(client, answer), "load_rules") == "reloaded (v1)"
    assert trace_note(check(client, answer), "load_rules") == "cache hit (v1)"
    client.put("/rules", json={"author": "tester", "rules": set_price(seed(), "Pro plan", "USD 59")})
    changed = check(client, answer)
    assert trace_note(changed, "load_rules") == "reloaded (v2)"
    assert changed["compliance"]["decision"] == "Rejected"
    assert trace_note(check(client, answer), "load_rules") == "cache hit (v2)"


def test_accurate_chat_quotes_the_current_prices(client: TestClient) -> None:
    client.put("/rules", json={"author": "tester", "rules": set_price(seed(), "Basic plan", "Rs 499")})
    body = client.post("/chat", json={"question": "How much is Basic?", "mode": "accurate"}).json()
    assert body["compliance"]["decision"] == "Approved"
    assert "Basic plan is Rs 499" in body["compliance"]["raw_answer"]


def test_accurate_drafts_follow_edited_policies_and_discounts() -> None:
    edited = seed()
    edited["discounts"] = [{"name": "Annual billing", "percent": 25}]
    edited["policies"][0]["text"] = "Refunds are available within 30 days of purchase."
    rules = Rules.model_validate(edited)
    assert mock_assistant.draft("Any discounts?", "accurate", rules) == "Annual billing gives you a 25% discount."
    assert mock_assistant.draft("Refund policy?", "accurate", rules) == edited["policies"][0]["text"]
    assert mock_assistant.draft("Is there a free trial?", "accurate", rules) == edited["policies"][1]["text"]
    assert "guaranteed refund" in mock_assistant.draft("Refund policy?", "mistakes", rules)


# --- audit log --------------------------------------------------------------

def test_audit_list_filters_and_order(client: TestClient) -> None:
    check(client, "The Pro plan costs $49 per month.", question="pro price")
    check(client, "Pro is $59", question="pro price wrong")
    client.post("/chat", json={"question": "Tell me about refunds", "mode": "mistakes"})
    client.put("/rules", json={"author": "tester", "rules": set_price(seed(), "Pro plan", "USD 59")})
    check(client, "Pro is $59", question="after change")

    everything = client.get("/audit").json()
    assert everything["total"] == 4
    assert [i["id"] for i in everything["items"]] == [4, 3, 2, 1]  # newest first

    def ids(**params: Any) -> list[int]:
        return [i["id"] for i in client.get("/audit", params=params).json()["items"]]

    assert ids(decision="Approved") == [4, 1]
    assert ids(decision="Rejected") == [3, 2]
    assert ids(version=2) == [4]
    assert ids(source="chat") == [3]
    assert ids(q="WRONG") == [2]
    assert ids(q="$59") == [4, 2]
    assert ids(limit=2, offset=1) == [3, 2]
    assert client.get("/audit", params={"decision": "Maybe"}).status_code == 422


def test_audit_entry_has_full_record(client: TestClient) -> None:
    body = check(client, "Pro is $59", question="how much is pro?")
    entry = client.get(f"/audit/{body['compliance']['audit_id']}").json()
    assert entry["question"] == "how much is pro?"
    assert entry["raw_answer"] == "Pro is $59"
    assert entry["shown_to_customer"] == SEED_RULES["safe_messages"]["pricing"]
    assert entry["decision"] == "Rejected" and entry["rule_version"] == 1
    assert entry["results"][0]["fact"]["raw"] == "$59"
    assert [s["step"] for s in entry["trace"]][-1] == "audit"
    assert entry["source"] == "scenario" and entry["recheck_of"] is None and entry["error"] is None


def test_audit_missing_is_404(client: TestClient) -> None:
    assert client.get("/audit/999").status_code == 404
    assert client.post("/audit/999/recheck").status_code == 404
