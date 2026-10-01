import asyncio
import json
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app.ai.llm import GroqClient, LLMError, LLMRateLimited, LLMTimeout
from app.pipeline.checks import (
    banned, dates, links, percents, periods, policy_ai, prices, unlimited,
)
from app.pipeline.decide import decide
from app.pipeline.extract import extract
from app.schemas.facts import Fact, FactResult
from app.schemas.rules import Rules
from conftest import TEST_MODEL, FakeLLM, InventedQuoteLLM, SlowLLM, gateway


def first(answer: str, rules: Rules, kind: str) -> Fact:
    return next(f for f in extract(answer, rules) if f.type == kind)


# --- prices ---------------------------------------------------------------

@pytest.mark.parametrize("answer", [
    "Pro is $49.", "Pro is 49.00 USD.", "Pro is US$49.004.", "Basic is 4999 PKR.",
    "Pro is Rs 13,999.", "Basic is $18.", "Business is 27999 PKR.",  # each plan's other official price
])
def test_price_ok(rules: Rules, answer: str) -> None:
    assert prices.check(first(answer, rules, "price"), rules).ok


def test_price_mismatch_reason_and_rule(rules: Rules) -> None:
    result = prices.check(first("Pro is $59.", rules, "price"), rules)
    assert not result.ok
    assert result.rule == "Pro plan = USD 49"
    assert result.reason == "price mismatch: answer says USD 59, official price is USD 49"


def test_price_other_currency_is_mismatch_not_converted(rules: Rules) -> None:
    result = prices.check(first("Pro is Rs 49.", rules, "price"), rules)
    assert not result.ok
    assert result.rule == "Pro plan = PKR 13,999"
    assert result.reason == "price mismatch: answer says PKR 49, official price is PKR 13,999"


def test_price_in_currency_without_official_price(rules: Rules) -> None:
    pro = next(r for r in rules.prices if r.product == "Pro plan")
    pro.other_prices = []  # Pro now only has a USD price
    result = prices.check(first("Pro is Rs 13,999.", rules, "price"), rules)
    assert not result.ok
    assert result.reason == ("price mismatch: answer says PKR 13,999, "
                             "there is no official PKR price (official: USD 49)")


def test_price_unknown_product(rules: Rules) -> None:
    result = prices.check(first("The Enterprise plan is $499.", rules, "price"), rules)
    assert not result.ok and result.reason.startswith("price for unknown product")


# --- percents ---------------------------------------------------------------

def test_percent(rules: Rules) -> None:
    assert percents.check(first("Save 20% yearly.", rules, "percent"), rules).ok
    bad = percents.check(first("Save 30 percent.", rules, "percent"), rules)
    assert not bad.ok and bad.reason == "unapproved discount: 30%"


# --- periods ----------------------------------------------------------------

def test_period_matches_topic_policy(rules: Rules) -> None:
    answer = "Refunds are available within 14 days."
    assert periods.check(first(answer, rules, "period"), answer, rules).ok


def test_period_mismatch(rules: Rules) -> None:
    answer = "Refunds are available within 30 days."
    result = periods.check(first(answer, rules, "period"), answer, rules)
    assert not result.ok and "period mismatch" in result.reason and "14" in result.reason


def test_period_uses_the_sentence_topic(rules: Rules) -> None:
    answer = "Refunds take 14 days. The Pro trial lasts 14 days."
    facts = [f for f in extract(answer, rules) if f.type == "period"]
    assert [periods.check(f, answer, rules).ok for f in facts] == [True, False]


def test_period_without_policy_fails_closed(rules: Rules) -> None:
    answer = "Delivery takes 3 days."
    result = periods.check(first(answer, rules, "period"), answer, rules)
    assert not result.ok and "not covered by any policy" in result.reason


# --- links ------------------------------------------------------------------

@pytest.mark.parametrize("link", ["HTTPS://MuhammadSheharyar16.GitHub.io/HisaabPro/Help/", "https://www.muhammadsheharyar16.github.io/hisaabpro/pricing", "www.muhammadsheharyar16.github.io/hisaabpro/signup"])
def test_allowed_links(rules: Rules, link: str) -> None:
    assert links.check(first(f"See {link}.", rules, "link"), rules).ok


@pytest.mark.parametrize("link", ["https://hisaabpro-deals.com/pro", "http://muhammadsheharyar16.github.io/hisaabpro/help",
                                  "https://muhammadsheharyar16.github.io/hisaabpro/help?ref=x", "https://muhammadsheharyar16.github.io/hisaabpro/offers"])
