import { NextResponse } from "next/server";
import { db } from "@/db";
import { createDataset, listDatasets } from "@/lib/datasets";
import { HttpError, jsonBody, route } from "@/lib/http";
export const GET = route(async () => NextResponse.json({ datasets: await listDatasets(await db()) }));
export const POST = route(async (req) => {
  const b = await jsonBody<{ name?: string; contract?: unknown; split_seed?: number }>(req);
  if (!b.name || !b.contract) throw new HttpError(400, "name and contract are required");
  return NextResponse.json(await createDataset(await db(), b.name, b.contract, b.split_seed ?? 42), { status: 201 });
});
