import pytest

from app.pipeline.extract import extract, sentence_spans
from app.schemas.facts import Fact
from app.schemas.rules import Rules


def of_type(facts: list[Fact], kind: str) -> list[Fact]:
    return [f for f in facts if f.type == kind]


@pytest.mark.parametrize(
    ("answer", "raw", "value"),
    [
        ("Pro is $49 a month.", "$49", "USD 49"),
        ("Pro is US$49 a month.", "US$49", "USD 49"),
        ("Pro is 49 USD a month.", "49 USD", "USD 49"),
        ("Basic is Rs 4,999.", "Rs 4,999", "PKR 4,999"),
        ("Basic is Rs. 4,999 monthly.", "Rs. 4,999", "PKR 4,999"),
        ("Basic is 4999 PKR.", "4999 PKR", "PKR 4,999"),
        ("Basic is PKR 4,999.00 monthly.", "PKR 4,999.00", "PKR 4,999"),
        ("Pro is 49 dollars.", "49 dollars", "USD 49"),
    ],
)
def test_price_formats_with_offsets(rules: Rules, answer: str, raw: str, value: str) -> None:
    [price] = of_type(extract(answer, rules), "price")
    assert price.raw == raw
    assert answer[price.start:price.end] == raw
    assert price.value == value
    assert price.product in {"Pro plan", "Basic plan"}


def test_multi_price_linking_nearest_before(rules: Rules) -> None:
    answer = "Basic is Rs 4,999, Pro is $49 and Business is $129"
    prices = of_type(extract(answer, rules), "price")
    assert [(p.raw, p.product) for p in prices] == [
        ("Rs 4,999", "Basic plan"), ("$49", "Pro plan"), ("$129", "Business plan"),
    ]


def test_price_links_to_product_after_when_none_before(rules: Rules) -> None:
    [price] = of_type(extract("For just $49 you get the Pro plan.", rules), "price")
    assert price.product == "Pro plan"


def test_price_links_to_only_product_mentioned(rules: Rules) -> None:
    answer = "The Business plan is great. It costs $99. Price: $99."
    prices = of_type(extract(answer, rules), "price")
    assert all(p.product == "Business plan" for p in prices)


def test_price_without_product_is_unlinked(rules: Rules) -> None:
    [price] = of_type(extract("The Enterprise plan costs $499.", rules), "price")
    assert price.product is None


def test_longest_product_name_wins(rules: Rules) -> None:
    [price] = of_type(extract("The Pro plan costs $49.", rules), "price")
    assert price.product == "Pro plan"


@pytest.mark.parametrize(
    "answer",
    [
        "Hisaab Pro costs Rs 4,999 for the Basic plan.",
        "Rs 4,999 gets you Basic, see https://muhammadsheharyar16.github.io/hisaab-pro/pricing",
    ],
)
def test_brand_names_and_links_are_not_products(rules: Rules, answer: str) -> None:
    [price] = of_type(extract(answer, rules), "price")
    assert price.product == "Basic plan"


def test_percent_and_period(rules: Rules) -> None:
    facts = extract("Save 20% yearly, or 15 percent monthly. Refunds within 14 days; a 7-day trial.", rules)
    assert [f.value for f in of_type(facts, "percent")] == ["20", "15"]
    assert [(f.raw, f.value) for f in of_type(facts, "period")] == [("14 days", "14"), ("7-day", "7")]


def test_links_strip_trailing_punctuation(rules: Rules) -> None:
    answer = "See https://muhammadsheharyar16.github.io/hisaabpro/help. Or (https://muhammadsheharyar16.github.io/hisaabpro/pricing), or www.muhammadsheharyar16.github.io/hisaabpro/signup!"
    links = of_type(extract(answer, rules), "link")
    assert [link.raw for link in links] == [
        "https://muhammadsheharyar16.github.io/hisaabpro/help", "https://muhammadsheharyar16.github.io/hisaabpro/pricing", "www.muhammadsheharyar16.github.io/hisaabpro/signup",
    ]
    assert all(answer[link.start:link.end] == link.raw for link in links)


