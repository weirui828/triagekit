import { NextResponse } from "next/server";
import { db } from "@/db";
import { datasetSummary } from "@/lib/datasets";
import { route } from "@/lib/http";
type Ctx = { params: Promise<{ id: string }> };
export const GET = route<Ctx>(async (_req, { params }) => NextResponse.json(await datasetSummary(await db(), (await params).id)));
