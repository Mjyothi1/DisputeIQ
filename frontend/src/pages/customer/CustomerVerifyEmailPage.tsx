import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { setCustomerToken } from "@/api/auth";
import { ApiError, portal } from "@/api/client";
import { Brand } from "@/components/Brand";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";

export function CustomerVerifyEmailPage() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await portal.verifyEmail(email.trim(), code.trim());
      setCustomerToken(res.token);
      await qc.invalidateQueries({ queryKey: ["portal"] });
      nav("/customer");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Verification failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await portal.resendVerification(email.trim());
      setNotice(res.message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not resend the code. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background px-4 py-8">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-panel border border-border bg-surface p-6 shadow-sm">
        <Brand to="/" sub="Customer portal" />
        <h1 className="font-serif text-2xl font-semibold">Verify your email</h1>
        <p className="text-sm text-muted-foreground">Enter the 6-digit code sent to your email. The code expires in 10 minutes.</p>
        <div>
          <Label htmlFor="verify-email">Email</Label>
          <Input id="verify-email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div>
          <Label htmlFor="verification-code">Verification code</Label>
          <Input id="verification-code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} required />
        </div>
        {error && <p role="alert" className="text-sm text-fail">{error}</p>}
        {notice && <p role="status" className="text-sm text-muted-foreground">{notice}</p>}
        <Button type="submit" className="w-full" disabled={busy || code.length !== 6 || !email.trim()}>
          {busy ? "Verifying…" : "Verify email"}
        </Button>
        <Button type="button" variant="outline" className="w-full" disabled={busy || !email.trim()} onClick={resend}>Resend code</Button>
        <p className="text-center text-sm text-muted-foreground"><Link className="text-primary hover:underline" to="/customer/login">Back to sign in</Link></p>
      </form>
    </div>
  );
}
