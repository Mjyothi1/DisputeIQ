import { AlertTriangle, ArrowLeft, RefreshCw, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "@/api/client";
import { useCase, useConfig, useReopen, useRerun } from "@/api/hooks";
import type { CaseDetail } from "@/api/types";
import { AuditTimeline } from "@/components/AuditTimeline";
import { RecommendationBadge, StatusBadge } from "@/components/badges";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { DeadlineGauge } from "@/components/DeadlineGauge";
import { DraftEditor } from "@/components/DraftEditor";
import { EvidenceList } from "@/components/EvidenceList";
import { ReviewPanel } from "@/components/ReviewPanel";
import { TransactionPanel } from "@/components/TransactionPanel";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { caseRef, formatDate, formatInr, humanize } from "@/lib/format";

function Section({
  title,
  children,
  aside,
}: {
  title: string;
  children: React.ReactNode;
  aside?: React.ReactNode;
}) {
  return (
    <section className="border-t border-border py-5 first:border-t-0 first:pt-0">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="font-serif text-lg font-semibold">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function CaseDetailPage() {
  const id = Number(useParams().id);
  const { data, isLoading, error } = useCase(id);

  if (!Number.isInteger(id)) return <Message title="Invalid case number" />;
  if (isLoading) {
    return (
      <div className="space-y-3" aria-busy>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (error || !data) {
    const notFound = error instanceof ApiError && error.status === 404;
    return (
      <Message
        title={notFound ? "Case not found" : "Could not load this case"}
        body={error?.message}
      />
    );
  }
  return <Body detail={data} key={`${data.id}-${data.decision?.id ?? 0}-${data.reviews.length}`} />;
}

function Message({ title, body }: { title: string; body?: string }) {
  return (
    <div className="rounded-panel border border-border bg-surface p-8 text-center" role="alert">
      <p className="font-medium">{title}</p>
      {body && <p className="mt-1 text-sm text-muted-foreground">{body}</p>}
      <Button asChild variant="outline" className="mt-4">
        <Link to="/">Back to queue</Link>
      </Button>
    </div>
  );
}

function Body({ detail }: { detail: CaseDetail }) {
  const config = useConfig();
  const threshold = config.data?.auto_confidence ?? 0.85;
  const atRisk = config.data?.at_risk_days ?? 7;
  const rerun = useRerun(detail.id);
  const reopen = useReopen(detail.id);
  const toast = useToast();
  const dec = detail.decision;
  const finished = detail.reviews[detail.reviews.length - 1];
  const origLetter = dec?.drafted_customer_letter ?? "";
  const origFiling = dec?.drafted_chargeback_filing ?? "";
  // After a review, show what was actually approved (the analyst's edits, if any).
  const startLetter = finished?.edited_letter ?? origLetter;
  const startFiling = finished?.edited_filing ?? origFiling;
  const [letter, setLetter] = useState(startLetter);
  const [filing, setFiling] = useState(startFiling);
  const locked = !detail.can_review;
  const f = detail.extracted_fields;
  const working = detail.status === "NEW" || detail.status === "PROCESSING";

  return (
    <div>
      <Link
        to="/"
        className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden /> Queue
      </Link>
      <header className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex flex-wrap items-center gap-3 font-serif text-2xl font-semibold">
            {caseRef(detail.id)} <StatusBadge status={detail.status} />
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {detail.customer_name} ({humanize(detail.customer_segment)}) · via{" "}
            {humanize(detail.channel)} · received {formatDate(detail.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-6">
          <div>
            <div className="mb-1 text-xs text-muted-foreground">Confidence</div>
            <ConfidenceMeter value={detail.confidence} threshold={threshold} />
          </div>
          <div>
            <div className="mb-1 text-xs text-muted-foreground">
              Deadline {formatDate(detail.deadline_at)}
            </div>
            <DeadlineGauge
              days={detail.days_to_deadline}
              atRiskDays={atRisk}
              filedLate={detail.filed_late}
            />
          </div>
          {detail.status === "AUTO_RESOLVED" && (
            <Button
              variant="outline"
              size="sm"
              disabled={reopen.isPending}
              onClick={() => {
                const reason = window.prompt(
                  "Reopen this auto-resolved case for human review. Reason (min 10 characters):",
                );
                if (!reason || reason.trim().length < 10) return;
                reopen.mutate(reason.trim(), {
                  onSuccess: () => toast.success("Case reopened for human review."),
                  onError: (e) => toast.error(e.message),
                });
              }}
            >
              Reopen for review
            </Button>
          )}
          {!working && (detail.status === "NEW" || detail.status === "NEEDS_HUMAN") && (
              <Button
                variant="outline"
                size="sm"
                disabled={rerun.isPending}
                onClick={() =>
                  rerun.mutate(undefined, {
                    onSuccess: () => toast.success("Re-running the agent."),
                    onError: (e) => toast.error(e.message),
                  })
                }
              >
                <RefreshCw className="h-3.5 w-3.5" aria-hidden /> Re-run agent
              </Button>
            )}
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0">
          {f?.injection_suspected && (
            <div
              role="alert"
              className="mb-5 flex gap-3 rounded-panel border border-warn/40 bg-warn/10 p-3 text-sm"
            >
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden />
              <div>
                <p className="font-medium">Possible prompt injection in the complaint</p>
                <p className="text-muted-foreground">
                  The complaint contains text that tries to instruct the system. It was ignored: the
                  decision comes from the rules and evidence only.
                </p>
              </div>
            </div>
          )}

          <Section title="Complaint">
            <blockquote className="whitespace-pre-wrap break-words rounded-control bg-muted/60 p-3 text-sm leading-relaxed">
              {detail.complaint_masked ?? "-"}
            </blockquote>
            <p className="mt-1 text-xs text-muted-foreground">
              Personal data is masked before the agent reads it.
            </p>
            {f && (
              <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm sm:grid-cols-[auto_1fr_auto_1fr]">
                <dt className="text-muted-foreground">Claim type</dt>
                <dd>{humanize(f.claim_type)}</dd>
                <dt className="text-muted-foreground">Merchant mentioned</dt>
                <dd>{f.merchant_hint ?? "-"}</dd>
                <dt className="text-muted-foreground">Amount claimed</dt>
                <dd>{f.claimed_amount != null ? formatInr(f.claimed_amount) : "-"}</dd>
                <dt className="text-muted-foreground">Amount expected</dt>
                <dd>{f.expected_amount != null ? formatInr(f.expected_amount) : "-"}</dd>
              </dl>
            )}
          </Section>

          <Section title="Matched transaction">
            <TransactionPanel txn={detail.transaction} />
          </Section>

          <Section title="Evidence checks">
            <EvidenceList evidence={detail.evidence} />
          </Section>

          <Section
            title="Recommendation"
            aside={dec && <RecommendationBadge value={dec.recommendation} />}
          >
            {dec ? (
              <div className="space-y-3">
                <p className="text-sm">
                  <span className="text-muted-foreground">Reason code: </span>
                  <strong>{humanize(detail.reason_code)}</strong>
                </p>
                {dec.friendly_fraud_flag && (
                  <p className="flex items-center gap-2 text-sm text-warn">
                    <AlertTriangle className="h-4 w-4" aria-hidden /> Possible friendly fraud: the
                    transaction was strongly authenticated, so a person must decide.
                  </p>
                )}
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{dec.rationale}</p>
                {dec.model && (
                  <p className="text-xs text-muted-foreground">
                    Analysis model: <span className="font-mono">{dec.model}</span>
                    {dec.model.startsWith("mock")
                      ? " (offline rule-based fixture — not Gemini)"
                      : dec.model.startsWith("gemini")
                        ? " (live Google Gemini)"
                        : ""}
                    {dec.prompt_version ? ` · prompt ${dec.prompt_version}` : ""}
                  </p>
                )}
                {detail.route_reasons.length > 0 && (
                  <div className="rounded-control bg-muted/60 p-3 text-sm">
                    <p className="mb-1 font-medium">Why this needs a person</p>
                    <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">
                      {detail.route_reasons.map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                {working
                  ? "The agent is still working on this case."
                  : "No recommendation was produced."}
              </p>
            )}
          </Section>

          {dec && (
            <Section title="Drafts">
              <div className="space-y-5">
                <DraftEditor
                  id="letter"
                  title="Letter to the customer"
                  original={origLetter}
                  value={letter}
                  onChange={setLetter}
                  readOnly={locked}
                />
                {(origFiling || startFiling) && (
                  <DraftEditor
                    id="filing"
                    title="Chargeback filing"
                    original={origFiling}
                    value={filing}
                    onChange={setFiling}
                    readOnly={locked}
                  />
                )}
              </div>
            </Section>
          )}

          <Section title="Audit trail">
            <AuditTimeline events={detail.audit} />
          </Section>
        </div>

        <ReviewPanel
          detail={detail}
          letter={letter}
          filing={filing}
          letterChanged={letter !== origLetter}
          filingChanged={filing !== origFiling}
        />
      </div>
    </div>
  );
}
