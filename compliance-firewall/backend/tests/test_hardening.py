"""Gap fixes: client token, rate limit, security headers, CORS, audit PII redaction,
schema migration and the AI cadence guard."""

import sqlite3
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.ai.prompts import EXTRACT_TASK
from app.ai.redact import redact
from app.core.security import ClientRateLimiter
from app.main import create_app
from app.rules.seed import SEED_RULES
from conftest import FakeLLM, make_settings, use_llm

SAFE = SEED_RULES["safe_messages"]


def check(client: TestClient, answer: str, **headers: str) -> Any:
    return client.post("/check", json={"question": "q", "answer": answer}, headers=headers)


# --- G2: client token on read/check endpoints -------------------------------------

def test_api_token_protects_check_chat_audit_and_governance(client: TestClient) -> None:
    client.app.state.settings.api_token = SecretStr("client-key")
    client.app.state.settings.admin_token = SecretStr("admin-key")
    for method, path, body in [("post", "/check", {"answer": "Pro is $49"}),
                               ("post", "/chat", {"question": "price?"}),
                               ("get", "/audit", None), ("get", "/governance", None),
                               ("get", "/rules", None), ("get", "/rules/versions", None)]:
        call = getattr(client, method)
        kwargs = {"json": body} if body else {}
        assert call(path, **kwargs).status_code == 401, path
        assert call(path, headers={"X-API-Key": "wrong"}, **kwargs).status_code == 401, path
        assert call(path, headers={"X-API-Key": "client-key"}, **kwargs).status_code == 200, path
        assert call(path, headers={"X-Admin-Token": "admin-key"}, **kwargs).status_code == 200, path
    assert client.get("/health").status_code == 200  # liveness stays open


def test_client_endpoints_closed_without_token_outside_debug(client: TestClient) -> None:
    client.app.state.settings.debug = False
    assert check(client, "Pro is $49").status_code == 403
    assert client.get("/audit").status_code == 403


def test_client_token_cannot_edit_rules(client: TestClient) -> None:
    client.app.state.settings.api_token = SecretStr("client-key")
    client.app.state.settings.admin_token = SecretStr("admin-key")
    body = {"rules": SEED_RULES, "author": "x"}
    assert client.put("/rules", json=body, headers={"X-API-Key": "client-key"}).status_code == 401


# --- G2: per-client rate limit ------------------------------------------------------

def test_rate_limit_per_client(client: TestClient) -> None:
    client.app.state.rate_limiter = ClientRateLimiter(per_minute=2)
    assert check(client, "Pro is $49").status_code == 200
    assert check(client, "Pro is $49").status_code == 200
    blocked = check(client, "Pro is $49")
    assert blocked.status_code == 429 and blocked.headers["Retry-After"] == "60"
    assert client.get("/audit").status_code == 200  # reads are not rate limited


def test_rate_limiter_is_per_key() -> None:
    limiter = ClientRateLimiter(per_minute=1)
    assert limiter.allow("1.1.1.1") and limiter.allow("2.2.2.2")
    assert not limiter.allow("1.1.1.1")


# --- G4: security headers and CORS ---------------------------------------------------

def test_security_headers_on_every_response(client: TestClient) -> None:
    for response in (client.get("/health"), check(client, "Pro is $49"), client.get("/audit/999")):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "strict-transport-security" not in response.headers  # plain HTTP in tests


def test_hsts_only_over_https(app: FastAPI) -> None:
    with TestClient(app, base_url="https://testserver") as https_client:
        assert "max-age=" in https_client.get("/health").headers["strict-transport-security"]


def test_cors_wildcard_only_in_debug() -> None:
    assert make_settings(cors_origins="*", debug=False).cors_origin_list == []
    assert make_settings(cors_origins="*", debug=True).cors_origin_list == ["*"]
    explicit = make_settings(cors_origins="http://localhost:8081, *", debug=False)
    assert explicit.cors_origin_list == ["http://localhost:8081"]


def test_cors_allows_only_configured_origin(tmp_path: Any) -> None:
    settings = make_settings(database_url=f"sqlite:///{tmp_path.as_posix()}/c.db",
                        debug=True, cors_origins="http://localhost:8081")
    with TestClient(create_app(settings)) as c:
        ok = c.options("/check", headers={"Origin": "http://localhost:8081",
                                          "Access-Control-Request-Method": "POST"})
        assert ok.headers.get("access-control-allow-origin") == "http://localhost:8081"
        evil = c.options("/check", headers={"Origin": "https://evil.example",
                                            "Access-Control-Request-Method": "POST"})
        assert "access-control-allow-origin" not in evil.headers


# --- G3: personal data is redacted before it is stored ----------------------------------

def test_audit_log_stores_no_personal_data(client: TestClient) -> None:
    answer = "Refunds are available within 14 days of purchase, write to ali@example.com."
    live = client.post("/check", json={"question": "I am ali@example.com, refund?", "answer": answer}).json()
    assert live["compliance"]["raw_answer"] == answer  # the live compliance view is unchanged

    entry = client.get(f"/audit/{live['compliance']['audit_id']}").json()
    stored = str(entry)
    assert "ali@example.com" not in stored
    assert entry["raw_answer"] == "Refunds are available within 14 days of purchase, write to [EMAIL]."
    assert entry["question"] == "I am [EMAIL], refund?"
    assert "PII redacted" in entry["trace"][-1]["note"]


