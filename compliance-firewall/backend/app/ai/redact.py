"""Privacy: remove personal data before text leaves the server for the LLM or is stored in the audit log."""

import re
from typing import Any

CARD_PLACEHOLDER = "[CARD]"
CNIC_PLACEHOLDER = "[CNIC]"

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_CNIC = re.compile(r"\b\d{5}-\d{7}-\d\b")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_PHONE = re.compile(r"(?<![\w+])(?<!\d[\s-])\+?\d(?:[\s-]?\d){9,13}(?![\s-]?\d)(?!\w)")


def luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2:
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def is_card_number(text: str) -> bool:
    digits = re.sub(r"\D", "", text)
    return 13 <= len(digits) <= 19 and luhn_ok(digits)


def redact(text: str) -> tuple[str, int]:
    """Return (redacted text, number of redactions)."""
    count = 0

    def card(match: re.Match[str]) -> str:
        nonlocal count
        if not is_card_number(match.group(0)):
            return match.group(0)
        count += 1
        return CARD_PLACEHOLDER

    text, n_email = _EMAIL.subn("[EMAIL]", text)
    text, n_cnic = _CNIC.subn(CNIC_PLACEHOLDER, text)
    text = _CARD.sub(card, text)
    text, n_phone = _PHONE.subn("[PHONE]", text)
    return text, count + n_email + n_cnic + n_phone


def redact_text(text: str | None) -> str | None:
    return None if text is None else redact(text)[0]


def redact_deep(value: Any) -> Any:
    """Redact every string inside nested dicts/lists (for JSON audit columns)."""
    if isinstance(value, str):
        return redact(value)[0]
    if isinstance(value, list):
        return [redact_deep(v) for v in value]
    if isinstance(value, dict):
        return {k: redact_deep(v) for k, v in value.items()}
    return value
