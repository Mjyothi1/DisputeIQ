# DisputeIQ: AI Dispute Resolution Agent for Card Issuers

An AI agent that automates dispute intake, investigation, reason-code classification,
eligibility checking, recommendation and document drafting, with a human analyst in control.

**Principle:** the LLM only understands text, classifies and writes. Deadlines, eligibility,
amounts, duplicate detection and routing are deterministic, unit-tested Python.

> The reason-code taxonomy and time windows are a simplified, illustrative model written for this
> prototype, not a copy of any card-network rulebook. All data is synthetic.

## Problem

Card issuers receive thousands of disputes ("I was charged twice", "I never made this payment").
Each needs a transaction lookup, evidence checks, a reason code, a deadline check, a decision and
two documents. Analysts spend most of their time on routine cases and risk missing deadlines.
DisputeIQ does the routine work, auto-resolves only the clear-cut low-value cases, and puts
everything else in front of a human with the evidence already assembled.

## Architecture

```mermaid
flowchart LR
  UI[React + TS UI] -->|REST| API[FastAPI]
  API --> AG[LangGraph agent]
  API --> DB[(PostgreSQL + pgvector)]
  AG --> DB
  AG --> LLM{{Gemini Flash / mock / Anthropic / OpenAI}}
  AG --> RULES[Rules: eligibility, policy, routing]
  AG --> TOOLS[Evidence tools]
```

Pipeline: `mask_pii → intake_extract → match_transaction → run_evidence_checks → classify_reason_code → eligibility_engine → recommend → draft_documents → route`.
Every node writes an audit event. Details: [docs/architecture.md](docs/architecture.md).

Safety properties:

* Auto-resolve only if confidence >= 0.85 **and** amount <= INR 10,000 **and** a clear-cut
REFUND on duplicate/ATM cases. Every rejection goes to a human.
* LLM output is schema-validated; money and dates in letters are filled by code from the database.
* Prompt injection is delimited and detected (heuristic), and the complaint text cannot set policy,
  amounts, deadlines or routing: those come from deterministic code over database evidence. A flagged
  complaint is always routed to a human. The model does influence extraction and reason-code
  classification, so detection is a defence-in-depth layer, not the only one.
* A transaction can never be auto-refunded twice: other disputes on the same transaction force human review.
* Closed / auto-resolved cases are never silently re-run; reopening needs an authenticated analyst and a reason.
* Friendly-fraud signals (e.g. OTP-authenticated "fraud" claims) are flagged and routed to humans.

## Run it locally (no Docker, free)

Needs only Python 3.11+ and Node 20+. Full steps: [RUN_LOCAL.md](RUN_LOCAL.md).

```bash
cp .env.example .env                 # add your free GEMINI_API_KEY from Google AI Studio
cd backend && python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# second terminal
cd frontend && cp .env.example .env && npm install && npm run dev
```

Demo data is **opt-in**: `BOOTSTRAP_DEMO_DATA` defaults to `false` everywhere (config, Docker,
`.env.example`). For a brand-new empty database set it to `true` once: the backend then seeds the
synthetic dataset (relative to today) and processes the backlog with the **offline rule engine
(`mock-rules-v1`, not an LLM)**. Existing data is never touched. Live complaints from the
"Submit complaint" page are analysed by the configured provider (Gemini by default); the case
page and the Metrics "Analysed by" panel show which model handled each case.

**Sign-in (prototype auth):** set `REVIEWER_ACCOUNTS="yourname=<long-random-key>"` in `.env`
(generate a key with `python -c "import secrets;print(secrets.token_urlsafe(24))"`). Open the UI
and enter the key; your reviewer name comes from the server, never from what you type.
Without it every case/customer/metrics endpoint refuses. See [docs/SECURITY.md](docs/SECURITY.md).

Isolated demo customers (one scenario each, so the frequent-disputer rule never interferes):
`cd backend && python -m data_gen.demo_customers` (additive, never deletes). Script:
[docs/DEMO_PLAN.md](docs/DEMO_PLAN.md).

* UI: http://localhost:5173 · API docs: http://localhost:8000/docs
* PostgreSQL works the same way: set `DATABASE_URL` and run `alembic upgrade head` first; that also
  enables pgvector similar-case retrieval.

Then run the demo: [docs/demo.md](docs/demo.md).

## Free hosting

* **Frontend:** Vercel (Hobby). Root directory `frontend`, env `VITE_API_URL=<backend URL>`.
* **Backend:** Render free web service (builds `backend/Dockerfile` on Render's servers; you do not
  need Docker installed). Env: `DATABASE_URL`, `CORS_ORIGINS=<Vercel URL>`, `GEMINI_API_KEY`.
* **Database:** Render free PostgreSQL. On first boot the API fills the empty database with demo
  data; it never deletes data.
* Free-tier limits to know: the Render web service sleeps after ~15 minutes idle (first request
  then takes about a minute); a Render free database expires 30 days after creation; Gemini's free
  tier has low per-minute limits, so submit live complaints one at a time.

## Tests, lint, evaluation

```bash
cd backend
pytest -q                                    # unit + pipeline + API tests (SQLite)
TEST_DATABASE_URL=postgresql+psycopg://disputeiq:disputeiq@localhost:5432/disputeiq pytest -q  # + pgvector tests
ruff check .                                 # clean
mypy app                                     # 8 known pre-existing findings (type-ignore/StrEnum on py3.13); not gating
python -m eval.run_eval                      # 100 held-out TEST cases -> eval/results/

cd ../frontend && npm test && npm run lint && npm run build
```

