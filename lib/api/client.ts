/**
 * Browser-side typed fetch wrapper for the CycloAI backend API.
 *
 * Config: set `NEXT_PUBLIC_API_URL` to the backend's base URL (it defaults
 * to `http://localhost:8000`). The backend must be running for any call to
 * succeed.
 *
 * SESSION LIMITATION — read this before using this module for anything
 * authenticated. Since sign-in was rewired, the session cookie is a
 * FIRST-PARTY cookie on THIS APP's host (the backend delivers it on a
 * response from the app's own origin, with no Domain attribute). The
 * browser therefore sends it to the app's server — where Next.js server
 * code reaches it via `cookies()` — but it does NOT send it to the
 * backend's host. Consequence: NO request made through this module
 * carries a session, whatever `credentials: "include"` says. This module
 * CANNOT make authenticated calls. Anything needing a session must go
 * through the server-side wrapper in `./server`, which forwards the
 * incoming request's cookies. A browser-side authenticated call fails as
 * a mysterious 401 on a screen where the user is clearly signed in — do
 * not reach for this module there.
 *
 * What this module is still right for: the endpoints that need no
 * session (currently the waitlist signup).
 *
 * Error handling: failed responses throw `ApiError`, which carries the HTTP
 * status AND the parsed body, because the backend puts meaningful detail in
 * its error bodies (validation findings on a 422, for instance). There are
 * no retries and no caching — the caller decides.
 */

import type { ApiErrorBody } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Thrown for every non-2xx response. Carries the status and the parsed body. */
export class ApiError extends Error {
  readonly status: number;
  readonly body: ApiErrorBody | null;

  constructor(status: number, body: ApiErrorBody | null) {
    const message =
      typeof body?.detail === "string"
        ? body.detail
        : Array.isArray(body?.detail)
          ? body.detail.map((item) => item.msg).join("; ")
          : `Request failed with status ${status}`;
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export type ApiMethod = "GET" | "POST" | "PATCH" | "DELETE";

interface RequestOptions {
  method: ApiMethod;
  body?: unknown;
}

/** Base URL the wrapper sends requests to. */
export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

async function parseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/**
 * Perform one typed request against the backend.
 *
 * Not exported directly: callers use `apiGet` / `apiPost` / `apiPatch` /
 * `apiDelete`, which share this shape (and error behaviour) with the
 * server-side module in `./server`.
 */
async function request<T>(path: string, options: RequestOptions): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method,
    credentials: "include",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  const parsed = await parseBody(response);
  if (!response.ok) {
    throw new ApiError(response.status, parsed as ApiErrorBody | null);
  }
  return parsed as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body });
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "PATCH", body });
}

export function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}
