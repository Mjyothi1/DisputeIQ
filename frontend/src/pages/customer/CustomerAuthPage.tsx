import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { setCustomerToken } from "@/api/auth";
import { ApiError, portal } from "@/api/client";
import { Brand } from "@/components/Brand";
import { DemoLoginPanel } from "@/components/DemoLoginPanel";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";

export function CustomerAuthPage({ mode }: { mode: "login" | "register" }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const register = mode === "register";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = register
        ? await portal.register(name.trim(), email.trim(), password)
        : await portal.login(email.trim(), password);
      setCustomerToken(res.token);
      await qc.invalidateQueries({ queryKey: ["portal"] });
      nav("/customer");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background px-4 py-8">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-panel border border-border bg-surface p-6 shadow-sm">
        <Brand to="/" sub="Customer portal" />
        <h1 className="font-serif text-2xl font-semibold">{register ? "Create your account" : "Sign in"}</h1>
        {register && (
          <div>
            <Label htmlFor="name">Full name</Label>
            <Input id="name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />
          </div>
        )}
        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div>
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete={register ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
          />
          {register && <p className="mt-1 text-xs text-muted-foreground">At least 8 characters.</p>}
        </div>
        {error && (
          <p role="alert" className="text-sm text-fail">
            {error}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={busy || password.length < 8 || !email}>
          {busy ? "Please wait…" : register ? "Create account" : "Sign in"}
        </Button>
        <p className="text-center text-sm text-muted-foreground">
          {register ? (
            <>Already have an account? <Link className="text-primary hover:underline" to="/customer/login">Sign in</Link></>
          ) : (
            <>New here? <Link className="text-primary hover:underline" to="/customer/register">Create an account</Link></>
          )}
        </p>
        <p className="text-center text-xs text-muted-foreground">
          Bank staff? <Link className="text-primary hover:underline" to="/reviewer">Reviewer portal</Link>
        </p>
      </form>
      {!register && <DemoLoginPanel className="w-full max-w-2xl" />}
    </div>
  );
}
