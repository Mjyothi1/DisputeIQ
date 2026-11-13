# Reviewer portal demo guide

1. Landing page → **Reviewer login** → enter priya's reviewer key. The header shows "Signed in as priya".
2. **Queue**: tabs show live counts; the Engine column says *Offline rules* for seeded history and *Gemini* for live
   cases. Customer-portal complaints start with `[Customer portal] Category: … Selected transaction: …` (the selected
   transaction is taken from the bank's own records, not typed by the customer).
3. Open a case: matched transaction, evidence checklist, confidence against the 0.85 threshold, model label, route
   reasons ("why this needs a person"), drafts and the audit timeline.
4. Decide in the right-hand panel:
   - **Approve** the agent's recommendation, or **Approve with my edits** after editing the letter/filing;
   - **Override** (choose another decision; a written reason is required);
   - **Reject the customer's dispute**.
   Your name comes from your key; notes stay internal.
5. **Reopen for review** is available on an auto-resolved case (reason required, audited). Closed cases are never
   silently re-run.
6. **Staff intake** lets bank staff enter a complaint on behalf of any customer (the old "Submit complaint" page).
7. **Metrics** shows live counts and which engine analysed each case.

Customers who try reviewer APIs get 403; reviewer keys cannot be used as customer sessions.
