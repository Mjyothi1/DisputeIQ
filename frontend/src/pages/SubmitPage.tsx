import { Loader2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "@/api/client";
import { useCustomers, useRecentTxns } from "@/api/hooks";
import type { Channel, RecentTxn } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { formatDate, formatInr } from "@/lib/format";

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
  const [search, setSearch] = useState("");
  const customers = useCustomers(search);
  const [customerId, setCustomerId] = useState<number | null>(null);
  const [channel, setChannel] = useState<Channel>("FORM");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const txns = useRecentTxns(customerId);
  const tooShort = text.trim().length < 5;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (customerId === null || tooShort) return;
    setBusy(true);
    try {
      const res = await api.submit({ customer_id: customerId, channel, raw_text: text.trim() });
      toast.success("Complaint received. The agent is processing it.");
      nav(`/cases/${res.dispute_id}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Could not submit the complaint.");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="font-serif text-2xl font-semibold">Submit a complaint</h1>
      <p className="mb-5 text-sm text-muted-foreground">
        Simulates a customer writing in. In production this arrives from email, chat or the banking
        app.
      </p>
      <form
        onSubmit={onSubmit}
        className="space-y-5 rounded-panel border border-border bg-surface p-5"
      >
        <div>
          <Label htmlFor="cust-search">Customer</Label>
          <Input
            id="cust-search"
            placeholder="Search by name"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <Select
            aria-label="Select customer"
            className="mt-2"
            size={5}
            value={customerId ?? ""}
            onChange={(e) => setCustomerId(Number(e.target.value))}
          >
            {(customers.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} · {c.cards.join(", ")}
              </option>
            ))}
          </Select>
          {customers.isError && <p className="mt-1 text-sm text-fail">{customers.error.message}</p>}
        </div>

        <div>
          <Label htmlFor="channel">Channel</Label>
          <Select
            id="channel"
            className="w-40"
            value={channel}
            onChange={(e) => setChannel(e.target.value as Channel)}
          >
            <option value="FORM">Web form</option>
            <option value="EMAIL">Email</option>
            <option value="CHAT">Chat</option>
          </Select>
        </div>

        <div>
          <Label htmlFor="complaint">Complaint</Label>
          <Textarea
            id="complaint"
            rows={6}
            maxLength={5000}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Describe what went wrong, in your own words."
          />
          {customerId !== null && txns.data && txns.data.length > 0 && (
            <details className="mt-2 text-sm">
              <summary className="cursor-pointer text-muted-foreground">
                Fill in from a recent transaction
              </summary>
              <ul className="mt-2 space-y-1.5">
                {txns.data.slice(0, 5).map((t) => (
                  <li key={t.id} className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="min-w-[14rem]">
                      {t.merchant_name} · {money(t)} · {formatDate(t.txn_time)}
                    </span>
                    {TEMPLATES.map((tpl) => (
                      <button
                        key={tpl.label}
                        type="button"
                        className="text-primary hover:underline"
                        onClick={() => setText(tpl.build(t))}
                      >
                        {tpl.label}
                      </button>
                    ))}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>

        <Button type="submit" disabled={busy || customerId === null || tooShort}>
          {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />} Submit complaint
        </Button>
      </form>
    </div>
  );
}
