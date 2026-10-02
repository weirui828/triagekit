import { NextResponse } from "next/server";
import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import { labelEvents, rows } from "@/db/schema";
import { contractOf, getDataset } from "@/lib/datasets";
import { HttpError, jsonBody, newId, now, route } from "@/lib/http";
import { ml } from "@/lib/ml";
// LLM suggestion: recorded as an llm_suggestion event, never as an accepted label.
export const POST = route(async (req) => {
  const b = await jsonBody<{ dataset_id: string; row_id: string }>(req);
  const dbc = await db();
  const d = await getDataset(dbc, b.dataset_id);
  const row = await dbc.select().from(rows).where(and(eq(rows.datasetId, b.dataset_id), eq(rows.id, b.row_id))).get();
  if (!row) throw new HttpError(404, "row not found");
  const s = await ml("post", "/llm/suggest", { body: { contract: contractOf(d), text: row.text } });
  if (!s.ok) return NextResponse.json({ ok: false, error: s.error, llm: s.llm }, { status: 200 });
  const ev = { eventId: newId(), datasetId: b.dataset_id, rowId: b.row_id, label: s.label, category: s.category ?? null, labeler: `llm:${s.llm?.model_id ?? "unknown"}`,
    at: now(), reason: s.reason ?? null, kind: "llm_suggestion", contractVersion: d.contractVersion, decisionId: null };
  await dbc.insert(labelEvents).values(ev);
  return NextResponse.json({ ok: true, label: s.label, category: s.category, reason: s.reason, llm: s.llm, event_id: ev.eventId });
});
