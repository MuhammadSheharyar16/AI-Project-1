"""Canned "AI draft" answers standing in for the client's assistant. Modes: accurate | mistakes."""

from typing import Literal

Mode = Literal["accurate", "mistakes"]

# (question keywords, accurate draft, draft with typical invented facts). First match wins.
_CANNED: list[tuple[tuple[str, ...], str, str]] = [
    (
        ("refund", "money back"),
        "Refunds are available within 14 days of purchase. After 14 days, payments are non-refundable.",
        "Don't worry, you get a guaranteed refund anytime, no questions asked!",
    ),
    (
        ("trial",),
        "New Pro plan customers get a 7-day free trial. No card is charged during the trial.",
        "Every plan comes with a 30-day free trial.",
    ),
    (
        ("cancel",),
        "You can cancel your subscription at any time from Account Settings.",
        "You can cancel within 30 days and we will send you a full refund.",
    ),
    (
        ("discount", "annual", "yearly", "coupon", "offer"),
        "Annual billing gives you a 20% discount.",
        "Use code SAVE50 to get 50% off any plan this week.",
    ),
    (
        ("price", "cost", "plan", "how much", "pricing", "pro", "basic", "business"),
        "Basic is Rs 4,999, Pro is $49 and Business is $99 per month. "
        "Compare plans at https://muhammadsheharyar16.github.io/hisaabpro/pricing.",
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


def draft(question: str, mode: Mode) -> str:
    lowered = question.lower()
    for keywords, accurate, mistakes in _CANNED:
        if any(k in lowered for k in keywords):
            return accurate if mode == "accurate" else mistakes
    return _FALLBACK[0] if mode == "accurate" else _FALLBACK[1]
