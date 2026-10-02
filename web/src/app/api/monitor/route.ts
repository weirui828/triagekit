import { NextResponse } from "next/server";
import { db } from "@/db";
import { route } from "@/lib/http";
import { monitor, referenceDistribution } from "@/lib/monitor";
export const GET = route(async (req) => {
  const days = Number(new URL(req.url).searchParams.get("days") ?? 30);
  const [m, ref] = await Promise.all([monitor(await db(), days), referenceDistribution().catch(() => null)]);
  return NextResponse.json({ ...m, reference: ref });
});
