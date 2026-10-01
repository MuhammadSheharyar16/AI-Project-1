"""AI security scan (code only, runs before any AI call).

Rejects answers that carry prompt-injection text, hidden/bidi control characters, leaked secrets,
payment card numbers or national ID (CNIC) numbers. Such text never reaches the LLM.
Also flags the [CARD]/[CNIC] placeholders left by audit redaction, so re-checking a stored answer
that leaked those numbers is still rejected.
"""

import re

from app.ai.redact import CARD_PLACEHOLDER, CNIC_PLACEHOLDER, is_card_number
from app.schemas.facts import Fact, FactResult

RULE = "AI security policy"

INJECTION_RE = re.compile(
    r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+|the\s+|your\s+)*"
    r"(?:previous|prior|above|earlier|system|original)\s+(?:instructions?|rules|prompts?|messages?)"
    r"|\bsystem\s+prompt\b|\byou\s+are\s+now\b|\bdeveloper\s+mode\b|\bjailbreak\w*"
    r"|\bact\s+as\s+(?:an?\s+)?(?:admin|administrator|system|developer)\b"
    r"|<<<|>>>|[\"']?\bverdict\b[\"']?\s*[:=]",
    re.I,
)
HIDDEN_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]+")
SECRET_RE = re.compile(
    r"\b(?:gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}"
    r"|xox[abpr]-[A-Za-z0-9-]{10,})\b"
)
CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
CNIC_RE = re.compile(r"\b\d{5}-\d{7}-\d\b")


REDACTED_RE = re.compile(re.escape(CARD_PLACEHOLDER) + "|" + re.escape(CNIC_PLACEHOLDER))


def _flag(match: re.Match[str], value: str, reason: str) -> FactResult:
    fact = Fact(type="security", raw=match.group(0), start=match.start(), end=match.end(),
                source="security_scan", value=value)
    return FactResult(fact=fact, ok=False, rule=RULE, reason=reason)


def scan(answer: str) -> list[FactResult]:
    results = [_flag(m, "prompt_injection", f'possible prompt injection: "{m.group(0)}"')
               for m in INJECTION_RE.finditer(answer)]
    results += [_flag(m, "hidden_characters", "hidden or bidirectional control characters")
                for m in HIDDEN_RE.finditer(answer)]
    results += [_flag(m, "secret", "leaked secret or API key") for m in SECRET_RE.finditer(answer)]
    results += [_flag(m, "national_id", "national ID (CNIC) number") for m in CNIC_RE.finditer(answer)]
    results += [_flag(m, "payment_card", "payment card number")
                for m in CARD_RE.finditer(answer) if is_card_number(m.group(0))]
    results += [_flag(m, "redacted_sensitive", "card or national ID number (redacted in the audit log)")
                for m in REDACTED_RE.finditer(answer)]
    return results
