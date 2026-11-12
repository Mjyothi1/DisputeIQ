# Design decisions

Ambiguities are resolved in favour of the simpler option and recorded here.

## Phase 1

1. **Spec source.** Followed the DisputeIQ brief (8 phases, field names such as `final_decision`,
   `input_summary`, `refund_status`). Borrowed compatible principles from the attached
   ResolveIQ `CLAUDE.md`: audit telemetry columns, `ground_truth` + dev/test `split`,
   `subscriptions` table, PII-never-reaches-LLM, configurable thresholds.
2. **`subscriptions` table added.** Not in the brief's table list, but the recurring-cancellation
   evidence check cannot be implemented without it.
3. **Enums stored as VARCHAR** (`native_enum=False`), not native PG enums: easier migrations.
4. **Money is `Numeric(12,2)`** / `Decimal`; never float.
5. **`transactions.account_debited` and `details` JSON** added to support "failed but debited" and
   ATM cash-not-dispensed checks deterministically.
6. **`audit_events` carries LLM telemetry** (model, prompt_version, tokens, cost_inr, latency_ms),
   null for non-LLM steps.
7. **Embedding dimension is configurable** (`EMBEDDING_DIM`, default 384 for a local
   sentence-transformers model). Changing it requires a new migration; the initial migration
   hardcodes 384.
8. **Frontend service** is added to Docker Compose in Phase 6, not before.
9. **Python:** requires >=3.11; verified locally on 3.13.

## Phases 2-4

10. **Policy decides, the LLM explains.** The recommendation is computed by `rules/policy.py`
    from reason code + eligibility + evidence. The LLM classifies the reason code and writes the
    rationale/letters; it can only *lower* confidence (`min(policy cap, classifier, explainer,
    match cap)`), never change the action. A prompt injection can therefore not change an outcome.
11. **Eligibility is evaluated as of the dispute's received date** (`created_at`), not "now", so
    re-runs and evaluations are reproducible and a customer is not penalised for analyst delay.
    The queue computes days-to-deadline against the current time from the stored `deadline_at`.
12. **Dates are never computed by the LLM.** It returns day/month(/year) as written; code
    resolves them (`tools/matching.resolve_date`).
13. **Documents: placeholders only.** The LLM writes prose with `{amount}`-style placeholders;
    code fills values from the DB and rejects model text containing literal amounts, dates or long
    numbers (falls back to a deterministic template and records it in the audit trail).
14. **Gemini Flash is the default LLM** (`LLM_PROVIDER=gemini`, model default defined once in `backend/app/core/config.py` via
    `GEMINI_MODEL`, SDK `google-genai`, key `GEMINI_API_KEY`). Verified free-tier eligible on the
    Gemini Developer API (input/output free of charge). The offline `mock` provider remains only
    as an **explicit** opt-in for tests/demos — Gemini failures (rate limit, quota, bad key,
    timeout) raise clear errors and route to a human; they never silently fall back to mock.
    Free-tier Gemini token cost is recorded as INR 0.
15. **Hash embeddings are the default** (no heavy dependency); `local` (sentence-transformers) and
    `openai` are supported and degrade to hash if unavailable.
16. **Case memory** (`case_embeddings`) holds resolved cases only. `data_gen/build_memory.py`
    bootstraps it from the DEV split labels as stand-in "historical analyst outcomes"; TEST is
    never indexed, and the agent never reads `ground_truth` (AST test enforces this).
17. **Thresholds live only in `rules/reason_codes.yaml`**, not in `.env`.
18. **Evidence verdicts** (PASS/FAIL/INCONCLUSIVE/INFO) are stored per reason code so the analyst
    checklist reads correctly (e.g. OTP authentication is FAIL on a fraud claim).
19. **Gemini structured output** uses `response_mime_type=application/json` + Pydantic
    `response_schema` via `google-genai`. Anthropic uses a forced tool call (no `temperature`);
    OpenAI uses `chat.completions.parse`. Permanent Gemini errors (401/403, hard quota) become
    `LLMError` immediately; soft 429s are retried by `RetryingClient`.

## Phase 6 (frontend)

20. **Extra read-only endpoints beyond the brief**, used only by the UI: `GET /customers`,
    `GET /customers/{id}/transactions`, `GET /reason-codes`, `GET /config` (routing thresholds, so the
    confidence meter can draw the auto-resolve tick from the single source in the YAML).
21. **Analyst identity** is a name typed in the header (stored in localStorage). There is no
    authentication; a real deployment would put SSO in front and take the name from the token.
22. **UI never shows `ground_truth` or raw PII**; the complaint is displayed in its masked form.
23. **Vitest 3** (not 2): Vitest 2 bundles Vite 5, which conflicts with Vite 6 types.

## Phases 7-8

24. **Evaluation uses only the TEST split** and never feeds back into thresholds or prompts;
    results are written to `eval/results/<ts>.{json,md}` plus `latest.*`, which `/metrics` surfaces.
25. **Eval report states the mock-provider caveat** in the file itself, so numbers are never
    shown without it.
26. **Deployment configs** (render.yaml, vercel.json) are provided untested; secrets only via
    dashboard env vars.
27. **Langfuse tracing is a no-op unless enabled** with keys; failures are swallowed so tracing can never
    break a dispute run; only masked text is exported.
28. **LLM complaint writer** runs the template writer first (so the random stream, and the whole
    dataset structure, is identical), accepts LLM text only if it contains every required fact, and
    caches results in `data_gen/.complaint_cache.json`.
29. **SQLite no-Docker mode.** `DATABASE_URL=sqlite:///...` + `python -m app.db.init_db` creates all
    tables except pgvector's `case_embeddings`; the pipeline then uses a null retriever. Verified
    end to end (seed, 100-case eval with identical accuracy, API submit/process). Alembic migrations
    and pgvector remain the Postgres path.
30. **`eval.run_eval` only overwrites `latest.*` on a full run** (no `--limit`, at least one case).


## Final hardening decisions (Zeta Innovate 2026)

15. **Prototype reviewer auth** (`REVIEWER_ACCOUNTS`, bearer keys). The analyst name is derived from the key on the
    server; the client can no longer supply it. Fails closed. Explicitly not SSO.
16. **Duplicate-refund guard in the pipeline's route step**: per-transaction lock (+ Postgres advisory lock),
    check for other disputes on the same transaction, decision and commit inside the lock. Chosen over a partial
    unique index because creating one would fail on existing duplicate rows in a live database and could stop a
    deployment's `alembic upgrade head`.
17. **Terminal cases are never re-run.** Only NEW / NEEDS_HUMAN are processable (atomic claim); an analyst can
    reopen an AUTO_RESOLVED case with a reason (`POST /disputes/{id}/reopen`), history preserved.
18. **429 is transient unless it names a daily/billing quota**; bounded retries with exponential backoff, jitter
    and Retry-After; hard quota and auth errors are never retried; retries are audited.
19. **Evaluation runs on its own in-memory database** and is split into mock vs live; mock results are labelled
    as circular and never presented as Gemini accuracy.
