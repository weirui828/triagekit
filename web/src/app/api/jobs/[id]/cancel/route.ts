import { NextResponse } from "next/server";
import { route } from "@/lib/http";
import { ml } from "@/lib/ml";
type Ctx = { params: Promise<{ id: string }> };
export const POST = route<Ctx>(async (_req, { params }) => NextResponse.json(await ml("post", "/jobs/{job_id}/cancel", { params: { job_id: (await params).id } })));
