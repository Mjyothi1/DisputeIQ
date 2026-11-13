/**
 * Mirrors backend COMPLETED_REFUND_CLAIM (app/agent/documents.py): wording that says money has
 * already moved. No payment integration exists, so letters must never say this.
 */
const COMPLETED_REFUND_CLAIM = new RegExp(
  [
    String.raw`\b(?:has|have|had)\s+been\s+(?:credited|refunded|reversed|processed|paid|returned)\b`,
    String.raw`\b(?:we|we've|we\s+have|i\s+have)\s+(?:now\s+)?(?:processed|credited|refunded|reversed|issued|paid)\b`,
    String.raw`\b(?:are|is|am)\s+(?:now\s+)?(?:refunding|crediting|reversing|returning)\b`,
    String.raw`\brefund(?:ed)?\s+(?:has|was)\s+(?:been\s+)?(?:processed|issued|credited|completed|paid)\b`,
    String.raw`\b(?:credited|refunded|reversed|returned)\s+(?:back\s+)?(?:to|into)\s+your\b`,
    String.raw`\brefund\s+(?:is\s+)?(?:processed|complete|completed)\b`,
  ].join("|"),
  "i",
);

export function claimsCompletedRefund(text: string | null | undefined): boolean {
  return !!text && COMPLETED_REFUND_CLAIM.test(text);
}

const REC_WORD: Record<string, string> = {
  REFUND: "Refund",
  FILE_CHARGEBACK: "Chargeback",
  REJECT: "Rejection",
  NEED_MORE_INFO: "Request for more information",
};

/** What the letter draft currently is, in plain words, for the reviewer. */
export function letterStatusNotice(status: string, recommendation: string | null | undefined): string {
  const rec = REC_WORD[recommendation ?? ""] ?? "Outcome";
  if (status === "NEEDS_HUMAN" || status === "NEW" || status === "PROCESSING")
    return `Draft only, not sent. ${rec} is recommended, not approved. The customer receives this letter only if you approve; until then they have the "under review" letter above.`;
  if (status === "AUTO_RESOLVED")
    return recommendation === "REFUND"
      ? "Sent on automatic resolution: refund authorised. The bank makes the payment separately; no payment confirmation is recorded here."
      : "Sent on automatic resolution.";
  return "Final letter for the reviewer's decision. A refund, if any, is authorised; the payment itself is made separately by the bank.";
}
