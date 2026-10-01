# POC-11 Compliance Firewall: requirements traceability (backend)

This document maps each row of `POC-11_Sheharyar.xlsx` to the backend code that implements it and the
test that proves it. It also covers the AI-assisted extraction, AI security and AI governance work
added on top of the sheet, and records how every gap found in the review was closed.

- **Status as of 2026-09-30:**
  - **265 tests pass** (`python -m pytest`).
  - The 50-answer suite scores 0 leaked, 100 % caught and 0 % of clean answers blocked, using the
    offline FakeLLM.
  - A live server run was checked with the real `.env` (tokens set, no Groq key).
- **Legend:**
  - ✅ implemented and tested
  - ⚠️ implemented, but needs something outside the code (a Groq key, a live run)
  - ⬜ not backend work
- **Links** are relative to `backend/docs/`. `#Lnn` jumps to the line.
- **Architecture diagram, and the "resources and limits" demo content:** [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 1. Solution Needed

| # | Requirement (sheet) | Status | Implementation | Proof (tests) |
|---|---|---|---|---|
| 1 | Editable "trusted rules": prices, policies, allowed links, banned phrases, safe messages. **Versioned.** | ✅ | Schema [`Rules`](../app/schemas/rules.py#L65) · seed v1 [`SEED_RULES`](../app/rules/seed.py#L8) · append-only [`save_new_version`](../app/rules/repository.py#L32) / [`restore_version`](../app/rules/repository.py#L52) · [`PUT /rules`](../app/api/routes/rules.py#L25), [`GET /rules/versions`](../app/api/routes/rules.py#L35), [`POST /rules/restore/{v}`](../app/api/routes/rules.py#L40) | [N+1, never overwritten](../tests/test_rules_versioning.py#L40), [restore](../tests/test_rules_versioning.py#L53), [invalid → 422 with no new version](../tests/test_rules_versioning.py#L86), [no overwrite function exists](../tests/test_rules_versioning.py#L91) |
| 2 | Every AI answer is intercepted, and its facts (prices, %, **dates**, links, promises) are extracted and checked | ✅ | Orchestrator [`firewall.run`](../app/pipeline/firewall.py#L140) · pattern extraction [`extract`](../app/pipeline/extract.py#L181): [price](../app/pipeline/normalize.py#L14), [percent](../app/pipeline/extract.py#L12), [period](../app/pipeline/extract.py#L15), [date](../app/pipeline/extract.py#L22), [link](../app/pipeline/extract.py#L30), [promise](../app/pipeline/extract.py#L31) · checks: [prices](../app/pipeline/checks/prices.py#L12), [percents](../app/pipeline/checks/percents.py#L13), [periods](../app/pipeline/checks/periods.py#L18), [dates](../app/pipeline/checks/dates.py#L9), [links](../app/pipeline/checks/links.py#L10), [banned](../app/pipeline/checks/banned.py#L11), [unlimited](../app/pipeline/checks/unlimited.py#L16), [policy AI](../app/pipeline/checks/policy_ai.py#L39) | [test_extract.py](../tests/unit/test_extract.py), [test_checks.py](../tests/unit/test_checks.py), [test_normalize.py](../tests/unit/test_normalize.py) |
| 3 | If everything matches, show the answer. If anything is wrong **or the check fails**, show a pre-approved safe message | ✅ | [`decide`](../app/pipeline/decide.py#L22) and [safe-message map](../app/pipeline/decide.py#L10) · a [single fail-closed catch](../app/pipeline/firewall.py#L214) · an [audit-save failure also becomes Error](../app/pipeline/firewall.py#L231) | [cases 8–12](../tests/test_client_cases.py#L84), [slow AI](../tests/test_client_cases.py#L162), [crash](../tests/test_client_cases.py#L167), [429](../tests/test_client_cases.py#L172), [no key](../tests/test_client_cases.py#L177), [audit failure](../tests/test_client_cases.py#L182) |
| 4 | Side-by-side view: customer vs compliance (raw answer, facts, reasons) | ✅ backend · ⬜ UI | [`CheckResponse`](../app/schemas/api.py#L53) = `customer.text` + `compliance{raw_answer, results, trace, governance}` · [every extracted fact is listed](../app/pipeline/firewall.py#L112), including ones never checked | [every fact listed when the AI is skipped](../tests/test_client_cases.py#L221), [on error](../tests/test_client_cases.py#L234) |
| 5 | Every decision is saved in an audit log with the rule version. 50 labelled test answers ship with the POC | ✅ | [`AuditEntry`](../app/models/audit_entry.py#L12) · [`_record`](../app/pipeline/firewall.py#L231) · [`data/test_answers.json`](../data/test_answers.json) (25 approve / 25 reject) · [`run_suite`](../app/pipeline/suite.py#L23) | [full audit record](../tests/test_rules_versioning.py#L132), [dataset balance](../tests/test_suite.py#L9), [suite targets](../tests/test_suite.py#L21) |

## 2. Must-Haves

| Must-have | Acceptance criteria (sheet) | Status | Backend evidence |
|---|---|---|---|
| Elegant UI / UX | Split screen with ✓/✗ per fact and plain-English reasons; rules edited through forms with the version shown; a filterable, colour-coded audit table | ✅ API · ⬜ UI | The ✓/✗ data comes from `results[].ok` and `reason`. Form data comes from [`GET /rules`](../app/api/routes/rules.py) (`version` and `author`). The audit table is [`GET /audit?decision=&version=&source=&q=`](../app/api/routes/audit.py#L27), with the filter logic in [`list_entries`](../app/audit/repository.py#L23), tested by [filters and order](../tests/test_rules_versioning.py#L108). |
| Free resources only | $0; free-tier AI; rules and audit stored locally; resources and limits on one slide | ✅ | Groq free tier ([`GroqClient`](../app/ai/llm.py#L29)). Local SQLite ([`make_engine`](../app/core/db.py#L11)). A call budget ([`AIBudget`](../app/ai/governance.py#L38)). The slide content is in [ARCHITECTURE.md, "Resources and limits"](ARCHITECTURE.md#resources-and-limits-demo-slide), and live numbers come from [`GET /governance`](../app/audit/report.py#L30). |
| Architecture diagram | AI draft → Intercept → Extract (**pattern rules + AI**) → code checks → AI promise check (verified quote) → Decision → text or safe message → Audit | ✅ | Diagram: [ARCHITECTURE.md](ARCHITECTURE.md#request-flow) (Mermaid). Code: [`mock_assistant.draft`](../app/ai/mock_assistant.py#L49) → [`POST /chat`](../app/api/routes/chat.py#L18) → [`extract`](../app/pipeline/extract.py#L181) and [`extract_ai.extract`](../app/pipeline/extract_ai.py#L134) → [`quote_is_verified`](../app/pipeline/checks/policy_ai.py#L32), all run by [`firewall.run`](../app/pipeline/firewall.py#L140). |
| ↳ Efficiency: cheap code checks first; if one fails, skip the AI | | ✅ | [Branch that skips AI after a code failure](../app/pipeline/firewall.py#L184). Proven by [case 10 (0 AI calls)](../tests/test_client_cases.py#L100) and [AI extraction skipped on code failure](../tests/test_ai_extraction.py#L163). |
| ↳ Answers with no facts skip the AI entirely | | ✅ | [No-facts fast path](../app/pipeline/firewall.py#L175). Proven by [case 2](../tests/test_client_cases.py#L40) and the [no-cues gate](../tests/test_ai_extraction.py#L68). |
| ↳ Rules load once and reload only when the version changes | | ✅ | [`RulesCache`](../app/rules/cache.py#L15). Proven by [cache hit, then reload](../tests/test_rules_versioning.py#L95). |
| Presentation demo (10 min) | Live cases in both views, edit a price live, the 50-answer suite, limitations | ✅ backend · ⚠️ live Groq · ⬜ slides | Every demo step has an endpoint ([README §4](../README.md#4-api)). The limitations list is in [ARCHITECTURE.md](ARCHITECTURE.md#resources-and-limits-demo-slide). The suite targets are met with FakeLLM ([test](../tests/test_suite.py#L21)). **Not yet measured on real Groq** (see G1). |

## 3. Client-Ready Test Cases

| Sheet scenario | Expected (sheet) | Status | Test |
|---|---|---|---|
| Correct Pro plan price | Approved; the customer sees the answer | ✅ | [`test_case_1`](../tests/test_client_cases.py#L33) |
| Greeting "Hi! How can I help?" | Approved instantly, no AI | ✅ | [`test_case_2`](../tests/test_client_cases.py#L40) |
| Correct 14-day refund policy | Approved | ✅ · ⚠️ needs a Groq key live | [`test_case_3`](../tests/test_client_cases.py#L51) |
| "Rs 4,999" vs "4999 PKR" | Recognised as matching; Approved | ✅ | [`test_case_4`](../tests/test_client_cases.py#L61), plus [every price format](../tests/unit/test_normalize.py) |
| Three prices, one wrong | Rejected; only the wrong one is flagged | ✅ | [`test_case_5`](../tests/test_client_cases.py#L69) |
| Allowed link with a trailing slash or different capitals | Treated as allowed | ✅ | [`test_case_6`](../tests/test_client_cases.py#L79) |
| Price edited, old answer re-checked | The decision changes; the audit shows the new version | ✅ | [`test_case_7`](../tests/test_client_cases.py#L194) |
| Pro is $59 when the rule says $49 | Pricing safe message; "price mismatch" | ✅ | [`test_case_8`](../tests/test_client_cases.py#L84) |
| Link not on the allowed list | Rejected: "unapproved link" | ✅ | [`test_case_9`](../tests/test_client_cases.py#L93) |
| "Guaranteed refund anytime" | Rejected: banned phrase + contradicts the 14-day policy | ✅ | [`test_case_10`](../tests/test_client_cases.py#L100) |
| Checker crashes or times out | Safe message; audit decision = Error | ✅ | [`test_case_11`](../tests/test_client_cases.py#L110), [`test_case_12`](../tests/test_client_cases.py#L118) (via [`simulate`](../app/pipeline/firewall.py#L129), [debug-only](../app/api/deps.py#L102)) |
| All 50 labelled answers in a batch | The customer never sees a Reject | ✅ · ⚠️ real Groq unmeasured | [`test_suite_meets_targets`](../tests/test_suite.py#L21) |

## 4. AI: extraction and verification ("pattern rules + AI")

| Capability | Status | Implementation | Proof |
|---|---|---|---|
| Groq `openai/gpt-oss-20b`, JSON mode, temperature 0, key only in `.env` | ✅ | [`GroqClient`](../app/ai/llm.py#L29) ([temperature 0](../app/ai/llm.py#L46)) · [`SecretStr` key](../app/core/config.py#L12) | `test_groq_request_shape_and_parse` in [test_checks.py](../tests/unit/test_checks.py) |
| Gate: AI extraction only when fact-like cues are left over after the pattern rules | ✅ | [`needs_ai`](../app/pipeline/extract_ai.py#L80), [`CUE_RE`](../app/pipeline/extract_ai.py#L27) | [gate cases](../tests/test_ai_extraction.py#L64) |
| AI facts must be **grounded**; hallucinations are discarded | ✅ | [`_ground`](../app/pipeline/extract_ai.py#L89), [`extract`](../app/pipeline/extract_ai.py#L134) | [hallucinated, invalid and duplicate facts dropped](../tests/test_ai_extraction.py#L139) |
| AI "periods" that are billing cadence or reply times are ignored | ✅ | [`CADENCE_RE`](../app/pipeline/extract_ai.py#L38), [`is_cadence`](../app/pipeline/extract_ai.py#L47) | [cadence ignored](../tests/test_hardening.py#L201), [real periods still checked](../tests/test_hardening.py#L213) |
| AI facts go through the same code checks | ✅ | [`_run_code_checks`](../app/pipeline/firewall.py#L95) | [price in words ✓](../tests/test_ai_extraction.py#L76), [wrong price ✗](../tests/test_ai_extraction.py#L91), [obfuscated link](../tests/test_ai_extraction.py#L102), ["half off"](../tests/test_ai_extraction.py#L112), [promise with no keyword](../tests/test_ai_extraction.py#L119) |
| Promise check with a **verified quote** | ✅ | [`policy_ai.check`](../app/pipeline/checks/policy_ai.py#L39), [`quote_is_verified`](../app/pipeline/checks/policy_ai.py#L32) | [invented quote rejected](../tests/test_client_cases.py#L154) |
| Malformed AI output or missing fields fail closed | ✅ | [`AIFactList`](../app/pipeline/extract_ai.py#L68) / `AIVerdict` | [malformed → Error](../tests/test_ai_extraction.py#L156), [missing fields → Rejected](../tests/test_ai_extraction.py#L132) |

## 5. AI security

| Threat | Status | Control | Proof |
|---|---|---|---|
| Prompt injection inside the AI answer | ✅ | [`INJECTION_RE`](../app/pipeline/checks/security.py#L16) in [`security.scan`](../app/pipeline/checks/security.py#L42), run **before** any AI call | [scan](../tests/test_ai_security.py#L39), [rejected with 0 AI calls](../tests/test_ai_security.py#L60), suite `r20` |
| Hidden or bidi Unicode ("Trojan Source") | ✅ | [`HIDDEN_RE`](../app/pipeline/checks/security.py#L24). No source file contains literal bidi or control characters. | [scan](../tests/test_ai_security.py#L39) |
| Secrets, cards or CNIC leaking to customers | ✅ | [`SECRET_RE`](../app/pipeline/checks/security.py#L25), [`CARD_RE`](../app/pipeline/checks/security.py#L29) + [Luhn](../app/ai/redact.py#L25), [`CNIC_RE`](../app/pipeline/checks/security.py#L30) | [flags](../tests/test_ai_security.py#L39), [no false alarms](../tests/test_ai_security.py#L56) |
| Personal data sent to the third-party LLM | ✅ | [`redact`](../app/ai/redact.py#L30) on **every** call [in the gateway](../app/ai/governance.py#L99) | [redaction](../tests/test_ai_security.py#L72), [the LLM never sees the email](../tests/test_ai_security.py#L91) |
| Personal data at rest in the audit log | ✅ | [`redact_deep`](../app/ai/redact.py#L52) in [`_record`](../app/pipeline/firewall.py#L243) (`AUDIT_REDACT_PII`, [default on](../app/core/config.py#L32)). [Placeholders stay flagged](../app/pipeline/checks/security.py#L33) so a recheck of a leak stays Rejected. | [no PII stored](../tests/test_hardening.py#L112), [leak still rejected on recheck](../tests/test_hardening.py#L125), [can be turned off](../tests/test_hardening.py#L135), [only real card numbers](../tests/test_hardening.py#L142) |
| Untrusted text breaking out of its data block | ✅ | [`_untrusted`](../app/ai/prompts.py#L52), [system prompt](../app/ai/prompts.py#L12) | [cannot close its block](../tests/test_ai_security.py#L102) |
| Hallucinated or tampered AI output | ✅ | Grounding, schema validation, verified quote, [`MAX_AI_FACTS`](../app/pipeline/extract_ai.py#L22) | see §4 |
| Unauthorised rule edits, reviews or suite runs | ✅ | [`require_admin`](../app/api/deps.py#L57), with a [constant-time compare](../app/api/deps.py#L54) | [token required](../tests/test_ai_security.py#L113), [closed outside debug](../tests/test_ai_security.py#L126), [client token cannot edit rules](../tests/test_hardening.py#L51) |
| Unauthorised reads of the audit log, checks or the report | ✅ | [`require_client`](../app/api/deps.py#L75) (`X-API-Key`, or the admin token) on every router except `/health` | [every endpoint protected](../tests/test_hardening.py#L29), [closed outside debug](../tests/test_hardening.py#L45) |
| Strangers spending the AI budget / abuse | ✅ | Per-client [`rate_limit`](../app/api/deps.py#L94) using [`ClientRateLimiter`](../app/core/security.py#L10) (429 + `Retry-After`), plus the app-wide [`AIBudget`](../app/ai/governance.py#L38) | [per client](../tests/test_hardening.py#L60), [per key](../tests/test_hardening.py#L69), [budget](../tests/test_ai_governance.py#L54) |
| Browser and transport attacks | ✅ | [`SecurityHeadersMiddleware`](../app/core/security.py#L45) (nosniff, DENY, no-referrer, no-store; HSTS over HTTPS) · [CORS: explicit list, no credentials](../app/main.py#L49), [`*` only in DEBUG](../app/core/config.py#L35) · HTTPS via uvicorn + mkcert ([README §2](../README.md#2-run)) | [headers](../tests/test_hardening.py#L77), [HSTS over HTTPS](../tests/test_hardening.py#L86), [wildcard only in debug](../tests/test_hardening.py#L91), [only the configured origin](../tests/test_hardening.py#L98) |
| API key leakage | ✅ | [`SecretStr`](../app/core/config.py#L12); errors never include it | [no key in errors](../tests/test_ai_security.py#L137) |
| Supply chain | ✅ | Pinned [`requirements.txt`](../requirements.txt) and full [`requirements.lock`](../requirements.lock) | installed and tested from these versions |

## 6. AI governance

| Control | Status | Implementation | Proof |
|---|---|---|---|
| Single gateway for every AI call | ✅ | [`AIGateway.ask`](../app/ai/governance.py#L89) | all AI tests go through it |
| Kill switch (`AI_ENABLED`) | ✅ | [gateway check](../app/ai/governance.py#L92) | [fails closed, 0 calls](../tests/test_ai_governance.py#L42) |
| Call budget (`AI_MAX_CALLS_PER_MINUTE`) | ✅ | [`AIBudget.try_acquire`](../app/ai/governance.py#L94) | [budget stop](../tests/test_ai_governance.py#L54), [window](../tests/test_ai_governance.py#L64) |
| Provenance: model and prompt version on every decision | ✅ | [`PROMPT_VERSION`](../app/ai/prompts.py#L75), [`AuditEntry`](../app/models/audit_entry.py#L12) | [recorded](../tests/test_ai_governance.py#L23) |
| AI call ledger | ✅ | `ai_calls_json` in the audit, `compliance.governance.ai_calls` in the response | [failed outcomes recorded](../tests/test_ai_governance.py#L69) |
| Human in the loop (append-only reviews) | ✅ | [`AuditReview`](../app/models/audit_review.py#L11), [`POST /audit/{id}/review`](../app/api/routes/audit.py#L50) | [reviews](../tests/test_ai_governance.py#L76) |
| Accountable rule changes (author) | ✅ | `author` on [`RuleSet`](../app/models/rule_set.py#L14) | [author recorded](../tests/test_ai_governance.py#L92), [author required](../tests/test_ai_security.py#L132) |
| Governance report (controls, warnings, usage) | ✅ | [`report.build`](../app/audit/report.py#L30) → `GET /governance`. It warns when a token is missing or PII redaction is off. | [report](../tests/test_ai_governance.py#L99) |

## 7. Gaps from the previous review: resolution

| # | Gap | Resolution | Status | Evidence |
|---|---|---|---|---|
| G1 | Never run against real Groq; the 8B model might report "a month" or reply times as periods | Code-side risk removed: AI periods that are billing cadence ("a month", "monthly", "/month") or reply times ("one business day", "24 hours") are ignored and counted in the trace. `.env` now has a slot for the key. **Still needs a live run.** | ✅ code · ⚠️ run | [`is_cadence`](../app/pipeline/extract_ai.py#L47), [tests](../tests/test_hardening.py#L201). To do: put `GROQ_API_KEY` in `.env`, then `POST /suite/run` with `X-Admin-Token`. |
| G2 | Read and check endpoints were open; no per-client limit | Client token (`API_TOKEN`, `X-API-Key`) on every endpoint except `/health`, with fail-closed 403 when unset outside DEBUG. Per-client rate limit on AI-capable endpoints. | ✅ | [`require_client`](../app/api/deps.py#L75), [`rate_limit`](../app/api/deps.py#L94), [tests](../tests/test_hardening.py#L29); live: 401 without the key, 429 after the limit |
| G3 | Audit log stored raw PII | Redaction before storage, on by default. Recheck-safe placeholders. Live: stored text had no email or card number. | ✅ | [`_record`](../app/pipeline/firewall.py#L243), [tests](../tests/test_hardening.py#L112) |
| G4 | `CORS=*` and plain HTTP | CORS defaults to an explicit list, `*` is ignored outside DEBUG, and there are no credentials. Security headers on every response. HSTS over HTTPS. Free HTTPS option documented (uvicorn + mkcert). | ✅ | [`SecurityHeadersMiddleware`](../app/core/security.py#L45), [CORS](../app/main.py#L49), [tests](../tests/test_hardening.py#L77) |
| G5 | Dependencies not pinned | `requirements.txt` has exact pins for direct deps. `requirements.lock` is the full tested set, with a platform marker for `colorama`. | ✅ | [`requirements.txt`](../requirements.txt), [`requirements.lock`](../requirements.lock) |
| G6 | No migrations; an old DB broke | Additive migration at startup adds any missing column (SQLite and Postgres). Missing values read as empty. | ✅ | [`migrate_missing_columns`](../app/core/db.py#L28), [called at startup](../app/main.py#L30), [old-DB test](../tests/test_hardening.py#L149) |
| G7 | Architecture drawing, demo "resources and limits", UI, slides | The diagram and the resources, limits and limitations content are in [ARCHITECTURE.md](ARCHITECTURE.md). The Expo UI and the slide deck are outside the backend. | ✅ docs · ⬜ UI/slides | [ARCHITECTURE.md](ARCHITECTURE.md) |

**Configuration delivered:** [`.env.example`](../.env.example) documents every setting. A local `.env`
(git-ignored) was generated with random `ADMIN_TOKEN` and `API_TOKEN` values and `DEBUG=true` for the
demo. `GROQ_API_KEY` is left empty for the owner to fill in.

**What remains outside this repository's control:**
1. A live `POST /suite/run` on real Groq (G1).
2. The Expo screens and the slide deck (G7).

## 8. How to re-verify

```bash
cd compliance-firewall/backend
pip install -r requirements.lock
python -m pytest                      # 265 tests: unit, client cases, suite, AI, security, governance, hardening
uvicorn app.main:app --host 0.0.0.0 --port 8000        # reads .env
curl -H "X-API-Key: $API_TOKEN" localhost:8000/governance
curl -X POST localhost:8000/suite/run -H "X-Admin-Token: $ADMIN_TOKEN"   # leaked / caught_rate / false_block_rate
```
