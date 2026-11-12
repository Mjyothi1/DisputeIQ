# DisputeIQ evaluation report

Generated 2026-11-12 19:20 UTC on the **held-out TEST split** (100 cases). Provider: `mock`, model: `mock-rules-v1`.

> Provider 'mock' is an offline rule-based stand-in for an LLM, so these numbers describe the deterministic pipeline plus a baseline classifier; cost and latency are estimates. The complaints are synthetic and template-generated, so accuracy is likely optimistic versus real customer text. Re-run with LLM_PROVIDER=gemini (GEMINI_API_KEY) for real-model results.

| Metric | Result |
|---|---|
| Reason-code accuracy | 99.0% |
| Decision accuracy (recommendation) | 99.0% |
| Deadline violations (target 0) | 0 |
| Auto-resolution rate | 16.0% (16 cases) |
| Auto-resolution accuracy | 100.0% |
| Unsafe auto-resolutions (target 0) | 0 |
| Prompt injection handled | 66.7% of 3 (detected by filter: 100.0%) |
| Avg latency per case | 0.022 s |
| Avg LLM cost per case | INR 1.0567 |
| Pipeline errors | 0 |

## By scenario

| Scenario | Cases | Reason code | Decision | Auto-resolved |
|---|---|---|---|---|
| atm_cash_was_dispensed | 1 | 100.0% | 100.0% | 0 |
| atm_failure | 7 | 100.0% | 100.0% | 6 |
| cancelled_but_active | 2 | 100.0% | 100.0% | 0 |
| cancelled_recurring | 8 | 100.0% | 100.0% | 0 |
| duplicate | 15 | 100.0% | 100.0% | 10 |
| friendly_fraud | 12 | 100.0% | 100.0% | 0 |
| genuine_fraud | 10 | 100.0% | 100.0% | 0 |
| gnr_clear | 5 | 100.0% | 100.0% | 0 |
| gnr_vague | 5 | 100.0% | 100.0% | 0 |
| incorrect_amount | 5 | 80.0% | 100.0% | 0 |
| not_as_described | 5 | 100.0% | 100.0% | 0 |
| out_of_window | 7 | 100.0% | 100.0% | 0 |
| prompt_injection | 3 | 100.0% | 66.7% | 0 |
| refund_not_processed | 5 | 100.0% | 100.0% | 0 |
| refunded_then_disputed | 7 | 100.0% | 100.0% | 0 |
| serial_duplicate | 3 | 100.0% | 100.0% | 0 |

## Reason-code confusion matrix

Rows are the true code, columns the prediction.

| true \ predicted | ATM_CASH_NOT_DISPENSED | CANCELLED_RECURRING | DUPLICATE_CHARGE | FRAUD_NOT_AUTHORISED | GOODS_NOT_RECEIVED | INCORRECT_AMOUNT | NOT_AS_DESCRIBED | REFUND_NOT_PROCESSED |
|---|---|---|---|---|---|---|---|---|
| ATM_CASH_NOT_DISPENSED | 11 | . | . | . | . | . | . | . |
| CANCELLED_RECURRING | . | 10 | . | . | . | . | . | . |
| DUPLICATE_CHARGE | . | . | 21 | . | . | . | . | . |
| FRAUD_NOT_AUTHORISED | . | . | . | 23 | . | . | . | . |
| GOODS_NOT_RECEIVED | . | . | . | . | 20 | . | . | . |
| INCORRECT_AMOUNT | . | . | . | . | 1 | 4 | . | . |
| NOT_AS_DESCRIBED | . | . | . | . | . | . | 5 | . |
| REFUND_NOT_PROCESSED | . | . | . | . | . | . | . | 5 |

## Misses (2)

| Case | Scenario | True code / decision | Predicted | Status |
|---|---|---|---|---|
| 33 | incorrect_amount | INCORRECT_AMOUNT / FILE_CHARGEBACK | GOODS_NOT_RECEIVED / FILE_CHARGEBACK | NEEDS_HUMAN |
| 84 | prompt_injection | GOODS_NOT_RECEIVED / REJECT | GOODS_NOT_RECEIVED / NEED_MORE_INFO | NEEDS_HUMAN |
