import { NextResponse } from "next/server";
import { jsonBody, route } from "@/lib/http";
import { ml, type S } from "@/lib/ml";
export const GET = route(async () => NextResponse.json(await ml("get", "/jobs")));
export const POST = route(async (req) => NextResponse.json(await ml("post", "/jobs", { body: await jsonBody<S["TrainConfig"]>(req) }), { status: 201 }));
