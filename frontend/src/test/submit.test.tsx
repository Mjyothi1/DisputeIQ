import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { formatCard } from "@/components/CustomerCombobox";
import { ToastProvider } from "@/components/ui/toast";
import { SubmitPage } from "@/pages/SubmitPage";

const ALL = [
  { id: 11, name: "Aarav Sharma", segment: "RETAIL", cards: ["VISA ending 1111"] },
  { id: 99, name: "Demo Customer - Meera Iyer", segment: "RETAIL", cards: ["VISA ending 4021"] },
];
const TXNS: Record<number, unknown[]> = {
  11: [{ id: 1, merchant_name: "NewsNow Premium", amount: "399.00", txn_time: "2026-11-08T00:00:00Z", card_last4: "1111" }],
  99: [
    { id: 3, merchant_name: "DemoMart Online", amount: "2499.00", txn_time: "2026-11-10T00:07:00Z", card_last4: "4021" },
    { id: 2, merchant_name: "DemoMart Online", amount: "2499.00", txn_time: "2026-11-10T00:00:00Z", card_last4: "4021" },
  ],
};
let posted: unknown = null;

function setup() {
  posted = null;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const u = new URL(String(url));
      if (u.pathname === "/customers") {
        const q = (u.searchParams.get("q") ?? "").toLowerCase();
        return new Response(JSON.stringify(ALL.filter((c) => c.name.toLowerCase().includes(q))));
      }
      if (u.pathname === "/disputes" && init?.method === "POST") {
        posted = JSON.parse(String(init.body));
        return new Response(JSON.stringify({ dispute_id: 7, status: "NEEDS_HUMAN", message: "" }), { status: 202 });
      }
      const m = u.pathname.match(/customers\/(\d+)\/transactions/);
      return new Response(JSON.stringify(m ? TXNS[Number(m[1])] : []));
    }),
  );
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ToastProvider>
          <SubmitPage />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function pickByTyping(text: string, optionName: RegExp) {
  await userEvent.type(screen.getByPlaceholderText(/type a customer name/i), text);
  const opt = await screen.findByRole("option", { name: optionName });
  await userEvent.pointer({ keys: "[MouseLeft>]", target: opt });
}

describe("Submit complaint", () => {
  it("formats cards from the API value without inventing digits", () => {
    expect(formatCard("VISA ending 4021")).toBe("VISA •••• 4021");
    expect(formatCard("weird")).toBe("weird");
  });

  it("REGRESSION: a different customer's transactions can never show under the selected name", async () => {
    setup();
    await pickByTyping("Aarav", /Aarav Sharma/);
    expect(await screen.findByText(/NewsNow Premium/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /change/i }));
    await pickByTyping("Meera", /Meera Iyer/);
    const sel = screen.getByTestId("selected-customer");
    expect(sel).toHaveTextContent("Demo Customer - Meera Iyer");
    expect(sel).toHaveTextContent("VISA •••• 4021");
    const list = await screen.findByRole("list", { name: /customer transactions/i });
    expect(within(list).getAllByText(/DemoMart Online/)).toHaveLength(2);
    expect(screen.queryByText(/NewsNow Premium/)).not.toBeInTheDocument();
    expect(screen.getByText(/2 most recent, newest first/)).toBeInTheDocument();
  });

  it("supports keyboard selection and shows a no-results state", async () => {
    setup();
    const box = screen.getByPlaceholderText(/type a customer name/i);
    await userEvent.type(box, "zzz");
    expect(await screen.findByText(/No customers match/)).toBeInTheDocument();
    await userEvent.clear(box);
    await userEvent.type(box, "Meera");
    await screen.findByRole("option", { name: /Meera Iyer/ });
    await waitFor(() => expect(screen.queryByLabelText("Searching")).not.toBeInTheDocument());
    await userEvent.keyboard("{ArrowDown}{Enter}");
    expect(screen.getByTestId("selected-customer")).toHaveTextContent("Meera Iyer");
  });

  it("blocks submission without a customer, then posts the selected customer's id", async () => {
    setup();
    await userEvent.type(screen.getByLabelText(/complaint/i), "I was charged twice for one order.");
    expect(screen.getByRole("button", { name: /submit complaint/i })).toBeDisabled();
    await pickByTyping("Meera", /Meera Iyer/);
    const list = await screen.findByRole("list", { name: /customer transactions/i });
    await userEvent.click(within(list).getAllByRole("button", { pressed: false })[0]);
    await userEvent.click(screen.getByRole("button", { name: /charged twice/i }));
    expect((screen.getByLabelText(/complaint/i) as HTMLTextAreaElement).value).toMatch(/DemoMart Online/);
    await userEvent.click(screen.getByRole("button", { name: /submit complaint/i }));
    await waitFor(() => expect(posted).toMatchObject({ customer_id: 99 }));
  });
});
