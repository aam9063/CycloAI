/**
 * Server-side typed fetch wrapper for the CycloAI backend API.
 *
 * For Server Components, route handlers and server actions. The operations
 * and the return/error shape are identical to the browser module in
 * `./client`, so a caller can be moved between them without rewriting its
 * logic.
 *
 * Config: the backend base URL comes from `NEXT_PUBLIC_API_URL` (default
 * `http://localhost:8000`); the backend must be running for any call to
 * succeed.
 *
 * The session is an httpOnly cookie. A server-side `fetch` does NOT carry
 * the browser's cookie store, so the incoming request's cookies must be
 * forwarded explicitly via the `Cookie` header — that is the single most
 * important line in this module. When there are no cookies there is NO
 * fallback: the request simply goes out unauthenticated and the backend's
 * `401` propagates as an `ApiError` the caller can handle. An absent
 * session is a real 401, not something to paper over.
 *
 * The wrapper never reads or writes tokens itself, never retries, and never
 * caches — the caller decides.
 */

import { cookies } from "next/headers";

import { ApiError, getApiBaseUrl, type ApiMethod } from "./client";
import type { ApiErrorBody } from "./types";

export { ApiError, getApiBaseUrl };

interface ServerRequestOptions {
  method: ApiMethod;
  body?: unknown;
}

async function buildCookieHeader(): Promise<string | undefined> {
  const cookieStore = await cookies(); // MUST await — Next 16 / React 19
  const pairs = cookieStore
    .getAll()
    .map(({ name, value }) => `${name}=${value}`);
  return pairs.length > 0 ? pairs.join("; ") : undefined;
}

/**
 * Perform one typed request against the backend on behalf of the current
 * user, forwarding the incoming request's cookies. Not exported directly:
 * callers use `serverGet` / `serverPost` / `serverPatch` / `serverDelete`.
 */
async function serverRequest<T>(
  path: string,
  options: ServerRequestOptions,
): Promise<T> {
  const cookieHeader = await buildCookieHeader();

  const headers: Record<string, string> = {};
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (cookieHeader !== undefined) {
    headers["Cookie"] = cookieHeader;
  }

  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: options.method,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = text;
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, parsed as ApiErrorBody | null);
  }
  return parsed as T;
}

export function serverGet<T>(path: string): Promise<T> {
  return serverRequest<T>(path, { method: "GET" });
}

export function serverPost<T>(path: string, body?: unknown): Promise<T> {
  return serverRequest<T>(path, { method: "POST", body });
}

export function serverPatch<T>(path: string, body: unknown): Promise<T> {
  return serverRequest<T>(path, { method: "PATCH", body });
}

export function serverDelete<T>(path: string): Promise<T> {
  return serverRequest<T>(path, { method: "DELETE" });
}
