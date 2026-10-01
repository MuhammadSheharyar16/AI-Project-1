"""AI-assisted fact extraction: finds facts the pattern rules missed.

Runs only when the answer still has fact-like cues the pattern rules did not explain (digits,
number words, currency words, domain-like text). Every AI fact must be GROUNDED: its quote has to
appear in the answer, or it is discarded. Grounded facts then go through the same code checks.
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.ai.governance import AIGateway
from app.ai.prompts import extraction_prompt
from app.pipeline.extract import sentence_spans
from app.pipeline.normalize import NUMBER_WORD, Money, date_key, url
from app.schemas.facts import Fact
from app.schemas.rules import Rules

MAX_AI_FACTS = 25
AIFactType = Literal["price", "percent", "period", "date", "link", "promise"]
_TYPE_ALIASES = {"discount": "percent", "url": "link", "deadline": "date", "duration": "period",
                 "time_limit": "period", "guarantee": "promise", "commitment": "promise"}

CUE_RE = re.compile(
    rf"\d|%|\$|₨|\b(?:{NUMBER_WORD}|hundred|thousand|lakh|half|quarter|dozen|dollars?|bucks?"
    r"|usd|pkr|rs|rupees?|percent|https?|www|dot\s?(?:com|pk|net|org)|cash\s?back|reimburs\w*"
    r"|compensat\w*|free of charge|no charge|on the house)\b"
    r"|\b[a-z0-9-]+\.(?:com|pk|net|org|io|co|ly|app)\b",
    re.I,
)


# Not policy time limits: billing cadence ("a month", "monthly", "/month") and reply/response
# times ("one business day", "24 hours"). A small model may still report these as periods.
CADENCE_RE = re.compile(
    r"^(?:a|an|per|each|every)\s+(?:day|week|month|year)$"
    r"|^(?:daily|weekly|monthly|yearly|annually)$"
    r"|\b(?:business|working)\s+days?\b|\b(?:hours?|minutes?|mins?)\b",
    re.I,
)
_CADENCE_BEFORE = re.compile(r"(?:\b(?:per|a|an|every|each)\s+|/)$", re.I)


def is_cadence(answer: str, start: int, end: int) -> bool:
    before = answer[max(0, start - 8):start]
    return bool(CADENCE_RE.search(answer[start:end]) or _CADENCE_BEFORE.search(before))


class AIFact(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: AIFactType
    quote: str = Field(min_length=1, max_length=500)
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    product: str | None = None
    number: Decimal | None = Field(default=None, ge=0, le=100)
    days: int | None = Field(default=None, ge=0, le=36500)
    month: int | None = Field(default=None, ge=1, le=12)
    day: int | None = Field(default=None, ge=1, le=31)
    year: int | None = Field(default=None, ge=1900, le=2200)
    url: str | None = None


class AIFactList(BaseModel):
    facts: list[dict[str, Any]] = Field(max_length=MAX_AI_FACTS)


@dataclass
class AIExtraction:
    facts: list[Fact] = field(default_factory=list)
    discarded: int = 0  # invalid shape, or quote not found in the answer
    duplicates: int = 0  # already found by the pattern rules
    cadence: int = 0  # "periods" that are billing cadence or reply times, not time limits


def needs_ai(answer: str, facts: list[Fact]) -> bool:
    """True when fact-like cues remain after blanking out what the pattern rules explained."""
    chars = list(answer)
    for fact in facts:
        if fact.type not in ("promise", "phrase", "security"):
            chars[fact.start:fact.end] = " " * (fact.end - fact.start)
    return CUE_RE.search("".join(chars)) is not None


def _ground(quote: str, answer: str) -> tuple[int, int] | None:
    start = answer.find(quote)
    if start >= 0:
        return start, start + len(quote)
    pattern = r"\s+".join(re.escape(word) for word in quote.split())
    match = re.search(pattern, answer, re.I) if pattern else None
    return (match.start(), match.end()) if match else None


def _sentence_span(answer: str, position: int) -> tuple[int, int]:
    return next(((s, e) for s, e in sentence_spans(answer) if s <= position < e), (0, len(answer)))


def _product(name: str | None, rules: Rules) -> str | None:
    if not name:
        return None
    wanted = name.strip().lower()
    return next((r.product for r in rules.prices if wanted in (n.lower() for n in r.names())), None)


def _value(ai: AIFact, raw: str) -> str | None:
    match ai.type:
        case "price":
            currency = (ai.currency or "").upper()
            if ai.amount is None or currency not in ("USD", "PKR"):
                return None
            return Money(ai.amount, currency).label()
        case "percent":
            return None if ai.number is None else f"{ai.number.normalize():f}"
        case "period":
            return None if ai.days is None else str(ai.days)
        case "date":
            return None if ai.month is None else date_key(ai.day, ai.month, ai.year)
        case "link":
            for candidate in (ai.url, raw):
                if candidate and candidate.lower().startswith(("http://", "https://", "www.")):
                    return url(candidate)
            return None
    return "ai"  # promise


def _overlaps(kind: str, start: int, end: int, taken: list[tuple[str, int, int]]) -> bool:
    return any(t == kind and start < e and s < end for t, s, e in taken)


async def extract(answer: str, rules: Rules, gateway: AIGateway, known: list[Fact]) -> AIExtraction:
    """Raises on AI failure or a malformed response; the firewall turns that into Error."""
    data = await gateway.ask("extract", extraction_prompt(rules, answer))
    items = AIFactList.model_validate(data).facts
    result = AIExtraction()
    taken = [(f.type, f.start, f.end) for f in known]
    for item in items:
        if isinstance(item.get("type"), str):
            item = {**item, "type": _TYPE_ALIASES.get(item["type"].lower(), item["type"].lower())}
        try:
            ai = AIFact.model_validate(item)
        except ValidationError:
            result.discarded += 1
            continue
        span = _ground(ai.quote, answer)
        if span is None:
            result.discarded += 1  # hallucinated: not in the answer
            continue
        start, end = _sentence_span(answer, span[0]) if ai.type == "promise" else span
        if _overlaps(ai.type, start, end, taken):
            result.duplicates += 1
            continue
        if ai.type == "period" and is_cadence(answer, start, end):
            result.cadence += 1
            continue
        raw = answer[start:end]
        result.facts.append(Fact(
            type=ai.type, raw=raw, start=start, end=end, source="ai", value=_value(ai, raw),
            product=_product(ai.product, rules) if ai.type == "price" else None,
        ))
        taken.append((ai.type, start, end))
    return result
