"""Link check: the normalised URL must be on the allowed list."""

from app.pipeline.normalize import url
from app.schemas.facts import Fact, FactResult
from app.schemas.rules import Rules

RULE = "allowed links list"


def check(fact: Fact, rules: Rules) -> FactResult:
    if (fact.value or url(fact.raw)) in rules.normalised_links():
        return FactResult(fact=fact, ok=True, rule=RULE, reason="link is on the allowed list")
    return FactResult(fact=fact, ok=False, rule=RULE, reason=f"unapproved link: {fact.raw}")
