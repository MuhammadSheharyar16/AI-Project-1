# Compliance Firewall for AI Answers — frontend

React web app for the firewall backend in `../backend`. Vite, React 19, TypeScript, three.js and
framer-motion. Everything is free and runs locally.

## Run

Start the backend first (see `../backend/README.md`):

```bash
cd compliance-firewall/backend
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
uvicorn app.main:app --port 8000
```

Then the frontend:

```bash
cd compliance-firewall/frontend
npm install
npm run dev                       # http://localhost:5173
```

`npm run build` type-checks and builds to `dist/`; `npm run preview` serves that build with the same
API proxy.

## How it talks to the backend

The browser only calls same-origin `/api/*`. The Vite server proxies those calls to the backend and
adds the `X-API-Key` and `X-Admin-Token` headers, which it reads from `../backend/.env` at startup.

- The tokens never reach the browser bundle, and the backend needs no CORS change.
- The dev server listens on `localhost` only, because anyone who can reach it can edit the rules.
  Don't expose it to the network.
- Restart `npm run dev` after changing tokens in the backend `.env`.

The backend URL is set in `frontend/.env`. Token overrides belong in `frontend/.env.local`
(git-ignored) or the environment:

| Variable | Default | Meaning |
|----------|---------|---------|
| `FIREWALL_API_URL` | `http://localhost:8000` | Backend address |
| `FIREWALL_API_TOKEN` | `API_TOKEN` from `../backend/.env` | Sent as `X-API-Key` |
| `FIREWALL_ADMIN_TOKEN` | `ADMIN_TOKEN` from `../backend/.env` | Sent as `X-Admin-Token` |

This proxy is a local-demo setup. A deployed version needs a real login in front of the admin actions.

## Pages

| Page | What it shows | Requirement |
|------|---------------|-------------|
| Overview | 3D firewall scene, live decision counts, animated architecture diagram | Architecture diagram |
| Live firewall | Split screen: customer chat and compliance view (raw answer, every fact with ✓/✗, rule, reason, pipeline trace). One-click client test cases, including the simulated crash and timeout | Success, edge and bad/abuse cases |
| Trusted rules | Forms for prices, discounts, policies, allowed links, banned phrases and safe messages. Version number shown; saving creates a new version; any old version can be restored | Editable, versioned rules |
| Audit log | Filterable, colour-coded table (Approved / Rejected / Error). Entry detail with re-check on the latest rules and human review | Audit log; "price edited, old answer re-checked" |
| Test suite | Runs the 50 labelled answers and scores them against the three targets | Batch of 50 |
| Governance | AI configuration, usage, security controls, and the free resources and their limits | Free resources only |

The simulated crash and timeout cases need `DEBUG=true` in the backend `.env`.

## Layout

```
src/
  api/          typed client for the backend, response types
  components/   3D hero scene, pipeline diagram, decision detail (facts, trace), shared UI
  pages/        one file per page
  scenarios.ts  the client test cases from the requirements sheet
  store.tsx     shared state: backend health, chat session, last suite run, toasts
  styles.css    the whole theme
```
