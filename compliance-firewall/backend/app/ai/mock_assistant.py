"""Canned "AI draft" answers standing in for the client's assistant. Modes: accurate | mistakes."""

from typing import Literal

from app.schemas.rules import Rules

Mode = Literal["accurate", "mistakes"]

_REFUND_KEYWORDS = ("refund", "money back")
_TRIAL_KEYWORDS = ("trial",)
_CANCEL_KEYWORDS = ("cancel",)
_DISCOUNT_KEYWORDS = ("discount", "annual", "yearly", "coupon", "offer")
# Topic -> id of the policy whose official wording is the accurate answer.
_POLICY_FOR = {_REFUND_KEYWORDS: "refund", _TRIAL_KEYWORDS: "trial", _CANCEL_KEYWORDS: "cancel"}
_PRICING_KEYWORDS = ("price", "cost", "plan", "how much", "pricing", "pro", "basic", "business")
_PRICING_LINK = "Compare plans at https://muhammadsheharyar16.github.io/hisaabpro/pricing."

# (question keywords, accurate draft, draft with typical invented facts). First match wins.
_CANNED: list[tuple[tuple[str, ...], str, str]] = [
    (
        _REFUND_KEYWORDS,
        "Refunds are available within 14 days of purchase. After 14 days, payments are non-refundable.",
        "Don't worry, you get a guaranteed refund anytime, no questions asked!",
    ),
    (
        _TRIAL_KEYWORDS,
        "New Pro plan customers get a 7-day free trial. No card is charged during the trial.",
        "Every plan comes with a 30-day free trial.",
    ),
    (
        _CANCEL_KEYWORDS,
        "You can cancel your subscription at any time from Account Settings.",
        "You can cancel within 30 days and we will send you a full refund.",
    ),
    (
        _DISCOUNT_KEYWORDS,
        "Annual billing gives you a 20% discount.",
        "Use code SAVE50 to get 50% off any plan this week.",
    ),
    (
        _PRICING_KEYWORDS,
        f"Basic is Rs 4,999, Pro is $49 and Business is $99 per month. {_PRICING_LINK}",
        "Basic is Rs 3,999, Pro is $59 and Business is $129 per month. "
        "Grab the deal at https://hisaabpro-deals.com/pricing.",
    ),
    (
        ("link", "help", "support", "sign up", "signup", "website"),
        "You can find help at https://muhammadsheharyar16.github.io/hisaabpro/help or sign up at https://muhammadsheharyar16.github.io/hisaabpro/signup.",
        "Visit https://hisaabpro-support.net/help for instant help.",
    ),
]

_FALLBACK = (
    "Hi! I'm the Hisaab Pro assistant. How can I help you today?",
    "Hisaab Pro is best price guaranteed, so you can't go wrong!",
)


def _price_list(rules: Rules) -> str:
    """ "Basic plan is Rs 4,999, Pro plan is USD 49 and Business plan is USD 99 per month." """
    parts = [f"{rule.product} is {rule.price}" for rule in rules.prices]
    listed = parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"
    return f"{listed} per month."


def _from_rules(keywords: tuple[str, ...], rules: Rules) -> str | None:
    """The accurate draft for this topic, built from the current rules. None: use the canned one."""
    if keywords is _PRICING_KEYWORDS:
        return f"{_price_list(rules)} {_PRICING_LINK}" if rules.prices else None
    if keywords is _DISCOUNT_KEYWORDS:
        if not rules.discounts:
            return "We don't have any discounts at the moment."
        return " ".join(f"{d.name} gives you a {d.percent.normalize():f}% discount." for d in rules.discounts)
    policy = rules.policy(_POLICY_FOR.get(keywords))
    return policy.text if policy else None


def draft(question: str, mode: Mode, rules: Rules | None = None) -> str:
    """With `rules`, accurate drafts quote the current prices, discounts and policy wording."""
    lowered = question.lower()
    for keywords, accurate, mistakes in _CANNED:
        if any(k in lowered for k in keywords):
            if mode != "accurate":
                return mistakes
            return (_from_rules(keywords, rules) if rules is not None else None) or accurate
    return _FALLBACK[0] if mode == "accurate" else _FALLBACK[1]
