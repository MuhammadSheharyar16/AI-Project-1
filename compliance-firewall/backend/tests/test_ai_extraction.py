"""AI-assisted fact extraction (pattern rules + AI): gating, grounding, and code checks on AI facts."""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.prompts import EXTRACT_TASK
from app.pipeline.extract import extract
from app.pipeline.extract_ai import needs_ai
from app.rules.seed import SEED_RULES
from app.schemas.rules import Rules
from conftest import FakeLLM, use_llm

SAFE = SEED_RULES["safe_messages"]


class ScriptedExtractor(FakeLLM):
    """Returns scripted facts for extraction prompts; judges promises like FakeLLM."""

    def __init__(self, reply: Any) -> None:
        super().__init__()
        self.reply = reply
        self.extract_calls = 0

    async def llm_json(self, prompt: str, timeout: float) -> dict[str, Any]:
        if prompt.startswith(EXTRACT_TASK):
            self.calls += 1
            self.extract_calls += 1
            return self.reply
        return await super().llm_json(prompt, timeout)


def run(app: FastAPI, client: TestClient, answer: str, reply: Any) -> tuple[dict[str, Any], ScriptedExtractor]:
    llm = ScriptedExtractor(reply)
    use_llm(app, llm)
    response = client.post("/check", json={"question": "q", "answer": answer})
    assert response.status_code == 200, response.text
    return response.json(), llm


def step(body: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in body["compliance"]["trace"] if s["step"] == name)


# --- gate: only call the AI when the pattern rules left cues unexplained --------

@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("Hi! How can I help?", False),
        ("Feel free to ask me anything.", False),
        ("The Pro plan costs $49 per month.", False),  # every cue explained by the price fact
        ("See https://muhammadsheharyar16.github.io/hisaabpro/help for details.", False),
        ("Refunds are available within 14 days of purchase.", False),
        ("Pro is forty-nine bucks a month.", True),
        ("Visit hisaabpro-deals dot com today.", True),
        ("Get half off this week.", True),
        ("We will reimburse you in full.", True),
        ("Call us on extension 4412.", True),
    ],
)
def test_needs_ai_gate(rules: Rules, answer: str, expected: bool) -> None:
    assert needs_ai(answer, extract(answer, rules)) is expected


def test_no_cues_means_no_ai_call(app: FastAPI, client: TestClient) -> None:
    body, llm = run(app, client, "The Pro plan costs $49 per month.", {"facts": []})
    assert llm.extract_calls == 0
    assert step(body, "ai_extract")["status"] == "skipped"


# --- AI facts are grounded, then code-checked -------------------------------------

def test_ai_price_in_words_is_approved(app: FastAPI, client: TestClient) -> None:
    answer = "Pro is forty-nine bucks a month."
    reply = {"facts": [{"type": "price", "quote": "forty-nine bucks", "amount": 49,
                        "currency": "USD", "product": "Pro plan"}]}
    body, llm = run(app, client, answer, reply)
    c = body["compliance"]
    assert c["decision"] == "Approved" and body["customer"]["text"] == answer
    [result] = c["results"]
    assert result["fact"]["source"] == "ai" and result["fact"]["raw"] == "forty-nine bucks"
    assert answer[result["fact"]["start"]:result["fact"]["end"]] == "forty-nine bucks"
    assert result["rule"] == "Pro plan = USD 49" and result["ok"]
    assert c["ai_used"] is True and llm.extract_calls == 1
    assert "1 new fact" in step(body, "ai_extract")["note"]


def test_ai_wrong_price_in_words_is_rejected(app: FastAPI, client: TestClient) -> None:
    reply = {"facts": [{"type": "price", "quote": "fifty-nine bucks", "amount": 59,
                        "currency": "usd", "product": "pro"}]}
    body, _ = run(app, client, "Pro is fifty-nine bucks a month.", reply)
    assert body["compliance"]["decision"] == "Rejected"
    assert body["customer"]["text"] == SAFE["pricing"]
    [bad] = body["compliance"]["results"]
    assert bad["reason"] == "price mismatch: answer says USD 59, official price is USD 49"
    assert step(body, "ai_check")["status"] == "skipped"


