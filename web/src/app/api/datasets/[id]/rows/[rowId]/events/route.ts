import { NextResponse } from "next/server";
import { db } from "@/db";
import { route } from "@/lib/http";
import { rowEvents } from "@/lib/labels";
type Ctx = { params: Promise<{ id: string; rowId: string }> };
export const GET = route<Ctx>(async (_req, { params }) => {
  const p = await params;
  return NextResponse.json({ events: await rowEvents(await db(), p.id, p.rowId) });
});
