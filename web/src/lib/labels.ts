import { and, asc, eq } from "drizzle-orm";
import type { Db } from "@/db";
import { labelEvents } from "@/db/schema";

export type EventKind = "imported" | "human" | "human_audit" | "llm_suggestion" | "clear";
// Kinds that set or clear the accepted label. Suggestions and audit annotations never do.
export const LABEL_SETTING: ReadonlySet<string> = new Set(["imported", "human", "clear"]);

export type Resolved = { label: 0 | 1 | null; category: string | null; seq: number | null };

export async function resolveLabels(db: Db, datasetId: string): Promise<Map<string, Resolved>> {
  const out = new Map<string, Resolved>();
  const evs = await db.select().from(labelEvents).where(eq(labelEvents.datasetId, datasetId)).orderBy(asc(labelEvents.seq));
  for (const e of evs) {
    if (!LABEL_SETTING.has(e.kind)) continue;
    out.set(e.rowId, { label: e.kind === "clear" ? null : (e.label as 0 | 1), category: e.category ?? out.get(e.rowId)?.category ?? null, seq: e.seq });
  }
  return out;
}

export function rowEvents(db: Db, datasetId: string, rowId: string) {
  return db.select().from(labelEvents).where(and(eq(labelEvents.datasetId, datasetId), eq(labelEvents.rowId, rowId))).orderBy(asc(labelEvents.seq));
}
