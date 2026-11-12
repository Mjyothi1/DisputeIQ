import { daysLabel } from "@/lib/format";
import { cn } from "@/lib/utils";

const RUNWAY_DAYS = 120; // the default dispute window; shorter windows (ATM) simply start shorter

export function urgency(
  days: number | null,
  atRiskDays: number,
): "none" | "overdue" | "urgent" | "soon" | "ok" {
  if (days === null) return "none";
  if (days < 0) return "overdue";
  if (days <= atRiskDays) return "urgent";
  if (days <= 21) return "soon";
  return "ok";
}

const TEXT = {
  none: "text-muted-foreground",
  overdue: "text-fail",
  urgent: "text-fail",
  soon: "text-warn",
  ok: "text-foreground",
};
const FILL = {
  none: "bg-muted",
  overdue: "bg-fail",
  urgent: "bg-fail",
  soon: "bg-warn",
  ok: "bg-primary",
};

export function DeadlineGauge({
  days,
  atRiskDays = 7,
  filedLate = false,
  className,
}: {
  days: number | null;
  atRiskDays?: number;
  /** The dispute window had already closed when the customer wrote in. */
  filedLate?: boolean;
  className?: string;
}) {
  if (filedLate) {
    return (
      <div
        className={cn("min-w-[88px]", className)}
        title="Raised after the dispute window had closed, so there is no filing deadline to meet."
      >
        <div className="text-sm font-medium text-muted-foreground">Filed after window</div>
        <div className="mt-1 h-1 w-full rounded-full bg-muted" aria-hidden />
      </div>
    );
  }
  const u = urgency(days, atRiskDays);
  const pct = days === null ? 0 : Math.max(0, Math.min(1, days / RUNWAY_DAYS)) * 100;
  return (
    <div className={cn("min-w-[88px]", className)}>
      <div className={cn("text-sm font-medium tabular-nums", TEXT[u])}>{daysLabel(days)}</div>
      <div className="mt-1 h-1 w-full rounded-full bg-muted" aria-hidden>
        <div
          className={cn("h-full rounded-full", FILL[u])}
          style={{ width: u === "overdue" ? "100%" : `${pct}%` }}
        />
      </div>
    </div>
  );
}
