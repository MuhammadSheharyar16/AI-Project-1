"""Price check: amount within 0.01 of the linked product's official price, in the same currency.

A plan has one official price. Prices are never converted between currencies.
"""

from decimal import Decimal

from app.pipeline.normalize import money
from app.schemas.facts import Fact, FactResult
from app.schemas.rules import Rules

TOLERANCE = Decimal("0.01")


def check(fact: Fact, rules: Rules) -> FactResult:
    said = money(fact.value or fact.raw)  # AI facts carry the amount in `value`
    if said is None:
        return FactResult(fact=fact, ok=False, reason=f"unreadable price: {fact.raw}")
    rule = next((r for r in rules.prices if r.product == fact.product), None)
    if rule is None:
        return FactResult(fact=fact, ok=False,
                          reason=f"price for unknown product: answer says {fact.value or fact.raw}")
    official = rule.official()
    label = f"{rule.product} = {official.label()}"
    if said.currency == official.currency and abs(said.amount - official.amount) <= TOLERANCE:
        return FactResult(fact=fact, ok=True, rule=label, reason="matches the official price")
    return FactResult(
        fact=fact, ok=False, rule=label,
        reason=f"price mismatch: answer says {said.label()}, official price is {official.label()}",
    )
