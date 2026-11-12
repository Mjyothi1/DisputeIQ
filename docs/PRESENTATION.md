# Corrected slide text (12 slides)

I could not inspect the slide file (not in the repo); this is rewritten from the structure you gave. **Verify every
number before presenting.**

1. **Introduction** - DisputeIQ: an AI-assisted dispute resolution agent for card issuers. Recommends, never pays out.
2. **The problem** - Card disputes are slow and manual. Use at most one statistic and cite it with year and source.
   *Check:* RBI figures I found conflict between releases (FY25 card/internet fraud reported as 13,516 cases in the annual
   report, later revised to 13,332 / about Rs 517 crore; the Rs 1,457 crore figure appears to belong to FY24). Reported
   fraud amounts are not losses. Use only a figure you have opened in the RBI primary document, or drop it.
3. **Manual vs DisputeIQ** - Manual: read, look up, check windows, draft letters. DisputeIQ: same steps as a traced pipeline with a human for anything risky. Don't claim measured time savings (not measured); if cited, label as "estimated".
4. **Case DIQ-000016** - Walkthrough of a seeded duplicate-charge case. State it was processed by the **offline rule engine**.
5. **Nine-step pipeline** - mask PII -> extract -> match transaction -> evidence checks -> classify -> eligibility -> recommend -> draft -> route. Every step is audited.
6. **AI vs code** - Model: extraction, reason-code classification, explanation, letter prose. Code: transaction matching, evidence, eligibility/deadlines, recommendation, amounts, routing. (Avoid "can never"; say "the complaint text cannot set these".)
7. **Trust and safeguards** - Auto-resolve only low-value, high-confidence, evidence-backed refunds; one refund per transaction; reviewer sign-in; terminal cases not re-run; PII masked (regex, best effort); injection detected (heuristic) and always escalated; full audit.
8. **Live demo** - Four scenarios: seeded/offline, live Gemini, human review, suspicious complaint. Label each.
9. **Evaluation** - Offline suites only: 100 synthetic cases (circular: 99% reason code, 0 unsafe auto-resolutions) and 33 hand-authored cases (83% reason code, 0 unsafe auto-resolutions). Live-Gemini accuracy: not yet measured. Say that.
10. **Deployment & stack** - React/Vite on Vercel; FastAPI on Render (Docker); PostgreSQL (+pgvector retrieval on Postgres); Gemini Flash. State what you verified yourself on the day; DB persistence on free tiers is limited.
11. **Impact & roadmap** - Roadmap: SSO + roles, real payment/core-banking hooks, network-specific rules, live-model evaluation on real (consented, anonymised) data, semantic embeddings, monitoring.
12. **Closing** - Humans decide anything risky; code enforces policy; every action is auditable.
