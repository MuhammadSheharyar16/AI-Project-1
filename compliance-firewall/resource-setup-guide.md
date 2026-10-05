# Resource Setup Guide — POC-11: Compliance Firewall for AI Answers

This guide lists every AI resource the project uses, where it comes from, how it is configured, and
the steps to reproduce the same environment and run the project on another machine.

Everything used is free. **No API keys or credentials are included in this ZIP.** You create your own
free key in step 2.

---

## 1. Resources used

### AI resource

| Resource | What it is used for | Where it comes from | Cost |
|----------|---------------------|---------------------|------|
| **Groq API**, model `openai/gpt-oss-20b` | The only AI model in the project. It does two jobs inside the firewall: (1) extracts facts the pattern rules missed (for example "forty-nine bucks"), and (2) checks each promise against the policy text and must quote the policy word for word. | https://console.groq.com (free account, no card needed) | Free tier, $0 |

Notes on how the AI is used:

- It is called over plain HTTPS at `https://api.groq.com/openai/v1/chat/completions` (OpenAI-compatible
  chat completions). No AI SDK is installed; the backend uses `httpx`.
- It runs in **JSON mode** at **temperature 0**.
- It is called only when needed. Answers with no facts, and answers that already failed a code check,
  never reach the AI. The full 50-answer test suite makes about 7–9 AI calls.
- The "AI assistant" that drafts answers in the live demo is a **mock** with scripted answers
  (`backend/app/ai/mock_assistant.py`). It does not call any model, so it needs no setup.
- No local model, embedding model, vector database or paid service is used.

### Other free resources

| Resource | Used for | Where it comes from |
|----------|----------|---------------------|
| Python 3.11+ | Backend runtime | https://www.python.org/downloads/ |
| FastAPI, Uvicorn, SQLModel, Pydantic, httpx, pytest | Backend API, storage layer, tests | PyPI, installed from `backend/requirements.lock` |
| SQLite | Rules (versioned) and the audit log, stored in a local file | Built into Python, nothing to install |
| Node.js 20.19+ or 22.12+ | Frontend tooling | https://nodejs.org |
| React, Vite, TypeScript, three.js, framer-motion | Frontend web app | npm, installed from `frontend/package-lock.json` |
| GitHub Pages | Hosts the fictional "Hisaab Pro" company site that the allowed links and safe messages point to | Already live at https://muhammadsheharyar16.github.io/hisaabpro/ (source in `demo-site/`) |

### Free-tier limits

Groq's free tier limits requests per minute and tokens per day for each model. The current numbers for
your account are shown at https://console.groq.com/settings/limits.

The project stays inside them with two settings in `backend/.env`:

- `AI_MAX_CALLS_PER_MINUTE` (default `25`): a hard cap on AI calls across the app.
- `RATE_LIMIT_PER_MINUTE` (default `60`): a per-client cap on the endpoints that can trigger AI calls.

If a limit is hit, or Groq returns HTTP 429, the firewall fails closed: the decision is **Error** and
the customer sees a safe message.

---

## 2. Get the Groq API key

1. Go to https://console.groq.com and sign up (email, Google or GitHub).
2. Open **API Keys** (https://console.groq.com/keys) and click **Create API Key**.
3. Copy the key. It starts with `gsk_` and is shown only once.
4. Keep it for step 3. Do not commit it or share it.

To confirm the model is still offered, check the model list at https://console.groq.com/docs/models.
If `openai/gpt-oss-20b` has been retired, set `GROQ_MODEL` to another free chat model that supports
JSON mode, then re-run the test suite (step 6) to confirm the results.

---

## 3. Set up and run the backend (port 8000)

Run these from the folder where the ZIP was extracted.

```bash
cd backend
python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
# Windows (cmd):         .venv\Scripts\activate
# macOS / Linux:         source .venv/bin/activate
```

Install the packages and create the settings file:

```bash
pip install -r requirements.lock
cp .env.example .env          # Windows cmd: copy .env.example .env
```

Generate two random tokens (run the command twice):

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Open `backend/.env` and fill in these values:

| Variable | Value |
|----------|-------|
| `GROQ_API_KEY` | Your key from step 2 (required) |
| `GROQ_MODEL` | `openai/gpt-oss-20b` (required, already set) |
| `DATABASE_URL` | `sqlite:///./data/firewall.db` (required, already set) |
| `API_TOKEN` | The first random token |
| `ADMIN_TOKEN` | The second random token |
| `DEBUG` | `true` if you want to demo the simulated crash and timeout cases, otherwise `false` |

Leave the other values as they are. Leave `DEMO_SITE_REPO` empty.

Start the server:

```bash
uvicorn app.main:app --port 8000 --reload
```

On first start the backend creates `backend/data/firewall.db` and seeds trusted rules version 1. No
manual database setup is needed. The API docs are at http://localhost:8000/docs.

---

## 4. Set up and run the frontend (port 5173)

Open a second terminal and leave the backend running.

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

The frontend needs no key of its own. Its dev server reads `API_TOKEN` and `ADMIN_TOKEN` from
`../backend/.env` and adds them to each request, so the tokens never reach the browser. Restart
`npm run dev` if you change the tokens.

---

## 5. Demo site (optional)

The Hisaab Pro site is already live on GitHub Pages, so nothing is required here. To view it locally:

```bash
cd demo-site
python -m http.server 8080      # then open http://localhost:8080
```

---

## 6. Check that everything works

| Check | How | Expected |
|-------|-----|----------|
| Backend is up | Open http://localhost:8000/docs | The API docs load |
| Frontend reaches the backend | Open http://localhost:5173 | The top bar does not say **Backend offline** |
| Automated tests | In `backend/`, run `python -m pytest` | All tests pass. They use a fake LLM, so they need no Groq key and make no AI calls. |
| Groq key works | **Live firewall** page → run the "correct 14-day refund policy" case | Decision is **Approved**, and the trace shows an AI call |
| Full suite | **Test suite** page → run the 50 labelled answers | 0 rejected answers shown to the customer, ≥ 95 % of violations caught, ≤ 10 % of clean answers blocked |

---

## 7. Troubleshooting

| Problem | Cause and fix |
|---------|---------------|
| Backend stops at startup with a settings validation error | `GROQ_API_KEY`, `GROQ_MODEL` or `DATABASE_URL` is missing from `backend/.env`. |
| Top bar says **Backend offline** | The backend is not running on port 8000. |
| Requests return 401 or 403 | `API_TOKEN` / `ADMIN_TOKEN` are empty, or the frontend was started before they were set. Fill them in and restart `npm run dev`. |
| Decisions that need the AI come back as **Error** | The Groq key is wrong, the model name is no longer offered, or the free-tier limit was reached. Check the key and model, wait a minute and try again. |
| The crash and timeout demo cases do nothing | They work only with `DEBUG=true` in `backend/.env`. |
| `npm install` or `npm run dev` fails on the Node version | Vite 8 needs Node.js 20.19+ or 22.12+. |

More detail is in `README.md` (how the firewall works) and `backend/docs/ARCHITECTURE.md` (flow
diagram, resources and limits).