def test_card_leak_stays_rejected_after_redaction_and_recheck(client: TestClient) -> None:
    body = check(client, "Your card 4111 1111 1111 1111 is saved.").json()
    assert body["compliance"]["decision"] == "Rejected"
    entry = client.get(f"/audit/{body['compliance']['audit_id']}").json()
    assert "4111" not in str(entry) and entry["raw_answer"] == "Your card [CARD] is saved."
    recheck = client.post(f"/audit/{entry['id']}/recheck").json()["compliance"]
    assert recheck["decision"] == "Rejected"
    assert "redacted" in recheck["results"][0]["reason"]


def test_redaction_can_be_turned_off(client: TestClient) -> None:
    client.app.state.settings.audit_redact_pii = False
    body = check(client, "Mail ali@example.com for help.").json()
    assert client.get(f"/audit/{body['compliance']['audit_id']}").json()["raw_answer"] == \
        "Mail ali@example.com for help."


def test_redact_only_real_card_numbers() -> None:
    assert redact("Order 1234 5678 9012 3456 shipped.") == ("Order 1234 5678 9012 3456 shipped.", 0)
    assert redact("Card 4111 1111 1111 1111.")[0] == "Card [CARD]."


# --- G6: additive migration of an old database ---------------------------------------

def test_old_database_is_migrated_on_startup(tmp_path: Any) -> None:
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE rule_sets (version INTEGER PRIMARY KEY, created_at DATETIME, note VARCHAR,
                                body JSON NOT NULL);
        CREATE TABLE audit_entries (id INTEGER PRIMARY KEY, created_at DATETIME, question TEXT NOT NULL,
            raw_answer TEXT NOT NULL, shown_to_customer TEXT NOT NULL, decision VARCHAR, rule_version INTEGER,
            results_json JSON NOT NULL, trace_json JSON NOT NULL, ai_used BOOLEAN, latency_ms INTEGER,
            source VARCHAR, recheck_of INTEGER, error TEXT);
        INSERT INTO audit_entries VALUES (1, '2026-01-01 00:00:00', 'q', 'Pro is $49', 'Pro is $49',
            'Approved', 1, '[]', '[]', 0, 3, 'scenario', NULL, NULL);
    """)
    import json
    con.execute("INSERT INTO rule_sets VALUES (1, '2026-01-01 00:00:00', 'seed', ?)", (json.dumps(SEED_RULES),))
    con.commit()
    con.close()

    settings = make_settings(database_url=f"sqlite:///{db.as_posix()}", debug=True)
    with TestClient(create_app(settings)) as c:
        old = c.get("/audit/1").json()
        assert old["decision"] == "Approved" and old["ai_calls"] == [] and old["ai_model"] is None
        assert c.get("/rules").json()["author"] is None
        assert c.post("/check", json={"answer": "Pro is $59"}).json()["compliance"]["decision"] == "Rejected"
        assert c.post("/audit/1/review", json={"reviewer": "A", "verdict": "agree"}).status_code == 201

    columns = {row[1] for row in sqlite3.connect(db).execute("PRAGMA table_info(audit_entries)")}
    assert {"ai_model", "prompt_version", "ai_calls_json"} <= columns


# --- G1: AI "periods" that are billing cadence or reply times are ignored ----------------

class CadenceLLM(FakeLLM):
    def __init__(self, facts: list[dict[str, Any]]) -> None:
        super().__init__()
        self.facts = facts

    async def llm_json(self, prompt: str, timeout: float) -> dict[str, Any]:
        if prompt.startswith(EXTRACT_TASK):
            self.calls += 1
            return {"facts": self.facts}
        return await super().llm_json(prompt, timeout)


@pytest.mark.parametrize(
    ("answer", "quote"),
    [
        ("Our team replies to most messages within one business day.", "one business day"),
        ("Pro is forty-nine bucks a month.", "a month"),
        ("Support answers within 24 hours.", "24 hours"),
    ],
)
def test_ai_cadence_periods_are_ignored(app: FastAPI, client: TestClient, answer: str, quote: str) -> None:
    facts = [{"type": "period", "quote": quote, "days": 1}]
    if "bucks" in answer:
        facts.append({"type": "price", "quote": "forty-nine bucks", "amount": 49, "currency": "USD",
                      "product": "Pro plan"})
    use_llm(app, CadenceLLM(facts))
    body = check(client, answer).json()
    assert body["compliance"]["decision"] == "Approved", body["compliance"]["results"]
    note = next(s["note"] for s in body["compliance"]["trace"] if s["step"] == "ai_extract")
    assert "1 cadence ignored" in note


def test_real_ai_period_is_still_checked(app: FastAPI, client: TestClient) -> None:
    use_llm(app, CadenceLLM([{"type": "period", "quote": "a fortnight", "days": 14}]))
    ok = check(client, "Refunds are possible for a fortnight.").json()
    assert ok["compliance"]["decision"] == "Approved"
    use_llm(app, CadenceLLM([{"type": "period", "quote": "a full quarter", "days": 90}]))
    bad = check(client, "Refunds are possible for a full quarter.").json()
    assert bad["compliance"]["decision"] == "Rejected"
    period = next(r for r in bad["compliance"]["results"] if r["fact"]["type"] == "period")
    assert period["fact"]["source"] == "ai" and "period mismatch" in period["reason"]
