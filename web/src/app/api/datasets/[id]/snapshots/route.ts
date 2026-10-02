import { NextResponse } from "next/server";
import { db } from "@/db";
import { createSnapshot, listSnapshots } from "@/lib/datasets";
import { route } from "@/lib/http";
import type { S } from "@/lib/ml";
type Ctx = { params: Promise<{ id: string }> };
export const GET = route<Ctx>(async (_req, { params }) => NextResponse.json({ snapshots: await listSnapshots(await db(), (await params).id) }));
export const POST = route<Ctx>(async (req, { params }) => {
  const raw = await req.text();
  const body = raw.trim() ? (JSON.parse(raw) as { preprocessing?: S["PreprocessingConfig"] }) : {};
  return NextResponse.json(await createSnapshot(await db(), (await params).id, body.preprocessing), { status: 201 });
});
