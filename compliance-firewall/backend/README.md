# Compliance Firewall for AI Answers — backend (POC-11)

The customer never sees an unchecked AI answer. The backend checks every AI support answer against the
editable **trusted rules**. It covers prices, discounts, policy time periods, links, banned phrases and
policy promises. The customer gets one of two things:

- the original answer, when the decision is **Approved**;
- a pre-approved **safe message**, when the decision is **Rejected** or **Error**.

Every decision goes into an audit log, along with the rule version used.

Everything here is free: FastAPI, SQLite, and the Groq free API with `openai/gpt-oss-20b`.

**Requirements coverage:** [docs/TRACEABILITY.md](docs/TRACEABILITY.md) maps every row of the POC-11
sheet, plus the AI, AI security and AI governance work, to linked code and tests, and records how each
gap was closed. **Architecture diagram and the demo's "resources and limits" content:**
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 1. Setup

Requirements: Python 3.11 or newer. It was developed and tested on 3.13.

```bash
cd compliance-firewall/backend
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.lock   # exact tested versions (requirements.txt = pinned direct deps)
cp .env.example .env               # Windows: copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"   # run twice: ADMIN_TOKEN and API_TOKEN
```

Then edit `.env`:

| Variable          | Default                         | Meaning |
|-------------------|---------------------------------|---------|
| `GROQ_API_KEY`    | **required**                    | Free key from https://console.groq.com/keys. It is only kept in `.env`. |
| `GROQ_MODEL`      | **required**, e.g. `openai/gpt-oss-20b` | Groq model used for the promise check. |
| `DATABASE_URL`    | **required**, e.g. `sqlite:///./data/firewall.db` | Any SQLAlchemy URL (see [Postgres](#10-switching-to-postgres)). |
| `CHECK_TIMEOUT_S` | `8`                             | Time limit for each AI call. When it runs out, the decision is **Error**. |
| `CORS_ORIGINS`    | *(empty)*; example: Expo web ports | Browser origins for Expo **web**. Native apps don't use CORS. `*` is ignored unless `DEBUG=true`. |
| `DEBUG`           | `false`                         | Turns on `?simulate=crash\|timeout` on `POST /check`, and opens token-protected endpoints **only if** their token is empty. Local demo only. |
| `AI_ENABLED`      | `true`                          | AI kill switch. When `false`, the LLM is never called and answers that need AI come back as **Error**. |
| `AI_MAX_CALLS_PER_MINUTE` | `25`                    | App-wide AI call budget, kept under the Groq free-tier limit. Going over it gives **Error**. |
| `ADMIN_TOKEN`     | *(empty)*                       | Required in the `X-Admin-Token` header for rule edits, restores, reviews and suite runs. When empty, those endpoints only work with `DEBUG=true`. |
| `API_TOKEN`       | *(empty)*                       | Required in the `X-API-Key` header for `/check`, `/chat`, `/audit*`, reading `/rules` and `/governance` (the admin token also works). When empty, those endpoints only work with `DEBUG=true`. `/health` is always open. |
| `RATE_LIMIT_PER_MINUTE` | `60`                      | Per-client (IP) limit on endpoints that can trigger AI calls: `/check`, `/chat`, recheck and suite. Going over it gives HTTP 429. |
| `AUDIT_REDACT_PII` | `true`                         | Redacts emails, phones, card and CNIC numbers before anything is stored in the audit log. |

`GROQ_API_KEY`, `GROQ_MODEL` and `DATABASE_URL` have no defaults in code: they are read only from `.env`
(or the environment), and the app will not start if one is missing. If `GROQ_API_KEY` is present but empty, the API still runs but fails closed. Any answer that needs the AI promise check
(for example "Refunds are available within 14 days") comes back as **Error**, with the general safe message.

## 2. Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The database file and the rules v1 seed are created automatically on first start. An older database
is upgraded in place: any missing columns are added at startup.

**HTTPS (optional, still $0):** create a local certificate with [mkcert](https://github.com/FiloSottile/mkcert)
(`mkcert -install && mkcert 192.168.1.20 localhost`), then run:
`uvicorn app.main:app --host 0.0.0.0 --port 8443 --ssl-keyfile 192.168.1.20+1-key.pem --ssl-certfile 192.168.1.20+1.pem`.
Responses then also carry `Strict-Transport-Security`.

- API docs: http://localhost:8000/docs
- **Testing from a phone on the same Wi-Fi.** `--host 0.0.0.0` makes the server listen on your LAN address.
  1. Find your computer's IP address. On Windows run `ipconfig` and look for the "IPv4 Address". On
     macOS or Linux run `ipconfig getifaddr en0` or `hostname -I`.
  2. In the Expo app, use `http://<that-ip>:8000` as the API base URL.
  3. On Windows, allow inbound connections on port 8000 when Windows Defender Firewall asks.
     Alternatively, run this in an admin shell:
     `netsh advfirewall firewall add rule name="firewall-api" dir=in action=allow protocol=TCP localport=8000`

## 3. Test

```bash
python -m pytest
```

The tests use a temporary SQLite file per test and a `FakeLLM` injected through
`app/api/deps.py::get_llm`. They are fast, free and repeatable, and never call Groq. Here's what each test file covers:

| File | Covers |
|------|--------|
| `tests/unit/test_normalize.py` | Every price format, currency handling (no conversion), URL normalisation |
| `tests/unit/test_extract.py`   | Facts and offsets, linking prices to products, percents, periods (words, weeks, months), dates, links, promises, "feel free" |
| `tests/unit/test_checks.py`    | Each code check; `decide`; the AI verified-quote rule (including an invented quote); the Groq client (429, 5xx, bad JSON, network error, no key) |
| `tests/test_client_cases.py`   | The 12 brief cases, plus fail-closed behaviour for a slow AI, a crashing AI, a 429, a missing key and a failed audit write |
| `tests/test_rules_versioning.py` | Seed, N+1 versions, restore, validation (422 and no new version), cache reload, audit filters |
| `tests/test_suite.py`          | 50 labelled answers: 0 leaked, ≥ 95 % caught, ≤ 10 % of approves blocked |
| `tests/test_ai_extraction.py`  | AI-assisted extraction: the gate, grounding, discarded hallucinations and duplicates, code checks on AI facts, malformed output → Error |
| `tests/test_ai_security.py`    | Injection, hidden-character, secret, card and CNIC scan; PII redaction; prompt fencing; admin token; no API-key leaks |
| `tests/test_ai_governance.py`  | Call ledger, model and prompt version, kill switch, budget, failed-call outcomes, human reviews, rule authors, `/governance` |
| `tests/test_hardening.py`      | Client token, per-client rate limit, security headers and HSTS, CORS, PII redaction at rest (plus recheck of a leak), migration of an old database, AI cadence guard |

## 4. API

Every check endpoint (`/chat`, `/check`, `/audit/{id}/recheck`) returns the same shape:

```json
{
  "customer": {"text": "For the latest official prices, please see https://muhammadsheharyar16.github.io/hisaabpro/pricing. ..."},
  "compliance": {
    "audit_id": 12, "decision": "Rejected", "rule_version": 1, "raw_answer": "Pro is $59",
    "results": [{"fact": {"type": "price", "raw": "$59", "start": 7, "end": 10, "source": "pattern",
                          "value": "USD 59", "product": "Pro plan"},
                 "ok": false, "rule": "Pro plan = USD 49",
                 "reason": "price mismatch: answer says USD 59, official price is USD 49", "quote": null}],
    "ai_used": false, "latency_ms": 3,
    "trace": [{"step": "load_rules", "status": "ran", "note": "cache hit (v1)", "ms": 0.4}, "..."],
    "error": null,
    "governance": {"ai_model": "openai/gpt-oss-20b", "prompt_version": "3f2a9c1b7d40",
                   "ai_calls": [{"purpose": "verify", "model": "openai/gpt-oss-20b",
                                 "prompt_version": "3f2a9c1b7d40", "outcome": "ok", "ms": 412.5,
                                 "redactions": 0, "error": null}]}
  }
}
```

Notes on the fields:

- `fact.type` is one of `price`, `percent`, `period`, `date`, `link`, `promise`, `phrase`
  (a banned phrase) or `security` (a security scan hit).
- `fact.source` is one of `pattern` (regex), `ai` (AI-assisted extraction), `banned_list` or
  `security_scan`.
- `fact.value` is the normalised value. For a period it's the number of days. For a date it's
  `2026-03-31`, or `--03-31` when there's no year, or `2026-06` when there's no day.
- `fact.product` is the product a price was linked to.
- `results` lists **every** extracted fact. Facts that were never checked have `skipped: true`,
  `ok: false` and a reason starting "not checked". That happens when the AI step was skipped because a
  code check had already failed, or when the pipeline errored. Skipped facts never pick the safe message.
- `trace[].step` is one of `load_rules`, `extract`, `simulate` (only when used), `code_checks`,
  `ai_extract`, `ai_check`, `decide` or `audit`.
- `governance.ai_calls` is the ledger of every AI call attempt for this decision. `outcome` is one
  of `ok`, `error`, `timeout`, `rate_limited`, `disabled` or `budget_exceeded`.

### curl examples

These are bash-style. On Windows, use Git Bash, or in PowerShell call `curl.exe` and escape the quotes.

```bash
API=http://localhost:8000
KEY="X-API-Key: $API_TOKEN"             # client endpoints (not needed when DEBUG=true and API_TOKEN is empty)

# Health
curl $API/health

# Mock assistant drafts an answer, then the firewall checks it (mode: accurate | mistakes)
curl -X POST $API/chat -H "$KEY" -H "Content-Type: application/json" \
  -d '{"question": "How much is Pro?", "mode": "mistakes"}'

# Check a given answer
curl -X POST $API/check -H "$KEY" -H "Content-Type: application/json" \
  -d '{"question": "Prices?", "answer": "Basic is Rs 4,999, Pro is $49 and Business is $129"}'

# Prove fail-closed (needs DEBUG=true)
curl -X POST "$API/check?simulate=crash"   -H "$KEY" -H "Content-Type: application/json" -d '{"answer": "Pro is $49"}'
curl -X POST "$API/check?simulate=timeout" -H "$KEY" -H "Content-Type: application/json" -d '{"answer": "Pro is $49"}'

# Rules: latest, versions, save a new version, restore an old one
curl -H "$KEY" $API/rules
curl -H "$KEY" $API/rules/versions
ADMIN="X-Admin-Token: $ADMIN_TOKEN"     # write endpoints (not needed when DEBUG=true and no token is set)
curl -H "$KEY" $API/rules | python -c "import sys,json; r=json.load(sys.stdin)['rules']; r['prices'][1]['price']='USD 59'; print(json.dumps({'rules': r, 'note': 'Pro price rise', 'author': 'Sara (compliance)'}))" > new_rules.json
curl -X PUT $API/rules -H "$ADMIN" -H "Content-Type: application/json" --data @new_rules.json
curl -X POST $API/rules/restore/1 -H "$ADMIN" -H "Content-Type: application/json" -d '{"author": "Sara (compliance)"}'

# Audit log (newest first). Filters: decision, version, source, q, limit, offset
curl -H "$KEY" "$API/audit?decision=Rejected&limit=10"
curl -H "$KEY" "$API/audit?source=chat&q=refund"
curl -H "$KEY" $API/audit/1
curl -H "$KEY" -X POST $API/audit/1/recheck        # re-runs entry 1 on the LATEST rules

# Human review of a decision (AI governance)
curl -X POST $API/audit/1/review -H "$ADMIN" -H "Content-Type: application/json" \
  -d '{"reviewer": "Ayesha", "verdict": "agree", "note": "correct block"}'

# AI governance and security report
curl -H "$KEY" $API/governance

# Run the 50 labelled answers
curl -X POST $API/suite/run -H "$ADMIN"
```

| Method | Path | Body / query | Returns |
|--------|------|--------------|---------|
| GET  | `/health` | – | `{status, rule_version, ai_configured, debug}` |
| POST | `/chat` | `{question, mode}` | check response (`source=chat`) |
| POST | `/check` | `{question?, answer}`, `?simulate=crash\|timeout` | check response (`source=scenario`) |
| GET  | `/rules` | – | `{version, created_at, note, author, rules}` |
| PUT 🔒 | `/rules` | `{rules, author, note?}` | 201 with the new version; 422 when invalid |
| GET  | `/rules/versions` | – | `[{version, created_at, note, author}]`, newest first |
| POST 🔒 | `/rules/restore/{v}` | `{author}` | 201 with the new version (a copy of v); 404 if v doesn't exist |
| GET  | `/audit` | `decision, version, source, q, limit (1–200), offset` | `{total, limit, offset, items}` |
| GET  | `/audit/{id}` | – | full audit entry, including `ai_model`, `prompt_version`, `ai_calls` and `reviews` |
| POST | `/audit/{id}/recheck` | – | check response (`source=recheck`, `recheck_of=id`) |
| POST 🔒 | `/audit/{id}/review` | `{reviewer, verdict: agree\|disagree, note?}` | 201 with the review (append-only; the decision itself never changes) |
| GET  | `/governance` | – | AI config, security controls, decision counts, AI usage, human-review rates |
| POST 🔒 | `/suite/run` | – | `{total, leaked, caught_rate, false_block_rate, ai_calls, rule_version, rows}` |

🔒 = needs `X-Admin-Token` when `ADMIN_TOKEN` is set. Every other endpoint except `/health` needs
`X-API-Key` (or the admin token) when `API_TOKEN` is set. Without a token set, these only work with
`DEBUG=true`. `/check`, `/chat`, recheck and suite are also rate-limited per client (429).

## 5. How a check works

1. **Load rules** from the in-memory cache. Each request runs one cheap `max(version)` query, and the
   rules are only reloaded when that number changes. The trace note says `cache hit (vN)` or `reloaded (vN)`.
2. **Extract facts** with pattern rules (regex), recording character offsets. Two scans run at the same time:
   - the **security scan** (see [AI security](#6-ai-security));
   - the **banned phrases** scan.

   The pattern rules extract:
   - **Prices:** `$49`, `US$49`, `49 USD`, `Rs 4,999`, `Rs. 4,999`, `4999 PKR`, `PKR 4,999.00`, `49 dollars`.
     Each price is linked to a product in this order:
     1. the nearest product before it (back to the previous price);
     2. otherwise the first product after it (up to the next price);
     3. otherwise the only product mentioned in the answer.
   - **Percents** (`20%`, `20 percent`).
   - **Periods**, converted to days: `14 days`, `14-day`, `fourteen days`, `two weeks`, `1 month`
     (30 days) and `2-year` (365 days per year).
   - **Calendar dates:** `31 March`, `1st of Dec 2026`, `March 31st, 2026`, `June 2027`,
     `2026-03-31` and `31/03/2026`. Numeric dates are read day first.
   - **Links:** `http(s)://…` and bare `www.…`.
   - **Promises:** sentences that mention refund, money back, guarantee, trial, for free, cancel or
     warranty. A plain "free", as in "feel free", doesn't count.
3. **Nothing found and no cues left** → Approved immediately, with the AI skipped entirely. "Nothing
   found" means no facts, no banned phrase and no security hit. "No cues left" means nothing fact-like
   remains once the pattern facts are removed.
4. **Code checks**, run per fact:
   - price (compared with the plan's one official price: same currency, amount within 0.01);
   - link (normalised URL must be on the allowed list);
   - percent (must be an approved discount);
   - period (must match a day count in the policy the sentence is about);
   - date (the same date must be stated in the policy the sentence is about);
   - banned phrases;
   - unlimited promises ("anytime", "forever", "lifetime", "no time limit") against a policy with a day limit.
5. **Any code check failed** → Rejected, and both AI steps are skipped.
6. **AI-assisted extraction** (the "pattern rules + AI" step). This runs only when **cues are left
   over** after the pattern facts are blanked out:
   - digits;
   - number words ("forty-nine", "half");
   - currency words ("bucks", "rupees");
   - domain-like text ("hisaabpro dot github dot io", "deals.com");
   - money-back words ("reimburse", "cash back").

   The AI returns typed facts, and each one must be **grounded**: its quote has to appear in the answer.
   - Ungrounded (hallucinated) facts and invalid items are discarded and counted in the trace.
   - Facts the pattern rules already found are dropped as duplicates.
   - Grounded AI facts (`source: "ai"`) go through **the same code checks**.
   - An AI fact with missing fields (for example a price with no amount) fails as "unreadable".
   - A malformed AI response gives **Error**.
7. **AI promise check** for each promise not already judged (pattern or AI-found). Groq runs in JSON mode at temperature 0 and
   returns `{verdict, policy_id, quote, reason}`. The promise only passes when the verdict is `supported`
   **and** the quote appears word for word in that policy's text. Otherwise the reason is
   `contradicted`, `not covered` or `unverified quote`. Each call is wrapped in
   `asyncio.wait_for(CHECK_TIMEOUT_S)`.
8. **Decide.** The answer is Approved only if every result is OK. On rejection, the first failing fact
   (by position) picks the safe message:
   - price or percent → `pricing`
   - link → `link`
   - promise, period, date or banned phrase → `policy`
   - security hit or Error → `general`
9. **Audit.** The entry is saved with:
   - the rule version, the per-fact results and the trace;
   - the AI model, the prompt version and the AI call ledger.

Every AI call, both extract and verify, goes through one gateway (`app/ai/governance.py`). The gateway:
- applies the kill switch, the per-minute budget, PII redaction and the timeout;
- records the call in the ledger.

## 6. AI security

| Threat | Control |
|--------|---------|
| Prompt injection in an AI answer ("ignore previous instructions", "system prompt", `<<<`/`>>>`, `"verdict":`) | Code scan before any AI call. A hit means Rejected with the general safe message, and the text never reaches the LLM. |
| Hidden or bidi Unicode used to sneak past checks (e.g. "Guaranteed\u200b refund") | Zero-width and bidi control characters are flagged as a security fact. |
| The AI assistant leaking secrets or sensitive data | The scan rejects API keys (`gsk_…`, `sk-…`, `AKIA…`, GitHub and Slack tokens), payment card numbers (Luhn-checked) and CNIC numbers. |
| Personal data sent to a third-party LLM | Emails, phone, card and CNIC numbers are redacted (`[EMAIL]` and so on) before every call. The ledger records how many redactions were made. |
| Untrusted text breaking out of its data block | Answers and claims are fenced between `<<<`/`>>>` markers. Marker characters inside the text are neutralised, and the system prompt says the fenced text is data. |
| Hallucinated or tampered AI output | Output is schema-validated, and malformed output gives Error. Extraction quotes must be grounded in the answer, with at most 25 facts. "Supported" verdicts need a word-for-word policy quote. |
| Unauthorised rule changes | `PUT /rules`, restore, reviews and suite runs require `X-Admin-Token`, compared in constant time. With no token configured, they only work in DEBUG. |
| Unauthorised reads of the audit log, or strangers spending the AI budget | Every endpoint except `/health` requires `X-API-Key` (or the admin token). `/check`, `/chat`, recheck and suite have a per-client rate limit (HTTP 429 with `Retry-After`). |
| Personal data at rest | With `AUDIT_REDACT_PII=true` (the default), question, answer, customer text and fact values are redacted before storage. Stored `[CARD]`/`[CNIC]` placeholders are flagged by the security scan, so a recheck of a leak stays Rejected. |
| Browser and transport attacks | Security headers on every response (`nosniff`, `DENY` framing, `no-referrer`, `no-store`, and HSTS over HTTPS). CORS is an explicit list with no credentials; `*` only works in DEBUG. Optional HTTPS via uvicorn plus mkcert. |
| Supply chain | Direct dependencies are pinned in `requirements.txt`, and the full tested set is in `requirements.lock`. |
| API key exposure | The key lives only in `.env` as a `SecretStr`. It is never logged, returned or included in error messages. |

## 7. AI governance

- **One gateway for every AI call.** It enforces:
  - the **kill switch** (`AI_ENABLED`);
  - the **call budget** (`AI_MAX_CALLS_PER_MINUTE`, a sliding window, app-wide);
  - **PII redaction**;
  - the **timeout**.
- **Provenance.** Every audit entry stores the model and a `prompt_version`: a 12-character hash of
  every prompt template. Any change to the prompt wording is traceable to the decisions it produced.
- **AI call ledger.** Each decision records every AI call attempt: purpose (`extract` or `verify`),
  outcome, time and the number of redactions.
- **Human in the loop.** `POST /audit/{id}/review` lets a compliance reviewer agree or disagree with a
  decision. Reviews are append-only and never change the recorded decision. The disagreement rate is
  reported.
- **Accountable rule changes.** Every rules version records its `author`. The seed version is `system`.
- **Report.** `GET /governance` shows:
  - the AI configuration: model, prompt version, temperature 0, JSON mode, kill switch, budget,
    timeout;
  - the security controls in force;
  - decision counts;
  - AI usage by outcome and purpose, with average latency;
  - human-review numbers.

  This is the content for the "resources and limits" demo slide.

## 8. Fail-closed choices (where the brief was ambiguous)

- **Any exception becomes Error.** This includes timeouts, a 429, network errors, HTTP errors, malformed or
  invalid AI JSON, a missing API key, the kill switch and the call budget. The customer gets the general safe message.
- **The audit log is part of the decision.** If the audit entry can't be saved, the decision becomes
  Error and the customer gets the general message. Nothing is shown without a record.
- **Periods need a matching policy.** A period in a sentence that matches no policy topic (such as
  "delivery takes 3 days") is **rejected**, because no policy can confirm it. When a sentence matches
  several policies, the period passes if any one of them states that day count.
- **URL normalisation keeps the query string and the fragment.** So `https://muhammadsheharyar16.github.io/hisaabpro/help?ref=x` is not
  allowed, and neither is `http://` when the allowed link is `https://`. URLs with a `user@host` part
  never match.
- **Bare `www.` links are also extracted and checked**, not just `http(s)://` ones.
- **Dates need a policy that states them.** A calendar date passes only if the same date appears in
  the policy the sentence is about. No seed policy contains a date, so any date in an answer is
  rejected ("unverified date").
- **Period units are approximate.** Weeks count as 7 days, months as 30 and years as 365. So
  "1 month" doesn't match a 31-day policy.
- **Some time phrases are deliberately not periods.** "$49 a month" is a billing cadence, and
  "one business day" is a support target, so neither is extracted. Hours ("within 24 hours") and
  weekday names ("by Friday") aren't extracted either. If they appear in a promise sentence, only
  the AI checks them.
- **Every percentage must be an approved discount.** This includes non-discount numbers such as
  "99.9% uptime".
- **The unlimited check has one exception.** If the same sentence also states the policy's own day
  count, it is left to the AI rather than failed. For example: "cancel any time; refunds within
  14 days".
- **Quote verification details.**
  - Whitespace, case and surrounding quote marks are ignored.
  - The quote must be at least 3 words long.
  - The quote must come from the policy the AI named.
- **The prompt treats the claim as data.** The claim is placed between delimiters as untrusted data.
  Even if the AI is tricked into saying "supported", it still has to produce a real quote.
- **Rules validation (`PUT /rules`, 422 on failure).**
  - Unknown fields are rejected.
  - Prices must parse.
  - Policy ids must be unique.
  - Product names and aliases must be unique.
  - Allowed links must be absolute URLs.
  - Safe messages may only link to allowed links and must not contain banned phrases.
- **No currency conversion.** Each plan has one official price in one currency (Pro: `USD 49`).
  A price for Pro in any other currency, such as `Rs 49` or `Rs 13,999`, is a mismatch.
- **`simulate=` only works with `DEBUG=true`.** Otherwise it returns 403.
- **Deleting or editing a rule version isn't possible.** Restoring an old version creates a new version.
- **Concurrent saves can collide.** If two `PUT /rules` calls race for the same version number, one gets 409.

## 9. Deviations from the brief (small, deliberate)

- **Folder name.** The folder is `compliance-firewall/` because it already existed. The brief spells it
  `compilance-firewall/`.
- **Python version.** It was developed on Python 3.13 because 3.11 wasn't installed. The code only uses
  3.11-compatible features.
- **Extra files:**
  - `pytest.ini` (import path);
  - `.gitignore` (`.env`, the venv and `data/*.db`);
  - `app/pipeline/suite.py`, the suite runner. Business logic can't live in route handlers, and the tree
    had no module for the suite.
  - `app/pipeline/checks/dates.py`. The POC sheet asks for dates to be checked; the brief only
    covered day periods.
  - AI-assisted extraction, AI security and AI governance. These were requested after the brief, and
    the POC sheet asks for "pattern rules + AI". They add these modules:
    - `app/pipeline/extract_ai.py`;
    - `app/pipeline/checks/security.py`;
    - `app/ai/governance.py`;
    - `app/ai/redact.py`;
    - `app/models/audit_review.py`;
    - `app/audit/report.py`;
    - `app/api/routes/governance.py`.
- **Database migration.** Startup runs `create_all` for new tables. It then runs an additive migration
  (`migrate_missing_columns` in `app/core/db.py`) that adds any model column an older database lacks,
  as a NULLable column; values that are missing read as empty. Columns are never dropped or changed.
  Alembic would be the next step if the schema starts changing in non-additive ways.
- **Extra settings.** `DEBUG` (for `simulate`) and `LOG_LEVEL`, which is optional and defaults to `INFO`.
- **Extra fields in the check response.** `fact.value` and `fact.product` were added so the app can show
  normalised values. The audit list returns `{total, limit, offset, items}` so the app can paginate.

## 10. Switching to Postgres

No code changes are needed:

```bash
pip install "psycopg[binary]"
# .env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require
```

The tables are created on startup and rules v1 is seeded when the table is empty.

## 11. Layout

```
app/
  main.py            app factory, CORS, routers, startup (create tables + seed)
  core/              settings, engine/session, logging
  models/            SQLModel tables: RuleSet, AuditEntry
  schemas/           Pydantic models: rules, facts, decision, API bodies
  rules/             versioned repository, cache, seed
  pipeline/          firewall orchestrator, extract, normalize, decide, suite runner, checks/*
  ai/                LLM protocol + Groq client, prompts, governance gateway, PII redaction, mock assistant
  audit/             audit repository (entries, reviews, stats), governance report
  api/               deps (overridable in tests, admin token guard) + thin routes
data/test_answers.json   50 labelled answers (25 approve / 25 reject)
tests/                   unit + API tests (FakeLLM, temp SQLite)
```