def test_numbers_inside_links_are_not_facts(rules: Rules) -> None:
    facts = extract("Go to https://muhammadsheharyar16.github.io/hisaabpro/help/30-days-50%off now.", rules)
    assert [f.type for f in facts] == ["link"]


@pytest.mark.parametrize(
    "sentence",
    [
        "Refunds are available within 14 days.",
        "You get your money back.",
        "It's guaranteed.",
        "Start a free trial today.",
        "You can use it for free.",
        "You can cancel anytime.",
        "The laptop has a warranty.",
        "Payments are non-refundable.",
    ],
)
def test_promise_keywords(rules: Rules, sentence: str) -> None:
    assert of_type(extract(sentence, rules), "promise")


def test_plain_free_is_not_a_promise(rules: Rules) -> None:
    assert extract("Feel free to ask me anything else!", rules) == []


def test_promise_is_whole_sentence_with_offsets(rules: Rules) -> None:
    answer = "Hi there! Refunds are available within 14 days of purchase. Anything else?"
    [promise] = of_type(extract(answer, rules), "promise")
    assert promise.raw == "Refunds are available within 14 days of purchase."
    assert answer[promise.start:promise.end] == promise.raw


def test_no_facts_in_greeting(rules: Rules) -> None:
    assert extract("Hi! How can I help?", rules) == []


def test_sentence_split_keeps_rs_abbreviation() -> None:
    text = "Basic is Rs. 4,999 with a refund. Pro is great."
    assert [text[s:e] for s, e in sentence_spans(text)] == [
        "Basic is Rs. 4,999 with a refund.", "Pro is great.",
    ]


@pytest.mark.parametrize(
    ("answer", "raw", "value"),
    [
        ("Refunds within fourteen days.", "fourteen days", "14"),
        ("Refunds within two weeks.", "two weeks", "14"),
        ("A two-week refund window.", "two-week", "14"),
        ("A 7-day trial.", "7-day", "7"),
        ("Refunds within twenty-one days.", "twenty-one days", "21"),
        ("Refunds within 1 month.", "1 month", "30"),
        ("A 2-year warranty.", "2-year", "730"),
    ],
)
def test_period_words_and_units(rules: Rules, answer: str, raw: str, value: str) -> None:
    [period] = of_type(extract(answer, rules), "period")
    assert (period.raw, period.value) == (raw, value)
    assert answer[period.start:period.end] == raw


@pytest.mark.parametrize(
    "answer",
    ["Pro is $49 a month.", "Pro is $49 per month.", "We reply within one business day.", "Refunds take a while."],
)
def test_not_periods(rules: Rules, answer: str) -> None:
    assert of_type(extract(answer, rules), "period") == []


@pytest.mark.parametrize(
    ("answer", "raw", "value"),
    [
        ("Refunds are open until 31 March.", "31 March", "--03-31"),
        ("Offer ends on 1st of Dec 2026.", "1st of Dec 2026", "2026-12-01"),
        ("Offer ends March 31st, 2026.", "March 31st, 2026", "2026-03-31"),
        ("Prices change in June 2027.", "June 2027", "2027-06"),
        ("Valid until 2026-03-31.", "2026-03-31", "2026-03-31"),
        ("Valid until 31/03/2026.", "31/03/2026", "2026-03-31"),
        ("Valid until 5.4.26 only.", "5.4.26", "2026-04-05"),
    ],
)
def test_dates(rules: Rules, answer: str, raw: str, value: str) -> None:
    [date] = of_type(extract(answer, rules), "date")
    assert (date.raw, date.value) == (raw, value)
    assert answer[date.start:date.end] == raw


@pytest.mark.parametrize(
    "answer",
    ["You may 2x your usage.", "Version 4.99 is out.", "Call 31/13/2026.", "Basic is Rs 4,999 in March."],
)
def test_not_dates(rules: Rules, answer: str) -> None:
    assert of_type(extract(answer, rules), "date") == []
