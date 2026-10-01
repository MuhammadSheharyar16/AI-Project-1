"""Date check: a calendar date must be stated in the policy its sentence is about."""

from app.pipeline.checks import date_values, topic_policies
from app.pipeline.extract import sentence_at
from app.schemas.facts import Fact, FactResult
from app.schemas.rules import Rules


def check(fact: Fact, answer: str, rules: Rules) -> FactResult:
    policies = topic_policies(sentence_at(answer, fact.start), rules)
    for policy in policies:
        if fact.value in date_values(policy.text):
            return FactResult(fact=fact, ok=True, rule=f"{policy.title}: {fact.raw}",
                              reason="date is stated in the policy")
    # Fail closed: a deadline or date that no policy states cannot be verified.
    where = ", ".join(p.title for p in policies) or "any policy"
    return FactResult(fact=fact, ok=False, rule=", ".join(p.title for p in policies) or None,
                      reason=f"unverified date: {fact.raw} is not stated in {where}")
