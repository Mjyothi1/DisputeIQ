import { ArrowLeft, CheckCircle2, Circle } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { usePortalComplaint } from "@/api/portalHooks";
import { StatusPill } from "@/components/customer/StatusPill";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate, formatDateTime, formatInr } from "@/lib/format";

export function ComplaintDetailPage() {
  const id = Number(useParams().id);
  const q = usePortalComplaint(id);
  if (q.isLoading) return <Skeleton className="h-64" />;
  if (q.isError || !q.data)
    return (
      <div className="rounded-panel border border-border bg-surface p-6 text-center">
        <p className="font-medium">We could not find this complaint.</p>
        <Link to="/customer" className="text-sm text-primary hover:underline">Back to home</Link>
      </div>
    );
  const c = q.data;
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <Link to="/customer" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" aria-hidden /> All complaints
      </Link>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-serif text-2xl font-semibold">{c.reference}</h1>
          <p className="text-sm text-muted-foreground">
            {c.category ?? "Complaint"} · {c.merchant ?? "Transaction"} {c.amount && formatInr(c.amount)}
            {c.transaction_date && ` · ${formatDate(c.transaction_date)}`}
          </p>
        </div>
        <StatusPill status={c.status} label={c.status_label} />
      </div>

      <div className="rounded-panel border border-border bg-surface p-4" role="status" data-testid="latest-update">
        <p className="text-sm font-medium">Latest update</p>
        <p className="mt-1 text-sm">{c.message}</p>
      </div>

      <div className="grid gap-5 md:grid-cols-[1fr_260px]">
        <div className="space-y-5">
          <section className="rounded-panel border border-border bg-surface p-4">
            <h2 className="mb-2 text-sm font-semibold">What you told us</h2>
            <p className="whitespace-pre-wrap text-sm">{c.description}</p>
          </section>
          {c.letter && (
            <section className="rounded-panel border border-border bg-surface p-4">
              <h2 className="mb-2 text-sm font-semibold">Letter from the bank</h2>
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{c.letter}</p>
            </section>
          )}
        </div>
        <section className="rounded-panel border border-border bg-surface p-4" aria-label="Progress">
          <h2 className="mb-3 text-sm font-semibold">Progress</h2>
          <ol className="space-y-3">
            {c.timeline.map((t) => (
              <li key={t.label} className="flex gap-2 text-sm">
                {t.at ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-pass" aria-hidden /> : <Circle className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />}
                <span>
                  {t.label}
                  {t.at && <span className="block text-xs text-muted-foreground">{formatDateTime(t.at)}</span>}
                </span>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </div>
  );
}
