import { humanize } from "@/lib/format";

/** Single-series horizontal bars: one hue (magnitude), direct value labels, native tooltips. */
export function BarList({
  data,
  label = humanize,
}: {
  data: Record<string, number>;
  label?: (k: string) => string;
}) {
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...rows.map(([, v]) => v));
  if (rows.length === 0) return <p className="text-sm text-muted-foreground">No data yet.</p>;
  return (
    <ul className="space-y-2.5">
      {rows.map(([k, v]) => (
        <li
          key={k}
          className="grid grid-cols-[minmax(0,10rem)_1fr_2.5rem] items-center gap-3 text-sm"
          title={`${label(k)}: ${v}`}
        >
          <span className="truncate">{label(k)}</span>
          <div className="h-2 rounded-full bg-muted" aria-hidden>
            <div
              className="h-full rounded-r-[4px] rounded-l-full bg-primary"
              style={{ width: `${(v / max) * 100}%` }}
            />
          </div>
          <span className="text-right tabular-nums">{v}</span>
        </li>
      ))}
    </ul>
  );
}