def test_ai_obfuscated_link_is_checked(app: FastAPI, client: TestClient) -> None:
    good = {"facts": [{"type": "link", "quote": "muhammadsheharyar16 dot github dot io slash hisaabpro slash help", "url": "https://muhammadsheharyar16.github.io/hisaabpro/help"}]}
    body, _ = run(app, client, "Visit muhammadsheharyar16 dot github dot io slash hisaabpro slash help for more.", good)
    assert body["compliance"]["decision"] == "Approved"
    bad = {"facts": [{"type": "link", "quote": "hisaabpro-deals dot com", "url": "https://hisaabpro-deals.com"}]}
    body, _ = run(app, client, "Visit hisaabpro-deals dot com today.", bad)
    assert body["compliance"]["decision"] == "Rejected"
    assert body["customer"]["text"] == SAFE["link"]


def test_ai_percent_in_words_is_checked(app: FastAPI, client: TestClient) -> None:
    reply = {"facts": [{"type": "discount", "quote": "half off", "number": 50}]}  # alias -> percent
    body, _ = run(app, client, "Get half off this week.", reply)
    assert body["compliance"]["decision"] == "Rejected"
    assert body["compliance"]["results"][0]["reason"] == "unapproved discount: 50%"


def test_ai_promise_without_keyword_goes_to_policy_check(app: FastAPI, client: TestClient) -> None:
    answer = "If you are unhappy we will reimburse you in full."
    reply = {"facts": [{"type": "promise", "quote": "we will reimburse you in full"}]}
    body, llm = run(app, client, answer, reply)
    c = body["compliance"]
    assert c["decision"] == "Rejected" and body["customer"]["text"] == SAFE["policy"]
    [promise] = c["results"]
    assert promise["fact"]["source"] == "ai" and promise["fact"]["raw"] == answer  # whole sentence
    assert promise["reason"].startswith("not covered")
    assert llm.calls == 2  # extract + verify
    assert [call["purpose"] for call in c["governance"]["ai_calls"]] == ["extract", "verify"]


def test_ai_fact_missing_fields_fails_closed(app: FastAPI, client: TestClient) -> None:
    reply = {"facts": [{"type": "price", "quote": "forty-nine bucks"}]}  # no amount/currency
    body, _ = run(app, client, "Pro is forty-nine bucks.", reply)
    assert body["compliance"]["decision"] == "Rejected"
    assert body["compliance"]["results"][0]["reason"].startswith("unreadable price")


def test_hallucinated_invalid_and_duplicate_facts_are_dropped(app: FastAPI, client: TestClient) -> None:
    answer = "Pro is $49, about forty-nine bucks."
    reply = {"facts": [
        {"type": "price", "quote": "$99", "amount": 99, "currency": "USD"},          # not in answer
        {"type": "weather", "quote": "Pro"},                                          # invalid type
        {"type": "price", "quote": "$49", "amount": 49, "currency": "USD"},          # pattern found it
        {"type": "price", "quote": "forty-nine  BUCKS", "amount": 49, "currency": "USD",
         "product": "Pro plan"},                                                      # grounded loosely
    ]}
    body, _ = run(app, client, answer, reply)
    assert body["compliance"]["decision"] == "Approved"
    sources = sorted(r["fact"]["source"] for r in body["compliance"]["results"])
    assert sources == ["ai", "pattern"]
    assert step(body, "ai_extract")["note"].startswith("1 new fact(s), 2 discarded (ungrounded/invalid), 1 already found")


@pytest.mark.parametrize("reply", [{"nope": []}, {"facts": "none"}, {"facts": [{}] * 26}])
def test_malformed_extraction_is_error(app: FastAPI, client: TestClient, reply: Any) -> None:
    body, _ = run(app, client, "Pro is forty-nine bucks.", reply)
    assert body["compliance"]["decision"] == "Error"
    assert body["customer"]["text"] == SAFE["general"]
    assert step(body, "ai_extract")["status"] == "failed"


def test_code_failure_skips_ai_extraction(app: FastAPI, client: TestClient) -> None:
    body, llm = run(app, client, "Pro is $59, just fifty-nine bucks.", {"facts": []})
    assert body["compliance"]["decision"] == "Rejected"
    assert llm.calls == 0
    assert step(body, "ai_extract")["note"] == "a code check failed"
