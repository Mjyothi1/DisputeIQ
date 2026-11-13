import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { getCustomerToken, getReviewerKey } from "@/api/auth";
import { App } from "@/App";
import { ToastProvider } from "@/components/ui/toast";

const TXNS = [
  { id: 3, merchant_name: "DemoMart Online", amount: "2499.00", currency: "INR", txn_time: "2026-11-10T00:07:00Z", card_last4: "4021", channel: "ECOM", has_open_dispute: false },
  { id: 2, merchant_name: "DemoMart Online", amount: "2499.00", currency: "INR", txn_time: "2026-11-10T00:00:00Z", card_last4: "4021", channel: "ECOM", has_open_dispute: false },
];
let calls: { url: string; init?: RequestInit }[] = [];

function api(handlers: Record<string, (init?: RequestInit) => [number, unknown]>) {
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    const path = new URL(String(url)).pathname;
    const key = `${init?.method ?? "GET"} ${path}`;
    const h = handlers[key] ?? handlers[path];
    const [status, body] = h ? h(init) : [404, { detail: "not mocked " + key }];
    return new Response(JSON.stringify(body), { status });
  }));
}

function at(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <ToastProvider>
          <Routes><Route path="/*" element={<App />} /></Routes>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => sessionStorage.clear());

describe("Landing page", () => {
  it("offers two distinct portals", () => {
    at("/");
    expect(screen.getByRole("link", { name: /customer login/i })).toHaveAttribute("href", "/customer/login");
    expect(screen.getByRole("link", { name: /reviewer login/i })).toHaveAttribute("href", "/reviewer");
  });
});

describe("Customer portal", () => {
  it("redirects to sign-in without a session, and the reviewer portal still asks for a reviewer key", async () => {
    at("/customer");
    expect(await screen.findByRole("heading", { name: /sign in/i })).toBeInTheDocument();
  });

  it("signs in with a customer token kept apart from the reviewer key", async () => {
    api({
      "POST /portal/login": () => [200, { token: "cust.abc.def", name: "Demo Customer - Meera Iyer", role: "customer" }],
      "/portal/me": () => [200, { name: "Demo Customer - Meera Iyer", email: "m@x.test", cards: [{ network: "VISA", last4: "4021", masked: "VISA •••• 4021" }] }],
      "/portal/transactions": () => [200, TXNS],
      "/portal/disputes": () => [200, []],
    });
    at("/customer/login");
    await userEvent.type(screen.getByLabelText(/email/i), "meera.iyer@demo.disputeiq.test");
    await userEvent.type(screen.getByLabelText("Password"), "demo-pass-2026");
    await userEvent.click(screen.getByRole("button", { name: /^sign in$/i }));
    expect(await screen.findByRole("heading", { name: /welcome, meera/i })).toBeInTheDocument();
    expect(screen.getByText("VISA •••• 4021")).toBeInTheDocument();
    expect(getCustomerToken()).toBe("cust.abc.def");
    expect(getReviewerKey()).toBe("");
    const me = calls.find((c) => c.url.endsWith("/portal/me"));
    expect((me?.init?.headers as Record<string, string>).authorization).toBe("Bearer cust.abc.def");
  });

  it("reports a problem on one of the customer's own transactions and shows the reference", async () => {
    sessionStorage.setItem("diq-customer-token", "cust.abc.def");
    let posted: Record<string, unknown> | null = null;
    api({
      "/portal/me": () => [200, { name: "Meera", email: "m@x.test", cards: [] }],
      "/portal/transactions": () => [200, TXNS],
      "/portal/categories": () => [200, { CHARGED_TWICE: "Charged twice", OTHER: "Something else" }],
      "POST /portal/disputes": (init) => {
        posted = JSON.parse(String(init?.body));
        return [202, { id: 42, reference: "DIQ-000042", merchant: "DemoMart Online", amount: "2499.00", category: "Charged twice", status: "SUBMITTED", status_label: "Submitted", message: "We have received your complaint.", created_at: "2026-11-13T00:00:00Z" }];
      },
    });
    at("/customer/report");
    const group = await screen.findByRole("radiogroup", { name: /your transactions/i });
    await userEvent.click(within(group).getAllByRole("radio")[0]);
    await userEvent.selectOptions(screen.getByLabelText(/what went wrong/i), "CHARGED_TWICE");
    await userEvent.type(screen.getByLabelText(/describe it/i), "Do baar paise kat gaye, ek hi order tha.");
    await userEvent.click(screen.getByRole("button", { name: /submit complaint/i }));
    expect(await screen.findByTestId("reference")).toHaveTextContent("DIQ-000042");
    expect(posted).toEqual({ transaction_id: 3, category: "CHARGED_TWICE", description: "Do baar paise kat gaye, ek hi order tha." });
    expect(posted).not.toHaveProperty("customer_id"); // identity comes from the session, never the form
  });

  it("shows the customer-facing status, latest update and timeline", async () => {
    sessionStorage.setItem("diq-customer-token", "cust.abc.def");
    api({
      "/portal/me": () => [200, { name: "Meera", email: "m@x.test", cards: [] }],
      "/portal/disputes/42": () => [200, {
        id: 42, reference: "DIQ-000042", merchant: "DemoMart Online", amount: "2499.00", category: "Charged twice",
        status: "APPROVED", status_label: "Approved", message: "Your dispute was approved and a refund has been authorised.",
        created_at: "2026-11-13T00:00:00Z", description: "Charged twice", transaction_date: "2026-11-10T00:00:00Z",
        letter: "Dear customer…", timeline: [{ label: "Complaint submitted", at: "2026-11-13T00:00:00Z" }, { label: "Decision: Approved", at: "2026-11-13T00:01:00Z" }],
      }],
    });
    at("/customer/complaints/42");
    expect(await screen.findByRole("heading", { name: "DIQ-000042" })).toBeInTheDocument();
    expect(screen.getByTestId("latest-update")).toHaveTextContent(/refund has been authorised/);
    expect(screen.getByText("Decision: Approved")).toBeInTheDocument();
    expect(screen.getByText("Letter from the bank")).toBeInTheDocument();
  });

  it("drops an expired/invalid session back to sign-in", async () => {
    sessionStorage.setItem("diq-customer-token", "cust.expired.sig");
    api({ "/portal/me": () => [401, { detail: "Please sign in" }] });
    at("/customer");
    expect(await screen.findByRole("heading", { name: /sign in/i })).toBeInTheDocument();
    await waitFor(() => expect(getCustomerToken()).toBe(""));
  });
});

describe("Reviewer portal", () => {
  it("lives under /reviewer and still requires the reviewer key", async () => {
    sessionStorage.setItem("diq-customer-token", "cust.abc.def"); // a customer session is not enough
    at("/reviewer");
    expect(await screen.findByRole("heading", { name: /reviewer sign-in/i })).toBeInTheDocument();
  });

  it("keeps old /cases links working", async () => {
    at("/cases/7");
    expect(await screen.findByRole("heading", { name: /reviewer sign-in/i })).toBeInTheDocument();
  });
});
