import { NextResponse } from "next/server";
import { db } from "@/db";
import { submitFeedback, type FeedbackInput } from "@/lib/feedback";
import { jsonBody, route } from "@/lib/http";
export const POST = route(async (req) => {
  const r = await submitFeedback(await db(), await jsonBody<FeedbackInput>(req));
  return NextResponse.json(r, { status: r.duplicate ? 200 : 201 });
});
