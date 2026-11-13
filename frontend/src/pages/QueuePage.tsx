import { AlertTriangle, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useConfig, useMetrics, useQueue } from "@/api/hooks";
import type { DisputeSummary, QueueQuery, Status } from "@/api/types";
import { EngineBadge, RecommendationBadge, StatusBadge } from "@/components/badges";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { DeadlineGauge } from "@/components/DeadlineGauge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { caseRef, formatInr, humanize } from "@/lib/format";
import { cn } from "@/lib/utils";

/** `optional` tabs (New, In progress) are only shown when they have cases or are selected. */
export const PRESETS: { key: string; label: string; status: Status[]; optional?: boolean; empty: string }[] = [
  { key: "review", label: "Needs review", status: ["NEEDS_HUMAN"], empty: "Nothing is waiting for a reviewer right now." },
  { key: "new", label: "New", status: ["NEW"], optional: true, empty: "No new cases waiting for the agent." },
  { key: "active", label: "In progress", status: ["PROCESSING"], optional: true, empty: "The agent is not processing anything right now." },
  { key: "auto", label: "Auto-resolved", status: ["AUTO_RESOLVED"], empty: "No case has been auto-resolved yet." },
  { key: "closed", label: "Closed", status: ["APPROVED", "REJECTED", "OVERRIDDEN"], empty: "No reviewer decisions yet." },
  { key: "all", label: "All", status: [], empty: "No disputes in the system yet. Submit a complaint to create one." },
];

/** Count per tab from the backend's live status totals (never hardcoded). */
export function presetCount(byStatus: Record<string, number> | undefined, status: Status[]): number | null {
  if (!byStatus) return null;
  const keys = status.length ? status : Object.keys(byStatus);
  return keys.reduce((n, k) => n + (byStatus[k] ?? 0), 0);
}
const PAGE_SIZE = 25;

