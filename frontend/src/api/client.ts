import type {
  Accepted,
  CaseDetail,
  Channel,
  Customer,
  Metrics,
  DisputePage,
  PublicConfig,
  QueueQuery,
  RecentTxn,
  ReasonCode,
  ReviewRequest,
} from "./types";
import type { PortalComplaint, PortalComplaintDetail, PortalProfile, PortalTxn, PortalToken, PortalRegistration } from "./types";
import { getCustomerToken, getReviewerKey, setCustomerToken, setReviewerKey } from "./auth";

export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** FastAPI returns `detail` as a string, or a list of validation errors. */
function describe(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map(
        (d: { loc?: unknown[]; msg?: string }) => `${(d.loc ?? []).slice(1).join(".")}: ${d.msg}`,
      )
      .join("; ");
  }
  return "Unexpected error";
}

type Auth = "reviewer" | "customer" | "none";

async function request<T>(path: string, init?: RequestInit, auth: Auth = "reviewer"): Promise<T> {
  let res: Response;
  try {
    const key = auth === "reviewer" ? getReviewerKey() : auth === "customer" ? getCustomerToken() : "";
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        "content-type": "application/json",
        ...(key ? { authorization: `Bearer ${key}` } : {}),
      },
    });
  } catch {
    throw new ApiError(0, `Cannot reach the API at ${API_URL}. Check that the backend is running.`);
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* keep statusText */
    }
    if (res.status === 401 && auth === "reviewer" && getReviewerKey()) setReviewerKey(""); // key rejected
    if (res.status === 401 && auth === "customer" && getCustomerToken()) setCustomerToken(""); // session ended
    throw new ApiError(res.status, describe(detail));
  }
  return (await res.json()) as T;
}

export function queueQueryString(q: QueueQuery): string {
  const p = new URLSearchParams();
  q.status.forEach((s) => p.append("status", s));
  if (q.q.trim()) p.set("q", q.q.trim());
  p.set("sort", q.sort);
  if (q.max_days_to_deadline !== null)
    p.set("max_days_to_deadline", String(q.max_days_to_deadline));
  if (q.max_confidence !== null) p.set("max_confidence", String(q.max_confidence));
  p.set("page", String(q.page));
  p.set("page_size", String(q.page_size));
  return p.toString();
}

export const api = {
  queue: (q: QueueQuery) => request<DisputePage>(`/disputes?${queueQueryString(q)}`),
  case: (id: number) => request<CaseDetail>(`/disputes/${id}`),
  submit: (body: { customer_id: number; channel: Channel; raw_text: string }, wait = true) =>
    request<Accepted>(`/disputes${wait ? "?wait=true" : ""}`, { method: "POST", body: JSON.stringify(body) }),
  process: (id: number) => request<Accepted>(`/disputes/${id}/process`, { method: "POST" }),
  review: (id: number, body: ReviewRequest) =>
    request<CaseDetail>(`/disputes/${id}/review`, { method: "POST", body: JSON.stringify(body) }),
  me: () => request<{ name: string }>("/auth/me"),
  reopen: (id: number, reason: string) =>
    request<CaseDetail>(`/disputes/${id}/reopen`, { method: "POST", body: JSON.stringify({ reason }) }),
  customers: (q: string) => request<Customer[]>(`/customers?limit=50&q=${encodeURIComponent(q)}`),
  recentTxns: (id: number) => request<RecentTxn[]>(`/customers/${id}/transactions?limit=25`),
  reasonCodes: () => request<ReasonCode[]>("/reason-codes"),
  metrics: () => request<Metrics>("/metrics"),
  config: () => request<PublicConfig>("/config"),
};

// ---- customer portal (customer session only; the server derives the customer from the token) ----

export const portal = {
  login: (email: string, password: string) =>
    request<PortalToken>("/portal/login", { method: "POST", body: JSON.stringify({ email, password }) }, "none"),
  register: (name: string, email: string, password: string) =>
    request<PortalRegistration>("/portal/register", { method: "POST", body: JSON.stringify({ name, email, password }) }, "none"),
  verifyEmail: (email: string, code: string) =>
    request<PortalToken>("/portal/verify-email", { method: "POST", body: JSON.stringify({ email, code }) }, "none"),
  resendVerification: (email: string) =>
    request<PortalRegistration>("/portal/resend-verification", { method: "POST", body: JSON.stringify({ email }) }, "none"),
  me: () => request<PortalProfile>("/portal/me", undefined, "customer"),
  transactions: () => request<PortalTxn[]>("/portal/transactions", undefined, "customer"),
  categories: () => request<Record<string, string>>("/portal/categories", undefined, "none"),
  complaints: () => request<PortalComplaint[]>("/portal/disputes", undefined, "customer"),
  complaint: (id: number) => request<PortalComplaintDetail>(`/portal/disputes/${id}`, undefined, "customer"),
  report: (body: { transaction_id: number; category: string; description: string }) =>
    request<PortalComplaint>("/portal/disputes", { method: "POST", body: JSON.stringify(body) }, "customer"),
};
