import { Loader2 } from "lucide-react";
import { Badge, type Tone } from "@/components/ui/badge";
import type { Recommendation, Status } from "@/api/types";

const STATUS: Record<Status, { label: string; tone: Tone }> = {
  NEW: { label: "New", tone: "neutral" },
  PROCESSING: { label: "Agent working", tone: "info" },
  AUTO_RESOLVED: { label: "Auto-resolved", tone: "pass" },
  NEEDS_HUMAN: { label: "Needs review", tone: "warn" },
  APPROVED: { label: "Approved", tone: "pass" },
  REJECTED: { label: "Rejected", tone: "fail" },
  OVERRIDDEN: { label: "Overridden", tone: "info" },
};

export function StatusBadge({ status }: { status: Status }) {
  const s = STATUS[status];
  return (
    <Badge tone={s.tone}>
      {status === "PROCESSING" && <Loader2 className="h-3 w-3 animate-spin" aria-hidden />}
      {s.label}
    </Badge>
  );
}

export const RECOMMENDATION_LABEL: Record<Recommendation, string> = {
  REFUND: "Refund",
  FILE_CHARGEBACK: "File chargeback",
  REJECT: "Reject",
  NEED_MORE_INFO: "Need more info",
};

const REC_TONE: Record<Recommendation, Tone> = {
  REFUND: "pass",
  FILE_CHARGEBACK: "primary",
  REJECT: "fail",
  NEED_MORE_INFO: "warn",
};

export function RecommendationBadge({ value }: { value: Recommendation | null }) {
  if (!value) return <span className="text-sm text-muted-foreground">Not yet</span>;
  return <Badge tone={REC_TONE[value]}>{RECOMMENDATION_LABEL[value]}</Badge>;
}
