import { AlertTriangle, Info, Undo2 } from "lucide-react";
import { claimsCompletedRefund } from "@/lib/refundWording";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface Props {
  id: string;
  title: string;
  original: string;
  value: string;
  onChange: (v: string) => void;
  readOnly?: boolean;
  /** Plain-language status of this draft (e.g. "Draft only, not sent"). */
  notice?: string;
  /** Warn when the text claims a completed refund (no payment integration exists). */
  checkRefundClaims?: boolean;
}

/** A letter-style editable draft. Shows whether the analyst has changed the agent's text. */
export function DraftEditor({ id, title, original, value, onChange, readOnly, notice, checkRefundClaims }: Props) {
  const edited = value !== original;
  const overclaims = checkRefundClaims && claimsCompletedRefund(value);
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <label htmlFor={id} className="text-sm font-medium">
          {title}
        </label>
        {edited && <Badge tone="warn">Edited</Badge>}
        {edited && !readOnly && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="ml-auto"
            onClick={() => onChange(original)}
          >
            <Undo2 className="h-3.5 w-3.5" /> Reset to draft
          </Button>
        )}
      </div>
      {notice && (
        <p className="mb-2 flex items-start gap-1.5 text-xs text-muted-foreground" data-testid={`${id}-notice`}>
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden /> {notice}
        </p>
      )}
      {overclaims && (
        <p role="alert" className="mb-2 flex items-start gap-1.5 rounded-control bg-fail/10 p-2 text-xs text-fail">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          This text says the refund was already processed or credited. No payment confirmation exists,
          so the customer will not be shown it. Say the refund is authorised instead.
        </p>
      )}
      <textarea
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        readOnly={readOnly}
        rows={Math.min(22, Math.max(8, value.split("\n").length + 1))}
        className="paper w-full resize-y rounded-control border border-border p-5 text-[15px] leading-relaxed"
      />
    </div>
  );
}
