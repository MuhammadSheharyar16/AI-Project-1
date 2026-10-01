"""AI promise check. A 'supported' verdict only counts with a VERIFIED word-for-word quote."""

import re
from typing import Literal

from pydantic import BaseModel, field_validator

from app.ai.governance import AIGateway
from app.ai.prompts import policy_check_prompt
from app.schemas.facts import Fact, FactResult
from app.schemas.rules import Rules

MIN_QUOTE_WORDS = 3


class AIVerdict(BaseModel):
    verdict: Literal["supported", "contradicted", "not_covered"]
    policy_id: str | None = None
    quote: str | None = None
    reason: str = ""

    @field_validator("policy_id", "quote", mode="before")
    @classmethod
    def _blank_is_none(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().strip("\"'“”‘’").strip().lower()


def quote_is_verified(quote: str | None, policy_text: str) -> bool:
    if not quote:
        return False
    q = _squash(quote)
    return len(q.split()) >= MIN_QUOTE_WORDS and q in _squash(policy_text)


async def check(fact: Fact, rules: Rules, gateway: AIGateway) -> FactResult:
    """Raises on LLM failure / timeout / malformed output; the firewall turns that into Error."""
    if not rules.policies:
        return FactResult(fact=fact, ok=False, reason="not covered by any policy: no policies exist")
    data = await gateway.ask("verify", policy_check_prompt(rules.policies, fact.raw))
    verdict = AIVerdict.model_validate(data)
    policy = rules.policy(verdict.policy_id)
    rule = policy.title if policy else None

    if verdict.verdict == "contradicted":
        return FactResult(fact=fact, ok=False, rule=rule, quote=verdict.quote,
                          reason=f"contradicted by {rule or 'a policy'}: {verdict.reason}".rstrip(": "))
    if verdict.verdict == "not_covered":
        return FactResult(fact=fact, ok=False, rule=rule, quote=verdict.quote,
                          reason=f"not covered by any policy: {verdict.reason}".rstrip(": "))
    if policy is None or not quote_is_verified(verdict.quote, policy.text):
        return FactResult(fact=fact, ok=False, rule=rule, quote=verdict.quote,
                          reason="unverified quote: the AI's quote is not word-for-word in the policy")
    return FactResult(fact=fact, ok=True, rule=rule, quote=verdict.quote,
                      reason=f"supported by the {policy.title} (quote verified)")
