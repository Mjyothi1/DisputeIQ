import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
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
  filed_late: false,
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

let signedIn = "Priya";

function setup(props: Partial<React.ComponentProps<typeof ReviewPanel>> = {}, d = detail) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      new Response(JSON.stringify(String(url).endsWith("/auth/me") ? { name: signedIn } : []), {
        status: 200,
      }),
    ),
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

beforeEach(() => {
  localStorage.clear();
  signedIn = "Priya";
});

describe("ReviewPanel", () => {
  it("blocks decisions until the server has identified the reviewer", () => {
    // /auth/me has not resolved yet on first render, so there is no identity to attribute to.
    setup();
    expect(screen.getByRole("alert")).toHaveTextContent(/sign in as a reviewer/i);
    expect(screen.getByRole("button", { name: /approve file chargeback/i })).toBeDisabled();
  });

  it("enables approval once signed in, and 'with edits' only after a draft changes", async () => {
    const { unmount } = setup();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /approve file chargeback/i })).toBeEnabled(),
    );
    expect(screen.getByRole("button", { name: /approve with my edits/i })).toBeDisabled();
    unmount();
    setup({ letterChanged: true, letter: "changed" });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /approve with my edits/i })).toBeEnabled(),
    );
    expect(screen.getByRole("button", { name: /approve file chargeback/i })).toBeDisabled();
  });

  it("requires a written reason to override", async () => {
    setup();
    await userEvent.click(await screen.findByRole("button", { name: /override the agent/i }));
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
