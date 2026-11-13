import { useQueryClient } from "@tanstack/react-query";
import { Briefcase, KeyRound, Loader2, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  DEMO_CUSTOMER,
  DEMO_EVENT,
  DEMO_REVIEWER,
  demoLoginEnabled,
  forgetDemoCreds,
  getDemoCreds,
  signInDemoCustomer,
  signInDemoReviewer,
} from "@/lib/demo";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";

/** "Demo sign-in" box for the live presentation. Uses the real sign-in endpoints (see lib/demo.ts). */
export function DemoLoginPanel({ className = "" }: { className?: string }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [creds, setCreds] = useState(getDemoCreds);
  const [key, setKey] = useState("");
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState<"reviewer" | "customer" | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const on = () => setCreds(getDemoCreds());
    window.addEventListener(DEMO_EVENT, on);
    return () => window.removeEventListener(DEMO_EVENT, on);
  }, []);
  if (!demoLoginEnabled()) return null;

  async function go(who: "reviewer" | "customer") {
    setBusy(who);
    setError(null);
    try {
      if (who === "reviewer") await signInDemoReviewer(qc, nav, creds.reviewerKey || key.trim());
      else await signInDemoCustomer(qc, nav, creds.customerPassword || pw);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not sign in.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section
      aria-labelledby="demo-login-h"
      className={"rounded-panel border border-dashed border-primary/50 bg-primary/5 p-4 " + className}
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 id="demo-login-h" className="flex items-center gap-2 text-sm font-semibold">
          <KeyRound className="h-4 w-4 text-primary" aria-hidden /> Demo sign-in (Zeta Innovate 2026)
        </h2>
        {(creds.reviewerKey || creds.customerPassword) && (
          <button type="button" className="text-xs text-muted-foreground hover:text-foreground" onClick={forgetDemoCreds}>
            Forget demo credentials
          </button>
        )}
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        One-click switching for the live demo. Each click signs in through the normal login. Credentials are
        not stored in the app: enter them once and this browser tab remembers them until it is closed.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-control border border-border bg-surface p-3">
          <p className="mb-2 flex items-center gap-1.5 text-sm font-medium">
            <Briefcase className="h-4 w-4" aria-hidden /> Reviewer: {DEMO_REVIEWER.name}
          </p>
          {!creds.reviewerKey && (
            <div className="mb-2">
              <Label htmlFor="demo-reviewer-key" className="text-xs">priya's access key</Label>
              <Input id="demo-reviewer-key" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} />
            </div>
          )}
          <Button
            type="button"
            size="sm"
            className="w-full"
            disabled={busy !== null || (!creds.reviewerKey && key.trim().length < 8)}
            onClick={() => void go("reviewer")}
          >
            {busy === "reviewer" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
            Sign in as {DEMO_REVIEWER.name} (reviewer)
          </Button>
        </div>
        <div className="rounded-control border border-border bg-surface p-3">
          <p className="mb-2 flex items-center gap-1.5 text-sm font-medium">
            <UserRound className="h-4 w-4" aria-hidden /> Customer: {DEMO_CUSTOMER.name}
          </p>
          <p className="mb-2 font-mono text-xs text-muted-foreground">{DEMO_CUSTOMER.email}</p>
          {!creds.customerPassword && (
            <div className="mb-2">
              <Label htmlFor="demo-customer-password" className="text-xs">Demo customer password</Label>
              <Input id="demo-customer-password" type="password" autoComplete="off" value={pw} onChange={(e) => setPw(e.target.value)} />
            </div>
          )}
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="w-full"
            disabled={busy !== null || (!creds.customerPassword && pw.length < 8)}
            onClick={() => void go("customer")}
          >
            {busy === "customer" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
            Sign in as {DEMO_CUSTOMER.name} (customer)
          </Button>
        </div>
      </div>
      {error && (
        <p role="alert" className="mt-3 text-sm text-fail">
          {error}
        </p>
      )}
    </section>
  );
}

/** Header button: switch to the other demo role in one click (only when credentials are remembered). */
export function DemoSwitchButton({ to }: { to: "reviewer" | "customer" }) {
  const qc = useQueryClient();
  const toast = useToast();
  const nav = useNavigate();
  const [creds, setCreds] = useState(getDemoCreds);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const on = () => setCreds(getDemoCreds());
    window.addEventListener(DEMO_EVENT, on);
    return () => window.removeEventListener(DEMO_EVENT, on);
  }, []);
  const ready = to === "reviewer" ? creds.reviewerKey : creds.customerPassword;
  if (!demoLoginEnabled() || !ready) return null;
  const label = to === "reviewer" ? `Switch to ${DEMO_REVIEWER.name} (reviewer)` : `Switch to ${DEMO_CUSTOMER.name} (customer)`;
  return (
    <Button
      variant="secondary"
      size="sm"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          if (to === "reviewer") await signInDemoReviewer(qc, nav);
          else await signInDemoCustomer(qc, nav);
        } catch (e) {
          // the current session is untouched; tell the presenter why
          toast.error(e instanceof Error ? e.message : "Could not switch accounts.");
        } finally {
          setBusy(false);
        }
      }}
    >
      {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {label}
    </Button>
  );
}
