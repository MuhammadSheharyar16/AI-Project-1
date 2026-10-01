"""Banned phrases: case-insensitive substring match (any whitespace between words)."""

import re

from app.schemas.facts import Fact, FactResult
from app.schemas.rules import Rules

RULE = "banned phrases list"


def find(answer: str, rules: Rules) -> list[FactResult]:
    results = []
    for phrase in rules.banned_phrases:
        pattern = r"\s+".join(re.escape(word) for word in phrase.split())
        for m in re.finditer(pattern, answer, re.I):
            fact = Fact(type="phrase", raw=m.group(0), start=m.start(), end=m.end(),
                        source="banned_list", value=phrase.lower())
            results.append(FactResult(fact=fact, ok=False, rule=RULE, reason=f'banned phrase: "{phrase}"'))
    return results
