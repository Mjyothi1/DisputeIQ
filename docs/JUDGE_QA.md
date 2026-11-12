# Likely judge questions (concise, defensible answers)

**AI / accuracy**
1. *How accurate is it?* Live Gemini accuracy is not measured yet. Offline suites: 99% (synthetic, circular) and 83% reason code / 0 unsafe auto-resolutions (33 hand-authored). The guarantee we stand behind is the safety invariant, not an accuracy figure.
2. *Why is mock 99%?* The mock classifier and templates share keywords; it shows rule/pipeline consistency only.
3. *What does the LLM actually do?* Extraction, reason-code classification, rationale, letter prose. Everything financial is code.
4. *What if Gemini is wrong?* Policy needs supporting evidence from DB checks; confidence is capped by match quality and rules; only low-value verified REFUNDs auto-resolve; everything else gets a human.
5. *Why Gemini Flash?* Free tier, structured output, speed. Provider is pluggable; no silent mock fallback.
6. *Hallucination?* Letters get amounts/dates from the DB; model text is validated against templates and rejected if inconsistent.
7. *How is a rate limit handled?* 429s are retried (bounded, backoff, jitter, Retry-After); daily quota/auth errors are not; on exhaustion the case goes to human review with an audit entry.
8. *Similar cases?* pgvector retrieval on Postgres only, hash embeddings (lexical); results are context in the prompt.
9. *Multilingual?* Hinglish handled by the model/extraction and the injection filter; offline engine is weaker (see misses).

**Security**
10. *Prompt injection?* Structural defence first (text can't set policy/amount/routing), regex second; flagged => human. Not perfect; stated.
11. *PII?* Regex masking of listed identifiers before LLM/logs; names/addresses aren't masked; raw text stored unmasked (gap).
12. *Authentication?* Prototype bearer keys, server-derived identity, fail closed. Not SSO.
13. *Can someone approve a case?* Only an authenticated reviewer; client-supplied names are ignored.
14. *Double refunds?* Per-transaction lock + check; repeats go to a human. Verified on SQLite with threads; Postgres path untested here.
15. *Audit?* Every step, actor, model, prompt version, tokens, cost, retries, reopen/review.

**Architecture / business**
16. *Why LangGraph?* Explicit nodes, traceability; logic lives in deterministic modules.
17. *Scale?* Stateless API, Postgres; limiter is in-process; Render free tier cold-starts.
18. *Does it move money?* No.
19. *Regulatory fit?* Illustrative taxonomy/windows, not network-certified; humans retain decisions; audit supports review.
20. *Cost?* Free tier INR 0; offline cost figures are reference estimates.
21. *Business impact?* Not measured; roadmap item (pilot with real cases).
22. *Why 85% / INR 10,000?* Configurable policy thresholds in `reason_codes.yaml`; chosen conservatively.
23. *Frequent disputers?* 3+ disputes in 12 months => human.
24. *Rerun risk?* Closed cases are not re-run; reopen needs analyst + reason.

**Deployment**
25. *What's deployed?* Vercel frontend, Render backend, Postgres, Gemini - as reported by the owner; not independently verified from the build sandbox (egress blocked). Verify `/health` before demo.
26. *Persistence?* Free Render Postgres expires; not permanent storage.
27. *Testing?* 336+ backend tests, 20 frontend tests, lint and build in CI.
