import { NextResponse } from "next/server";
import { db } from "@/db";
import { route } from "@/lib/http";
import { recentDecisions } from "@/lib/monitor";
export const GET = route(async (req) => NextResponse.json({ decisions: await recentDecisions(await db(), Number(new URL(req.url).searchParams.get("limit") ?? 50)) }));
