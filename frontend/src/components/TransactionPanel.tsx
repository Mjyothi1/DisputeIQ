import type { Transaction } from "@/api/types";
import { formatDateTime, formatInr, humanize } from "@/lib/format";

export function TransactionPanel({ txn }: { txn: Transaction | null }) {
  if (!txn) {
    return (
      <p className="text-sm text-muted-foreground">
        The agent could not match this complaint to a transaction with enough confidence.
      </p>
    );
  }
  const rows: [string, string][] = [
    ["Merchant", `${txn.merchant_name}${txn.merchant_city ? `, ${txn.merchant_city}` : ""}`],
    ["Category", humanize(txn.merchant_category)],
    ["Date and time", formatDateTime(txn.txn_time)],
    ["Card", `${txn.card_network} ending ${txn.card_last4}`],
    ["Channel", humanize(txn.channel)],
    ["Authentication", humanize(txn.auth_method)],
    ["Status", humanize(txn.status)],
    ["Refund", humanize(txn.refund_status)],
    ["Recurring", txn.is_recurring ? "Yes" : "No"],
  ];
  return (
    <div>
      <div className="mb-3 font-serif text-2xl font-semibold tabular-nums">
        {formatInr(txn.amount)}
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1.5 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted-foreground">{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
