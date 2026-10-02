import { NextResponse } from "next/server";
import { route } from "@/lib/http";
import { ml } from "@/lib/ml";
type Ctx = { params: Promise<{ id: string }> };
export const GET = route<Ctx>(async (_req, { params }) => NextResponse.json(await ml("get", "/runs/{run_id}", { params: { run_id: (await params).id } })));
