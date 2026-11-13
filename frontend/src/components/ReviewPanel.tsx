import { CheckCircle2, Loader2 } from "lucide-react";
import { useState } from "react";
import { ApiError } from "@/api/client";
import { useMe, useReasonCodes, useReview } from "@/api/hooks";
import type { CaseDetail, Recommendation, ReviewAction } from "@/api/types";
import { RECOMMENDATION_LABEL, RecommendationBadge } from "@/components/badges";
import { Button } from "@/components/ui/button";
import { Label, Select, Textarea } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { formatDateTime, humanize } from "@/lib/format";

interface Props {
  detail: CaseDetail;
  letter: string;
  filing: string;
  letterChanged: boolean;
  filingChanged: boolean;
}

const DECISIONS: Recommendation[] = ["REFUND", "FILE_CHARGEBACK", "REJECT", "NEED_MORE_INFO"];

export function ReviewPanel({ detail, letter, filing, letterChanged, filingChanged }: Props) {
  const me = useMe();
  const analyst = me.data?.name ?? "";
  const review = useReview(detail.id);
  const codes = useReasonCodes();
  const toast = useToast();
  const [overriding, setOverriding] = useState(false);
  const [finalDecision, setFinalDecision] = useState<Recommendation>("REJECT");
  const [reasonCode, setReasonCode] = useState("");
  const [notes, setNotes] = useState("");
  const edited = letterChanged || filingChanged;
  const latest = detail.reviews[detail.reviews.length - 1];

  if (["NEW", "PROCESSING"].includes(detail.status)) {
    return (
      <Rail>
        <p className="flex items-center gap-2 text-sm">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> The agent is working on this
          case.
        </p>
      </Rail>
    );
  }

  if (!detail.can_review) {
    return (
      <Rail>
        <h2 className="mb-2 font-semibold">Decision</h2>
        {latest ? (
          <div className="space-y-2 text-sm">
            <p className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-pass" aria-hidden /> Reviewed by{" "}
              {latest.analyst}
            </p>
            <p>
              <span className="text-muted-foreground">Final decision: </span>
              <RecommendationBadge value={latest.final_decision} />
            </p>
            <p className="text-muted-foreground">
              {humanize(latest.action)} on {formatDateTime(latest.created_at)}
            </p>
            {latest.notes && <p className="rounded-control bg-muted p-2">{latest.notes}</p>}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            This case is closed and cannot be reviewed.
          </p>
        )}
      </Rail>
    );
  }

  const rec = detail.decision?.recommendation ?? "NEED_MORE_INFO";
  const nameMissing = analyst.trim() === "";

  function submit(action: ReviewAction, extra: Partial<Parameters<typeof review.mutate>[0]> = {}) {
    review.mutate(
      {
        action,
        notes: notes.trim() || undefined,
        edited_letter: letterChanged ? letter : undefined,
        edited_filing: filingChanged ? filing : undefined,
        ...extra,
      },
      {
        onSuccess: () => toast.success("Decision recorded."),
        onError: (e) =>
          toast.error(e instanceof ApiError ? e.message : "Could not save the decision."),
      },
    );
  }

  const busy = review.isPending;
  const notesRequired = overriding && notes.trim() === "";

  return (
    <Rail>
      <h2 className="mb-1 font-semibold">Your decision</h2>
      <p className="mb-3 text-sm text-muted-foreground">
        Agent recommends <RecommendationBadge value={rec} />
        <span className="mt-1 block text-xs">A recommendation, not yet approved. Nothing is sent to the customer until you decide.</span>
      </p>
      {nameMissing && (
        <p className="mb-3 rounded-control bg-warn/14 p-2 text-sm text-warn" role="alert">
          Sign in as a reviewer so the decision is attributed to you.
        </p>
      )}

      <div className="space-y-2">
        <Button
          className="w-full"
          disabled={busy || nameMissing || overriding || edited}
          onClick={() => submit("APPROVE")}
        >
          Approve {RECOMMENDATION_LABEL[rec].toLowerCase()}
        </Button>
        <Button
          className="w-full"
          variant="outline"
          disabled={busy || nameMissing || overriding || !edited}
          onClick={() => submit("EDIT")}
        >
          Approve with my edits
        </Button>
        {!edited && <p className="text-xs text-muted-foreground">Edit a draft to enable this.</p>}
      </div>

      <div className="mt-5 border-t border-border pt-4">
        {!overriding ? (
          <div className="space-y-2">
            <Button
              variant="ghost"
              className="w-full justify-start"
              disabled={busy}
              onClick={() => setOverriding(true)}
            >
              Override the agent...
            </Button>
            <Button
              variant="ghost"
              className="w-full justify-start text-fail"
              disabled={busy || nameMissing}
              onClick={() => submit("REJECT")}
            >
              Reject the customer&apos;s dispute
            </Button>
          </div>
        ) : (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (notesRequired || nameMissing) return;
              submit("OVERRIDE", {
                final_decision: finalDecision,
                reason_code: reasonCode || undefined,
              });
            }}
          >
            <div>
              <Label htmlFor="final">Final decision</Label>
              <Select
                id="final"
                value={finalDecision}
                onChange={(e) => setFinalDecision(e.target.value as Recommendation)}
              >
                {DECISIONS.map((d) => (
                  <option key={d} value={d}>
                    {RECOMMENDATION_LABEL[d]}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <Label htmlFor="rc">Reason code</Label>
              <Select id="rc" value={reasonCode} onChange={(e) => setReasonCode(e.target.value)}>
                <option value="">Keep {humanize(detail.reason_code)}</option>
                {(codes.data ?? []).map((c) => (
                  <option key={c.code} value={c.code}>
                    {humanize(c.code)}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <Label htmlFor="why">Why are you overriding? (required)</Label>
              <Textarea id="why" value={notes} onChange={(e) => setNotes(e.target.value)} />
            </div>
            <div className="flex gap-2">
              <Button type="submit" disabled={busy || notesRequired || nameMissing}>
                {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />} Confirm override
              </Button>
              <Button type="button" variant="ghost" onClick={() => setOverriding(false)}>
                Cancel
              </Button>
            </div>
          </form>
        )}
      </div>

      {!overriding && (
        <div className="mt-4">
          <Label htmlFor="notes">Notes (optional)</Label>
          <Textarea id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
      )}
    </Rail>
  );
}

function Rail({ children }: { children: React.ReactNode }) {
  return (
    <aside className="rounded-panel border border-border bg-surface p-4 lg:sticky lg:top-20">
      {children}
    </aside>
  );
}
