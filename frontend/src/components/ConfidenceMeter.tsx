import { cn } from "@/lib/utils";

interface Props {
  value: number | null;
  /** Auto-resolve threshold; drawn as a tick so the analyst sees why a case was routed to them. */
  threshold: number;
  className?: string;
  showValue?: boolean;
}

export function bandFor(value: number, threshold: number): "pass" | "warn" | "fail" {
  if (value >= threshold) return "pass";
  if (value >= 0.6) return "warn";
  return "fail";
}

const FILL = { pass: "bg-pass", warn: "bg-warn", fail: "bg-fail" } as const;

export function ConfidenceMeter({ value, threshold, className, showValue = true }: Props) {
  if (value === null) return <span className="text-sm text-muted-foreground">-</span>;
  const band = bandFor(value, threshold);
  const pct = Math.round(value * 100);
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div
        role="meter"
        aria-label="Confidence"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-valuetext={`${pct}% (auto-resolve at ${Math.round(threshold * 100)}%)`}
        className="relative h-1.5 w-20 shrink-0 rounded-full bg-muted"
        title={`Auto-resolve threshold: ${Math.round(threshold * 100)}%`}
      >
        <div className={cn("h-full rounded-full", FILL[band])} style={{ width: `${pct}%` }} />
        <div
          className="absolute -top-0.5 h-2.5 w-px bg-foreground/70"
          style={{ left: `${threshold * 100}%` }}
          aria-hidden
        />
      </div>
      {showValue && <span className="w-9 text-sm tabular-nums">{value.toFixed(2)}</span>}
    </div>
  );
}
