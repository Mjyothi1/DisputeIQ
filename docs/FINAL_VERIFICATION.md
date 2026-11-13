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
