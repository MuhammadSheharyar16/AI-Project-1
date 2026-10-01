"""Shared helpers for the per-fact checks."""

import re

from app.pipeline.extract import DATE_RE, PERIOD_RE, date_value, period_days
from app.schemas.rules import Policy, Rules


def topic_policies(text: str, rules: Rules) -> list[Policy]:
    """Policies whose topic keywords appear in the text ("refund" also matches "refunds")."""
    return [
        p for p in rules.policies
        if any(re.search(rf"\b{re.escape(topic)}", text, re.I) for topic in p.topics)
    ]


def day_counts(text: str) -> set[int]:
    """Every time period in the text, in days ("7-day" -> 7, "two weeks" -> 14)."""
    return {period_days(m) for m in PERIOD_RE.finditer(text)}


def date_values(text: str) -> set[str]:
    return {v for m in DATE_RE.finditer(text) if (v := date_value(m))}
