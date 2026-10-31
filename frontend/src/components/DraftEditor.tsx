import { Undo2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface Props {
  id: string;
  title: string;
  original: string;
  value: string;
  onChange: (v: string) => void;
  readOnly?: boolean;
}

/** A letter-style editable draft. Shows whether the analyst has changed the agent's text. */
export function DraftEditor({ id, title, original, value, onChange, readOnly }: Props) {
  const edited = value !== original;
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
