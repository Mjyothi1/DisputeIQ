import { CheckCircle2, CircleHelp, Info, XCircle } from "lucide-react";
import type { Evidence } from "@/api/types";
import { cn } from "@/lib/utils";

const CHECK_LABEL: Record<string, string> = {
  duplicate_charge: "Duplicate charge",
  strong_authentication: "Strong authentication (OTP / PIN)",
  refund_issued: "Refund already issued",
  subscription_cancelled: "Subscription cancelled before charge",
  dispute_history: "Customer dispute history",
  atm_failure: "ATM dispensed no cash",
  amount_mismatch: "Charged amount differs from expected",
};

const ICON = {
  PASS: { Icon: CheckCircle2, cls: "text-pass", label: "Supports the claim" },
  FAIL: { Icon: XCircle, cls: "text-fail", label: "Weakens the claim" },
  INCONCLUSIVE: { Icon: CircleHelp, cls: "text-warn", label: "Inconclusive" },
  INFO: { Icon: Info, cls: "text-muted-foreground", label: "Not relevant to this reason code" },
} as const;

function Row({ e }: { e: Evidence }) {
  const { Icon, cls, label } = ICON[e.result];
  return (
    <li className="flex items-start gap-3 py-2.5">
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", cls)} aria-label={label} role="img" />
      <div className="min-w-0">
        <div className="text-sm font-medium">{CHECK_LABEL[e.check_name] ?? e.check_name}</div>
        <div className="text-sm text-muted-foreground">{e.details?.summary ?? "-"}</div>
      </div>
    </li>
  );
}

export function EvidenceList({ evidence }: { evidence: Evidence[] }) {
  if (evidence.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No checks were run because no transaction was matched to this complaint.
      </p>
    );
  }
  const relevant = evidence.filter((e) => e.result !== "INFO");
  const other = evidence.filter((e) => e.result === "INFO");
  return (
    <div>
      <ul className="divide-y divide-border">
        {relevant.map((e) => (
          <Row key={e.id} e={e} />
        ))}
      </ul>
      {other.length > 0 && (
        <details className="mt-1 text-sm">
          <summary className="cursor-pointer py-2 text-muted-foreground">
            {other.length} other checks, not relevant to this reason code
          </summary>
          <ul className="divide-y divide-border">
            {other.map((e) => (
              <Row key={e.id} e={e} />
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
