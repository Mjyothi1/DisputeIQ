import { AlertTriangle, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useConfig, useQueue } from "@/api/hooks";
import type { DisputeSummary, QueueQuery, Status } from "@/api/types";
import { RecommendationBadge, StatusBadge } from "@/components/badges";
import { ConfidenceMeter } from "@/components/ConfidenceMeter";
import { DeadlineGauge } from "@/components/DeadlineGauge";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { caseRef, formatInr, humanize } from "@/lib/format";
import { cn } from "@/lib/utils";

const PRESETS: { key: string; label: string; status: Status[] }[] = [
  { key: "review", label: "Needs review", status: ["NEEDS_HUMAN"] },
  { key: "active", label: "In progress", status: ["NEW", "PROCESSING"] },
  { key: "auto", label: "Auto-resolved", status: ["AUTO_RESOLVED"] },
  { key: "closed", label: "Closed", status: ["APPROVED", "REJECTED", "OVERRIDDEN"] },
  { key: "all", label: "All", status: [] },
];
const PAGE_SIZE = 25;

export function QueuePage() {
  const config = useConfig();
  const threshold = config.data?.auto_confidence ?? 0.85;
  const atRisk = config.data?.at_risk_days ?? 7;
  const [preset, setPreset] = useState("review");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<QueueQuery["sort"]>("urgency");
  const [dueSoon, setDueSoon] = useState(false);
  const [lowConf, setLowConf] = useState(false);
  const [page, setPage] = useState(1);

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
          {PRESETS.map((p) => (
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
          <p className="font-medium">No cases match these filters.</p>
          <p className="text-sm text-muted-foreground">Try another status, or clear the search.</p>
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
                  <Link to={`/cases/${d.id}`} className="font-medium text-primary hover:underline">
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
                  <DeadlineGauge days={d.days_to_deadline} atRiskDays={atRisk} />
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
              to={`/cases/${d.id}`}
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
                <DeadlineGauge days={d.days_to_deadline} atRiskDays={atRisk} />
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
