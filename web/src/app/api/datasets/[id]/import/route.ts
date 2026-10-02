import { NextResponse } from "next/server";
import { db } from "@/db";
import { importCsv } from "@/lib/datasets";
import { HttpError, jsonBody, route } from "@/lib/http";
type Ctx = { params: Promise<{ id: string }> };
export const POST = route<Ctx>(async (req, { params }) => {
  const { id } = await params;
  const ct = req.headers.get("content-type") ?? "";
  let csv: string;
  if (ct.includes("text/csv") || ct.includes("text/plain")) csv = await req.text();
  else if (ct.includes("multipart/form-data")) {
    const f = (await req.formData()).get("file");
    if (!(f instanceof File)) throw new HttpError(400, "multipart field 'file' is required");
    csv = await f.text();
  } else csv = (await jsonBody<{ csv?: string }>(req)).csv ?? "";
  if (!csv.trim()) throw new HttpError(400, "empty CSV");
  const res = await importCsv(await db(), id, csv);
  return NextResponse.json(res, { status: res.committed ? 201 : 422 });
});
