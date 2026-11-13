# Speaking notes (pairs with docs/DisputeIQ_Zeta_Innovate_2026.pptx)

Talk to the judges, not the slides. Roughly 45 seconds per slide; the bullets are prompts, not lines to recite.

1. **DisputeIQ.** "When a customer disputes a card charge, someone at the bank has to read the complaint, find the transaction, check the evidence and the deadline, and write back. DisputeIQ does that groundwork and decides only the cases that are safe to decide automatically."
2. **Problem.** Three pains: manual lookups, hard network deadlines, and friendly fraud ("I didn't do it" on an OTP payment). Don't quote statistics you haven't checked in the source.
3. **Solution.** Same steps an analyst takes, but traced. Point at the right card: the low-risk refunds close themselves; everything else arrives at an analyst already investigated, with drafts.
4. **Architecture.** React on Vercel, FastAPI on Render, Postgres, Gemini Flash. Gemini only ever sees masked text. Mention the engine label: history was processed offline and is labelled that way.
5. **Pipeline.** "Blue boxes are the model, dark boxes are code. The model reads and classifies; code matches the transaction, checks evidence, computes the deadline, decides and routes."
6. **Evidence.** The auto-resolve rule card: all six conditions must hold. "A clever complaint can't talk its way past a database check."
7. **Scenarios.** Introduce the six customers; then switch to the live demo (LIVE_DEMO_SCRIPT.md).
8. **Safeguards.** Reviewer sign-in, one refund per transaction, PII masking, injection handling, audit, bounded retries. Say plainly that masking and injection detection are heuristics; the guarantee comes from the design.
9. **Evaluation.** "We only have offline numbers so far. The 99% is circular, so the number we stand behind is zero unsafe auto-resolutions. Live Gemini accuracy is our next measurement."
10. **Close.** "Humans decide the risky cases. Code enforces policy. Everything is auditable." Then limitations and next steps.

## Likely questions

- **How accurate is it?** We haven't measured live Gemini accuracy yet. Offline: 99% on circular synthetic data, 83% on 33 harder hand-authored cases, and zero unsafe auto-resolutions in both.
- **What if Gemini is wrong?** A wrong classification still has to pass evidence checks; anything uncertain, high-value or non-refund goes to a person.
- **What if Gemini is down?** Bounded retries, then the case goes to a human with a visible warning. No silent fallback.
- **Prompt injection?** Detected and flagged, but more importantly the complaint text cannot set the policy, the amount, the deadline or the route.
- **Can it refund twice?** No: a second dispute on the same transaction always goes to a human; the check runs under a per-transaction lock.
- **Is it production-ready?** It's a working prototype: auth is static reviewer keys, not SSO; PII masking is regex; the taxonomy is illustrative.
- **Does it move money?** No. It recommends and drafts; payments stay in core banking.
- **Why LangGraph?** Explicit, auditable steps; the business logic lives in plain, tested Python.
- More answers: [JUDGE_QA.md](JUDGE_QA.md).
