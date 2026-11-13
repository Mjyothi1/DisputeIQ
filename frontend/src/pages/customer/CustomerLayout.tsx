import { useEffect, useState } from "react";
import { NavLink, Navigate, Outlet, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { CUSTOMER_AUTH_EVENT, getCustomerToken, setCustomerToken } from "@/api/auth";
import { usePortalMe } from "@/api/portalHooks";
import { Brand } from "@/components/Brand";
import { DemoSwitchButton } from "@/components/DemoLoginPanel";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const link = ({ isActive }: { isActive: boolean }) =>
  cn("rounded-control px-3 py-1.5 text-sm font-medium", isActive ? "bg-accent" : "text-muted-foreground hover:text-foreground");

export function CustomerLayout() {
  const [token, setToken] = useState(getCustomerToken);
  const nav = useNavigate();
  const qc = useQueryClient();
  useEffect(() => {
    const on = () => setToken(getCustomerToken());
    window.addEventListener(CUSTOMER_AUTH_EVENT, on);
    return () => window.removeEventListener(CUSTOMER_AUTH_EVENT, on);
  }, []);
  const me = usePortalMe();
  if (!token || me.isError) return <Navigate to="/customer/login" replace />;
  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5 sm:px-6">
          <Brand to="/customer" sub="Customer portal" />
          <nav className="flex items-center gap-1" aria-label="Customer">
            <NavLink to="/customer" end className={link}>
              Home
            </NavLink>
            <NavLink to="/customer/report" className={link}>
              Report a problem
            </NavLink>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden text-sm text-muted-foreground sm:inline">{me.data?.name}</span>
            <DemoSwitchButton to="reviewer" />
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setCustomerToken("");
                qc.clear();
                nav("/");
              }}
            >
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
        <Outlet />
      </main>
    </div>
  );
}
