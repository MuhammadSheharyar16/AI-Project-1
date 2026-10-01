"""Final status and the safe message chosen by the first failing fact type."""

from app.schemas.decision import DecisionStatus
from app.schemas.facts import FactResult
from app.schemas.rules import Rules

# Used only when the rules themselves could not be loaded.
FALLBACK_GENERAL = "Sorry, I can't answer that right now. Please contact our support team."

SAFE_MESSAGE_FOR = {
    "price": "pricing",
    "percent": "pricing",
    "link": "link",
    "promise": "policy",
    "period": "policy",
    "date": "policy",
    "phrase": "policy",
    "security": "general",
}


def decide(results: list[FactResult]) -> tuple[DecisionStatus, str | None]:
    """Return (status, safe message key). Approved only if every result is OK."""
    failures = sorted(
        (r for r in results if not r.ok and not r.skipped), key=lambda r: (r.fact.start, r.fact.end)
    )
    if not failures:
        return "Approved", None
    return "Rejected", SAFE_MESSAGE_FOR.get(failures[0].fact.type, "general")


def safe_message(key: str, rules: Rules | None) -> str:
    if rules is None:
        return FALLBACK_GENERAL
    return getattr(rules.safe_messages, key, rules.safe_messages.general)
