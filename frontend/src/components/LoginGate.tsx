import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { setReviewerKey } from "@/api/auth";
import { api, ApiError } from "@/api/client";
import { Link } from "react-router-dom";
import { Brand } from "@/components/Brand";
import { DemoLoginPanel } from "@/components/DemoLoginPanel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** Prototype reviewer sign-in. Not enterprise SSO: a server-issued access key per reviewer. */
export function LoginGate() {
  const qc = useQueryClient();
  const [key, setKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function signIn(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setReviewerKey(key.trim());
    try {
      await api.me();
      await qc.invalidateQueries();
    } catch (err) {
      setReviewerKey("");
      setError(
        err instanceof ApiError && err.status === 401
          ? "That access key was not recognised."
          : err instanceof Error
            ? err.message
            : "Could not sign in.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 px-4 py-8">
      <form onSubmit={signIn} className="w-full max-w-sm space-y-4 rounded-card border border-border bg-surface p-6">
        <Brand to="/" sub="Reviewer portal" />
        <h1 className="font-serif text-2xl font-semibold">Reviewer sign-in</h1>
        <p className="text-sm text-muted-foreground">
          Case data and decisions are restricted to authorised reviewers. Enter the access key
          issued for you by the demo administrator.
        </p>
        <label className="block text-sm font-medium" htmlFor="reviewer-key">
          Reviewer access key
        </label>
        <Input
          id="reviewer-key"
          type="password"
          autoComplete="off"
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
        {error && (
          <p role="alert" className="text-sm text-fail">
            {error}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={busy || key.trim().length < 8}>
          {busy ? "Checking…" : "Sign in"}
        </Button>
        <p className="text-center text-sm text-muted-foreground">
          A bank customer? <Link to="/customer/login" className="text-primary hover:underline">Go to the customer portal</Link>
        </p>
      </form>
      <DemoLoginPanel className="w-full max-w-2xl" />
    </div>
  );
}
