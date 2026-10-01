from decimal import Decimal

import pytest

from app.pipeline.normalize import Money, days, money, number, url


@pytest.mark.parametrize(
    ("text", "amount", "currency"),
    [
        ("$49", "49", "USD"),
        ("US$49", "49", "USD"),
        ("49 USD", "49", "USD"),
        ("USD 49", "49", "USD"),
        ("49 dollars", "49", "USD"),
        ("$49.99", "49.99", "USD"),
        ("Rs 4,999", "4999", "PKR"),
        ("Rs. 4,999", "4999", "PKR"),
        ("rs 4999", "4999", "PKR"),
        ("4999 PKR", "4999", "PKR"),
        ("PKR 4,999.00", "4999", "PKR"),
        ("4,999 rupees", "4999", "PKR"),
        ("  $ 1,250  ", "1250", "USD"),
    ],
)
def test_money_parses_every_format(text: str, amount: str, currency: str) -> None:
    parsed = money(text)
    assert parsed is not None
    assert parsed.amount == Decimal(amount)
    assert parsed.currency == currency


@pytest.mark.parametrize("text", ["49", "forty-nine dollars", "14 days", "20%", "", "USD"])
def test_money_rejects_non_prices(text: str) -> None:
    assert money(text) is None


def test_rule_and_answer_formats_compare_equal() -> None:
    assert money("4999 PKR") == money("Rs 4,999") == money("PKR 4,999.00")
    assert money("$49") != money("Rs 49")  # never convert currencies


def test_money_label() -> None:
    assert Money(Decimal("4999"), "PKR").label() == "PKR 4,999"
    assert Money(Decimal("49.5"), "USD").label() == "USD 49.50"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("HTTPS://MuhammadSheharyar16.GitHub.io/HisaabPro/Help/", "https://muhammadsheharyar16.github.io/hisaabpro/help"),
        ("https://www.muhammadsheharyar16.github.io/hisaabpro/pricing", "https://muhammadsheharyar16.github.io/hisaabpro/pricing"),
        ("https://muhammadsheharyar16.github.io/hisaabpro/", "https://muhammadsheharyar16.github.io/hisaabpro"),
        ("www.muhammadsheharyar16.github.io/hisaabpro/signup", "https://muhammadsheharyar16.github.io/hisaabpro/signup"),
        ("https://muhammadsheharyar16.github.io/hisaabpro/help?ref=ai", "https://muhammadsheharyar16.github.io/hisaabpro/help?ref=ai"),
        ("http://muhammadsheharyar16.github.io/hisaabpro/help", "http://muhammadsheharyar16.github.io/hisaabpro/help"),
        ("https://muhammadsheharyar16.github.io@evil.com/hisaabpro/help", "https://muhammadsheharyar16.github.io@evil.com/hisaabpro/help"),
    ],
)
def test_url_normalisation(raw: str, expected: str) -> None:
    assert url(raw) == expected


@pytest.mark.parametrize(
    ("text", "value"),
    [("14", 14), ("fourteen", 14), ("Seven", 7), ("twenty-one", 21), ("thirty one", 31), ("ninety", 90)],
)
def test_number_words(text: str, value: int) -> None:
    assert number(text) == value


@pytest.mark.parametrize(
    ("amount", "unit", "value"),
    [("14", "days", 14), ("1", "day", 1), ("two", "weeks", 14), ("1", "month", 30), ("2", "Years", 730)],
)
def test_days_conversion(amount: str, unit: str, value: int) -> None:
    assert days(amount, unit) == value
