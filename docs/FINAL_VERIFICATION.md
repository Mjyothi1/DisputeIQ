# Final verification (two-portal release)

Status labels: **VERIFIED** (executed here, evidence below) · **NOT VERIFIED** (could not be executed from this sandbox).

| Check | Status | Evidence |
|-|-|-|
| Backend tests, SQLite | VERIFIED | `pytest -q`: 370 passed, 3 skipped (pgvector tests) |
| Backend tests, PostgreSQL 16 + pgvector | VERIFIED | `TEST_DATABASE_URL=… pytest -q`: 373 passed, 0 skipped |
| Ruff | VERIFIED | clean |
| mypy | VERIFIED (unchanged) | 8 findings, all pre-existing; none in new modules |
| Migration 0004 on PostgreSQL | VERIFIED | 0003 → insert legacy rows → 0004 (rows intact, new columns NULL) → downgrade → upgrade; `alembic check`: no drift |
| Startup seeding lock on PostgreSQL | VERIFIED | two concurrent bootstraps: one skipped; 6 demo customers, 6 accounts, no duplicates |
| Frontend lint / tsc / tests / build | VERIFIED | eslint clean, tsc clean, 36 tests passed, Vite build OK |
| Browser end-to-end (local servers, offline engine) | VERIFIED | Playwright: landing → Meera login → report duplicate → AUTO_RESOLVED → Kavya complaint → customer token on `/disputes` = 403 → priya override → Kavya sees "Approved / chargeback", reviewer notes not shown → Kavya reading dispute #1 = 404; no page errors, no 5xx |
| Six original scenarios | VERIFIED offline | `tests/test_demo_customers.py` (offline engine). Live Gemini outcomes depend on model confidence |
| Production deployment (Vercel, Render) | NOT VERIFIED | Sandbox has no network access to either host; nothing was deployed from here |
| Live Gemini | NOT VERIFIED | No key in sandbox |

## Security tests (backend, `tests/test_portal.py`)
Registration/login, uniform invalid-login errors, salted scrypt hashes, forged/tampered/expired tokens rejected,
role field in registration ignored, customers get 403 on all reviewer APIs, reviewer keys rejected by the portal,
own transactions only, IDOR on transactions/complaints returns 404, `customer_id` in body ignored, portal fails closed
without a secret, customer view excludes notes/evidence/model/confidence, reviewer decision reflected to customer.

## Known limitations
- Prototype auth: static reviewer keys; customer sessions are 8-hour signed tokens with no server-side revocation list
  (signing out clears the browser copy only).
- In-process rate limits (single instance).
- A new self-registered customer has no cards; linking real accounts would need KYC/onboarding.
- No payment integration: "Approved" means a refund/chargeback was *authorised*, not credited.

## Refund wording (follow-up fix)
- **Problem:** the refund letter template (and the offline engine's letter) said "we are refunding the amount to your
  account" while the case could still be awaiting review. There is no payment integration.
- **Fix:** templates and the prompt now say "refund authorised; the bank makes the payment separately". Model text that
  claims a completed refund is rejected, and the template is used instead (recorded in the audit). Letters already
  stored with the old wording are corrected when displayed; database rows are unchanged. Customer messages:
  - awaiting review → "under review" wording (the evidence-supported version only when a refund or chargeback is
    recommended), with no letter;
  - approved → "Refund authorised".
  A reviewer-edited letter that claims payment is withheld from the customer.
- **Tests:** `backend/tests/test_refund_wording.py` covers every backend status and checks that no notes or rationale
  leak. `frontend/src/test/refundWording.test.tsx` covers the guard (same cases as the backend), the reviewer
  notices, the warning and the customer pages.

## Letter content fix (production case DIQ-000314)
- **Problem:** a repeat Meera complaint (correctly held for review by the duplicate guard) had a stored Gemini draft
  saying "We have processed a refund", with repeated greetings. PR #5 flagged it, but still displayed the unsafe text.
  The greeting also used the first word of the name ("Dear Demo," for "Demo Customer - Meera Iyer").
- **Fix (`backend/app/services/letters.py`):** every displayed letter is built from database facts for the case's
  current state:
  - pending → "under review; refund recommended, not yet approved";
  - auto-resolved → the stored letter only if clean, otherwise the template;
  - reviewed → the letter for the reviewer's final decision ("refund authorised; the bank makes the payment
    separately"), or the reviewer's edit if clean.

  New cases routed to review store the pending letter. Model text has greetings and sign-offs stripped before the
  letter is assembled. Reviewer edits claiming payment are refused with 422. Stored rows are never rewritten.
- **Tests:** `backend/tests/test_letters.py` reproduces DIQ-000314 end to end (reviewer letter, approval letter,
  customer view, approve flow, unsafe auto-resolved letter, greetings). `frontend/src/test/caseLetters.test.tsx` covers
  the reviewer page.
