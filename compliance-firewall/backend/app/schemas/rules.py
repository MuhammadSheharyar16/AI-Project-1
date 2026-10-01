"""Trusted rules: the editable source of truth the firewall checks answers against."""

import re
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.pipeline.normalize import Money, money, url

_LINK_IN_TEXT = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PriceRule(_Strict):
    product: str = Field(min_length=1, max_length=80)
    aliases: list[str] = Field(default_factory=list)
    price: str = Field(min_length=1, description='e.g. "USD 49", "$49" or "Rs 4,999"')
    # The same plan's official price in other currencies (one per currency). Never converted.
    other_prices: list[str] = Field(default_factory=list, description='e.g. ["Rs 13,999"]')

    @field_validator("price")
    @classmethod
    def _price_parses(cls, value: str) -> str:
        if money(value) is None:
            raise ValueError(f"unrecognised price format: {value!r}")
        return value

    @field_validator("other_prices")
    @classmethod
    def _other_prices_parse(cls, value: list[str]) -> list[str]:
        for price in value:
            if money(price) is None:
                raise ValueError(f"unrecognised price format: {price!r}")
        return value

    @model_validator(mode="after")
    def _one_price_per_currency(self) -> "PriceRule":
        currencies = [m.currency for m in self.all_money()]
        if len(currencies) != len(set(currencies)):
            raise ValueError(f"{self.product}: only one official price per currency")
        return self

    @field_validator("aliases")
    @classmethod
    def _aliases_not_blank(cls, value: list[str]) -> list[str]:
        cleaned = [a.strip() for a in value]
        if any(not a for a in cleaned):
            raise ValueError("aliases must not be blank")
        return cleaned

    def all_money(self) -> list[Money]:
        """Every official price of this plan, `price` first."""
        parsed = [money(p) for p in (self.price, *self.other_prices)]
        assert all(parsed)  # guaranteed by the validators
        return parsed  # type: ignore[return-value]

    def money_in(self, currency: str) -> Money | None:
        return next((m for m in self.all_money() if m.currency == currency), None)

    def names(self) -> list[str]:
        return [self.product, *self.aliases]


class Discount(_Strict):
    name: str = Field(min_length=1)
    percent: Decimal = Field(gt=0, le=100)


class Policy(_Strict):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    title: str = Field(min_length=1)
    topics: list[str] = Field(min_length=1)
    text: str = Field(min_length=1)


class SafeMessages(_Strict):
    pricing: str = Field(min_length=1)
    policy: str = Field(min_length=1)
    link: str = Field(min_length=1)
    general: str = Field(min_length=1)


class Rules(_Strict):
    prices: list[PriceRule]
    discounts: list[Discount] = Field(default_factory=list)
    policies: list[Policy] = Field(default_factory=list)
    allowed_links: list[str] = Field(default_factory=list)
    banned_phrases: list[str] = Field(default_factory=list)
    # Company/brand names. Never read as a product, so "Hisaab Pro" is not the "Pro" plan.
    brand_names: list[str] = Field(default_factory=list)
    safe_messages: SafeMessages

    @field_validator("allowed_links")
    @classmethod
    def _links_are_urls(cls, value: list[str]) -> list[str]:
        for link in value:
            if not link.lower().startswith(("http://", "https://")):
                raise ValueError(f"allowed link must start with http:// or https://: {link!r}")
        return value

    @field_validator("banned_phrases", "brand_names")
    @classmethod
    def _phrases_not_blank(cls, value: list[str]) -> list[str]:
        if any(not p.strip() for p in value):
            raise ValueError("banned phrases and brand names must not be blank")
        return [p.strip() for p in value]

    @model_validator(mode="after")
    def _consistent(self) -> "Rules":
        ids = [p.id for p in self.policies]
        if len(ids) != len(set(ids)):
            raise ValueError("policy ids must be unique")
        names = [n.lower() for rule in self.prices for n in rule.names()]
        if len(names) != len(set(names)):
            raise ValueError("product names and aliases must be unique")
        allowed = self.normalised_links()
        for key, text in self.safe_messages.model_dump().items():
            for link in _LINK_IN_TEXT.findall(text):
                if url(link.rstrip(".,;:!?)")) not in allowed:
                    raise ValueError(f"safe message {key!r} uses a link that is not allowed: {link}")
            lowered = text.lower()
            for phrase in self.banned_phrases:
                if phrase.lower() in lowered:
                    raise ValueError(f"safe message {key!r} contains banned phrase {phrase!r}")
        return self

    def normalised_links(self) -> set[str]:
        return {url(link) for link in self.allowed_links}

    def policy(self, policy_id: str | None) -> Policy | None:
        return next((p for p in self.policies if p.id == policy_id), None)
