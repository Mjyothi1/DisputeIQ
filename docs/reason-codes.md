# Reason-code taxonomy (simplified, illustrative)

This is a prototype taxonomy written for this project. It is **not** a card-network rulebook;
real codes, conditions and time limits differ by network and change over time. Windows are
configurable in `backend/app/rules/reason_codes.yaml`.

| Code | Customer says | Key evidence | Window (illustrative) |
|---|---|---|---|
| FRAUD_NOT_AUTHORISED | "I did not make this purchase" | Authentication method (OTP/PIN = strong evidence the cardholder paid), dispute history | 120 days |
| DUPLICATE_CHARGE | Charged twice | Same merchant, amount within 5%, within 24h | 120 days |
| GOODS_NOT_RECEIVED | Paid, nothing arrived | Transaction exists, refund not issued | 120 days |
| NOT_AS_DESCRIBED | Item differs from listing | Transaction exists, refund not issued | 120 days |
| CANCELLED_RECURRING | Cancelled but still billed | Subscription cancelled before charge | 120 days |
| INCORRECT_AMOUNT | Billed more than agreed | Claimed expected amount vs charged | 120 days |
| REFUND_NOT_PROCESSED | Merchant promised refund | Refund status on transaction | 120 days |
| ATM_CASH_NOT_DISPENSED | ATM debited, no cash | ATM failure flag on the transaction | 30 days |

Window start is the transaction date; eligibility is evaluated as of the dispute creation time,
so results are reproducible.

## Recommendations

REFUND (issuer refunds), FILE_CHARGEBACK (raise against merchant), REJECT (not eligible or
contradicted by evidence), NEED_MORE_INFO (ambiguous or insufficient). Only REFUND on the
auto-resolve codes can bypass a human.
