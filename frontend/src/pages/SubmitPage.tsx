import { CheckCircle2, Loader2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "@/api/client";
import { useRecentTxns } from "@/api/hooks";
import type { Channel, Customer, RecentTxn } from "@/api/types";
import { CustomerCombobox } from "@/components/CustomerCombobox";
import { Button } from "@/components/ui/button";
import { Label, Select, Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { caseRef, formatDate, formatInr } from "@/lib/format";
import { cn } from "@/lib/utils";

const money = (t: RecentTxn) => formatInr(t.amount).replace(/\.00$/, "");

export const TEMPLATES: { label: string; build: (t: RecentTxn) => string }[] = [
  {
    label: "Charged twice",
    build: (t) =>
      `I was charged twice by ${t.merchant_name} on ${formatDate(t.txn_time)} for ${money(t)}. I only bought once. Please reverse the extra charge.`,
  },
  {
    label: "Not my transaction",
    build: (t) =>
      `I did not make the ${money(t)} payment to ${t.merchant_name} on ${formatDate(t.txn_time)}. My card was with me. I did not share any OTP.`,
  },
  {
    label: "Never received it",
    build: (t) =>
      `I paid ${money(t)} to ${t.merchant_name} on ${formatDate(t.txn_time)} but I never received what I ordered. The merchant is not replying.`,
  },
];

export function SubmitPage() {
  const nav = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [selectedTxn, setSelectedTxn] = useState<number | null>(null);
  const [channel, setChannel] = useState<Channel>("FORM");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const customerId = customer?.id ?? null;
  const txns = useRecentTxns(customerId);
  const tooShort = text.trim().length < 5;

  function chooseCustomer(c: Customer | null) {
    setCustomer(c);
    setSelectedTxn(null); // never carry a transaction over to a different customer
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy || customerId === null || tooShort) return;
    setBusy(true);
    try {
      const res = await api.submit({ customer_id: customerId, channel, raw_text: text.trim() }, true);
      void queryClient.invalidateQueries({ queryKey: ["queue"] });
      void queryClient.invalidateQueries({ queryKey: ["metrics"] });
      void queryClient.invalidateQueries({ queryKey: ["case", res.dispute_id] });
      toast.success(
        `Complaint ${caseRef(res.dispute_id)} processed: ${res.status.replace(/_/g, " ").toLowerCase()}. The case page shows which engine analysed it.`,
      );
      nav(`/cases/${res.dispute_id}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not submit the complaint.");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="font-serif text-2xl font-semibold">Submit a complaint</h1>
      <p className="mb-5 text-sm text-muted-foreground">
        Simulates a customer writing in (in production this arrives from email, chat or the banking
        app). The agent finds the transaction from the complaint text itself; picking one below only
        helps you write a realistic complaint.
      </p>
      <form onSubmit={onSubmit} className="space-y-6 rounded-panel border border-border bg-surface p-5">
        <section>
          <Label htmlFor="cust-search">
            1. Customer <span className="text-fail">*</span>
          </Label>
          <CustomerCombobox value={customer} onChange={chooseCustomer} />
        </section>

        {customer && (
          <section aria-labelledby="txn-heading">
            <div className="mb-1.5 flex items-baseline justify-between gap-2">
              <h2 id="txn-heading" className="text-sm font-medium">
                2. Transactions for {customer.name}
              </h2>
              {txns.data && (
                <span className="text-xs text-muted-foreground">
                  {txns.data.length} most recent, newest first
                </span>
              )}
            </div>
            {txns.isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-10" />
                <Skeleton className="h-10" />
              </div>
            ) : txns.isError ? (
              <p className="text-sm text-fail">Could not load transactions: {txns.error.message}</p>
            ) : !txns.data?.length ? (
              <p className="rounded-control bg-muted/40 p-3 text-sm text-muted-foreground">
                This customer has no card transactions on file.
              </p>
            ) : (
              <ul className="max-h-72 divide-y divide-border overflow-y-auto rounded-control border border-border" aria-label="Customer transactions">
                {txns.data.map((t) => {
                  const on = selectedTxn === t.id;
                  return (
                    <li key={t.id} className={cn("px-3 py-2", on && "bg-primary/5")}>
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <button
                          type="button"
                          aria-pressed={on}
                          className="flex min-w-0 items-center gap-2 text-left text-sm"
                          onClick={() => setSelectedTxn(on ? null : t.id)}
                        >
                          {on ? (
                            <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" aria-hidden />
                          ) : (
                            <span className="h-4 w-4 shrink-0 rounded-full border border-border" aria-hidden />
                          )}
                          <span className="truncate font-medium">{t.merchant_name}</span>
                          <span className="tabular-nums">{money(t)}</span>
                          <span className="text-muted-foreground">{formatDate(t.txn_time)}</span>
                          <span className="font-mono text-xs text-muted-foreground">
                            txn #{t.id} · •••• {t.card_last4}
                          </span>
                        </button>
                        {on && (
                          <span className="flex flex-wrap gap-2 text-xs">
                            {TEMPLATES.map((tpl) => (
                              <button
                                key={tpl.label}
                                type="button"
                                className="rounded-control border border-border px-2 py-0.5 text-primary hover:bg-accent"
                                onClick={() => setText(tpl.build(t))}
                              >
                                {tpl.label}
                              </button>
                            ))}
                          </span>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <p className="mt-1 text-xs text-muted-foreground">
              Select a transaction to use a complaint template, or write your own below.
            </p>
          </section>
        )}

        <section>
          <Label htmlFor="complaint">
            3. Complaint <span className="text-fail">*</span>
          </Label>
          <Textarea
            id="complaint"
            rows={6}
            maxLength={5000}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Describe what went wrong, in your own words (English or Hinglish)."
            required
          />
          <div className="mt-1 flex justify-between text-xs text-muted-foreground">
            <span>PII such as card numbers, phone numbers and OTPs is masked before any AI call.</span>
            <span>{text.length}/5000</span>
          </div>
        </section>

        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <Label htmlFor="channel">Channel</Label>
            <Select id="channel" className="w-40" value={channel} onChange={(e) => setChannel(e.target.value as Channel)}>
              <option value="FORM">Web form</option>
              <option value="EMAIL">Email</option>
              <option value="CHAT">Chat</option>
            </Select>
          </div>
          <div className="text-right">
            {customerId === null && <p className="mb-1 text-xs text-muted-foreground">Choose a customer first.</p>}
            <Button type="submit" disabled={busy || customerId === null || tooShort}>
              {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
              {busy ? "Agent is analysing… (can take ~10 s)" : "Submit complaint"}
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}
