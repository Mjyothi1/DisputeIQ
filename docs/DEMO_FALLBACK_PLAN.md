# Demo fallback plan

Rule: **never describe offline output as Gemini output.** The case page and the queue's Engine column show the real engine.

| Situation | What you see | What to do / say |
|-|-|-|
| Render cold start | Sign-in or queue spins for ~30-60 s | Open `/health` 10 minutes before. If it still spins, say "free-tier instance waking up", continue with the slides, retry. |
| Gemini 429 / 503 | Submission takes longer; case may land in **Needs review** with a red "AI provider did not complete every step" banner and `llm_retry` / `llm_provider_error` in the audit | Show it: "Rate limit hit. We retry with backoff, then fail safe to a human. We never fabricate an answer or silently switch to rules." |
| Gemini fully unavailable | Every new case goes to Needs review with the failure banner | Demo the seeded (offline) cases and the reviewer workflow; play the rehearsal recording for the live path. |
| A transaction doesn't appear | Submit page lists the selected customer's own transactions with ids | Check the selected-customer box shows the right name and •••• last4. If a demo customer has no transactions, use a spare demo customer; production data must be checked separately (see VERIFICATION.md). |
| Duplicate routed to human instead of auto-resolved | Route reasons list e.g. "Confidence 0.8 below threshold 0.85" | "Correct: below threshold we escalate. Confidence is capped by evidence quality, not by what the customer writes." |
| Demo customer already used | Second complaint is flagged as duplicate / frequent disputer | Use a spare customer (Isha, Arjun). Don't reuse customers between rehearsal and the live run on the same database. |
| Customer can't sign in | "Email or password is incorrect" or "not configured" | Check `DEMO_CUSTOMER_PASSWORD` and `BOOTSTRAP_DEMO_CUSTOMERS=true` are set on Render (accounts are created at startup); `AUTH_SECRET` or `REVIEWER_ACCOUNTS` must be set. |
| Production frontend down | Vercel page fails | Run locally (`RUN_LOCAL.md`) with `LLM_PROVIDER=gemini` if a key is available, otherwise `LLM_PROVIDER=mock` and say "offline rules engine, not Gemini". |
| Unexpected live result | Anything not in LIVE_DEMO_SCRIPT.md | Open the audit timeline and explain what the system did and why; that transparency is the point. Don't retry repeatedly on stage. |

Keep a screen recording of a successful rehearsal of the live path as the last resort.
