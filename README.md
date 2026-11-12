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
* Prompt injection is delimited, detected, and cannot reach decision logic.
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

On first start the backend creates `backend/disputeiq.db` and fills it with the demo dataset
(seeded relative to today, backlog processed by the offline rule engine so no Gemini quota is
used). After that the data is kept: restarts never reset it. Live complaints from the
"Submit complaint" page are analysed by Gemini.

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
ruff check . && mypy app
python -m eval.run_eval                      # 100 held-out TEST cases -> eval/results/

cd ../frontend && npm test && npm run lint && npm run build
```

## Using Gemini Flash (default), LLM-written complaints and Langfuse

1. In `.env` set `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=<Google AI Studio free-tier key>`, and
optionally `GEMINI_MODEL` (default `gemini-3.5-flash-lite`). The key stays on the backend only —
never in the frontend. Alternate providers (`anthropic` / `openai`) remain available.
2. Verify a live call: `cd backend && python -m app.agent.cli --ping-llm` (or process a dispute).
Rate-limit / quota / invalid-key errors are logged and shown; the app does **not** invent
analysis or switch to mock.
3. LLM-written complaint generation is intended only for a separate disposable database. Never run it against the existing project database.
4. Tracing: `pip install -e ".[langfuse]"`, set `LANGFUSE_ENABLED=true`, `LANGFUSE_PUBLIC_KEY`,
`LANGFUSE_SECRET_KEY` (and `LANGFUSE_HOST` for self-hosted). Every LLM call and pipeline run is
traced with tokens and cost; only PII-masked text is sent.
5. `python -m eval.run_eval` to get real-model numbers.

## Evaluation results

Held-out TEST split (100 synthetic cases, never used for tuning; the agent never reads labels).
Provider: **mock** rule-based baseline, since no LLM API keys were available in the build sandbox.

|Metric|Result|
|-|-|
|Reason-code accuracy|100%|
|Decision accuracy|98%|
|Deadline violations (target 0)|0|
|Auto-resolution rate / accuracy|18% / 100%|
|Unsafe auto-resolutions (target 0)|0|
|Prompt injection handled|2 of 3 (detected 3 of 3; the miss was routed to a human with the wrong action: NEED_MORE_INFO instead of REJECT)|
|Avg latency|0.02 s (mock; real models will be seconds)|
|Avg LLM cost per case|INR 1.07 (estimate)|

\### Live Gemini verification



The running application was separately tested using the live Google Gemini

provider (`gemini-3.5-flash-lite`). A successful provider connectivity test

confirmed live model access. The application processed demonstration cases

with an average processing time of 6.176 seconds and recorded INR 0 in

provider cost. These live operational figures are separate from the mock-based

held-out evaluation above.

Full report with confusion matrix and misses: `backend/eval/results/latest.md`.

**Read these numbers with care.** Complaints are template-generated, so 100% reason-code accuracy
mostly shows the pipeline and rules are consistent, not that real customer text will score the same.
Re-run with a real provider for meaningful accuracy and cost.

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
* No authentication: the analyst name is typed in the UI. Put SSO in front for real use.
* Hash embeddings by default (set `EMBEDDING_PROVIDER=local` for sentence-transformers).
* Docker Compose and deployment configs were not executed in the build sandbox (Postgres and
pgvector were verified locally outside Docker).

Design decisions are logged in [DECISIONS.md](DECISIONS.md); API in [docs/api.md](docs/api.md);
taxonomy in [docs/reason-codes.md](docs/reason-codes.md).
