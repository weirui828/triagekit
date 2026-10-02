import { NextResponse } from "next/server";
import { db } from "@/db";
import { jsonBody, route } from "@/lib/http";
import { triageOne, type TriageInput } from "@/lib/triage";
export const POST = route(async (req) => {
  const r = await triageOne(await db(), await jsonBody<TriageInput>(req));
  return NextResponse.json(r, { status: r.duplicate ? 200 : 201 });
});
