"""Unlimited check: "anytime/forever/lifetime" promises against a policy with a day limit."""

import re

from app.pipeline.checks import day_counts, topic_policies
from app.schemas.facts import Fact, FactResult
from app.schemas.rules import Rules

UNLIMITED_RE = re.compile(
    r"\b(?:any\s?time|forever|lifetime|for life|no time limit|without (?:a |any )?time limit"
    r"|unlimited time)\b",
    re.I,
)


def check(fact: Fact, rules: Rules) -> FactResult | None:
    """Return a failing result on contradiction, or None to leave the promise for the AI."""
    word = UNLIMITED_RE.search(fact.raw)
    if word is None:
        return None
    stated = day_counts(fact.raw)
    for policy in topic_policies(fact.raw, rules):
        limits = day_counts(policy.text)
        if limits and not limits & stated:
            n = min(limits)
            return FactResult(
                fact=fact, ok=False, rule=f"{policy.title}: {n}-day limit",
                reason=f'contradicts {n}-day policy: answer says "{word.group(0)}" '
                       f"but the {policy.title} has a {n}-day limit",
            )
    return None
