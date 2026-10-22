"use client";

import { useEffect, useState } from "react";

// Same-origin: in production /api is served by the FastAPI service; in development next.config.ts
// rewrites /api/* to the local API (API_ORIGIN). Responses are CDN-cached by the API itself.
const BASE = "/api/v1";
const MEMO_MS = 60_000; // instant back-navigation; the CDN handles real caching
const memo = new Map<string, { at: number; data: unknown }>();

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function getJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
  const hit = memo.get(path);
  if (hit && Date.now() - hit.at < MEMO_MS) return hit.data as T;
  const res = await fetch(`${BASE}${path}`, { signal, headers: { Accept: "application/json" } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {}
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  const data = (await res.json()) as T;
  memo.set(path, { at: Date.now(), data });
  return data;
}

interface State<T> {
  path: string | null;
  data?: T;
  error?: Error;
}

/**
 * Fetch `path` (relative to /api/v1); pass null to skip. `loading` = the result isn't for this path yet.
 * keepPrevious: while a new path loads, keep returning the last data (e.g. switching AQI scale).
 */
export function useApi<T>(path: string | null, { keepPrevious = false } = {}) {
  const [state, setState] = useState<State<T>>({ path: null });
  useEffect(() => {
    if (!path) return;
    const ctrl = new AbortController();
    getJSON<T>(path, ctrl.signal)
      .then((data) => setState({ path, data }))
      .catch((error: Error) => {
        if (error.name !== "AbortError") setState({ path, error });
      });
    return () => ctrl.abort();
  }, [path]);
  const current = state.path === path;
  return {
    data: current || keepPrevious ? state.data : undefined,
    error: current ? state.error : undefined,
    loading: path !== null && !current,
  };
}
