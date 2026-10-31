import { caseRef, daysLabel, formatInr, humanize } from "./format";

describe("format", () => {
  it("formats rupees with Indian grouping", () => {
    expect(formatInr("125000.5")).toBe("₹1,25,000.50");
    expect(formatInr(null)).toBe("-");
  });
  it("humanizes codes", () => {
    expect(humanize("FRAUD_NOT_AUTHORISED")).toBe("Fraud not authorised");
    expect(humanize(undefined)).toBe("-");
  });
  it("pads case references", () => {
    expect(caseRef(42)).toBe("DIQ-000042");
  });
  it("labels deadlines", () => {
    expect(daysLabel(5)).toBe("5d left");
    expect(daysLabel(0)).toBe("Due today");
    expect(daysLabel(-3)).toBe("Overdue by 3d");
    expect(daysLabel(null)).toBe("No deadline");
  });
});
