import { NextResponse } from "next/server";
import { db } from "@/db";
import { listRows } from "@/lib/datasets";
import { route } from "@/lib/http";
type Ctx = { params: Promise<{ id: string }> };
export const GET = route<Ctx>(async (req, { params }) => {
  const q = new URL(req.url).searchParams;
  const labeled = q.get("labeled");
  const res = await listRows(await db(), (await params).id, { split: q.get("split") ?? undefined, labeled: labeled === "labeled" || labeled === "unlabeled" ? labeled : undefined, limit: Number(q.get("limit") ?? 100), offset: Number(q.get("offset") ?? 0) });
  return NextResponse.json(res);
});
