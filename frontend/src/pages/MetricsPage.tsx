import { AlertTriangle } from "lucide-react";
import { useMetrics } from "@/api/hooks";
import type { EvalHeadline } from "@/api/types";
import { BarList } from "@/components/BarList";
import { RECOMMENDATION_LABEL } from "@/components/badges";
import { Skeleton } from "@/components/ui/skeleton";
import { humanize } from "@/lib/format";

const pct = (x: number | null | undefined) => (x == null ? "n/a" : `${(x * 100).toFixed(1)}%`);
const inr = (x: number | null | undefined, d = 2) => (x == null ? "n/a" : `₹${x.toFixed(d)}`);

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="font-serif text-2xl font-semibold tabular-nums">{value}</dd>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function Panel({
  title,
  children,
  note,
}: {
  title: string;
  children: React.ReactNode;
  note?: string;
}) {
  return (
    <section className="rounded-panel border border-border bg-surface p-5">
      <h2 className="font-serif text-lg font-semibold">{title}</h2>
      {note && <p className="mb-3 text-sm text-muted-foreground">{note}</p>}
      <div className={note ? "" : "mt-3"}>{children}</div>
    </section>
  );
}

export function MetricsPage() {
  const { data: m, isLoading, error } = useMetrics();
  if (error) {
    return (
      <div role="alert" className="rounded-panel border border-fail/40 bg-fail/10 p-4 text-sm">
        <p className="flex items-center gap-2 font-medium text-fail">
          <AlertTriangle className="h-4 w-4" aria-hidden /> Could not load metrics
        </p>
        <p>{error.message}</p>
      </div>
    );
  }
  if (isLoading || !m) {
    return (
      <div className="space-y-4" aria-busy>
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  const ev: EvalHeadline | null = m.evaluation;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-serif text-2xl font-semibold">Metrics</h1>
        <p className="text-sm text-muted-foreground">
          Live figures from the case database, and the latest evaluation on held-out cases.
        </p>
      </div>

      {m.llm_provider_note && (
        <p className="rounded-control bg-warn/10 p-3 text-sm text-warn" role="note">
          {m.llm_provider_note}
        </p>
      )}

      <Panel title="Operations">
        <dl className="grid grid-cols-2 gap-x-8 gap-y-5 sm:grid-cols-3 lg:grid-cols-6">
          <Stat
            label="Cases processed"
            value={`${m.cases_processed}`}
            hint={`of ${m.cases_total} received`}
          />
          <Stat
            label="Auto-resolution rate"
            value={pct(m.auto_resolution_rate)}
            hint={`${m.auto_resolved} cases`}
          />
          <Stat
            label="Avg processing time"
            value={m.avg_processing_time_s == null ? "n/a" : `${m.avg_processing_time_s}s`}
          />
          <Stat
            label="Avg cost per case"
            value={inr(m.avg_cost_inr, 3)}
            hint={`${inr(m.total_cost_inr)} total`}
          />
          <Stat
            label="Open past deadline"
            value={`${m.deadline_violations}`}
            hint={`${m.deadline_at_risk} due within 7 days`}
          />
          <Stat
            label="Analyst override rate"
            value={pct(m.override_rate)}
            hint={`${m.reviewed} reviewed`}
          />
        </dl>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Cases by status">
          <BarList data={m.by_status} label={humanize} />
        </Panel>
        <Panel title="Cases by reason code">
          <BarList data={m.by_reason_code} label={humanize} />
        </Panel>
        <Panel title="Agent recommendations">
          <BarList
            data={m.by_recommendation}
            label={(k) =>
              RECOMMENDATION_LABEL[k as keyof typeof RECOMMENDATION_LABEL] ?? humanize(k)
            }
          />
        </Panel>
        <Panel title="Flags raised">
          <dl className="grid grid-cols-2 gap-5">
            <Stat
              label="Possible friendly fraud"
              value={`${m.friendly_fraud_flagged}`}
              hint="Strongly authenticated, sent to a person"
            />
            <Stat
              label="Prompt injection detected"
              value={`${m.injection_flagged}`}
              hint="Text ignored, flagged to analyst"
            />
          </dl>
        </Panel>
      </div>

      <Panel
        title="Evaluation on held-out cases"
        note={
          ev
            ? `${ev.n_cases} test cases, ${ev.provider} provider (${ev.model}), run ${ev.generated_at}.`
            : undefined
        }
      >
        {ev ? (
          <div className="space-y-4">
            <dl className="grid grid-cols-2 gap-x-8 gap-y-5 sm:grid-cols-3 lg:grid-cols-4">
              <Stat label="Reason-code accuracy" value={pct(ev.reason_code_accuracy)} />
              <Stat label="Decision accuracy" value={pct(ev.decision_accuracy)} />
              <Stat
                label="Auto-resolution accuracy"
                value={pct(ev.auto_resolution_accuracy)}
                hint={`${ev.auto_resolved} auto-resolved, ${ev.unsafe_auto_resolutions} unsafe`}
              />
              <Stat
                label="Deadline violations"
                value={`${ev.deadline_violations}`}
                hint="Target 0"
              />
              <Stat
                label="Injection handled"
                value={pct(ev.injection_handled)}
                hint={`of ${ev.injection_cases} cases`}
              />
              <Stat label="Avg latency" value={`${ev.avg_latency_s}s`} />
              <Stat label="Avg cost" value={inr(ev.avg_cost_inr, 3)} />
              <Stat label="Pipeline errors" value={`${ev.pipeline_errors}`} />
            </dl>
            <p className="text-sm text-muted-foreground">{ev.note}</p>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            No evaluation has been run yet. From the backend folder run{" "}
            <code>python -m eval.run_eval</code>.
          </p>
        )}
      </Panel>
    </div>
  );
}
