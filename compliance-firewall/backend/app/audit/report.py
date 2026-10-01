"""AI governance report: configuration, controls in force and live usage numbers."""

from sqlmodel import Session

from app.ai.governance import AIPolicy
from app.audit import repository as audit_repo
from app.pipeline.extract_ai import MAX_AI_FACTS
from app.pipeline.checks.policy_ai import MIN_QUOTE_WORDS
from app.rules import repository as rules_repo
from app.schemas.api import GovernanceReport

SECURITY_CONTROLS = [
    "Answers are scanned in code before any AI call: prompt-injection text, hidden/bidi control "
    "characters, leaked API keys, payment card numbers (Luhn) and CNIC numbers are rejected.",
    "Personal data (emails, phone, card and CNIC numbers) is redacted before text is sent to the LLM.",
    "Untrusted text is fenced between <<< >>> markers and cannot close its own block.",
    "AI output is schema-validated; a malformed response fails closed (Error).",
    f"AI-extracted facts must be grounded (quote found in the answer), at most {MAX_AI_FACTS} per answer.",
    f"AI 'supported' verdicts need a verified word-for-word policy quote (>= {MIN_QUOTE_WORDS} words).",
    "Any AI error, timeout, 429, kill switch or budget stop gives Error and the general safe message.",
    "Rule edits, reviews and suite runs require X-Admin-Token (ADMIN_TOKEN).",
    "Checks, chat, audit reads, rules reads and this report require X-API-Key (API_TOKEN).",
    "Per-client rate limit on endpoints that can trigger AI calls (HTTP 429).",
    "Security headers on every response; CORS is an explicit origin list without credentials.",
    "AI 'periods' that are billing cadence or reply times are ignored, not treated as policy limits.",
    "The Groq API key lives only in the backend .env and is never logged or returned.",
]


def build(session: Session, ai: AIPolicy, admin_token_set: bool, api_token_set: bool = False,
          redact_pii: bool = True) -> GovernanceReport:
    outcomes, purposes, avg_ms = audit_repo.ai_call_stats(session)
    reviews = audit_repo.review_counts(session)
    reviewed = sum(reviews.values())
    latest = rules_repo.get_latest(session)
    return GovernanceReport(
        ai={
            "provider": "Groq (free tier)",
            "model": ai.model,
            "prompt_version": ai.prompt_version,
            "temperature": 0,
            "json_mode": True,
            "enabled": ai.enabled,
            "timeout_s": ai.timeout_s,
            "max_calls_per_minute": ai.budget.max_per_minute,
            "uses": ["extract (facts the pattern rules missed)", "verify (promises against policies)"],
        },
        security_controls=SECURITY_CONTROLS
        + (["Personal data is redacted before it is stored in the audit log."] if redact_pii else
           ["WARNING: AUDIT_REDACT_PII=false, so the audit log may store personal data."])
        + ([] if admin_token_set else
           ["WARNING: ADMIN_TOKEN is not set (write endpoints need DEBUG=true)."])
        + ([] if api_token_set else
           ["WARNING: API_TOKEN is not set (client endpoints need DEBUG=true)."]),
        rules={
            "latest_version": latest.version if latest else None,
            "latest_author": latest.author if latest else None,
            "versions": len(rules_repo.list_versions(session)),
        },
        decisions=audit_repo.decision_counts(session),
        ai_usage={
            "calls_by_outcome": dict(outcomes),
            "calls_by_purpose": dict(purposes),
            "avg_call_ms": avg_ms,
            "window": "latest 1000 decisions",
        },
        human_review={
            "reviews": reviewed,
            "agree": reviews.get("agree", 0),
            "disagree": reviews.get("disagree", 0),
            "disagreement_rate": round(reviews.get("disagree", 0) / reviewed, 4) if reviewed else 0.0,
        },
    )
