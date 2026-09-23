/**
 * Browser-side typed fetch wrapper for the CycloAI backend API.
 *
 * Config: set `NEXT_PUBLIC_API_URL` to the backend's base URL (it defaults
 * to `http://localhost:8000`). The backend must be running for any call to
 * succeed.
 *
 * The session is an httpOnly cookie set by the backend. Because the cookie
 * is not readable from JavaScript and the browser will not send cookies on
 * cross-origin fetches by default, EVERY request below is sent with
 * `credentials: "include"` — this is the single most important line in the
 * module. Nothing here reads or writes tokens: copying the session into
 * JavaScript would defeat httpOnly.
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
