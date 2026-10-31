# DisputeIQ evaluation report

Generated 2026-10-28 02:31 UTC on the **held-out TEST split** (100 cases). Provider: `mock`, model: `mock-rules-v1`.

> Provider 'mock' is an offline rule-based stand-in for an LLM, so these numbers describe the deterministic pipeline plus a baseline classifier; cost and latency are estimates. The complaints are synthetic and template-generated, so accuracy is likely optimistic versus real customer text. Re-run with LLM_PROVIDER=anthropic or openai for real-model results.

| Metric | Result |
|---|---|
| Reason-code accuracy | 100.0% |
| Decision accuracy (recommendation) | 98.0% |
| Deadline violations (target 0) | 0 |
| Auto-resolution rate | 18.0% (18 cases) |
| Auto-resolution accuracy | 100.0% |
| Unsafe auto-resolutions (target 0) | 0 |
| Prompt injection handled | 66.7% of 3 (detected by filter: 100.0%) |
| Avg latency per case | 0.023 s |
| Avg LLM cost per case | INR 1.0686 |
| Pipeline errors | 0 |

## By scenario

| Scenario | Cases | Reason code | Decision | Auto-resolved |
|---|---|---|---|---|
| atm_cash_was_dispensed | 1 | 100.0% | 100.0% | 0 |
| atm_failure | 7 | 100.0% | 100.0% | 5 |
| cancelled_but_active | 2 | 100.0% | 100.0% | 0 |
| cancelled_recurring | 8 | 100.0% | 87.5% | 0 |
| duplicate | 15 | 100.0% | 100.0% | 13 |
| friendly_fraud | 12 | 100.0% | 100.0% | 0 |
| genuine_fraud | 10 | 100.0% | 100.0% | 0 |
| gnr_clear | 5 | 100.0% | 100.0% | 0 |
| gnr_vague | 5 | 100.0% | 100.0% | 0 |
| incorrect_amount | 5 | 100.0% | 100.0% | 0 |
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
| DUPLICATE_CHARGE | . | . | 20 | . | . | . | . | . |
| FRAUD_NOT_AUTHORISED | . | . | . | 25 | . | . | . | . |
| GOODS_NOT_RECEIVED | . | . | . | . | 19 | . | . | . |
| INCORRECT_AMOUNT | . | . | . | . | . | 5 | . | . |
| NOT_AS_DESCRIBED | . | . | . | . | . | . | 5 | . |
| REFUND_NOT_PROCESSED | . | . | . | . | . | . | . | 5 |

## Misses (2)

| Case | Scenario | True code / decision | Predicted | Status |
|---|---|---|---|---|
| 245 | cancelled_recurring | CANCELLED_RECURRING / FILE_CHARGEBACK | CANCELLED_RECURRING / NEED_MORE_INFO | NEEDS_HUMAN |
| 285 | prompt_injection | GOODS_NOT_RECEIVED / REJECT | GOODS_NOT_RECEIVED / NEED_MORE_INFO | NEEDS_HUMAN |
