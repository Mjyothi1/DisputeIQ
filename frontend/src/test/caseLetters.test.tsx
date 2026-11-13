import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import type { CaseDetail } from "@/api/types";
import { ToastProvider } from "@/components/ui/toast";
import { claimsCompletedRefund } from "@/lib/refundWording";
import { CaseDetailPage } from "@/pages/CaseDetailPage";

const PENDING_LETTER =
  "Date: 13 Nov 2026\nTo: Demo Customer - Meera Iyer\nRe: Card dispute DIQ-000314\n\nDear Meera,\n\nThank you for contacting us about the INR 2,499.00 charge. Your dispute is currently under review. Our checks so far support your claim, and a refund has been recommended; it has not yet been approved.\n\nSincerely,\nCard Disputes Team";
const ON_APPROVAL =
  "Date: 13 Nov 2026\nTo: Demo Customer - Meera Iyer\nRe: Card dispute DIQ-000314\n\nDear Meera,\n\nWe have reviewed your dispute and a refund of the amount has been authorised. The bank will make the payment to your account separately.\n\nSincerely,\nCard Disputes Team";

const base: CaseDetail = {
  id: 314, status: "NEEDS_HUMAN", channel: "FORM", customer_name: "Demo Customer - Meera Iyer", customer_segment: "RETAIL",
  complaint_masked: "Charged twice", extracted_fields: null, reason_code: "DUPLICATE_CHARGE", confidence: 0.83,
  deadline_at: null, days_to_deadline: 100, filed_late: false, created_at: "2026-11-13T00:00:00Z", transaction: null,
  evidence: [], reviews: [], audit: [], can_review: true,
  route_reasons: ["Transaction already has another dispute (DIQ-000313 AUTO_RESOLVED); possible duplicate or repeat claim - no automatic refund."],
  decision: { id: 1, recommendation: "REFUND", rationale: "r", confidence: 0.83, friendly_fraud_flag: false,
    drafted_customer_letter: PENDING_LETTER, drafted_chargeback_filing: null, model: "gemini-3.8-flash", prompt_version: "v1", created_at: "2026-11-13T00:00:00Z" },
  letter_on_approval: ON_APPROVAL,
};

function show(detail: CaseDetail) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const p = new URL(String(url)).pathname;
    if (p === "/config") return new Response(JSON.stringify({ auto_confidence: 0.85, at_risk_days: 7, auto_max_amount_inr: 10000, auto_resolve_codes: [] }));
    if (p === "/auth/me") return new Response(JSON.stringify({ name: "priya" }));
    if (p === "/reason-codes") return new Response(JSON.stringify([]));
    return new Response(JSON.stringify(detail));
  }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/reviewer/cases/${detail.id}`]}>
        <ToastProvider>
          <Routes><Route path="/reviewer/cases/:id" element={<CaseDetailPage />} /></Routes>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("reviewer letters (DIQ-000314 regression)", () => {
  it("pending: shows the under-review letter read-only and the authorised letter as the approval draft", async () => {
    show(base);
    const current = await screen.findByTestId("current-letter");
    expect(current).toHaveTextContent(/currently under review/);
    expect(current).toHaveTextContent(/recommended; it has not yet been approved/);
    const editor = screen.getByLabelText("Letter sent if you approve") as HTMLTextAreaElement;
    expect(editor.value).toMatch(/has been authorised/);
    expect(claimsCompletedRefund(editor.value)).toBe(false);
    expect(claimsCompletedRefund(current.textContent)).toBe(false);
    expect(screen.queryByText(/already processed or credited/)).not.toBeInTheDocument(); // nothing unsafe to warn about
    expect(screen.getByTestId("letter-notice")).toHaveTextContent(/recommended, not approved/);
  });

  it("closed: shows only the letter that was sent", async () => {
    show({ ...base, status: "APPROVED", can_review: false, letter_on_approval: null,
      decision: { ...base.decision!, drafted_customer_letter: ON_APPROVAL },
      reviews: [{ id: 1, analyst: "priya", action: "APPROVE", final_decision: "REFUND", notes: null, edited_letter: null, edited_filing: null, created_at: "2026-11-13T01:00:00Z" }] });
    const editor = (await screen.findByLabelText("Letter to the customer")) as HTMLTextAreaElement;
    expect(editor.value).toMatch(/has been authorised/);
    expect(screen.queryByTestId("current-letter")).not.toBeInTheDocument();
  });

  it("still warns if an unsafe letter ever reaches the UI", async () => {
    show({ ...base, letter_on_approval: "Dear Meera,\n\nWe have processed a refund." });
    expect(await screen.findByText(/already processed or credited/)).toBeInTheDocument();
  });
});