## Using Gemini Flash (default), LLM-written complaints and Langfuse

1. In `.env` set `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=<Google AI Studio free-tier key>`, and
optionally `GEMINI_MODEL` (the default is defined once, in `backend/app/core/config.py`;
the name is not verified against Google's live model list by this repo, so run `--ping-llm`). The key stays on the backend only —
never in the frontend. Alternate providers (`anthropic` / `openai`) remain available.
2. Verify a live call: `cd backend && python -m app.agent.cli --ping-llm` (or process a dispute).
Rate-limit / quota / invalid-key errors are logged and shown; the app does **not** invent
analysis or switch to mock.
3. LLM-written complaint generation is intended only for a separate disposable database. Never run it against the existing project database.
4. Tracing: `pip install -e ".[langfuse]"`, set `LANGFUSE_ENABLED=true`, `LANGFUSE_PUBLIC_KEY`,
`LANGFUSE_SECRET_KEY` (and `LANGFUSE_HOST` for self-hosted). Every LLM call and pipeline run is
traced with tokens and cost; only PII-masked text is sent.
5. `python -m eval.run_eval` to get real-model numbers.

## Evaluation results (read the caveats first)

There are two offline suites and, so far, **no live-Gemini accuracy number**. Full methodology:
[docs/EVALUATION.md](docs/EVALUATION.md).

| Suite | Provider | Cases | Reason code | Decision | Unsafe auto-resolutions |
|-|-|-|-|-|-|
| Synthetic template TEST split (`python -m eval.run_eval --provider mock`) | mock rules | 100 | 99% | 99% | 0 |
| Hand-authored varied/Hinglish/adversarial (`python -m eval.handwritten --provider mock`) | mock rules | 33 | 83.3% (20/24 labelled) | routing 87.9% | 0 |
| Either suite with `--provider gemini` | Gemini | - | **not run** (no key/quota in the build sandbox) | - | - |

* The synthetic suite is **circular**: the mock classifier shares keywords with the complaint
  templates, so ~100% shows pipeline/rule consistency, not language understanding. It is not Gemini's
  accuracy and must not be quoted as such.
* The hand-authored suite was written by an AI assistant imitating varied phrasing (not real customers)
  and is small; treat it as a smoke-level signal.
* The safety property that *is* verified: across both suites, **0 unsafe auto-resolutions** and every
  injection-bearing complaint was flagged and sent to a human.
* Live Gemini processing was observed separately (connectivity test; ~6 s per case, INR 0 on the free
  tier, as reported by the project owner); that is an operational check, not an accuracy measurement.

Reports: `backend/eval/results/latest.md` (synthetic), `handwritten-mock.md`.

## Screenshots

Screenshots captured from the running application using seeded demo data.

### Analyst Queue
![Analyst Queue](docs/screenshots/queue.png)

### Case Detail: Friendly Fraud Flag
![Case Detail](docs/screenshots/case-detail.png)

### Auto-Resolved Duplicate
![Auto-Resolved Case](docs/screenshots/case-auto-resolved.png)

### Submit Complaint
![Submit Complaint](docs/screenshots/submit.png)

### Metrics Dashboard
![Metrics Dashboard](docs/screenshots/metrics.png)

### Dark Mode
![Dark Mode](docs/screenshots/queue-dark.png)

## Deployment

DisputeIQ is deployed as a full-stack prototype.

- Frontend: https://dispute-iq-beryl.vercel.app/
- Backend: https://disputeiq-backend.onrender.com
- Health Check: https://disputeiq-backend.onrender.com/health
- Database: PostgreSQL hosted on Render.
- AI Provider: Google Gemini.

The frontend is hosted on Vercel, while the FastAPI backend and PostgreSQL database are hosted on Render.

The deployment is intended for prototype demonstration and evaluation, not production banking operations. Local end-to-end complaint submission has been tested. The deployed frontend and backend health endpoint have been verified separately; the complete deployed complaint flow still requires validation.

Note: The free Render PostgreSQL database has a limited lifetime and should not be treated as permanent production storage.

## Limitations

* Gemini is the primary live provider (`google-genai` SDK). Anthropic/OpenAI remain optional
alternates. Langfuse export is optional and tested against a local stub when disabled.
* Default complaints are template-written (an LLM writer is available via `--llm` but was not run here).
* Simplified taxonomy; no network-specific rules, evidence formats or representment flow.
* Prototype auth only: static per-reviewer bearer keys (`REVIEWER_ACCOUNTS`), no SSO/MFA/expiry/rotation.
  Not production-ready. Concurrency guard is verified on SQLite (threads); the Postgres advisory-lock
  path is implemented but was not exercised against a real Postgres here.
* PII masking and prompt-injection detection are regex heuristics, not guarantees (see docs/SECURITY.md).
* Similar-case retrieval (pgvector) is only active on PostgreSQL; the default `hash` embedder is lexical,
  not semantic. Retrieved cases are passed to the classifier/rationale prompt as context.
* Hash embeddings by default (set `EMBEDDING_PROVIDER=local` for sentence-transformers).
* Docker Compose and deployment configs were not executed in the build sandbox (Postgres and
pgvector were verified locally outside Docker).

Design decisions are logged in [DECISIONS.md](DECISIONS.md); API in [docs/api.md](docs/api.md);
taxonomy in [docs/reason-codes.md](docs/reason-codes.md).
