import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { DraftEditor } from "@/components/DraftEditor";
import { claimsCompletedRefund, letterStatusNotice } from "@/lib/refundWording";
import { ComplaintDetailPage } from "@/pages/customer/ComplaintDetailPage";

// Same cases as backend/tests/test_refund_wording.py, so the two guards stay in step.
const CLAIMS = [
  "We have processed a refund for this charge.",
  "The amount has been credited to your account.",
  "We are refunding the amount to your account.",
  "Your refund has been processed.",
  "The refund was issued today.",
  "The money will be credited back to your account.",
  "We've refunded the duplicate charge.",
  "Refund processed.",
];
const TRUTHFUL = [
  "A refund of the amount has been authorised. The bank will make the payment separately.",
  "Your dispute is currently under review.",
  "We are raising a formal dispute with the merchant on your behalf.",
  "The refund has not been processed by the merchant yet.",
];

describe("refund wording guard", () => {
  it.each(CLAIMS)("flags a completed-payment claim: %s", (t) => expect(claimsCompletedRefund(t)).toBe(true));
  it.each(TRUTHFUL)("allows truthful wording: %s", (t) => expect(claimsCompletedRefund(t)).toBe(false));
});

describe("letter status notice (reviewer)", () => {
  it("pending review: draft only, recommended not approved", () => {
    const n = letterStatusNotice("NEEDS_HUMAN", "REFUND");
    expect(n).toMatch(/draft only, not sent/i);
    expect(n).toMatch(/refund is recommended, not approved/i);
  });
  it("auto-resolved refund: authorised, payment separate", () => {
    const n = letterStatusNotice("AUTO_RESOLVED", "REFUND");
    expect(n).toMatch(/refund authorised/i);
    expect(n).toMatch(/payment separately/i);
    expect(claimsCompletedRefund(n)).toBe(false);
  });
  it.each(["APPROVED", "OVERRIDDEN", "REJECTED"])("closed (%s): final letter, never 'processed'", (s) => {
    const n = letterStatusNotice(s, "REFUND");
    expect(n).toMatch(/final letter/i);
    expect(claimsCompletedRefund(n)).toBe(false);
  });
});

describe("DraftEditor", () => {
  it("shows the status notice and warns on premature refund claims", () => {
    const { rerender } = render(
      <DraftEditor id="letter" title="Letter" original="a" value="A refund has been authorised." onChange={() => {}} notice="Draft only, not sent." checkRefundClaims />,
    );
    expect(screen.getByTestId("letter-notice")).toHaveTextContent("Draft only, not sent.");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    rerender(
      <DraftEditor id="letter" title="Letter" original="a" value="We have processed your refund." onChange={() => {}} checkRefundClaims />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/already processed or credited/i);
  });
});

describe("customer complaint page", () => {
  function show(body: Record<string, unknown>) {
    sessionStorage.setItem("diq-customer-token", "cust.t.s");
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      id: 5, reference: "DIQ-000005", merchant: "DemoTravel Bookings", amount: "32000.00", category: "Charged twice",
      created_at: "2026-11-13T00:00:00Z", description: "Charged twice", transaction_date: null, timeline: [], ...body,
    }))));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/customer/complaints/5"]}>
          <Routes><Route path="/customer/complaints/:id" element={<ComplaintDetailPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it("under review: review wording, no letter, nothing about a refund being paid", async () => {
    show({ status: "UNDER_REVIEW", status_label: "Under review", letter: null,
      message: "Your dispute is currently under review. Our team has identified evidence supporting your claim and is evaluating the appropriate resolution." });
    expect(await screen.findByTestId("latest-update")).toHaveTextContent(/currently under review/);
    expect(screen.queryByText("Letter from the bank")).not.toBeInTheDocument();
    expect(claimsCompletedRefund(document.body.textContent)).toBe(false);
  });

  it("approved refund: 'Refund authorised' and payment made separately", async () => {
    show({ status: "APPROVED", status_label: "Refund authorised", letter: "Dear Meera, a refund of the amount has been authorised.",
      message: "Your dispute was approved and a refund has been authorised. The bank makes the payment to your account separately; it can take a few working days to appear on your statement." });
    expect(await screen.findByText("Refund authorised")).toBeInTheDocument();
    expect(screen.getByTestId("latest-update")).toHaveTextContent(/makes the payment to your account separately/);
    expect(claimsCompletedRefund(document.body.textContent)).toBe(false);
  });
});
