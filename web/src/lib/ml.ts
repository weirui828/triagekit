// Typed client for the internal Python API. Only this module talks to it.
import type { components, paths } from "@/generated/ml-api";

export type S = components["schemas"];
export const ML_SCHEMA_VERSION = "1";

export class MlError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`ml api ${status}: ${typeof body === "object" && body && "detail" in body ? String((body as { detail: unknown }).detail) : JSON.stringify(body)}`);
  }
}

type Paths = keyof paths;
type Method<P extends Paths> = keyof paths[P];
type Body<P extends Paths, M extends Method<P>> = paths[P][M] extends { requestBody: { content: { "application/json": infer B } } } ? B : never;
type Ok<P extends Paths, M extends Method<P>> = paths[P][M] extends { responses: { 200: { content: { "application/json": infer R } } } }
  ? R
  : paths[P][M] extends { responses: { 201: { content: { "application/json": infer R } } } }
    ? R
    : never;

function base(): string {
  return (process.env.ML_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
}

export async function ml<P extends Paths, M extends Method<P>>(
  method: M,
  p: P,
  opts: { body?: Body<P, M>; params?: Record<string, string>; query?: Record<string, string | number> } = {},
): Promise<Ok<P, M>> {
  let url = base() + String(p).replace(/\{(\w+)\}/g, (_, k) => encodeURIComponent(opts.params?.[k] ?? ""));
  if (opts.query) url += "?" + new URLSearchParams(Object.entries(opts.query).map(([k, v]) => [k, String(v)])).toString();
  const headers: Record<string, string> = { "content-type": "application/json" };
  const res = await fetch(url, { method: String(method).toUpperCase(), headers, body: opts.body ? JSON.stringify(opts.body) : undefined, cache: "no-store" });
  const text = await res.text();
  const json = text ? JSON.parse(text) : null;
  if (!res.ok) throw new MlError(res.status, json);
  return json as Ok<P, M>;
}
