"""Version 1 of the trusted rules, inserted only when the table is empty."""

from sqlmodel import Session

from app.rules import repository
from app.schemas.rules import Rules

SEED_RULES: dict = {
    "prices": [
        {"product": "Basic plan", "aliases": ["basic"], "price": "Rs 4,999", "other_prices": ["USD 18"]},
        {"product": "Pro plan", "aliases": ["pro"], "price": "USD 49", "other_prices": ["Rs 13,999"]},
        {"product": "Business plan", "aliases": ["business"], "price": "USD 99", "other_prices": ["Rs 27,999"]},
    ],
    "discounts": [{"name": "Annual billing", "percent": 20}],
    "policies": [
        {
            "id": "refund",
            "title": "Refund policy",
            "topics": ["refund", "money back", "refundable"],
            "text": "Refunds are available within 14 days of purchase. "
                    "After 14 days, payments are non-refundable.",
        },
        {
            "id": "trial",
            "title": "Free trial policy",
            "topics": ["trial"],
            "text": "New Pro plan customers get a 7-day free trial. No card is charged during the trial.",
        },
        {
            "id": "cancel",
            "title": "Cancellation policy",
            "topics": ["cancel", "cancellation"],
            "text": "You can cancel your subscription at any time from Account Settings. "
                    "Access continues until the end of the billing period.",
        },
    ],
    "allowed_links": [
        "https://muhammadsheharyar16.github.io/hisaabpro/pricing",
        "https://muhammadsheharyar16.github.io/hisaabpro/help",
        "https://muhammadsheharyar16.github.io/hisaabpro/help/policies",
        "https://muhammadsheharyar16.github.io/hisaabpro/signup",
    ],
    "brand_names": ["Hisaab Pro"],
    "banned_phrases": [
        "guaranteed refund",
        "100% guaranteed",
        "lifetime free",
        "no questions asked",
        "best price guaranteed",
    ],
    "safe_messages": {
        "pricing": "For the latest official prices, please see https://muhammadsheharyar16.github.io/hisaabpro/pricing. "
                   "Our team is happy to confirm the right plan for you.",
        "policy": "Please see our official policies at https://muhammadsheharyar16.github.io/hisaabpro/help/policies. "
                  "Our support team can help with any questions about your account.",
        "link": "For help and resources, please visit https://muhammadsheharyar16.github.io/hisaabpro/help.",
        "general": "Sorry, I can't answer that right now. Please visit https://muhammadsheharyar16.github.io/hisaabpro/help "
                   "or contact our support team.",
    },
}


def seed_if_empty(session: Session) -> bool:
    """Insert v1 when no rules exist. Returns True if it seeded."""
    if repository.latest_version_number(session) is not None:
        return False
    repository.save_new_version(session, Rules.model_validate(SEED_RULES), note="seed", author="system")
    return True
