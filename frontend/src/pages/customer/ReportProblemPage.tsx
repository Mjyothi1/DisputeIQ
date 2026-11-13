import { CheckCircle2, Loader2 } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "@/api/client";
import { usePortalCategories, usePortalTxns, useReportProblem } from "@/api/portalHooks";
import type { PortalComplaint } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Label, Select, Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate, formatInr } from "@/lib/format";
import { cn } from "@/lib/utils";

export function ReportProblemPage() {
  const [params] = useSearchParams();
  const txns = usePortalTxns();
  const cats = usePortalCategories();
  const report = useReportProblem();
  const [txnId, setTxnId] = useState<number | null>(params.get("txn") ? Number(params.get("txn")) : null);
  const [category, setCategory] = useState("");
  const [text, setText] = useState("");
  const [done, setDone] = useState<PortalComplaint | null>(null);
  const [error, setError] = useState<string | null>(null);
  const ready = txnId !== null && category !== "" && text.trim().length >= 5;

  if (done) {
    return (
      <div className="mx-auto max-w-xl rounded-panel border border-border bg-surface p-6 text-center" role="status">
        <CheckCircle2 className="mx-auto mb-3 h-10 w-10 text-pass" aria-hidden />
        <h1 className="font-serif text-2xl font-semibold">Complaint submitted</h1>
        <p className="mt-2 text-sm text-muted-foreground">Your reference number is</p>
        <p className="mt-1 font-mono text-xl font-semibold" data-testid="reference">{done.reference}</p>
        <p className="mt-3 text-sm text-muted-foreground">
          We are checking your transaction now. You can follow the progress on the complaint page.
        </p>
        <div className="mt-5 flex justify-center gap-3">
          <Button asChild><Link to={`/customer/complaints/${done.id}`}>Track this complaint</Link></Button>
          <Button asChild variant="outline"><Link to="/customer">Back to home</Link></Button>
        </div>
      </div>
    );
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!ready || txnId === null) return;
    setError(null);
    try {
      setDone(await report.mutateAsync({ transaction_id: txnId, category, description: text.trim() }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit. Please try again.");
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="font-serif text-2xl font-semibold">Report a problem</h1>
      <p className="mb-5 text-sm text-muted-foreground">Tell us which transaction is wrong and what happened.</p>
      <form onSubmit={submit} className="space-y-6 rounded-panel border border-border bg-surface p-5">
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">1. Which transaction? <span className="text-fail">*</span></legend>
          {txns.isLoading ? (
            <Skeleton className="h-24" />
          ) : !txns.data?.length ? (
            <p className="text-sm text-muted-foreground">There are no transactions on your cards to report.</p>
          ) : (
            <ul className="max-h-72 divide-y divide-border overflow-y-auto rounded-control border border-border" role="radiogroup" aria-label="Your transactions">
              {txns.data.map((t) => {
                const on = txnId === t.id;
                return (
                  <li key={t.id}>
                    <label className={cn("flex cursor-pointer items-center gap-3 px-3 py-2.5", on && "bg-primary/5")}>
                      <input type="radio" name="txn" className="accent-[hsl(var(--primary))]" checked={on} onChange={() => setTxnId(t.id)} />
                      <span className="flex-1">
                        <span className="font-medium">{t.merchant_name}</span>
                        <span className="block text-xs text-muted-foreground">{formatDate(t.txn_time)} · •••• {t.card_last4}</span>
                      </span>
                      <span className="tabular-nums">{formatInr(t.amount)}</span>
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
        </fieldset>

        <div>
          <Label htmlFor="category">2. What went wrong? <span className="text-fail">*</span></Label>
          <Select id="category" value={category} onChange={(e) => setCategory(e.target.value)} required>
            <option value="">Choose one…</option>
            {Object.entries(cats.data ?? {}).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </Select>
        </div>

        <div>
          <Label htmlFor="desc">3. Describe it in your own words <span className="text-fail">*</span></Label>
          <Textarea
            id="desc"
            rows={5}
            maxLength={3000}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="e.g. I was charged twice for one order. / Mere card se do baar paise kat gaye."
          />
          <p className="mt-1 text-xs text-muted-foreground">English or Hinglish is fine. Never share your full card number, CVV or OTP.</p>
        </div>

        {error && <p role="alert" className="text-sm text-fail">{error}</p>}
        <Button type="submit" disabled={!ready || report.isPending}>
          {report.isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
          Submit complaint
        </Button>
      </form>
    </div>
  );
}
