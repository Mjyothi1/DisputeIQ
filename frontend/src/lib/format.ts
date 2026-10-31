const inr = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 2,
});

export function formatInr(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "-";
  return inr.format(Number(value));
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** "DUPLICATE_CHARGE" -> "Duplicate charge" */
export function humanize(code: string | null | undefined): string {
  if (!code) return "-";
  const text = code.replaceAll("_", " ").toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function caseRef(id: number): string {
  return `DIQ-${String(id).padStart(6, "0")}`;
}

export function daysLabel(days: number | null | undefined): string {
  if (days === null || days === undefined) return "No deadline";
  if (days < 0) return `Overdue by ${-days}d`;
  if (days === 0) return "Due today";
  return `${days}d left`;
}