def test_unapproved_links(rules: Rules, link: str) -> None:
    result = links.check(first(f"See {link} now", rules, "link"), rules)
    assert not result.ok and result.reason.startswith("unapproved link")


# --- banned phrases ---------------------------------------------------------

def test_banned_phrase_case_insensitive_with_offsets(rules: Rules) -> None:
    answer = "It is 100% GUARANTEED and Guaranteed  refund too."
    found = banned.find(answer, rules)
    assert sorted(r.fact.value for r in found) == ["100% guaranteed", "guaranteed refund"]
    assert all(answer[r.fact.start:r.fact.end] == r.fact.raw and not r.ok for r in found)


def test_no_banned_phrase(rules: Rules) -> None:
    assert banned.find("Refunds are available within 14 days.", rules) == []


# --- unlimited --------------------------------------------------------------

@pytest.mark.parametrize("answer", ["Get a refund anytime.", "Your free trial lasts forever.",
                                    "Refunds have no time limit."])
def test_unlimited_contradicts_day_limited_policy(rules: Rules, answer: str) -> None:
    result = unlimited.check(first(answer, rules, "promise"), rules)
    assert result is not None and not result.ok and "contradicts" in result.reason


def test_unlimited_ok_for_policy_without_day_limit(rules: Rules) -> None:
    assert unlimited.check(first("You can cancel at any time.", rules, "promise"), rules) is None


def test_non_unlimited_promise_left_for_ai(rules: Rules) -> None:
    assert unlimited.check(first("Refunds are available within 14 days.", rules, "promise"), rules) is None


# --- decide -----------------------------------------------------------------

def _result(kind: str, ok: bool, start: int) -> FactResult:
    return FactResult(fact=Fact(type=kind, raw="x", start=start, end=start + 1), ok=ok)


@pytest.mark.parametrize(
    ("kind", "key"),
    [("price", "pricing"), ("percent", "pricing"), ("link", "link"),
     ("promise", "policy"), ("period", "policy"), ("phrase", "policy")],
)
def test_decide_safe_message_by_type(kind: str, key: str) -> None:
    assert decide([_result("price", True, 0), _result(kind, False, 5)]) == ("Rejected", key)


def test_decide_first_failing_by_position() -> None:
    assert decide([_result("link", False, 30), _result("price", False, 2)]) == ("Rejected", "pricing")


def test_decide_approved() -> None:
    assert decide([]) == ("Approved", None)
    assert decide([_result("price", True, 0)]) == ("Approved", None)


# --- policy_ai (verified quote) --------------------------------------------


class StaticLLM:
    def __init__(self, reply: dict[str, Any]) -> None:
        self.reply = reply

    async def llm_json(self, prompt: str, timeout: float) -> dict[str, Any]:
        return self.reply


def ai_check(answer: str, rules: Rules, llm: Any, timeout: float = 1.0) -> FactResult:
    return asyncio.run(policy_ai.check(first(answer, rules, "promise"), rules, gateway(llm, timeout)))


def test_ai_supported_with_real_quote(rules: Rules) -> None:
    result = ai_check("Refunds are available within 14 days of purchase.", rules, FakeLLM())
    assert result.ok and result.rule == "Refund policy"
    assert result.quote == "Refunds are available within 14 days of purchase."


def test_ai_invented_quote_is_rejected(rules: Rules) -> None:
    result = ai_check("Refunds are available within 14 days of purchase.", rules, InventedQuoteLLM())
    assert not result.ok and result.reason.startswith("unverified quote")


@pytest.mark.parametrize(
    "reply",
    [
        {"verdict": "supported", "policy_id": "trial", "quote": "Refunds are available within 14 days of purchase."},
        {"verdict": "supported", "policy_id": "nope", "quote": "Refunds are available within 14 days of purchase."},
        {"verdict": "supported", "policy_id": "refund", "quote": "Refunds"},
        {"verdict": "supported", "policy_id": "refund", "quote": ""},
    ],
)
def test_ai_quote_must_be_in_the_named_policy(rules: Rules, reply: dict[str, Any]) -> None:
    result = ai_check("Refunds are available within 14 days.", rules, StaticLLM(reply))
    assert not result.ok and "unverified quote" in result.reason


def test_ai_quote_tolerates_whitespace_and_case(rules: Rules) -> None:
    reply = {"verdict": "supported", "policy_id": "refund",
             "quote": '"refunds are  available within\n14 days of purchase"'}
    assert ai_check("Refunds are available within 14 days.", rules, StaticLLM(reply)).ok


