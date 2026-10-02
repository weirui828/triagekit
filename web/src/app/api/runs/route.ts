import { NextResponse } from "next/server";
import { route } from "@/lib/http";
import { ml } from "@/lib/ml";
export const GET = route(async (req) => {
  const q = new URL(req.url).searchParams;
  return NextResponse.json(await ml("get", "/runs", { query: { experiment: q.get("experiment") ?? "triagekit", limit: Number(q.get("limit") ?? 50) } }));
});
