# API

Interactive docs at `/docs` (Swagger) when the backend runs.

| Method | Path | Notes |
|---|---|---|
| GET | /health | liveness and DB check |
| POST | /disputes | body `{customer_id, channel, raw_text}`; returns 202 and processes in the background (`?wait=true` processes inline) |
| GET | /disputes | filters: `status` (repeatable), `reason_code`, `min_confidence`, `max_confidence`, `max_days_to_deadline`, `q`, `sort=urgency\|newest\|confidence`, `page`, `page_size` |
| GET | /disputes/{id} | full case: transaction, evidence, decision, reviews, route reasons, audit |
| POST | /disputes/{id}/process | re-run the agent (409 if running or already human-decided) |
| POST | /disputes/{id}/review | `{analyst, action: APPROVE\|EDIT\|OVERRIDE\|REJECT, final_decision?, reason_code?, notes?, edited_letter?, edited_filing?}` |
| GET | /disputes/{id}/audit | audit events |
| GET | /metrics | live metrics + latest evaluation headline |

Additions used by the UI beyond the original brief: `GET /customers`,
`GET /customers/{id}/transactions`, `GET /reason-codes`, `GET /config`
(`llm_provider` / `llm_model` are included so the UI can show live Gemini vs mock).

LLM: default `LLM_PROVIDER=gemini` with `GEMINI_API_KEY` / `GEMINI_MODEL` (default in config.py)
(free tier). Failures are audited on the case; there is no silent mock fallback.
Connectivity check: `python -m app.agent.cli --ping-llm`.
