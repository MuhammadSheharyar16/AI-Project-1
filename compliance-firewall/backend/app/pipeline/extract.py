"""Regex fact extraction with character offsets: price, percent, period, date, link, promise."""

import re
from decimal import Decimal

from app.pipeline.normalize import (
    MONTHS, NUMBER_WORD, PRICE_RE, date_key, days, money_from_match, url,
)
from app.schemas.facts import Fact
from app.schemas.rules import Rules

PERCENT_RE = re.compile(r"(?<![\d.])(?P<n>\d{1,3}(?:\.\d+)?)\s?(?:%|percent\b|per cent\b)", re.I)
# "14 days", "14-day", "fourteen days", "two weeks", "1 month", "2-year". A bare "a month" is not
# a period on purpose ("$49 a month" is a price cadence, not a policy time limit).
PERIOD_RE = re.compile(
    rf"\b(?P<n>\d{{1,4}}|{NUMBER_WORD})\s?(?:-\s?)?(?P<unit>days?|weeks?|months?|years?)\b", re.I
)
_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
_ORD = r"(?:st|nd|rd|th)?"
# "31 March", "31st of March 2026", "March 31", "Mar 31st, 2026", "March 2026",
# "2026-03-31", "31/03/2026" (numeric dates are read day-first).
DATE_RE = re.compile(
    rf"\b(?:(?P<d1>\d{{1,2}}){_ORD}\s+(?:of\s+)?(?P<m1>{_MONTH})\.?(?:,?\s+(?P<y1>\d{{4}}))?"
    rf"|(?P<m2>{_MONTH})\.?\s+(?P<d2>\d{{1,2}}){_ORD}(?:,?\s+(?P<y2>\d{{4}}))?"
    rf"|(?P<m3>{_MONTH})\.?\s+(?P<y3>\d{{4}})"
    rf"|(?P<y4>\d{{4}})-(?P<mo4>\d{{1,2}})-(?P<d4>\d{{1,2}})"
    rf"|(?P<d5>\d{{1,2}})[/.](?P<mo5>\d{{1,2}})[/.](?P<y5>\d{{4}}|\d{{2}}))\b",
    re.I,
)
LINK_RE = re.compile(r"(?:https?://|\bwww\.)[^\s<>\"'\[\]{}]+", re.I)
PROMISE_RE = re.compile(
    r"\b(?:refund\w*|money[- ]back|guarantee\w*|trials?|for free|cancel\w*|warrant\w*)\b", re.I
)
_LINK_TRAILING = ".,;:!?)'\""
# Sentence ends at . ! ? + whitespace, or at a newline. "Rs." is an abbreviation, not an end.
_SENTENCE_BREAK = re.compile(r"(?<!\bRs\.)(?<=[.!?])\s+|\n+", re.I)

Span = tuple[int, int]


def sentence_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    start = 0
    for match in _SENTENCE_BREAK.finditer(text):
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(text)))
    trimmed: list[Span] = []
    for s, e in spans:
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if s < e:
            trimmed.append((s, e))
    return trimmed


def sentence_at(text: str, position: int) -> str:
    for s, e in sentence_spans(text):
        if s <= position < e:
            return text[s:e]
    return text


def _overlaps(start: int, end: int, spans: list[Span]) -> bool:
    return any(start < e and s < end for s, e in spans)


def _number(text: str) -> str:
    value = Decimal(text)
    return str(int(value)) if value == value.to_integral_value() else str(value)


def period_days(match: re.Match[str]) -> int:
    return days(match.group("n"), match.group("unit"))


def date_value(match: re.Match[str]) -> str | None:
    """Normalised date key, or None when the numbers are not a real day/month."""
    g = match.groupdict()

    def num(*keys: str) -> int | None:
        value = next((g[k] for k in keys if g[k]), None)
        return int(value) if value else None

    month_name = next((g[k] for k in ("m1", "m2", "m3") if g[k]), None)
    month = MONTHS[month_name.lower()] if month_name else num("mo4", "mo5")
    day, year = num("d1", "d2", "d4", "d5"), num("y1", "y2", "y3", "y4", "y5")
    if year is not None and year < 100:
        year += 2000
    if month is None or not 1 <= month <= 12 or (day is not None and not 1 <= day <= 31):
        return None
    return date_key(day, month, year)


