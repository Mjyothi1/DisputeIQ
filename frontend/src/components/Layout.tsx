import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { AUTH_EVENT, getReviewerKey, setReviewerKey } from "@/api/auth";
import { useMe } from "@/api/hooks";
import { LoginGate } from "@/components/LoginGate";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const THEME_KEY = "diq-theme";

function safeSet(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage unavailable: the preference just won't persist */
  }
}

function ThemeToggle() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  const toggle = () => {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    safeSet(THEME_KEY, next ? "dark" : "light");
    setDark(next);
  };
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      className="inline-flex h-9 w-9 items-center justify-center rounded-control hover:bg-accent"
    >
      {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}

const link = ({ isActive }: { isActive: boolean }) =>
  cn(
    "rounded-control px-3 py-1.5 text-sm font-medium transition-colors",
    isActive ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground",
  );

export function Layout() {
  const [key, setKey] = useState(getReviewerKey);
  useEffect(() => {
    const on = () => setKey(getReviewerKey());
    window.addEventListener(AUTH_EVENT, on);
    return () => window.removeEventListener(AUTH_EVENT, on);
  }, []);
  const me = useMe();
  if (!key || me.isError) return <LoginGate />;
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1280px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5 sm:px-6">
          <NavLink to="/" className="flex items-center gap-2 font-serif text-lg font-semibold">
            <span className="flex h-7 w-7 items-center justify-center rounded-control bg-primary text-sm text-primary-foreground">
              D
            </span>
            DisputeIQ
          </NavLink>
          <nav className="flex items-center gap-1" aria-label="Main">
            <NavLink to="/" end className={link}>
              Queue
            </NavLink>
            <NavLink to="/submit" className={link}>
              Submit complaint
            </NavLink>
            <NavLink to="/metrics" className={link}>
              Metrics
            </NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <span className="text-sm text-muted-foreground" data-testid="reviewer-name">
              {me.data ? `Signed in as ${me.data.name}` : "Signing in…"}
            </span>
            <Button variant="outline" size="sm" onClick={() => setReviewerKey("")}>
              Sign out
            </Button>
            <ThemeToggle />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1280px] px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