def test_ai_contradicted_and_not_covered(rules: Rules) -> None:
    contradicted = ai_check("No refunds are given once you have paid.", rules, FakeLLM())
    assert not contradicted.ok and contradicted.reason.startswith("contradicted")
    uncovered = ai_check("All plans include a 2-year hardware warranty.", rules, FakeLLM())
    assert not uncovered.ok and uncovered.reason.startswith("not covered")


def test_ai_malformed_verdict_raises(rules: Rules) -> None:
    with pytest.raises(ValidationError):
        ai_check("Refunds are available within 14 days.", rules, StaticLLM({"verdict": "maybe"}))


def test_ai_timeout_raises(rules: Rules) -> None:
    with pytest.raises(LLMTimeout):
        ai_check("Refunds are available within 14 days.", rules, SlowLLM(), timeout=0.05)


# --- GroqClient (offline, via httpx.MockTransport) ---------------------------

def groq(handler: Any, key: str = "test-key") -> GroqClient:
    return GroqClient(key, TEST_MODEL, transport=httpx.MockTransport(handler))


def completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_groq_request_shape_and_parse() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return completion('{"verdict": "not_covered"}')

    assert asyncio.run(groq(handler).llm_json("prompt", 1.0)) == {"verdict": "not_covered"}
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["model"] == TEST_MODEL
    assert seen["body"]["temperature"] == 0
    assert seen["body"]["response_format"] == {"type": "json_object"}


def test_groq_429_is_rate_limited() -> None:
    client = groq(lambda request: httpx.Response(429, json={"error": "slow down"}))
    with pytest.raises(LLMRateLimited):
        asyncio.run(client.llm_json("p", 1.0))


def _network_down(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("no route to host")


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(500),
        lambda request: completion("not json"),
        lambda request: completion("[1, 2]"),
        lambda request: httpx.Response(200, json={"unexpected": True}),
        _network_down,
    ],
)
def test_groq_failures_raise_llm_error(handler: Any) -> None:
    with pytest.raises(LLMError):
        asyncio.run(groq(handler).llm_json("p", 1.0))


def test_groq_without_key_raises() -> None:
    with pytest.raises(LLMError, match="GROQ_API_KEY"):
        asyncio.run(groq(lambda request: completion("{}"), key="").llm_json("p", 1.0))


# --- periods in words / other units, and dates ------------------------------

@pytest.mark.parametrize(
    ("answer", "ok"),
    [
        ("Refunds are available within two weeks of purchase.", True),
        ("Refunds are available within fourteen days.", True),
        ("The Pro trial lasts one week.", True),
        ("Refunds are available within one month.", False),
        ("Refunds are available within three weeks.", False),
    ],
)
def test_period_words_and_units_checked(rules: Rules, answer: str, ok: bool) -> None:
    assert periods.check(first(answer, rules, "period"), answer, rules).ok is ok


def test_period_reason_shows_the_answer_wording(rules: Rules) -> None:
    answer = "Refunds are available within one month."
    reason = periods.check(first(answer, rules, "period"), answer, rules).reason
    assert reason == "period mismatch: answer says one month (30 days), but Refund policy says 14 days"


def test_unlimited_respects_stated_period_in_weeks(rules: Rules) -> None:
    fact = first("Cancel anytime; refunds within two weeks.", rules, "promise")
    assert unlimited.check(fact, rules) is None


def test_date_not_in_policy_is_rejected(rules: Rules) -> None:
    answer = "Refunds are available until 31 March."
    result = dates.check(first(answer, rules, "date"), answer, rules)
    assert not result.ok
    assert result.reason == "unverified date: 31 March is not stated in Refund policy"


def test_date_without_topic_is_rejected(rules: Rules) -> None:
    answer = "The sale ends on 2026-12-01."
    result = dates.check(first(answer, rules, "date"), answer, rules)
    assert not result.ok and "any policy" in result.reason


def test_date_stated_in_policy_is_ok(rules: Rules) -> None:
    data = rules.model_dump(mode="json")
    data["policies"][0]["text"] += " Refund requests close on 31 March 2026."
    custom = Rules.model_validate(data)
    answer = "Refund requests are accepted until 31/03/2026."
    result = dates.check(first(answer, custom, "date"), answer, custom)
    assert result.ok and result.rule == "Refund policy: 31/03/2026"


def test_date_failure_picks_policy_message() -> None:
    assert decide([_result("date", False, 3)]) == ("Rejected", "policy")
