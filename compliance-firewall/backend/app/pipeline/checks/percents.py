"""Percent check: every percentage must equal an approved discount."""

from decimal import Decimal

from app.schemas.facts import Fact, FactResult
from app.schemas.rules import Rules


def _pct(value: Decimal) -> str:
    return f"{value.normalize():f}%"


def check(fact: Fact, rules: Rules) -> FactResult:
    approved = ", ".join(f"{d.name} = {_pct(d.percent)}" for d in rules.discounts) or "none"
    rule = f"approved discounts: {approved}"
    if fact.value is None:
        return FactResult(fact=fact, ok=False, rule=rule, reason=f"unreadable percent: {fact.raw}")
    said = Decimal(fact.value)
    if any(d.percent == said for d in rules.discounts):
        return FactResult(fact=fact, ok=True, rule=rule, reason="matches an approved discount")
    return FactResult(fact=fact, ok=False, rule=rule, reason=f"unapproved discount: {_pct(said)}")
