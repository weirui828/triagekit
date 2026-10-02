import { NextResponse } from "next/server";
import { jsonBody, route } from "@/lib/http";
import { ml, type S } from "@/lib/ml";
export const POST = route(async (req) => NextResponse.json(await ml("post", "/prune", { body: await jsonBody<S["PruneRequest"]>(req) })));
