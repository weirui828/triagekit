import { and, eq } from "drizzle-orm";
import { createHash } from "node:crypto";
import type { Db } from "@/db";
import { datasets, decisions, feedback, labelEvents, rows } from "@/db/schema";
import { HttpError, newId, now } from "./http";
import { getDecision } from "./triage";

export type FeedbackInput = {
  decision_id: string; label: 0 | 1; category?: string | null; labeler?: string; reason?: string | null;
  feedback_id?: string | null; dataset_id?: string | null;
};

/**
 * Human feedback on a decision. Idempotent on feedback_id (or a hash of decision+label+labeler).
 * Train rows get a label-setting `human` event; validation/test rows get a `human_audit` annotation only.
 */
export async function submitFeedback(db: Db, input: FeedbackInput) {
  if (input.label !== 0 && input.label !== 1) throw new HttpError(400, "label must be 0 or 1");
  const labeler = input.labeler ?? "api";
  const fid = input.feedback_id ?? createHash("sha256").update(`${input.decision_id}|${input.label}|${input.category ?? ""}|${labeler}`).digest("hex").slice(0, 32);
  const existing = await db.select().from(feedback).where(eq(feedback.feedbackId, fid)).get();
  if (existing) return { ...present(existing), duplicate: true };

  const decision = await getDecision(db, input.decision_id);
  return db.transaction(async (tx) => {
    let datasetId = decision.datasetId ?? input.dataset_id ?? null;
    if (!datasetId) {
      const ds = await tx.select({ id: datasets.id }).from(datasets).orderBy(datasets.createdAt);
      if (ds.length !== 1) throw new HttpError(400, "dataset_id is required when the decision is not tied to a dataset and more than one dataset exists");
      datasetId = ds[0].id;
    }
    const ds = await tx.select().from(datasets).where(eq(datasets.id, datasetId)).get();
    if (!ds) throw new HttpError(404, `dataset ${datasetId} not found`);
    const contract = JSON.parse(ds.contractJson) as { categories: { allowed: string[] } };
    if (input.category && contract.categories.allowed.length && !contract.categories.allowed.includes(input.category)) throw new HttpError(400, `category ${input.category} not in contract`);

    let rowId = decision.rowId;
    if (!rowId) {
      rowId = `prod-${decision.decisionId}`;
      const dup = await tx.select({ id: rows.id, split: rows.split, groupId: rows.groupId }).from(rows).where(and(eq(rows.datasetId, datasetId), eq(rows.text, decision.text))).get();
      // New reviewed production examples default to train; identical text inherits the existing row's split.
      const split = dup ? dup.split : "train";
      await tx.insert(rows).values({ datasetId, id: rowId, text: decision.text, category: input.category ?? null, split, source: `production:${decision.decisionId}`, groupId: dup?.groupId ?? null, createdAt: now() });
      await tx.update(decisions).set({ datasetId, rowId }).where(eq(decisions.decisionId, decision.decisionId));
    }
    const row = (await tx.select().from(rows).where(and(eq(rows.datasetId, datasetId), eq(rows.id, rowId))).get())!;
    const eligible = row.split === "train" || row.split === "unassigned";
    const eventId = newId();
    await tx.insert(labelEvents).values({ eventId, datasetId, rowId, label: input.label, category: input.category ?? null, labeler, at: now(), reason: input.reason ?? null, kind: eligible ? "human" : "human_audit", contractVersion: ds.contractVersion, decisionId: decision.decisionId });
    const rec = {
      feedbackId: fid, decisionId: decision.decisionId, modelVersion: decision.modelVersion, label: input.label, category: input.category ?? null, labeler, reason: input.reason ?? null,
      datasetId, rowId, eventId, trainingEligible: eligible, createdAt: now(),
    };
    await tx.insert(feedback).values(rec);
    return { ...present(rec), duplicate: false };
  });
}

function present(f: typeof feedback.$inferSelect) {
  return {
    feedback_id: f.feedbackId, decision_id: f.decisionId, model_version: f.modelVersion, label: f.label, category: f.category, labeler: f.labeler,
    dataset_id: f.datasetId, row_id: f.rowId, event_id: f.eventId, training_eligible: f.trainingEligible, created_at: f.createdAt,
  };
}
