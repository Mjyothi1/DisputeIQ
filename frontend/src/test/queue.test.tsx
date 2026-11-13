import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { engineLabel } from "@/components/badges";
import { QueuePage, presetCount } from "@/pages/QueuePage";

const item = (id: number, status: string, model: string) => ({
  id, customer_name: "C", channel: "FORM", status, reason_code: "DUPLICATE_CHARGE", confidence: 0.9,
  recommendation: "REFUND", friendly_fraud: false, merchant: "M", amount: "100.00", deadline_at: null,
  days_to_deadline: 10, filed_late: false, created_at: "2026-11-01T00:00:00Z", model,
});

function setup(byStatus: Record<string, number>, items: unknown[]) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const u = new URL(String(url));
    if (u.pathname === "/metrics") return new Response(JSON.stringify({ by_status: byStatus }));
    if (u.pathname === "/config") return new Response(JSON.stringify({ auto_confidence: 0.85, at_risk_days: 7 }));
    return new Response(JSON.stringify({ items, total: items.length, page: 1, page_size: 25 }));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><MemoryRouter><QueuePage /></MemoryRouter></QueryClientProvider>);
}

describe("Queue", () => {
  it("computes tab counts from backend totals, never hardcoded", () => {
    const bs = { NEEDS_HUMAN: 3, AUTO_RESOLVED: 2, APPROVED: 1, REJECTED: 1 };
    expect(presetCount(bs, ["NEEDS_HUMAN"])).toBe(3);
    expect(presetCount(bs, ["APPROVED", "REJECTED", "OVERRIDDEN"])).toBe(2);
    expect(presetCount(bs, [])).toBe(7);
    expect(presetCount(undefined, [])).toBeNull();
  });

  it("hides empty optional tabs, shows counts, and labels the engine honestly", async () => {
    setup({ NEEDS_HUMAN: 1, AUTO_RESOLVED: 1 }, [item(1, "NEEDS_HUMAN", "mock-rules-v1"), item(2, "AUTO_RESOLVED", "gemini-3.8-flash")]);
    expect(await screen.findByRole("tab", { name: /needs review\s*1/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /all\s*2/i })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /^new/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /in progress/i })).not.toBeInTheDocument();
    expect(engineLabel("mock-rules-v1")?.label).toBe("Offline rules");
    expect(engineLabel("gemini-3.8-flash")?.label).toBe("Gemini");
  });

  it("opens on All when nothing needs review, with a meaningful empty state otherwise", async () => {
    setup({ AUTO_RESOLVED: 1 }, [item(2, "AUTO_RESOLVED", "mock-rules-v1")]);
    const all = await screen.findByRole("tab", { name: /all\s*1/i });
    await vi.waitFor(() => expect(all).toHaveAttribute("aria-selected", "true"));
  });
});
