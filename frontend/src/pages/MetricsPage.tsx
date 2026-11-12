import { AlertTriangle, ArrowRight } from "lucide-react";
import { Link } from "react-router-dom";
import { useMetrics } from "@/api/hooks";
import type { EvalHeadline } from "@/api/types";
import { BarList } from "@/components/BarList";
import { RECOMMENDATION_LABEL, RecommendationBadge } from "@/components/badges";
import { Skeleton } from "@/components/ui/skeleton";
import { humanize } from "@/lib/format";

const pct = (x: number | null | undefined) => (x == null ? "n/a" : `${(x * 100).toFixed(1)}%`);
const inr = (x: number | null | undefined, d = 2) => (x == null ? "n/a" : `₹${x.toFixed(d)}`);

function Stat({
  label,
  value,
  hint,
  to,
}: {
  label: string;
  value: string;
  hint?: string;
  to?: string;
}) {
  const content = (
    <div>
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="font-serif text-2xl font-semibold tabular-nums">{value}</dd>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      {to && (
        <span className="mt-1 inline-flex items-center gap-1 text-xs text-primary group-hover:underline">
          View cases <ArrowRight className="h-3 w-3" />
        </span>
      )}
    </div>
  );

  if (to) {
    return (
      <Link to={to} className="group block rounded-control p-1 hover:bg-muted/40 transition-colors">
        {content}
      </Link>
    );
  }
  return content;
}

function Panel({
  title,
  children,
  note,
  action,
}: {
  title: string;
  children: React.ReactNode;
  note?: string;
  action?: React.ReactNode;
}) {
  return (
    <section className="rounded-panel border border-border bg-surface p-5">
      <div className="flex items-center justify-between">
        <h2 className="font-serif text-lg font-semibold">{title}</h2>
        {action}
      </div>
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
  const recentRecs = m.recent_recommendations ?? [];

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
            to="/?preset=auto"
          />
          <Stat
            label="Avg processing time"
            value={m.avg_processing_time_s == null ? "n/a" : `${m.avg_processing_time_s}s`}
          />
          <Stat
            label="Avg cost per case"
            value={inr(m.avg_cost_inr, 3)}
            hint={`${inr(m.total_cost_inr)} total · offline runs are priced at a reference rate (estimate); Gemini free tier bills INR 0`}
          />
          <Stat
            label="Open past deadline"
            value={`${m.deadline_violations}`}
            hint={`${m.deadline_at_risk} due within 7 days`}
            to="/?preset=review"
          />
          <Stat
            label="Analyst override rate"
            value={pct(m.override_rate)}
            hint={`${m.reviewed} reviewed`}
            to="/?preset=closed"
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

        <Panel title="Analysed by">
          <BarList
            data={m.by_model ?? {}}
            label={(k) =>
              k.startsWith("mock")
                ? `${k} (offline rules, not an LLM)`
                : k.startsWith("gemini")
                  ? `${k} (live Gemini)`
                  : k
            }
          />
          <p className="mt-3 text-xs text-muted-foreground">
            Seeded queue cases are processed offline; only live submissions use Gemini.
          </p>
        </Panel>
        <Panel
          title="Agent recommendations"
          action={
            <Link to="/?preset=all" className="text-xs text-primary hover:underline">
              View all in queue &rarr;
            </Link>
          }
        >
          <BarList
            data={m.by_recommendation}
            label={(k) =>
              RECOMMENDATION_LABEL[k as keyof typeof RECOMMENDATION_LABEL] ?? humanize(k)
            }
          />
          {recentRecs.length > 0 && (
            <div className="mt-5 border-t border-border pt-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Active Stored Recommendations
              </h3>
              <div className="divide-y divide-border/60 text-sm">
                {recentRecs.slice(0, 5).map((r) => (
                  <div key={r.dispute_id} className="py-2.5 flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <Link
                          to={`/cases/${r.dispute_id}`}
                          className="font-medium text-primary hover:underline"
                        >
                          {r.case_ref}
                        </Link>
                        {r.customer_name && (
                          <span className="text-xs text-muted-foreground truncate">
                            · {r.customer_name}
                          </span>
                        )}
                        <RecommendationBadge value={r.recommendation} />
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
                        {r.rationale}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <span className="inline-block text-xs font-medium tabular-nums">
                        {(r.confidence * 100).toFixed(0)}% conf
                      </span>
                      <p className="text-[11px] text-muted-foreground">
                        {r.requires_approval ? "Needs review" : "Auto-resolved"}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Panel>

        <Panel
          title="Flags raised"
          action={
            <Link to="/?preset=review" className="text-xs text-primary hover:underline">
              Inspect in queue &rarr;
            </Link>
          }
        >
          <dl className="grid grid-cols-2 gap-5">
            <Stat
              label="Possible friendly fraud"
              value={`${m.friendly_fraud_flagged}`}
              hint="Strongly authenticated, sent to a person"
              to="/?preset=review&q=fraud"
            />
            <Stat
              label="Prompt injection detected"
              value={`${m.injection_flagged}`}
              hint="Text ignored, flagged to analyst"
              to="/?preset=all&q=injection"
            />
            <Stat
              label="Suspicious transactions"
              value={`${m.suspicious_flagged ?? m.friendly_fraud_flagged}`}
              hint="High-risk and unauthorized claims"
              to="/?preset=all&q=fraud"
            />
            {m.by_channel && (
              <Stat
                label="Primary channel"
                value={
                  Object.entries(m.by_channel).sort((a, b) => b[1] - a[1])[0]
                    ? humanize(Object.entries(m.by_channel).sort((a, b) => b[1] - a[1])[0][0])
                    : "Form"
                }
                hint="Customer intake channel"
              />
            )}
          </dl>
          {m.by_channel && Object.keys(m.by_channel).length > 0 && (
            <div className="mt-4 border-t border-border pt-3">
              <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Channel Intake Distribution
              </h4>
              <BarList data={m.by_channel} label={humanize} />
            </div>
          )}
        </Panel>
      </div>

      <Panel
        title="Offline Benchmark Evaluation"
        note={
          ev
            ? `Evaluation dataset: Held-out TEST split (${ev.n_cases} test cases) · Provider: ${ev.provider} (${ev.model}) · Run date: ${ev.generated_at}.`
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
            No offline benchmark evaluation has been run yet. From the backend folder run{" "}
            <code>python -m eval.run_eval</code>.
          </p>
        )}
      </Panel>
    </div>
  );
}
