import { NextResponse } from "next/server";
import { route } from "@/lib/http";
import { ml } from "@/lib/ml";
type Ctx = { params: Promise<{ id: string }> };
export const GET = route<Ctx>(async (req, { params }) => {
  const q = new URL(req.url).searchParams;
  return NextResponse.json(await ml("get", "/jobs/{job_id}/logs", { params: { job_id: (await params).id }, query: { offset: Number(q.get("offset") ?? 0), limit: Number(q.get("limit") ?? 500) } }));
});
