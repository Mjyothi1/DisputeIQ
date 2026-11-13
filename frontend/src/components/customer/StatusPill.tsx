import { Loader2 } from "lucide-react";
import type { PortalStatus } from "@/api/types";
import { Badge, type Tone } from "@/components/ui/badge";

const TONE: Record<PortalStatus, Tone> = {
  SUBMITTED: "neutral",
  PROCESSING: "info",
  UNDER_REVIEW: "warn",
  APPROVED: "pass",
  REJECTED: "fail",
  MORE_INFO: "warn",
};

export function StatusPill({ status, label }: { status: PortalStatus; label: string }) {
  return (
    <Badge tone={TONE[status]}>
      {(status === "PROCESSING" || status === "SUBMITTED") && <Loader2 className="h-3 w-3 animate-spin" aria-hidden />}
      {label}
    </Badge>
  );
}
