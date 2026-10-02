import { NextResponse } from "next/server";
import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import { datasets, labelEvents, rows } from "@/db/schema";
import { HttpError, jsonBody, newId, now, route } from "@/lib/http";
type Body = { dataset_id: string; row_id: string; label: 0 | 1 | null; category?: string | null; labeler?: string; reason?: string | null; decision_id?: string | null };
// Writes label events only. label=null appends an explicit clear event.
export const POST = route(async (req) => {
  const b = await jsonBody<Body>(req);
  if (!b.dataset_id || !b.row_id) throw new HttpError(400, "dataset_id and row_id are required");
  if (b.label !== 0 && b.label !== 1 && b.label !== null) throw new HttpError(400, "label must be 0, 1 or null");
  const dbc = await db();
  const d = await dbc.select().from(datasets).where(eq(datasets.id, b.dataset_id)).get();
  if (!d) throw new HttpError(404, "dataset not found");
  const row = await dbc.select().from(rows).where(and(eq(rows.datasetId, b.dataset_id), eq(rows.id, b.row_id))).get();
  if (!row) throw new HttpError(404, "row not found");
  const allowed = (JSON.parse(d.contractJson) as { categories: { allowed: string[] } }).categories.allowed;
  if (b.category && allowed.length && !allowed.includes(b.category)) throw new HttpError(400, "category not in contract");
  const audit = row.split === "validation" || row.split === "test";
  const ev = { eventId: newId(), datasetId: b.dataset_id, rowId: b.row_id, label: b.label, category: b.category ?? null, labeler: b.labeler ?? "api", at: now(), reason: b.reason ?? null,
    kind: b.label === null ? "clear" : audit ? "human_audit" : "human", contractVersion: d.contractVersion, decisionId: b.decision_id ?? null };
  if (audit && b.label === null) throw new HttpError(409, "evaluation labels cannot be cleared; create a new evaluation version instead");
  await dbc.insert(labelEvents).values(ev);
  return NextResponse.json({ event: ev, training_eligible: !audit }, { status: 201 });
});
