"""Facts extracted from an answer and the result of checking each one."""

from typing import Literal

from pydantic import BaseModel

FactType = Literal["price", "percent", "period", "date", "link", "promise", "phrase", "security"]


class Fact(BaseModel):
    type: FactType
    raw: str
    start: int
    end: int
    source: Literal["pattern", "ai", "banned_list", "security_scan"] = "pattern"
    value: str | None = None  # normalised: "USD 49", "20", "14" (days), "2026-03-31", a URL
    product: str | None = None  # prices only: the product this price was linked to


class FactResult(BaseModel):
    fact: Fact
    ok: bool
    rule: str | None = None
    reason: str = ""
    quote: str | None = None
    skipped: bool = False  # never checked (a code check already failed, or the check errored)
