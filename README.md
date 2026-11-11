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
  UI\[React + TS UI] -->|REST| API\[FastAPI]
  API --> AG\[LangGraph agent]
  API --> DB\[(PostgreSQL + pgvector)]
  AG --> DB
  AG --> LLM{{Gemini Flash / mock / Anthropic / OpenAI}}
  AG --> RULES\[Rules: eligibility, policy, routing]
  AG --> TOOLS\[Evidence tools]
```

Pipeline: `mask\_pii â†’ intake\_extract â†’ match\_transaction â†’ run\_evidence\_checks â†’ classify\_reason\_code â†’ eligibility\_engine â†’ recommend â†’ draft\_documents â†’ route`.
Every node writes an audit event. Details: [docs/architecture.md](docs/architecture.md).

Safety properties:

* Auto-resolve only if confidence >= 0.85 **and** amount <= INR 10,000 **and** a clear-cut
REFUND on duplicate/ATM cases. Every rejection goes to a human.
* LLM output is schema-validated; money and dates in letters are filled by code from the database.
* Prompt injection is delimited, detected, and cannot reach decision logic.
* Friendly-fraud signals (e.g. OTP-authenticated "fraud" claims) are flagged and routed to humans.

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build -d
# Seed only a new disposable database; never reset existing data.
# Build memory only after seeding a separate disposable database.
```

* UI: http://localhost:5173
* API docs: http://localhost:8000/docs
* Default LLM is **Google Gemini Flash** (`LLM\_PROVIDER=gemini`, model `gemini-3.5-flash-lite` via
`GEMINI\_MODEL`). Set `GEMINI\_API\_KEY` from [Google AI Studio](https://aistudio.google.com/apikey)
(free tier). For offline unit tests only, set `LLM\_PROVIDER=mock` explicitly â€” failures never
silently fall back to mock.

Then run the demo: [docs/demo.md](docs/demo.md).

## Run without Docker (SQLite, nothing to install)

See [RUN\_LOCAL.md](RUN_LOCAL.md). In short: set `DATABASE\_URL=sqlite:///./disputeiq.db`, run
`python -m app.db.init\_db`, seed, start uvicorn and `npm run dev`. SQLite mode has everything except
pgvector similar-case retrieval (the agent then classifies without past-case context; the
numbers in this README for SQLite differ only in estimated cost). Use PostgreSQL for the full design.

## Run with local PostgreSQL

```bash
# backend (needs Postgres with pgvector; `docker compose up -d db` is the easy way)
cd backend \&\& python3 -m venv .venv \&\& . .venv/bin/activate
pip install -e ".\[dev]"
alembic upgrade head
# Seed only a new disposable database; never reset existing data.
# Build memory only after seeding a separate disposable database.
uvicorn app.main:app --reload

# frontend
cd frontend \&\& cp .env.example .env \&\& npm install \&\& npm run dev
```

## Tests, lint, evaluation

```bash
cd backend
pytest -q                                    # unit + pipeline + API tests (SQLite)
TEST\_DATABASE\_URL=postgresql+psycopg://disputeiq:disputeiq@localhost:5432/disputeiq pytest -q  # + pgvector tests
ruff check . \&\& mypy app
python -m eval.run\_eval                      # 100 held-out TEST cases -> eval/results/

cd ../frontend \&\& npm test \&\& npm run lint \&\& npm run build
```

## Using Gemini Flash (default), LLM-written complaints and Langfuse

1. In `.env` set `LLM\_PROVIDER=gemini`, `GEMINI\_API\_KEY=<Google AI Studio free-tier key>`, and
optionally `GEMINI\_MODEL` (default `gemini-3.5-flash-lite`). The key stays on the backend only â€”
never in the frontend. Alternate providers (`anthropic` / `openai`) remain available.
2. Verify a live call: `cd backend \&\& python -m app.agent.cli --ping-llm` (or process a dispute).
Rate-limit / quota / invalid-key errors are logged and shown; the app does **not** invent
analysis or switch to mock.
3. LLM-written complaint generation is intended only for a separate disposable database. Never run it against the existing project database.
4. Tracing: `pip install -e ".\[langfuse]"`, set `LANGFUSE\_ENABLED=true`, `LANGFUSE\_PUBLIC\_KEY`,
`LANGFUSE\_SECRET\_KEY` (and `LANGFUSE\_HOST` for self-hosted). Every LLM call and pipeline run is
traced with tokens and cost; only PII-masked text is sent.
5. `python -m eval.run\_eval` to get real-model numbers.

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
|Prompt injection handled|2 of 3 (detected 3 of 3; the miss was routed to a human with the wrong action: NEED\_MORE\_INFO instead of REJECT)|
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
* Hash embeddings by default (set `EMBEDDING\_PROVIDER=local` for sentence-transformers).
* Docker Compose and deployment configs were not executed in the build sandbox (Postgres and
pgvector were verified locally outside Docker).

Design decisions are logged in [DECISIONS.md](DECISIONS.md); API in [docs/api.md](docs/api.md);
taxonomy in [docs/reason-codes.md](docs/reason-codes.md).
