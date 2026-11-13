import { ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

export function Brand({ to = "/", sub }: { to?: string; sub?: string }) {
  return (
    <Link to={to} className="flex items-center gap-2 font-serif text-lg font-semibold">
      <span className="flex h-8 w-8 items-center justify-center rounded-control bg-primary text-primary-foreground">
        <ShieldCheck className="h-4.5 w-4.5" aria-hidden />
      </span>
      <span>
        DisputeIQ
        {sub && <span className="ml-2 align-middle text-xs font-sans font-medium text-muted-foreground">{sub}</span>}
      </span>
    </Link>
  );
}
