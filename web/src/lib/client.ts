"use client";
/** Browser helper for /api calls. */
export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init;
  const res = await fetch(path, { ...rest, headers: { ...(json !== undefined ? { "content-type": "application/json" } : {}), ...(rest.headers ?? {}) }, body: json !== undefined ? JSON.stringify(json) : rest.body });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new Error(data?.detail ? `${data.error}: ${typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)}` : data?.error ?? `HTTP ${res.status}`);
  return data as T;
}
export const fmt = (v: number | null | undefined, d = 3) => (v === null || v === undefined ? "–" : v.toFixed(d));
