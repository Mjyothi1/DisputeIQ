import { Check, Loader2, Search, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { useCustomers } from "@/api/hooks";
import type { Customer } from "@/api/types";
import { cn } from "@/lib/utils";

/** "VISA ending 4021" (API value) -> "VISA •••• 4021". Unknown formats are shown unchanged. */
export function formatCard(card: string): string {
  const m = card.match(/^(.+?) ending (\d{4})$/);
  return m ? `${m[1]} •••• ${m[2]}` : card;
}

interface Props {
  value: Customer | null;
  onChange: (c: Customer | null) => void;
}

/**
 * Searchable customer picker (WAI-ARIA combobox). Typing ALWAYS clears the current selection, so
 * the page can never show one customer's name next to another customer's transactions.
 */
export function CustomerCombobox({ value, onChange }: Props) {
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const customers = useCustomers(debounced);
  const options = customers.data ?? [];
  const stale = query !== debounced || customers.isFetching;

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 200);
    return () => clearTimeout(t);
  }, [query]);
  useEffect(() => setActive(0), [debounced]);

  function pick(c: Customer) {
    onChange(c);
    setOpen(false);
    setQuery("");
  }

  if (value) {
    return (
      <div
        className="flex items-center justify-between gap-3 rounded-control border border-primary/40 bg-primary/5 px-3 py-2"
        data-testid="selected-customer"
      >
        <div className="min-w-0">
          <p className="flex items-center gap-1.5 truncate text-sm font-medium">
            <Check className="h-4 w-4 shrink-0 text-pass" aria-hidden /> {value.name}
          </p>
          <p className="text-xs text-muted-foreground">
            {value.cards.length ? value.cards.map(formatCard).join(" · ") : "No card on file"} · ID {value.id}
          </p>
        </div>
        <button
          type="button"
          className="inline-flex items-center gap-1 rounded-control px-2 py-1 text-xs text-primary hover:bg-accent"
          onClick={() => {
            onChange(null);
            setOpen(true);
            setTimeout(() => inputRef.current?.focus(), 0);
          }}
        >
          <X className="h-3.5 w-3.5" aria-hidden /> Change
        </button>
      </div>
    );
  }

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, Math.max(options.length - 1, 0)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      if (open && options[active] && !stale) {
        e.preventDefault();
        pick(options[active]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className="relative">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden />
        <input
          ref={inputRef}
          id="cust-search"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && options[active] ? `${listId}-${options[active].id}` : undefined}
          autoComplete="off"
          placeholder="Type a customer name, e.g. Meera"
          className="h-9 w-full rounded-control border border-border bg-surface pl-9 pr-9 text-sm placeholder:text-muted-foreground"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={onKey}
        />
        {stale && open && (
          <Loader2 className="absolute right-3 top-2.5 h-4 w-4 animate-spin text-muted-foreground" aria-label="Searching" />
        )}
      </div>
      {open && (
        <ul
          id={listId}
          role="listbox"
          aria-label="Matching customers"
          className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-control border border-border bg-surface py-1 shadow-lg"
        >
          {customers.isError ? (
            <li className="px-3 py-2 text-sm text-fail">{customers.error.message}</li>
          ) : customers.isLoading ? (
            <li className="px-3 py-2 text-sm text-muted-foreground">Loading customers…</li>
          ) : options.length === 0 ? (
            <li className="px-3 py-2 text-sm text-muted-foreground">
              No customers match &quot;{debounced}&quot;.
            </li>
          ) : (
            options.map((c, i) => (
              <li
                key={c.id}
                id={`${listId}-${c.id}`}
                role="option"
                aria-selected={i === active}
                className={cn(
                  "cursor-pointer px-3 py-2",
                  i === active ? "bg-accent" : "hover:bg-accent/60",
                  stale && "opacity-60",
                )}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => {
                  e.preventDefault(); // keep focus; select on press so a re-render can't shift the target
                  pick(c);
                }}
              >
                <p className="text-sm font-medium">{c.name}</p>
                <p className="text-xs text-muted-foreground">
                  {c.cards.length ? c.cards.map(formatCard).join(" · ") : "No card on file"}
                </p>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}
