import { AlertCircle, CreditCard, FilePlus2 } from "lucide-react";
import { Link } from "react-router-dom";
import { usePortalComplaints, usePortalMe, usePortalTxns } from "@/api/portalHooks";
import { StatusPill } from "@/components/customer/StatusPill";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate, formatInr } from "@/lib/format";

export function CustomerDashboard() {
  const me = usePortalMe();
  const txns = usePortalTxns();
  const complaints = usePortalComplaints();
  const first = me.data?.name.replace(/^Demo Customer - /, "").split(" ")[0];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-serif text-2xl font-semibold">{first ? `Welcome, ${first}` : "Welcome"}</h1>
          <p className="text-sm text-muted-foreground">Your cards, recent transactions and complaints.</p>
        </div>
        <Button asChild>
          <Link to="/customer/report">
            <FilePlus2 className="h-4 w-4" aria-hidden /> Report a problem
          </Link>
        </Button>
      </div>

      <section aria-labelledby="cards-h">
        <h2 id="cards-h" className="mb-2 text-sm font-semibold text-muted-foreground">Your cards</h2>
        {me.isLoading ? (
          <Skeleton className="h-16" />
        ) : me.data?.cards.length ? (
          <div className="flex flex-wrap gap-3">
            {me.data.cards.map((c) => (
              <div key={c.last4} className="flex items-center gap-3 rounded-panel border border-border bg-surface px-4 py-3">
                <CreditCard className="h-5 w-5 text-primary" aria-hidden />
                <span className="font-mono text-sm">{c.masked}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No cards are linked to this account yet.</p>
        )}
      </section>

      <section aria-labelledby="complaints-h" className="rounded-panel border border-border bg-surface">
        <h2 id="complaints-h" className="border-b border-border px-4 py-3 font-semibold">My complaints</h2>
        {complaints.isLoading ? (
          <div className="space-y-2 p-4"><Skeleton className="h-10" /><Skeleton className="h-10" /></div>
        ) : complaints.isError ? (
          <p className="flex items-center gap-2 p-4 text-sm text-fail"><AlertCircle className="h-4 w-4" />{complaints.error.message}</p>
        ) : !complaints.data?.length ? (
          <p className="p-4 text-sm text-muted-foreground">You have not reported any problems. Use “Report a problem” if a transaction looks wrong.</p>
        ) : (
          <ul className="divide-y divide-border">
            {complaints.data.map((c) => (
              <li key={c.id}>
                <Link to={`/customer/complaints/${c.id}`} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 hover:bg-accent/50">
                  <div className="min-w-0">
                    <p className="font-medium">
                      {c.reference} <span className="font-normal text-muted-foreground">· {c.merchant ?? "Transaction"} {c.amount && formatInr(c.amount)}</span>
                    </p>
                    <p className="truncate text-sm text-muted-foreground">
                      {c.category ?? "Complaint"} · submitted {formatDate(c.created_at)} · {c.message}
                    </p>
                  </div>
                  <StatusPill status={c.status} label={c.status_label} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="txn-h" className="rounded-panel border border-border bg-surface">
        <h2 id="txn-h" className="border-b border-border px-4 py-3 font-semibold">Recent transactions</h2>
        {txns.isLoading ? (
          <div className="space-y-2 p-4"><Skeleton className="h-10" /><Skeleton className="h-10" /></div>
        ) : !txns.data?.length ? (
          <p className="p-4 text-sm text-muted-foreground">No transactions yet.</p>
        ) : (
          <ul className="max-h-96 divide-y divide-border overflow-y-auto">
            {txns.data.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div>
                  <p className="font-medium">{t.merchant_name}</p>
                  <p className="text-sm text-muted-foreground">
                    {formatDate(t.txn_time)} · card •••• {t.card_last4}
                    {t.has_open_dispute && <span className="ml-2 text-warn">· complaint raised</span>}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="tabular-nums font-medium">{formatInr(t.amount)}</span>
                  <Link to={`/customer/report?txn=${t.id}`} className="text-sm text-primary hover:underline">
                    Report
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
