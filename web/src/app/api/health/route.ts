import { NextResponse } from "next/server";
import { ml } from "@/lib/ml";
export async function GET() {
  try {
    const h = await ml("get", "/health");
    return NextResponse.json({ ok: true, ml: h });
  } catch (e) {
    return NextResponse.json({ ok: false, ml: null, error: String(e) }, { status: 503 });
  }
}
