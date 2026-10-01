"""The 12 cases from the client brief."""

from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.llm import GroqClient
from app.rules.seed import SEED_RULES
from conftest import TEST_MODEL, CrashingLLM, FakeLLM, InventedQuoteLLM, SlowLLM, use_llm

SAFE = SEED_RULES["safe_messages"]


def check(client: TestClient, answer: str, question: str = "q", **params: str) -> dict[str, Any]:
    response = client.post("/check", json={"question": question, "answer": answer}, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def failures(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in body["compliance"]["results"] if not r["ok"]]


def assert_approved(body: dict[str, Any], answer: str) -> None:
    assert body["compliance"]["decision"] == "Approved", body["compliance"]["results"]
    assert body["customer"]["text"] == answer
    assert body["compliance"]["audit_id"] is not None
    assert body["compliance"]["rule_version"] == 1


def test_case_1_correct_pro_price(client: TestClient) -> None:
    answer = "The Pro plan costs $49 per month."
    body = check(client, answer)
    assert_approved(body, answer)
    assert body["compliance"]["ai_used"] is False


def test_case_2_greeting_skips_ai(client: TestClient, fake_llm: FakeLLM) -> None:
    answer = "Hi! How can I help?"
    body = check(client, answer)
    assert_approved(body, answer)
    assert body["compliance"]["ai_used"] is False
    assert body["compliance"]["results"] == []
    assert fake_llm.calls == 0
    steps = {s["step"]: s["status"] for s in body["compliance"]["trace"]}
    assert steps["code_checks"] == "skipped" and steps["ai_check"] == "skipped"


def test_case_3_refund_policy_verified_by_ai(client: TestClient, fake_llm: FakeLLM) -> None:
    answer = "Refunds are available within 14 days of purchase."
    body = check(client, answer)
    assert_approved(body, answer)
    assert body["compliance"]["ai_used"] is True
    assert fake_llm.calls == 1
    promise = next(r for r in body["compliance"]["results"] if r["fact"]["type"] == "promise")
    assert promise["ok"] and promise["quote"] == "Refunds are available within 14 days of purchase."


def test_case_4_pkr_formats_match(client: TestClient) -> None:
    answer = "The Basic plan is 4999 PKR per month."
    body = check(client, answer)
    assert_approved(body, answer)
    [price] = body["compliance"]["results"]
    assert price["rule"] == "Basic plan = PKR 4,999"


def test_case_5_only_wrong_price_flagged(client: TestClient) -> None:
    body = check(client, "Basic is Rs 4,999, Pro is $49 and Business is $129")
    assert body["compliance"]["decision"] == "Rejected"
    [bad] = failures(body)
    assert bad["fact"]["raw"] == "$129"
    assert bad["reason"] == "price mismatch: answer says USD 129, official price is USD 99"
    assert len(body["compliance"]["results"]) == 3
    assert body["customer"]["text"] == SAFE["pricing"]


def test_case_6_link_formatting_normalised(client: TestClient) -> None:
    answer = "You can find everything at HTTPS://MuhammadSheharyar16.GitHub.io/HisaabPro/Help/"
    assert_approved(check(client, answer), answer)


def test_case_8_wrong_price_gets_pricing_message(client: TestClient) -> None:
    body = check(client, "Pro is $59")
    assert body["compliance"]["decision"] == "Rejected"
    assert body["customer"]["text"] == SAFE["pricing"]
    assert "price mismatch" in failures(body)[0]["reason"]
    assert body["compliance"]["raw_answer"] == "Pro is $59"
    assert body["compliance"]["ai_used"] is False


def test_case_9_unapproved_link(client: TestClient) -> None:
    body = check(client, "Claim your deal at https://hisaabpro-deals.com/pro today.")
    assert body["compliance"]["decision"] == "Rejected"
    assert body["customer"]["text"] == SAFE["link"]
    assert "unapproved link" in failures(body)[0]["reason"]


def test_case_10_banned_phrase_and_unlimited(client: TestClient, fake_llm: FakeLLM) -> None:
    body = check(client, "Guaranteed refund anytime")
    assert body["compliance"]["decision"] == "Rejected"
    reasons = [r["reason"] for r in failures(body)]
    assert any("banned phrase" in r for r in reasons)
    assert any("contradicts 14-day policy" in r for r in reasons)
    assert body["customer"]["text"] == SAFE["policy"]
    assert fake_llm.calls == 0  # a code check failed, so the AI is skipped


def test_case_11_simulated_crash_fails_closed(client: TestClient) -> None:
    body = check(client, "The Pro plan costs $49 per month.", simulate="crash")
    assert body["compliance"]["decision"] == "Error"
    assert body["customer"]["text"] == SAFE["general"]
    assert "simulated crash" in body["compliance"]["error"]
    assert body["compliance"]["audit_id"] is not None


def test_case_12_simulated_timeout_fails_closed(client: TestClient) -> None:
    body = check(client, "The Pro plan costs $49 per month.", simulate="timeout")
    assert body["compliance"]["decision"] == "Error"
    assert body["customer"]["text"] == SAFE["general"]
    assert "timed out" in body["compliance"]["error"]
    failed = [s for s in body["compliance"]["trace"] if s["status"] == "failed"]
    assert [s["step"] for s in failed] == ["simulate"]


def test_simulate_forbidden_without_debug(client: TestClient) -> None:
    client.app.state.settings.debug = False
    response = client.post("/check", json={"answer": "hi"}, params={"simulate": "crash"})
    assert response.status_code == 403


def test_chat_modes(client: TestClient) -> None:
    good = client.post("/chat", json={"question": "How much is Pro?", "mode": "accurate"}).json()
    bad = client.post("/chat", json={"question": "How much is Pro?", "mode": "mistakes"}).json()
    assert good["compliance"]["decision"] == "Approved"
    assert bad["compliance"]["decision"] == "Rejected"
    assert bad["customer"]["text"] != bad["compliance"]["raw_answer"]


# --- fail-closed on real AI failures -------------------------------------------


PROMISE = "Refunds are available within 14 days of purchase."


def assert_error(body: dict[str, Any], contains: str) -> None:
    assert body["compliance"]["decision"] == "Error"
    assert body["customer"]["text"] == SAFE["general"]
    assert body["customer"]["text"] != body["compliance"]["raw_answer"]
    assert contains in body["compliance"]["error"]


def test_invented_quote_is_rejected_as_unverified(app: FastAPI, client: TestClient) -> None:
    use_llm(app, InventedQuoteLLM())
    body = check(client, PROMISE)
    assert body["compliance"]["decision"] == "Rejected"
    assert body["customer"]["text"] == SAFE["policy"]
    assert "unverified quote" in failures(body)[0]["reason"]


def test_slow_ai_times_out_to_error(app: FastAPI, client: TestClient) -> None:
    use_llm(app, SlowLLM())
    assert_error(check(client, PROMISE), "timed out")


def test_crashing_ai_is_error(app: FastAPI, client: TestClient) -> None:
    use_llm(app, CrashingLLM())
    assert_error(check(client, PROMISE), "provider exploded")


def test_groq_429_is_error(app: FastAPI, client: TestClient) -> None:
    use_llm(app, GroqClient("k", "m", transport=httpx.MockTransport(lambda r: httpx.Response(429))))
    assert_error(check(client, PROMISE), "429")


def test_missing_groq_key_is_error(app: FastAPI, client: TestClient) -> None:
    use_llm(app, GroqClient("", TEST_MODEL))
    assert_error(check(client, PROMISE), "GROQ_API_KEY")


def test_audit_failure_is_error(client: TestClient, monkeypatch: Any) -> None:
    from app.audit import repository

    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(repository, "save", boom)
    body = check(client, "The Pro plan costs $49 per month.")
    assert_error(body, "audit save failed")
    assert body["compliance"]["audit_id"] is None


def test_case_7_rule_change_flips_recheck(client: TestClient) -> None:
    original = check(client, "The Pro plan costs $49 per month.")
    assert original["compliance"]["decision"] == "Approved"
    assert original["compliance"]["rule_version"] == 1
    old_id = original["compliance"]["audit_id"]

    rules = client.get("/rules").json()["rules"]
    next(p for p in rules["prices"] if p["product"] == "Pro plan")["price"] = "USD 59"
    saved = client.put("/rules", json={"author": "tester", "rules": rules, "note": "Pro price rise"})
    assert saved.status_code == 201 and saved.json()["version"] == 2

    recheck = client.post(f"/audit/{old_id}/recheck").json()["compliance"]
    assert recheck["decision"] == "Rejected"
    assert recheck["rule_version"] == 2
    assert "price mismatch" in recheck["results"][0]["reason"]

    entry = client.get(f"/audit/{recheck['audit_id']}").json()
    assert entry["recheck_of"] == old_id
    assert entry["source"] == "recheck"
    assert entry["rule_version"] == 2
    # The original decision is untouched.
    old = client.get(f"/audit/{old_id}").json()
    assert (old["decision"], old["rule_version"], old["recheck_of"]) == ("Approved", 1, None)


# --- compliance view lists every extracted fact ---------------------------------

def test_every_fact_is_listed_even_when_ai_is_skipped(client: TestClient, fake_llm: FakeLLM) -> None:
    body = check(client, "Refunds are available within 14 days of purchase. Pro is $59.")
    c = body["compliance"]
    assert c["decision"] == "Rejected" and c["ai_used"] is False and fake_llm.calls == 0
    # The promise comes first in the answer, but only a real failure picks the message.
    assert body["customer"]["text"] == SAFE["pricing"]
    by_type = {r["fact"]["type"]: r for r in c["results"]}
    assert set(by_type) == {"promise", "period", "price"}
    assert by_type["promise"]["skipped"] is True and by_type["promise"]["ok"] is False
    assert "not checked" in by_type["promise"]["reason"]
    assert by_type["price"]["skipped"] is False and "price mismatch" in by_type["price"]["reason"]


def test_every_fact_is_listed_on_error(app: FastAPI, client: TestClient) -> None:
    use_llm(app, CrashingLLM())
    c = check(client, "Pro is $49. Refunds are available within 14 days of purchase.")["compliance"]
    assert c["decision"] == "Error"
    promise = next(r for r in c["results"] if r["fact"]["type"] == "promise")
    assert promise["skipped"] is True and "stopped with an error" in promise["reason"]
    assert {r["fact"]["type"] for r in c["results"]} == {"price", "period", "promise"}