export function QueuePage() {
  const [searchParams] = useSearchParams();
  const config = useConfig();
  const metrics = useMetrics();
  const byStatus = metrics.data?.by_status;
  const threshold = config.data?.auto_confidence ?? 0.85;
  const atRisk = config.data?.at_risk_days ?? 7;
  const [preset, setPreset] = useState(searchParams.get("preset") ?? "review");
  const [search, setSearch] = useState(searchParams.get("q") ?? "");
  const [sort, setSort] = useState<QueueQuery["sort"]>("urgency");
  const [dueSoon, setDueSoon] = useState(false);
  const [lowConf, setLowConf] = useState(false);
  const [page, setPage] = useState(1);

  // Sync with searchParams when navigating from metrics links
  useEffect(() => {
    const p = searchParams.get("preset");
    const q = searchParams.get("q");
    if (p && PRESETS.some((item) => item.key === p)) setPreset(p);
    if (q !== null) setSearch(q);
  }, [searchParams]);

  // Open on "Needs review" only when something needs review; otherwise show everything.
  const [defaulted, setDefaulted] = useState(searchParams.get("preset") !== null);
  useEffect(() => {
    if (defaulted || !byStatus) return;
    if ((byStatus.NEEDS_HUMAN ?? 0) === 0 && (presetCount(byStatus, []) ?? 0) > 0) setPreset("all");
    setDefaulted(true);
  }, [byStatus, defaulted]);

  const query: QueueQuery = {
    status: PRESETS.find((p) => p.key === preset)?.status ?? [],
    q: search,
    sort,
    max_days_to_deadline: dueSoon ? atRisk : null,
    max_confidence: lowConf ? threshold : null,
    page,
    page_size: PAGE_SIZE,
  };
  const { data, isLoading, error, refetch, isFetching } = useQueue(query);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const reset =
    <T,>(set: (v: T) => void) =>
    (v: T) => {
      set(v);
      setPage(1);
    };

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-serif text-2xl font-semibold">Analyst queue</h1>
          <p className="text-sm text-muted-foreground">
            Cases closest to their deadline come first.
          </p>
        </div>
        <div className="relative w-full sm:w-72">
          <Search
            className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground"
            aria-hidden
          />
          <label htmlFor="q" className="sr-only">
            Search cases
          </label>
          <Input
            id="q"
            className="pl-9"
            placeholder="Search customer, merchant, text or case #"
            value={search}
            onChange={(e) => reset(setSearch)(e.target.value)}
          />
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div
          role="tablist"
          aria-label="Status"
          className="flex flex-wrap gap-1 rounded-control bg-muted p-1"
        >
          {PRESETS.filter(
            (p) => !p.optional || preset === p.key || (presetCount(byStatus, p.status) ?? 0) > 0,
          ).map((p) => (
            <button
              key={p.key}
              role="tab"
              aria-selected={preset === p.key}
              onClick={() => reset(setPreset)(p.key)}
              className={cn(
                "rounded-[5px] px-3 py-1 text-sm font-medium transition-colors",
                preset === p.key
                  ? "bg-surface shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {p.label}
              {presetCount(byStatus, p.status) !== null && (
                <span className="ml-1.5 rounded-full bg-muted px-1.5 text-xs tabular-nums text-muted-foreground">
                  {presetCount(byStatus, p.status)}
                </span>
              )}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={dueSoon}
            onChange={(e) => reset(setDueSoon)(e.target.checked)}
          />
          Due within {atRisk} days
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={lowConf}
            onChange={(e) => reset(setLowConf)(e.target.checked)}
          />
          Below auto-resolve confidence
        </label>
        <div className="ml-auto flex items-center gap-2">
          <label htmlFor="sort" className="text-sm text-muted-foreground">
            Sort
          </label>
          <Select
            id="sort"
            className="w-44"
            value={sort}
            onChange={(e) => reset(setSort)(e.target.value as QueueQuery["sort"])}
          >
            <option value="urgency">Deadline urgency</option>
            <option value="newest">Newest first</option>
            <option value="confidence">Lowest confidence</option>
          </Select>
        </div>
      </div>

      {error ? (
        <div role="alert" className="rounded-panel border border-fail/40 bg-fail/10 p-4 text-sm">
          <p className="mb-2 flex items-center gap-2 font-medium text-fail">
            <AlertTriangle className="h-4 w-4" aria-hidden /> Could not load the queue
          </p>
          <p className="mb-3">{error.message}</p>
          <Button size="sm" variant="outline" onClick={() => void refetch()}>
            Try again
          </Button>
        </div>
      ) : isLoading ? (
        <div className="space-y-2" aria-busy>
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : data && data.items.length === 0 ? (
        <div className="rounded-panel border border-dashed border-border p-10 text-center">
          <p className="font-medium">
            {search || dueSoon || lowConf
              ? "No cases match these filters."
              : PRESETS.find((p) => p.key === preset)?.empty}
          </p>
          <p className="text-sm text-muted-foreground">
            {search || dueSoon || lowConf ? "Clear the search or filters, or pick another status." : "Pick another status tab above."}
          </p>
        </div>
      ) : (
        data && (
          <>
            <Table items={data.items} threshold={threshold} atRisk={atRisk} dim={isFetching} />
            <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
              <span>
                {data.total} case{data.total === 1 ? "" : "s"}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="Previous page"
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span>
                  Page {page} of {pages}
                </span>
                <Button
                  variant="outline"
                  size="icon"
                  aria-label="Next page"
                  disabled={page >= pages}
                  onClick={() => setPage(page + 1)}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </>
        )
      )}
    </div>
  );
}

function Rec({ d }: { d: DisputeSummary }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <RecommendationBadge value={d.recommendation} />
      {d.friendly_fraud && (
        <span
          className="inline-flex items-center gap-1 text-xs font-medium text-warn"
          title="Transaction was strongly authenticated"
        >
          <AlertTriangle className="h-3 w-3" aria-hidden /> Friendly fraud?
        </span>
      )}
    </div>
  );
}

function Table({
  items,
  threshold,
  atRisk,
  dim,
}: {
  items: DisputeSummary[];
  threshold: number;
  atRisk: number;
  dim: boolean;
}) {
  return (
    <div className={cn("transition-opacity", dim && "opacity-70")}>
      <div className="hidden overflow-hidden rounded-panel border border-border bg-surface md:block">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border bg-muted/50 text-muted-foreground">
            <tr>
              {[
                "Case",
                "Claim",
                "Amount",
                "Recommendation",
                "Confidence",
                "Deadline",
                "Engine",
                "Status",
              ].map((h) => (
                <th key={h} scope="col" className="px-3 py-2.5 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {items.map((d) => (
              <tr key={d.id} className="hover:bg-accent/60">
                <td className="px-3 py-3">
                  <Link to={`/reviewer/cases/${d.id}`} className="font-medium text-primary hover:underline">
                    {caseRef(d.id)}
                  </Link>
                  <div className="text-muted-foreground">{d.customer_name}</div>
                </td>
                <td className="px-3 py-3">
                  <div>{humanize(d.reason_code)}</div>
                  <div className="text-muted-foreground">
                    {d.merchant ?? "No matched transaction"}
                  </div>
                </td>
                <td className="px-3 py-3 tabular-nums">{formatInr(d.amount)}</td>
                <td className="px-3 py-3">
                  <Rec d={d} />
                </td>
                <td className="px-3 py-3">
                  <ConfidenceMeter value={d.confidence} threshold={threshold} />
                </td>
                <td className="px-3 py-3">
                  <DeadlineGauge days={d.days_to_deadline} atRiskDays={atRisk} filedLate={d.filed_late} />
                </td>
                <td className="px-3 py-3">
                  <EngineBadge model={d.model} />
                </td>
                <td className="px-3 py-3">
                  <StatusBadge status={d.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="space-y-2 md:hidden">
        {items.map((d) => (
          <li key={d.id}>
            <Link
              to={`/reviewer/cases/${d.id}`}
              className="block rounded-panel border border-border bg-surface p-3"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-medium text-primary">{caseRef(d.id)}</div>
                  <div className="text-sm text-muted-foreground">
                    {d.customer_name} · {humanize(d.reason_code)}
                  </div>
                </div>
                <StatusBadge status={d.status} />
              </div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <span className="tabular-nums">{formatInr(d.amount)}</span>
                <Rec d={d} />
              </div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <ConfidenceMeter value={d.confidence} threshold={threshold} />
                <DeadlineGauge days={d.days_to_deadline} atRiskDays={atRisk} filedLate={d.filed_late} />
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
