import { Bot, UserRound, Wrench } from "lucide-react";
import { useState } from "react";
import type { AuditEvent } from "@/api/types";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const STEP_LABEL: Record<string, string> = {
  mask_pii: "Mask personal data",
  intake_extract: "Extract claim details",
  match_transaction: "Match transaction",
  run_evidence_checks: "Run evidence checks",
  classify_reason_code: "Classify reason code",
  eligibility_engine: "Check eligibility and deadline",
  recommend: "Recommend action",
  draft_documents: "Draft documents",
  route: "Route case",
  pipeline_complete: "Pipeline complete",
  pipeline_error: "Pipeline error",
  human_approve: "Analyst approved",
  human_edit: "Analyst edited and approved",
  human_override: "Analyst overrode",
  human_reject: "Analyst rejected",
};

const ACTOR = {
  TOOL: { Icon: Wrench, cls: "bg-muted text-muted-foreground", label: "Rules and tools" },
  AGENT: { Icon: Bot, cls: "bg-primary/15 text-primary", label: "AI agent" },
  HUMAN: { Icon: UserRound, cls: "bg-warn/15 text-warn", label: "Analyst" },
} as const;

/** Split into pipeline runs (each starts at mask_pii); human events attach to the latest run. */
export function groupRuns(events: AuditEvent[]): AuditEvent[][] {
  const runs: AuditEvent[][] = [];
  for (const e of events) {
    if (e.step === "mask_pii" || runs.length === 0) runs.push([]);
    runs[runs.length - 1].push(e);
  }
  return runs;
}

function Event({ e }: { e: AuditEvent }) {
  const [open, setOpen] = useState(false);
  const { Icon, cls, label } = ACTOR[e.actor];
  const text = e.output_summary ?? "";
  const long = text.length > 160;
  const cost = e.cost_inr !== null ? Number(e.cost_inr) : null;
  return (
    <li className="relative pb-5 pl-9 last:pb-0">
      <span
        className="absolute left-[13px] top-7 -bottom-0 w-px bg-border last:hidden"
        aria-hidden
      />
      <span
        className={cn(
          "absolute left-0 top-0 flex h-7 w-7 items-center justify-center rounded-full",
          cls,
        )}
        title={label}
      >
        <Icon className="h-3.5 w-3.5" aria-label={label} role="img" />
      </span>
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="text-sm font-medium">{STEP_LABEL[e.step] ?? e.step}</span>
        <time className="text-xs text-muted-foreground" dateTime={e.timestamp}>
          {formatDateTime(e.timestamp)}
        </time>
      </div>
      {text && (
        <p className="mt-0.5 break-words text-sm text-muted-foreground">
          {long && !open ? `${text.slice(0, 160)}…` : text}
          {long && (
            <button
              className="ml-1 text-primary underline-offset-2 hover:underline"
              onClick={() => setOpen(!open)}
            >
              {open ? "Show less" : "Show more"}
            </button>
          )}
        </p>
      )}
      {e.model && (
        <p className="mt-1 text-xs text-muted-foreground">
          {e.model} · {e.tokens_in ?? 0} in / {e.tokens_out ?? 0} out tokens
          {cost !== null && ` · INR ${cost.toFixed(2)}`}
          {e.latency_ms !== null && ` · ${e.latency_ms} ms`}
          {e.prompt_version && ` · prompt ${e.prompt_version}`}
        </p>
      )}
    </li>
  );
}

export function AuditTimeline({ events }: { events: AuditEvent[] }) {
  if (events.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">The agent has not processed this case yet.</p>
    );
  }
  const runs = groupRuns(events);
  return (
    <div className="space-y-6">
      {runs.map((run, i) => (
        <div key={run[0].id}>
          {runs.length > 1 && (
            <h3 className="mb-3 text-sm font-medium text-muted-foreground">
              {i === runs.length - 1 ? "Latest run" : `Earlier run ${i + 1}`}
            </h3>
          )}
          <ol>
            {run.map((e) => (
              <Event key={e.id} e={e} />
            ))}
          </ol>
        </div>
      ))}
    </div>
  );
}
