/*
 * Coupling/Cohesion: single owner of the auth-token in browser storage.
 * No React import so apiClient can read it without coupling to context.
 * SSR-safe: returns null on the server (window-guarded), mirrors getCartToken.
 */
const AUTH_TOKEN_KEY = "aims-auth-token";

export function getAuthToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthToken(): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.removeItem(AUTH_TOKEN_KEY);
}

/** Event dispatched when the API returns 401 so the auth provider can log out. */
export const UNAUTHORIZED_EVENT = "aims:unauthorized";
