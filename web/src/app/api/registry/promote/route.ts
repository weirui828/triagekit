import { NextResponse } from "next/server";
import { jsonBody, route } from "@/lib/http";
import { ml, type S } from "@/lib/ml";
export const POST = route(async (req) => {
  const b = await jsonBody<S["PromoteRequest"]>(req);
  return NextResponse.json(await ml("post", "/registry/promote", { body: { ...b, initiated_by: b.initiated_by ?? "web" } }));
});
