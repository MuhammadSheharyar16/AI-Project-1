"""AI governance: call ledger, model/prompt provenance, kill switch, budget, reviews, report."""

from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.governance import AIBudget
from app.ai.llm import GroqClient
from app.ai.prompts import PROMPT_VERSION
from app.rules.seed import SEED_RULES
from conftest import TEST_MODEL, FakeLLM, SlowLLM, use_llm

SAFE = SEED_RULES["safe_messages"]
PROMISE = "Refunds are available within 14 days of purchase."


def check(client: TestClient, answer: str) -> dict[str, Any]:
    return client.post("/check", json={"question": "q", "answer": answer}).json()


def test_every_ai_call_is_recorded_with_model_and_prompt_version(client: TestClient) -> None:
    body = check(client, PROMISE)
    gov = body["compliance"]["governance"]
    assert gov["ai_model"] == TEST_MODEL
    assert gov["prompt_version"] == PROMPT_VERSION and len(PROMPT_VERSION) == 12
    [call] = gov["ai_calls"]
    assert call["purpose"] == "verify" and call["outcome"] == "ok"
    assert call["model"] == TEST_MODEL and call["prompt_version"] == PROMPT_VERSION

    entry = client.get(f"/audit/{body['compliance']['audit_id']}").json()
    assert entry["ai_model"] == TEST_MODEL and entry["prompt_version"] == PROMPT_VERSION
    assert entry["ai_calls"][0]["outcome"] == "ok"


def test_no_ai_means_empty_ledger(client: TestClient) -> None:
    gov = check(client, "The Pro plan costs $49 per month.")["compliance"]["governance"]
    assert gov["ai_calls"] == []


def test_kill_switch_fails_closed_without_calling_the_llm(client: TestClient, fake_llm: FakeLLM) -> None:
    client.app.state.settings.ai_enabled = False
    body = check(client, PROMISE)
    assert body["compliance"]["decision"] == "Error"
    assert body["customer"]["text"] == SAFE["general"]
    assert "AI_ENABLED=false" in body["compliance"]["error"]
    assert fake_llm.calls == 0 and body["compliance"]["ai_used"] is False
    assert body["compliance"]["governance"]["ai_calls"][0]["outcome"] == "disabled"
    # Answers that need no AI keep working.
    assert check(client, "The Pro plan costs $49 per month.")["compliance"]["decision"] == "Approved"


def test_budget_stops_ai_calls_and_fails_closed(client: TestClient, fake_llm: FakeLLM) -> None:
    client.app.state.ai_budget = AIBudget(max_per_minute=1)
    assert check(client, PROMISE)["compliance"]["decision"] == "Approved"
    second = check(client, PROMISE)
    assert second["compliance"]["decision"] == "Error"
    assert "budget" in second["compliance"]["error"]
    assert second["compliance"]["governance"]["ai_calls"][0]["outcome"] == "budget_exceeded"
    assert fake_llm.calls == 1


def test_budget_window() -> None:
    budget = AIBudget(max_per_minute=2)
    assert [budget.try_acquire() for _ in range(3)] == [True, True, False]


def test_failed_calls_are_recorded(app: FastAPI, client: TestClient) -> None:
    use_llm(app, SlowLLM())
    assert check(client, PROMISE)["compliance"]["governance"]["ai_calls"][0]["outcome"] == "timeout"
    use_llm(app, GroqClient("k", "m", transport=httpx.MockTransport(lambda r: httpx.Response(429))))
    assert check(client, PROMISE)["compliance"]["governance"]["ai_calls"][0]["outcome"] == "rate_limited"


def test_human_review_is_append_only_and_shown_on_the_entry(client: TestClient) -> None:
    audit_id = check(client, "Pro is $59")["compliance"]["audit_id"]
    first = client.post(f"/audit/{audit_id}/review",
                        json={"reviewer": "Ayesha", "verdict": "agree", "note": "correct block"})
    assert first.status_code == 201 and first.json()["verdict"] == "agree"
    client.post(f"/audit/{audit_id}/review", json={"reviewer": "Bilal", "verdict": "disagree"})

    entry = client.get(f"/audit/{audit_id}").json()
    assert [(r["reviewer"], r["verdict"]) for r in entry["reviews"]] == [("Ayesha", "agree"), ("Bilal", "disagree")]
    assert entry["decision"] == "Rejected"  # a review never changes the recorded decision

    assert client.post("/audit/999/review", json={"reviewer": "A", "verdict": "agree"}).status_code == 404
    assert client.post(f"/audit/{audit_id}/review", json={"reviewer": "A", "verdict": "maybe"}).status_code == 422
    assert client.post(f"/audit/{audit_id}/review", json={"reviewer": "", "verdict": "agree"}).status_code == 422


def test_rule_versions_record_the_author(client: TestClient) -> None:
    client.put("/rules", json={"rules": SEED_RULES, "author": "Sara (compliance)", "note": "review"})
    versions = client.get("/rules/versions").json()
    assert [(v["version"], v["author"]) for v in versions] == [(2, "Sara (compliance)"), (1, "system")]
    assert client.get("/rules").json()["author"] == "Sara (compliance)"


def test_governance_report(app: FastAPI, client: TestClient) -> None:
    check(client, PROMISE)                                    # 1 AI call, Approved
    check(client, "Pro is $59")                               # Rejected, no AI
    audit_id = check(client, "Hi!")["compliance"]["audit_id"]  # Approved, no AI
    client.post(f"/audit/{audit_id}/review", json={"reviewer": "A", "verdict": "disagree"})
    use_llm(app, SlowLLM())
    check(client, PROMISE)                                    # Error: timeout

    report = client.get("/governance").json()
    assert report["ai"]["model"] == TEST_MODEL
    assert report["ai"]["prompt_version"] == PROMPT_VERSION
    assert report["ai"]["temperature"] == 0 and report["ai"]["json_mode"] is True
    assert report["ai"]["enabled"] is True and report["ai"]["max_calls_per_minute"] == 25
    assert report["decisions"] == {"Approved": 2, "Rejected": 1, "Error": 1}
    assert report["ai_usage"]["calls_by_outcome"] == {"ok": 1, "timeout": 1}
    assert report["ai_usage"]["calls_by_purpose"] == {"verify": 2}
    assert report["human_review"] == {"reviews": 1, "agree": 0, "disagree": 1, "disagreement_rate": 1.0}
    assert report["rules"]["latest_version"] == 1 and report["rules"]["latest_author"] == "system"
    assert any("prompt-injection" in c for c in report["security_controls"])
    assert any("ADMIN_TOKEN is not set" in c for c in report["security_controls"])
