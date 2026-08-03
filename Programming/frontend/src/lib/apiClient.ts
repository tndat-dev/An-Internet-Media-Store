import { clearAuthToken, getAuthToken, UNAUTHORIZED_EVENT } from "@/lib/authToken";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

type ApiClientOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

/**
 * Error thrown by apiClient on a non-2xx response. Keeps the legacy
 * `message` ("API request failed: <json>") for back-compat while exposing the
 * parsed body, status, and flattened field errors for forms.
 */
export class ApiError extends Error {
  status: number;
  body: unknown;
  fieldErrors: Record<string, string>;

  constructor(status: number, body: unknown) {
    super(`API request failed: ${typeof body === "object" && body !== null ? JSON.stringify(body) : `status ${status}`}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    this.fieldErrors = flattenFieldErrors(body);
  }
}

/** Flatten DRF errors `{field: ["msg", ...] | "msg"}` -> `{field: "msg"}`. */
function flattenFieldErrors(body: unknown): Record<string, string> {
  const result: Record<string, string> = {};
  if (typeof body !== "object" || body === null) {
    return result;
  }
  for (const [key, value] of Object.entries(body as Record<string, unknown>)) {
    if (Array.isArray(value)) {
      if (value.length > 0) result[key] = String(value[0]);
    } else if (typeof value === "string") {
      result[key] = value;
    } else if (value != null) {
      result[key] = String(value);
    }
  }
  return result;
}

/** Extract field errors from any thrown error (use in forms). */
export function parseApiError(error: unknown): Record<string, string> {
  if (error instanceof ApiError) {
    return error.fieldErrors;
  }
  // Fallback for the legacy string-encoded message.
  if (error instanceof Error) {
    const prefix = "API request failed: ";
    if (error.message.startsWith(prefix)) {
      try {
        return flattenFieldErrors(JSON.parse(error.message.slice(prefix.length)));
      } catch {
        return {};
      }
    }
  }
  return {};
}

export async function apiClient<T>(
  path: string,
  options: ApiClientOptions = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");

  // Attach the auth token when present (does not touch X-Cart-Token; callers
  // may still override Authorization explicitly).
  const token = getAuthToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Token ${token}`);
  }

  let body: BodyInit | undefined;
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.body);
  }

  const url = `${API_BASE_URL}${path}`;
  console.log("[apiClient] request:", {
    url,
    method: options.method ?? "GET",
    body: options.body,
  });

  const response = await fetch(url, {
    ...options,
    headers,
    body,
  });

  console.log("[apiClient] response:", {
    url,
    status: response.status,
    ok: response.ok,
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => null);
    console.log("[apiClient] error body:", {
      url,
      status: response.status,
      body: errorBody,
    });
    if (response.status === 401) {
      // Token invalid/expired -> clear it and let the auth provider react.
      clearAuthToken();
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
      }
    }
    throw new ApiError(response.status, errorBody);
  }

  // No body to parse (e.g. 204 No Content) — calling response.json() on an
  // empty body throws "Unexpected end of JSON input".
  if (response.status === 204 || response.headers.get("Content-Length") === "0") {
    return undefined as T;
  }

  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}
