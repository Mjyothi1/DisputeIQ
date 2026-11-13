/**
 * Live-demo account switching. NOT an authentication bypass:
 * - Every switch calls the real backend sign-in (reviewer key check / customer password login).
 * - No secret is built into the app. The presenter types the reviewer key and the demo customer
 *   password once; they live only in this browser tab's sessionStorage (gone when the tab closes)
 *   and can be cleared with "Forget".
 * - Switching always ends the other session first, so a tab is never signed in as both roles.
 */
import type { QueryClient } from "@tanstack/react-query";
import { setCustomerToken, setReviewerKey } from "@/api/auth";
import { ApiError, api, portal } from "@/api/client";

export const DEMO_REVIEWER = { name: "priya" } as const;
// Seeded by backend/data_gen/demo_customers.py (demo_email); password = DEMO_CUSTOMER_PASSWORD.
export const DEMO_CUSTOMER = { name: "Rohan Desai", email: "rohan.desai@demo.disputeiq.test" } as const;

const K_REVIEWER = "diq-demo-reviewer-key";
const K_PASSWORD = "diq-demo-customer-password";
export const DEMO_EVENT = "diq-demo-change";

/** Shown unless the deployment opts out with VITE_SHOW_DEMO_LOGIN=false. */
export const demoLoginEnabled = (): boolean => import.meta.env.VITE_SHOW_DEMO_LOGIN !== "false";

function read(k: string): string {
  try {
    return sessionStorage.getItem(k) ?? "";
  } catch {
    return "";
  }
}
function write(k: string, v: string): void {
  try {
    if (v) sessionStorage.setItem(k, v);
    else sessionStorage.removeItem(k);
  } catch {
    /* storage unavailable */
  }
}

export interface DemoCreds {
  reviewerKey: string;
  customerPassword: string;
}

export function getDemoCreds(): DemoCreds {
  return { reviewerKey: read(K_REVIEWER), customerPassword: read(K_PASSWORD) };
}

export function saveDemoCreds(c: Partial<DemoCreds>): void {
  if (c.reviewerKey !== undefined) write(K_REVIEWER, c.reviewerKey.trim());
  if (c.customerPassword !== undefined) write(K_PASSWORD, c.customerPassword);
  window.dispatchEvent(new Event(DEMO_EVENT));
}

export function forgetDemoCreds(): void {
  write(K_REVIEWER, "");
  write(K_PASSWORD, "");
  window.dispatchEvent(new Event(DEMO_EVENT));
}

function message(err: unknown, fallback: string): string {
  if (err instanceof ApiError && err.status === 401) return fallback;
  return err instanceof Error ? err.message : "Could not sign in.";
}

type Navigate = (to: string) => void;
const isPortalQuery = (k: unknown) => k === "portal" || k === "portal-categories";

/**
 * Sign in as the demo reviewer through the normal reviewer-key check (GET /auth/me).
 * Order: authenticate -> navigate -> end the customer session and drop its cached data.
 * If authentication fails nothing else changes (a signed-in customer stays signed in).
 */
export async function signInDemoReviewer(
  qc: QueryClient,
  navigate: Navigate,
  key = getDemoCreds().reviewerKey,
): Promise<string> {
  if (!key) throw new Error("Enter the reviewer access key first.");
  setReviewerKey(key);
  let name: string;
  try {
    name = (await api.me()).name;
  } catch (err) {
    setReviewerKey("");
    throw new Error(message(err, "That reviewer access key was not recognised."));
  }
  saveDemoCreds({ reviewerKey: key });
  navigate("/reviewer");
  setCustomerToken("");
  qc.removeQueries({ predicate: (q) => isPortalQuery(q.queryKey[0]) });
  return name;
}

/**
 * Sign in as the demo customer through the normal customer login (POST /portal/login).
 * Order: authenticate -> store the customer session -> navigate -> end the reviewer session.
 */
export async function signInDemoCustomer(
  qc: QueryClient,
  navigate: Navigate,
  password = getDemoCreds().customerPassword,
): Promise<string> {
  if (!password) throw new Error("Enter the demo customer password first.");
  let res: Awaited<ReturnType<typeof portal.login>>;
  try {
    res = await portal.login(DEMO_CUSTOMER.email, password);
  } catch (err) {
    throw new Error(
      message(err, "The demo customer password was not accepted (or Rohan's demo login has not been created)."),
    );
  }
  saveDemoCreds({ customerPassword: password });
  qc.removeQueries({ predicate: (q) => isPortalQuery(q.queryKey[0]) }); // never show a previous customer's data
  setCustomerToken(res.token);
  navigate("/customer");
  setReviewerKey("");
  qc.removeQueries({ predicate: (q) => !isPortalQuery(q.queryKey[0]) });
  return res.name;
}
