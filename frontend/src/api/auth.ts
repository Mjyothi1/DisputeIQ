/** Prototype reviewer sign-in: the key lives in sessionStorage (cleared when the tab closes). */
const KEY = "diq-reviewer-key";
export const AUTH_EVENT = "diq-auth-change";

export function getReviewerKey(): string {
  try {
    return sessionStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
}

export function setReviewerKey(key: string): void {
  try {
    if (key) sessionStorage.setItem(KEY, key);
    else sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: sign-in just won't persist across reloads */
  }
  window.dispatchEvent(new Event(AUTH_EVENT));
}

/** Customer-portal session (signed token from the server). Separate from reviewer access. */
const CUSTOMER_KEY = "diq-customer-token";
export const CUSTOMER_AUTH_EVENT = "diq-customer-auth-change";

export function getCustomerToken(): string {
  try {
    return sessionStorage.getItem(CUSTOMER_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setCustomerToken(token: string): void {
  try {
    if (token) sessionStorage.setItem(CUSTOMER_KEY, token);
    else sessionStorage.removeItem(CUSTOMER_KEY);
  } catch {
    /* storage unavailable */
  }
  window.dispatchEvent(new Event(CUSTOMER_AUTH_EVENT));
}
