# Security notes (prototype) - what is and is not protected

## Authentication / authorization
* Prototype reviewer keys: `REVIEWER_ACCOUNTS="name=key,..."` (env, never committed). `Authorization: Bearer <key>`.
  The reviewer name is derived **server-side**; a client-supplied `analyst` field is ignored.
* Protected: all `/disputes*` (read, submit, process, review, reopen, audit), `/customers*`, `/metrics`, `/auth/me`.
  Open: `/health`, `/config`, `/reason-codes` (no customer data).
* Fails closed (503) when no accounts are configured; keys compared in constant time; 30 submits/min per reviewer;
  64 KB request limit; CORS allows only `Authorization` and `Content-Type` headers.
* **Not** SSO: static shared keys, no expiry/rotation, no MFA, no lockout. The key sits in browser `sessionStorage`.

## Money-safety controls (deterministic code, not the LLM)
* Auto-resolve only if: REFUND, allow-listed code, confidence >= 0.85, amount <= INR 10,000, eligible, no injection flag,
  no friendly-fraud/frequent-disputer flag, **and no other dispute on the same transaction**.
* Duplicate guard: per-transaction lock + check + commit (Postgres adds an advisory lock). Verified with threads on
  SQLite; the Postgres lock path is implemented but untested against a real Postgres.
* Closed cases are never re-run; an analyst may reopen an AUTO_RESOLVED case with a reason (audited).
* No payment/refund is executed anywhere: this is a recommendation system.

## PII masking (regex, best effort)
Masked before any LLM call / log / audit: emails, UPI IDs, bank account numbers (keyword-anchored), card numbers
(13-19 digits, last 4 kept), Indian mobiles, Aadhaar (keyword or 4-4-4 grouped), PAN ids, CVV/CVC, OTP values
(keyword-anchored), card expiry (keyword-anchored). Plain digit strings (order/reference numbers) are left alone.
**Not masked:** names, addresses, DOB, identifiers in unusual formats or written in words, Aadhaar as a bare 12-digit
number without a keyword. `raw_text` is stored unmasked in the database (analysts see the masked version through the API).

## Prompt injection
* Structural: complaint text is delimited as data, model output is schema-validated, and policy, amounts, deadlines and
  routing are computed by code from database evidence. A flagged complaint always goes to a human.
* Heuristic: regex patterns (English, Hinglish, spaced/zero-width obfuscation, authority claims, "note to the AI").
  Not perfect. The LLM still influences extraction and reason-code classification, so a missed attack could skew those;
  it still cannot create a refund the evidence does not support, and anything over INR 10,000, low confidence or
  non-REFUND goes to a human anyway.

## Known gaps
No rate limiting beyond in-process submits; single-instance limiter; raw complaint text stored unmasked; no audit
of failed logins; no HTTPS enforcement in-app (Render/Vercel terminate TLS); Gemini receives masked text only.
