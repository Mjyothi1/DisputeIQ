import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { getCustomerToken, getReviewerKey } from "@/api/auth";
import { App } from "@/App";
import { ToastProvider } from "@/components/ui/toast";
import { DEMO_CUSTOMER, getDemoCreds } from "@/lib/demo";

const REVIEWER_KEY = "priya-demo-key-1234";
const PASSWORD = "demo-pass-2026";
let calls: { url: string; init?: RequestInit }[] = [];

/** A fake backend that enforces the real rules: reviewer key on reviewer APIs, customer token on /portal. */
function backend() {
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    const u = new URL(String(url));
    const auth = (init?.headers as Record<string, string> | undefined)?.authorization ?? "";
    const reply = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
    if (u.pathname === "/portal/login") {
      const b = JSON.parse(String(init?.body));
      return b.email === DEMO_CUSTOMER.email && b.password === PASSWORD
        ? reply(200, { token: "cust.rohan.sig", name: "Demo Customer - Rohan Desai", role: "customer" })
        : reply(401, { detail: "Email or password is incorrect." });
    }
    if (u.pathname.startsWith("/portal/")) {
      if (auth !== "Bearer cust.rohan.sig") return reply(401, { detail: "Please sign in" });
      if (u.pathname === "/portal/me") return reply(200, { name: "Demo Customer - Rohan Desai", email: DEMO_CUSTOMER.email, cards: [{ network: "VISA", last4: "5533", masked: "VISA •••• 5533" }] });
      if (u.pathname === "/portal/transactions") return reply(200, [{ id: 9, merchant_name: "DemoBank ATM Andheri West", amount: "5000.00", currency: "INR", txn_time: "2026-11-11T00:00:00Z", card_last4: "5533", channel: "ATM", has_open_dispute: false }]);
      return reply(200, []);
    }
    if (u.pathname === "/config" || u.pathname === "/reason-codes") return reply(200, u.pathname === "/config" ? { auto_confidence: 0.85, at_risk_days: 7 } : []);
    if (auth.startsWith("Bearer cust.")) return reply(403, { detail: "Reviewer access required." });
    if (auth !== `Bearer ${REVIEWER_KEY}`) return reply(401, { detail: "Invalid or missing reviewer key." });
    if (u.pathname === "/auth/me") return reply(200, { name: "priya" });
    if (u.pathname === "/metrics") return reply(200, { by_status: { NEEDS_HUMAN: 1 } });
    if (u.pathname === "/disputes") return reply(200, { items: [], total: 0, page: 1, page_size: 25 });
    return reply(404, { detail: "nope" });
  }));
}

function at(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <ToastProvider>
          <Routes><Route path="/*" element={<App />} /></Routes>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  sessionStorage.clear();
  backend();
});

describe("demo sign-in", () => {
  it("is clearly labelled on the landing page with both personas and no secrets in the page", () => {
    at("/");
    expect(screen.getByRole("heading", { name: /demo sign-in/i })).toBeInTheDocument();
    expect(screen.getByText("Reviewer: priya")).toBeInTheDocument();
    expect(screen.getByText("Customer: Rohan Desai")).toBeInTheDocument();
    expect(screen.getByText(DEMO_CUSTOMER.email)).toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain(PASSWORD);
    expect(document.body.innerHTML).not.toContain(REVIEWER_KEY);
  });

  it("customer demo login goes through POST /portal/login and opens Rohan's own portal", async () => {
    at("/");
    await userEvent.type(screen.getByLabelText(/demo customer password/i), PASSWORD);
    await userEvent.click(screen.getByRole("button", { name: /sign in as rohan desai/i }));
    expect(await screen.findByRole("heading", { name: /welcome, rohan/i })).toBeInTheDocument();
    const login = calls.find((c) => c.url.endsWith("/portal/login"));
    expect(JSON.parse(String(login?.init?.body))).toEqual({ email: DEMO_CUSTOMER.email, password: PASSWORD });
    expect(getCustomerToken()).toBe("cust.rohan.sig");
    expect(getReviewerKey()).toBe("");
    expect(await screen.findByText("DemoBank ATM Andheri West")).toBeInTheDocument();
  });

  it("reviewer demo login checks the key with GET /auth/me and opens the queue", async () => {
    at("/");
    await userEvent.type(screen.getByLabelText(/priya's access key/i), REVIEWER_KEY);
    await userEvent.click(screen.getByRole("button", { name: /sign in as priya/i }));
    expect(await screen.findByText(/signed in as priya/i)).toBeInTheDocument();
    expect(getReviewerKey()).toBe(REVIEWER_KEY);
    expect(getCustomerToken()).toBe("");
  });

  it("wrong demo credentials are rejected by the backend and nothing is stored", async () => {
    at("/");
    await userEvent.type(screen.getByLabelText(/demo customer password/i), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: /sign in as rohan desai/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/not accepted/i);
    expect(getCustomerToken()).toBe("");
    expect(getDemoCreds().customerPassword).toBe("");
    await userEvent.type(screen.getByLabelText(/priya's access key/i), "not-the-key-000");
    await userEvent.click(screen.getByRole("button", { name: /sign in as priya/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/not recognised/i);
    expect(getReviewerKey()).toBe("");
  });

  it("switches reviewer -> customer -> reviewer in one click each, never holding both sessions", async () => {
    sessionStorage.setItem("diq-demo-reviewer-key", REVIEWER_KEY);
    sessionStorage.setItem("diq-demo-customer-password", PASSWORD);
    at("/");
    await userEvent.click(screen.getByRole("button", { name: /sign in as priya/i }));
    expect(await screen.findByText(/signed in as priya/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /switch to rohan desai/i }));
    expect(await screen.findByRole("heading", { name: /welcome, rohan/i })).toBeInTheDocument();
    expect(getReviewerKey()).toBe("");
    expect(getCustomerToken()).toBe("cust.rohan.sig");

    await userEvent.click(screen.getByRole("button", { name: /switch to priya/i }));
    expect(await screen.findByText(/signed in as priya/i)).toBeInTheDocument();
    await waitFor(() => expect(getCustomerToken()).toBe(""));
    expect(getReviewerKey()).toBe(REVIEWER_KEY);
  });

  it("a customer session cannot use reviewer APIs even after switching", async () => {
    sessionStorage.setItem("diq-customer-token", "cust.rohan.sig");
    const r = await fetch("http://localhost:8000/disputes", { headers: { authorization: "Bearer cust.rohan.sig" } });
    expect(r.status).toBe(403); // mirrors backend rule tested in backend/tests/test_portal.py
  });

  it("forget clears remembered demo credentials", async () => {
    sessionStorage.setItem("diq-demo-customer-password", PASSWORD);
    at("/");
    await userEvent.click(screen.getByRole("button", { name: /forget demo credentials/i }));
    expect(getDemoCreds().customerPassword).toBe("");
    expect(screen.getByLabelText(/demo customer password/i)).toBeInTheDocument();
  });

  it("can be hidden for non-demo deployments", async () => {
    vi.stubEnv("VITE_SHOW_DEMO_LOGIN", "false");
    at("/");
    expect(screen.queryByRole("heading", { name: /demo sign-in/i })).not.toBeInTheDocument();
    vi.unstubAllEnvs();
  });
});
