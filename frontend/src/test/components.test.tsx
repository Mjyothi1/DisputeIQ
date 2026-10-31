import { render, screen } from "@testing-library/react";
import type { AuditEvent, Evidence } from "@/api/types";
import { groupRuns } from "@/components/AuditTimeline";
import { bandFor, ConfidenceMeter } from "@/components/ConfidenceMeter";
import { DeadlineGauge, urgency } from "@/components/DeadlineGauge";
import { EvidenceList } from "@/components/EvidenceList";
import { TEMPLATES } from "@/pages/SubmitPage";
import { queueQueryString } from "@/api/client";

describe("ConfidenceMeter", () => {
  it("exposes value and the auto-resolve threshold to assistive tech", () => {
    render(<ConfidenceMeter value={0.9} threshold={0.85} />);
    const meter = screen.getByRole("meter", { name: "Confidence" });
    expect(meter).toHaveAttribute("aria-valuenow", "90");
    expect(meter).toHaveAttribute("aria-valuetext", expect.stringContaining("auto-resolve at 85%"));
  });
  it("bands relative to the threshold", () => {
    expect(bandFor(0.9, 0.85)).toBe("pass");
    expect(bandFor(0.7, 0.85)).toBe("warn");
    expect(bandFor(0.4, 0.85)).toBe("fail");
  });
});

describe("DeadlineGauge", () => {
  it("classifies urgency", () => {
    expect(urgency(null, 7)).toBe("none");
    expect(urgency(-1, 7)).toBe("overdue");
    expect(urgency(7, 7)).toBe("urgent");
    expect(urgency(15, 7)).toBe("soon");
    expect(urgency(60, 7)).toBe("ok");
  });
  it("renders the label", () => {
    render(<DeadlineGauge days={3} />);
    expect(screen.getByText("3d left")).toBeInTheDocument();
  });
});

describe("EvidenceList", () => {
  const ev = (id: number, check_name: string, result: Evidence["result"]): Evidence => ({
    id,
    check_name,
    result,
    details: { summary: `${check_name} summary` },
  });
  it("hides irrelevant checks behind a disclosure", () => {
    render(
      <EvidenceList evidence={[ev(1, "duplicate_charge", "PASS"), ev(2, "atm_failure", "INFO")]} />,
    );
    expect(screen.getByText("Duplicate charge")).toBeVisible();
    expect(screen.getByText(/1 other checks/)).toBeInTheDocument();
  });
  it("explains the empty state", () => {
    render(<EvidenceList evidence={[]} />);
    expect(screen.getByText(/no transaction was matched/i)).toBeInTheDocument();
  });
});

describe("AuditTimeline grouping", () => {
  const e = (id: number, step: string): AuditEvent => ({
    id,
    step,
    actor: "TOOL",
    input_summary: null,
    output_summary: null,
    model: null,
    prompt_version: null,
    tokens_in: null,
    tokens_out: null,
    cost_inr: null,
    latency_ms: null,
    timestamp: "2026-10-27T10:00:00Z",
  });
  it("starts a new run at each mask_pii and keeps human events with the latest run", () => {
    const runs = groupRuns([
      e(1, "mask_pii"),
      e(2, "route"),
      e(3, "mask_pii"),
      e(4, "route"),
      e(5, "human_approve"),
    ]);
    expect(runs.map((r) => r.length)).toEqual([2, 3]);
  });
});

describe("queue query string", () => {
  it("serialises filters", () => {
    const qs = queueQueryString({
      status: ["NEEDS_HUMAN", "NEW"],
      q: " visa ",
      sort: "urgency",
      max_days_to_deadline: 7,
      max_confidence: null,
      page: 2,
      page_size: 25,
    });
    expect(qs).toBe(
      "status=NEEDS_HUMAN&status=NEW&q=visa&sort=urgency&max_days_to_deadline=7&page=2&page_size=25",
    );
  });
});

describe("complaint templates", () => {
  it("only mention values from the transaction, never card numbers", () => {
    const txn = {
      id: 1,
      merchant_name: "QuickKart",
      amount: "1499.00",
      txn_time: "2026-09-01T10:00:00Z",
      card_last4: "1234",
    };
    for (const t of TEMPLATES) {
      const text = t.build(txn);
      expect(text).toContain("QuickKart");
      expect(text).toContain("1,499");
      expect(text).not.toMatch(/\d{12,}/);
    }
  });
});
