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
