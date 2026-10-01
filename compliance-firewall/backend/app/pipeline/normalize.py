"""Normalisers shared by the extractor, the checks and the rules schema."""

import re
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlsplit

_AMOUNT = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_PREFIX = r"\bUS\$|\$|\bUSD|\bPKR|\bRs\.?|₨"
_SUFFIX = r"USD\b|PKR\b|dollars?\b|rupees?\b"

# One pattern for both directions: "$49", "US$49", "USD 49", "Rs. 4,999", "PKR 4,999.00"
# and "49 USD", "4999 PKR", "49 dollars".
PRICE_RE = re.compile(
    rf"(?P<pre>{_PREFIX})\s?(?P<amt1>{_AMOUNT})(?!\d)"
    rf"|(?<![\d.,$])(?P<amt2>{_AMOUNT})\s?(?P<post>{_SUFFIX})",
    re.IGNORECASE,
)

_CURRENCY = {
    "$": "USD", "us$": "USD", "usd": "USD", "dollar": "USD", "dollars": "USD",
    "rs": "PKR", "rs.": "PKR", "pkr": "PKR", "rupee": "PKR", "rupees": "PKR", "₨": "PKR",
}


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str

    def label(self) -> str:
        if self.amount == self.amount.to_integral_value():
            number = f"{int(self.amount):,}"
        else:
            number = f"{self.amount:,.2f}"
        return f"{self.currency} {number}"


def money_from_match(match: re.Match[str]) -> Money:
    token = (match.group("pre") or match.group("post")).lower()
    amount = match.group("amt1") or match.group("amt2")
    return Money(Decimal(amount.replace(",", "")), _CURRENCY[token])


def money(text: str) -> Money | None:
    """Parse a whole string like "Rs 4,999" or "49 USD". Returns None if it is not a price."""
    match = PRICE_RE.fullmatch(text.strip())
    return money_from_match(match) if match else None


_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
         "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
         "eighteen", "nineteen"]
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90}
NUMBER_WORD = (
    rf"(?:(?:{'|'.join(_TENS)})(?:[-\s](?:{'|'.join(_ONES[1:10])}))?|{'|'.join(_ONES)})"
)
DAYS_PER_UNIT = {"day": 1, "week": 7, "month": 30, "year": 365}

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def number(text: str) -> int:
    """"14", "fourteen", "twenty-one" or "twenty one" -> int."""
    text = text.strip().lower()
    if text.isdigit():
        return int(text)
    parts = re.split(r"[-\s]+", text)
    if parts[0] in _TENS:
        return _TENS[parts[0]] + (_ONES.index(parts[1]) if len(parts) > 1 else 0)
    return _ONES.index(parts[0])


def days(amount: str, unit: str) -> int:
    """Convert "2" + "weeks" to 14. A month counts as 30 days and a year as 365."""
    return number(amount) * DAYS_PER_UNIT[unit.lower().rstrip("s")]


def date_key(day: int | None, month: int, year: int | None) -> str:
    """Comparable date form: "2026-03-31", "--03-31" (no year) or "2026-03" (no day)."""
    year_part = f"{year:04d}" if year is not None else "-"
    return f"{year_part}-{month:02d}" + (f"-{day:02d}" if day is not None else "")


def url(text: str) -> str:
    """Lowercase scheme/host/path, strip "www." and trailing slashes. Query/fragment are kept."""
    raw = text.strip()
    if raw.lower().startswith("www."):
        raw = "https://" + raw
    parts = urlsplit(raw)
    if "@" in parts.netloc:
        netloc = parts.netloc.lower()  # userinfo tricks never match an allowed link
    else:
        netloc = (parts.hostname or "").lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        if parts.port is not None:
            netloc += f":{parts.port}"
    normalised = f"{parts.scheme.lower()}://{netloc}{parts.path.lower().rstrip('/')}"
    if parts.query:
        normalised += f"?{parts.query}"
    if parts.fragment:
        normalised += f"#{parts.fragment}"
    return normalised
