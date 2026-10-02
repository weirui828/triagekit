import { eq } from "drizzle-orm";
import type { Db } from "@/db";
import { decisions } from "@/db/schema";
import { HttpError, newId, now } from "./http";
import { ml, type S } from "./ml";

export type TriageInput = { text: string; request_id?: string | null; source?: string | null };

export function decisionResponse(d: typeof decisions.$inferSelect) {
  return {
    decision_id: d.decisionId, request_id: d.requestId, probability: d.probability, predicted_label: d.predictedLabel, final_label: d.finalLabel,
    resolved_by: d.resolvedBy, action: d.action, model_version: d.modelVersion, policy_version: d.policyVersion, reason: d.reason, latency_ms: d.latencyMs, created_at: d.createdAt,
  };
}

async function insertDecision(db: Db, input: TriageInput, r: S["ScoreResult"], latencyMs: number) {
  const row = {
    decisionId: newId(), requestId: input.request_id ?? null, text: input.text, source: input.source ?? null, datasetId: null, rowId: null,
    probability: r.probability, predictedLabel: r.predicted_label, finalLabel: r.final_label ?? null, resolvedBy: r.resolved_by, action: r.action,
    modelVersion: r.model_version, policyVersion: r.policy_version, reason: r.reason ?? null, latencyMs, createdAt: now(),
  };
  await db.insert(decisions).values(row);
  return row as typeof decisions.$inferSelect;
}

export function findByRequestId(db: Db, requestId: string) {
  return db.select().from(decisions).where(eq(decisions.requestId, requestId)).get();
}

export async function triageOne(db: Db, input: TriageInput) {
  if (!input.text?.trim()) throw new HttpError(400, "text is required");
  if (input.request_id) {
    const existing = await findByRequestId(db, input.request_id);
    if (existing) return { ...decisionResponse(existing), duplicate: true };
  }
  const t0 = Date.now();
  const r = await ml("post", "/score", { body: { text: input.text, request_id: input.request_id ?? null } });
  return { ...decisionResponse(await insertDecision(db, input, r, Date.now() - t0)), duplicate: false };
}

export async function triageBatch(db: Db, items: TriageInput[]) {
  const out: ({ index: number; request_id: string | null; decision: ReturnType<typeof decisionResponse> | null; error: string | null })[] = [];
  const pending: { index: number; input: TriageInput }[] = [];
  for (const [index, input] of items.entries()) {
    if (!input.text?.trim()) { out.push({ index, request_id: input.request_id ?? null, decision: null, error: "text is required" }); continue; }
    const existing = input.request_id ? await findByRequestId(db, input.request_id) : undefined;
    if (existing) { out.push({ index, request_id: input.request_id ?? null, decision: decisionResponse(existing), error: null }); continue; }
    pending.push({ index, input });
  }
  if (pending.length) {
    const t0 = Date.now();
    const res = await ml("post", "/score/batch", { body: { items: pending.map((p) => ({ text: p.input.text, request_id: p.input.request_id ?? null })) } });
    const latency = Math.round((Date.now() - t0) / pending.length);
    for (const item of res.items) {
      const p = pending[item.index];
      if (item.result) out.push({ index: p.index, request_id: p.input.request_id ?? null, decision: decisionResponse(await insertDecision(db, p.input, item.result, latency)), error: null });
      else out.push({ index: p.index, request_id: p.input.request_id ?? null, decision: null, error: item.error ?? "scoring failed" });
    }
  }
  out.sort((a, b) => a.index - b.index);
  return { items: out };
}

export async function getDecision(db: Db, decisionId: string) {
  const d = await db.select().from(decisions).where(eq(decisions.decisionId, decisionId)).get();
  if (!d) throw new HttpError(404, `decision ${decisionId} not found`);
  return d;
}