def product_mentions(text: str, rules: Rules) -> list[tuple[int, int, str]]:
    """All product name/alias mentions as (start, end, product), longest names win overlaps.

    Brand names and links are never product mentions ("Hisaab Pro" is not the Pro plan).
    """
    terms = sorted(
        ((name, rule.product) for rule in rules.prices for name in rule.names()),
        key=lambda term: -len(term[0]),
    )
    taken: list[Span] = [m.span() for m in LINK_RE.finditer(text)]
    for brand in rules.brand_names:
        taken += [m.span() for m in re.finditer(rf"\b{re.escape(brand)}\b", text, re.I)]
    mentions: list[tuple[int, int, str]] = []
    for name, product in terms:
        for m in re.finditer(rf"\b{re.escape(name)}\b", text, re.I):
            if not _overlaps(m.start(), m.end(), taken):
                taken.append((m.start(), m.end()))
                mentions.append((m.start(), m.end(), product))
    return sorted(mentions)


def _link_facts(text: str) -> list[Fact]:
    facts = []
    for m in LINK_RE.finditer(text):
        raw = m.group(0).rstrip(_LINK_TRAILING)
        facts.append(Fact(type="link", raw=raw, start=m.start(), end=m.start() + len(raw), value=url(raw)))
    return facts


def _price_facts(text: str, rules: Rules, blocked: list[Span]) -> list[Fact]:
    matches = [m for m in PRICE_RE.finditer(text) if not _overlaps(m.start(), m.end(), blocked)]
    mentions = product_mentions(text, rules)
    distinct = {product for _, _, product in mentions}
    facts = []
    for i, m in enumerate(matches):
        prev_end = matches[i - 1].end() if i > 0 else 0
        next_start = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        before = [p for s, e, p in mentions if s >= prev_end and e <= m.start()]
        after = [p for s, e, p in mentions if s >= m.end() and e <= next_start]
        if before:
            product = before[-1]
        elif after:
            product = after[0]
        elif len(distinct) == 1:
            product = next(iter(distinct))
        else:
            product = None
        facts.append(Fact(
            type="price", raw=m.group(0), start=m.start(), end=m.end(),
            value=money_from_match(m).label(), product=product,
        ))
    return facts


def _numeric_facts(text: str, pattern: re.Pattern[str], kind: str, blocked: list[Span]) -> list[Fact]:
    return [
        Fact(type=kind, raw=m.group(0), start=m.start(), end=m.end(), value=_number(m.group("n")))
        for m in pattern.finditer(text)
        if not _overlaps(m.start(), m.end(), blocked)
    ]


def _period_facts(text: str, blocked: list[Span]) -> list[Fact]:
    return [
        Fact(type="period", raw=m.group(0), start=m.start(), end=m.end(), value=str(period_days(m)))
        for m in PERIOD_RE.finditer(text)
        if not _overlaps(m.start(), m.end(), blocked)
    ]


def _date_facts(text: str, blocked: list[Span]) -> list[Fact]:
    facts = []
    for m in DATE_RE.finditer(text):
        value = date_value(m)
        if value and not _overlaps(m.start(), m.end(), blocked):
            facts.append(Fact(type="date", raw=m.group(0), start=m.start(), end=m.end(), value=value))
    return facts


def _promise_facts(text: str) -> list[Fact]:
    facts = []
    for s, e in sentence_spans(text):
        sentence = text[s:e]
        keyword = PROMISE_RE.search(sentence)
        if keyword:
            facts.append(Fact(type="promise", raw=sentence, start=s, end=e, value=keyword.group(0).lower()))
    return facts


def extract(answer: str, rules: Rules) -> list[Fact]:
    links = _link_facts(answer)
    link_spans = [(f.start, f.end) for f in links]
    prices = _price_facts(answer, rules, link_spans)
    blocked = link_spans + [(f.start, f.end) for f in prices]
    dates = _date_facts(answer, blocked)
    blocked += [(f.start, f.end) for f in dates]
    facts = [
        *prices,
        *_numeric_facts(answer, PERCENT_RE, "percent", blocked),
        *_period_facts(answer, blocked),
        *dates,
        *links,
        *_promise_facts(answer),
    ]
    return sorted(facts, key=lambda f: (f.start, f.end))
