import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import type { CaseDetail } from "@/api/types";
import { ReviewPanel } from "@/components/ReviewPanel";
import { ToastProvider } from "@/components/ui/toast";

const detail: CaseDetail = {
  id: 7,
  status: "NEEDS_HUMAN",
  channel: "FORM",
  customer_name: "Asha Rao",
  customer_segment: "RETAIL",
  complaint_masked: "x",
  extracted_fields: null,
  reason_code: "GOODS_NOT_RECEIVED",
  confidence: 0.6,
  deadline_at: null,
  days_to_deadline: 10,
  created_at: "2026-10-01T00:00:00Z",
  transaction: null,
  evidence: [],
  decision: {
    id: 1,
    recommendation: "FILE_CHARGEBACK",
    rationale: "r",
    confidence: 0.6,
    friendly_fraud_flag: false,
    drafted_customer_letter: "a",
    drafted_chargeback_filing: "b",
    model: null,
    prompt_version: null,
    created_at: "2026-10-01T00:00:00Z",
  },
  reviews: [],
  route_reasons: [],
  can_review: true,
  audit: [],
};

function setup(props: Partial<React.ComponentProps<typeof ReviewPanel>> = {}, d = detail) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify([]), { status: 200 })),
  );
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ToastProvider>
          <ReviewPanel
            detail={d}
            letter="a"
            filing="b"
            letterChanged={false}
            filingChanged={false}
            {...props}
          />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => localStorage.clear());

describe("ReviewPanel", () => {
  it("asks for an analyst name before any decision is possible", () => {
    setup();
    expect(screen.getByRole("alert")).toHaveTextContent(/enter your name/i);
    expect(screen.getByRole("button", { name: /approve file chargeback/i })).toBeDisabled();
  });

  it("enables approval once an analyst is named, and 'with edits' only after a draft changes", () => {
    localStorage.setItem("diq-analyst", "Priya");
    const { unmount } = setup();
    expect(screen.getByRole("button", { name: /approve file chargeback/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /approve with my edits/i })).toBeDisabled();
    unmount();
    setup({ letterChanged: true, letter: "changed" });
    expect(screen.getByRole("button", { name: /approve file chargeback/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /approve with my edits/i })).toBeEnabled();
  });

  it("requires a written reason to override", async () => {
    localStorage.setItem("diq-analyst", "Priya");
    setup();
    await userEvent.click(screen.getByRole("button", { name: /override the agent/i }));
    const confirm = screen.getByRole("button", { name: /confirm override/i });
    expect(confirm).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/why are you overriding/i), "Customer sent proof");
    expect(confirm).toBeEnabled();
  });

  it("shows the outcome, not controls, for a closed case", () => {
    setup(
      {},
      {
        ...detail,
        status: "APPROVED",
        can_review: false,
        reviews: [
          {
            id: 1,
            analyst: "Priya",
            action: "APPROVE",
            final_decision: "FILE_CHARGEBACK",
            notes: null,
            edited_letter: null,
            edited_filing: null,
            created_at: "2026-10-02T00:00:00Z",
          },
        ],
      },
    );
    expect(screen.getByText(/reviewed by priya/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
  });
});
