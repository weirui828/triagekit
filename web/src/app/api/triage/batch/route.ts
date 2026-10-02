import { NextResponse } from "next/server";
import { db } from "@/db";
import { HttpError, jsonBody, route } from "@/lib/http";
import { triageBatch, type TriageInput } from "@/lib/triage";
export const POST = route(async (req) => {
  const b = await jsonBody<{ items?: TriageInput[] }>(req);
  if (!Array.isArray(b.items) || b.items.length === 0 || b.items.length > 500) throw new HttpError(400, "items must contain 1-500 entries");
  return NextResponse.json(await triageBatch(await db(), b.items));
});
