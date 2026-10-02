import { NextResponse } from "next/server";
import { MlError } from "./ml";

export class HttpError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
  }
}

type Handler<C> = (req: Request, ctx: C) => Promise<Response> | Response;

export function route<C = unknown>(fn: Handler<C>): Handler<C> {
  return async (req, ctx) => {
    try {
      return await fn(req, ctx);
    } catch (e) {
      if (e instanceof HttpError) return NextResponse.json({ error: e.message, detail: e.detail ?? null }, { status: e.status });
      if (e instanceof MlError) return NextResponse.json({ error: "ml_api_error", detail: e.body }, { status: e.status >= 500 ? 502 : e.status });
      console.error(e);
      return NextResponse.json({ error: "internal_error", detail: String(e) }, { status: 500 });
    }
  };
}

export async function jsonBody<T>(req: Request): Promise<T> {
  try {
    return (await req.json()) as T;
  } catch {
    throw new HttpError(400, "invalid JSON body");
  }
}

export const now = () => new Date().toISOString();
export const newId = () => crypto.randomUUID().replace(/-/g, "");
