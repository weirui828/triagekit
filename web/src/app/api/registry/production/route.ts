import { NextResponse } from "next/server";
import { route } from "@/lib/http";
import { ml } from "@/lib/ml";
export const GET = route(async () => NextResponse.json(await ml("get", "/registry/production")));
