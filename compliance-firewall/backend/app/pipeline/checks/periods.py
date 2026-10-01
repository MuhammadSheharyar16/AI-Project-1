"""Period check: "N days" must match a day count in the policy its sentence is about."""

import re

from app.pipeline.checks import day_counts, topic_policies
from app.pipeline.extract import sentence_at
from app.schemas.facts import Fact, FactResult
from app.schemas.rules import Rules


def _said(fact: Fact, days: int) -> str:
    """ "14 days", or "two weeks (14 days)" when the answer used words or another unit."""
    if re.fullmatch(r"\d+\s?-?\s?days?", fact.raw, re.I):
        return f"{days} days"
    return f"{fact.raw} ({days} days)"


def check(fact: Fact, answer: str, rules: Rules) -> FactResult:
    if fact.value is None:
        return FactResult(fact=fact, ok=False, reason=f"unreadable period: {fact.raw}")
    days = int(fact.value)
    policies = topic_policies(sentence_at(answer, fact.start), rules)
    if not policies:
        # Fail closed: a time period no policy talks about cannot be verified.
        return FactResult(fact=fact, ok=False,
                          reason=f"period mismatch: {_said(fact, days)} is not covered by any policy")
    for policy in policies:
        if days in day_counts(policy.text):
            return FactResult(fact=fact, ok=True, rule=f"{policy.title}: {days} days",
                              reason="matches the policy period")
    described = "; ".join(
        f"{p.title} says {', '.join(str(n) for n in sorted(day_counts(p.text)))} days"
        if day_counts(p.text) else f"{p.title} has no day limit"
        for p in policies
    )
    return FactResult(fact=fact, ok=False, rule=", ".join(p.title for p in policies),
                      reason=f"period mismatch: answer says {_said(fact, days)}, but {described}")
