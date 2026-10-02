import { and, gte, sql } from "drizzle-orm";
import type { Db } from "@/db";
import { decisions, feedback } from "@/db/schema";
import { ml } from "./ml";

export const BINS = 10;

export function histogram(values: number[]): number[] {
  const h = new Array(BINS).fill(0);
  for (const v of values) h[Math.min(BINS - 1, Math.max(0, Math.floor(v * BINS)))]++;
  return h;
}

/**
 * Monitoring aggregates stratified by model/policy version. Every rate carries its denominator.
 * Override rate = overrides / reviewed decisions; review coverage = reviewed / all decisions.
 * Unreviewed decisions are not confirmed correct; score-distribution shift is a drift indicator only.
 */
export async function monitor(db: Db, days = 30) {
  const since = new Date(Date.now() - days * 86400_000).toISOString();
  const ds = await db.select().from(decisions).where(gte(decisions.createdAt, since));
  const fb = await db.select().from(feedback).where(gte(feedback.createdAt, since));
  const fbByDecision = new Map<string, typeof fb[number]>();
  for (const f of fb) if (!fbByDecision.has(f.decisionId)) fbByDecision.set(f.decisionId, f);

  type Bucket = { decisions: number; auto_handle: number; escalate: number; review: number; reviewed: number; overrides: number; scores: number[] };
  const mk = (): Bucket => ({ decisions: 0, auto_handle: 0, escalate: 0, review: 0, reviewed: 0, overrides: 0, scores: [] });
  const byVersion = new Map<string, Bucket>();
  const byDay = new Map<string, Map<string, Bucket>>();
  for (const d of ds) {
    const key = `${d.modelVersion}|${d.policyVersion}`;
    const day = d.createdAt.slice(0, 10);
    for (const b of [byVersion.get(key) ?? byVersion.set(key, mk()).get(key)!, (byDay.get(day) ?? byDay.set(day, new Map()).get(day)!).get(key) ?? (byDay.get(day)!.set(key, mk()), byDay.get(day)!.get(key)!)]) {
      b.decisions++;
      b[d.action as "auto_handle" | "escalate" | "review"]++;
      b.scores.push(d.probability);
      const f = fbByDecision.get(d.decisionId);
      if (f) {
        b.reviewed++;
        if (d.finalLabel !== null && f.label !== d.finalLabel) b.overrides++;
        if (d.finalLabel === null && f.label !== d.predictedLabel) b.overrides++;
      }
    }
  }
  const rate = (n: number, d: number) => (d ? n / d : null);
  const present = (b: Bucket) => ({
    decisions: b.decisions, actions: { auto_handle: b.auto_handle, escalate: b.escalate, review: b.review },
    review_fraction: rate(b.review, b.decisions), reviewed: b.reviewed, review_coverage: rate(b.reviewed, b.decisions),
    overrides: b.overrides, override_rate: rate(b.overrides, b.reviewed), score_histogram: histogram(b.scores),
  });
  return {
    days, since, total_decisions: ds.length, total_feedback: fb.length,
    by_version: [...byVersion.entries()].map(([k, b]) => { const [model_version, policy_version] = k.split("|"); return { model_version, policy_version, ...present(b) }; }),
    by_day: [...byDay.entries()].sort().map(([day, m]) => ({ day, versions: [...m.entries()].map(([k, b]) => { const [model_version, policy_version] = k.split("|"); return { model_version, policy_version, ...present(b) }; }) })),
  };
}

/** Fixed reference: the production run's held-out test score distribution. */
export async function referenceDistribution() {
  const prod = await ml("get", "/registry/production");
  if (!prod.run_id) return null;
  const p = await ml("get", "/runs/{run_id}/predictions", { params: { run_id: prod.run_id } });
  return { run_id: prod.run_id, model_version: prod.loaded_version, n: p.rows.length, score_histogram: histogram(p.rows.map((r) => r.probability)) };
}

export async function recentDecisions(db: Db, limit = 50) {
  const ds = await db.select().from(decisions).orderBy(sql`${decisions.createdAt} desc`).limit(limit);
  const fb = ds.length ? await db.select().from(feedback).where(and(sql`${feedback.decisionId} in (${sql.join(ds.map((d) => sql`${d.decisionId}`), sql`, `)})`)) : [];
  const fbBy = new Map(fb.map((f) => [f.decisionId, f]));
  return ds.map((d) => ({
    decision_id: d.decisionId, request_id: d.requestId, text: d.text, probability: d.probability, predicted_label: d.predictedLabel, final_label: d.finalLabel,
    resolved_by: d.resolvedBy, action: d.action, model_version: d.modelVersion, policy_version: d.policyVersion, reason: d.reason, created_at: d.createdAt,
    feedback: fbBy.has(d.decisionId) ? { label: fbBy.get(d.decisionId)!.label, labeler: fbBy.get(d.decisionId)!.labeler, training_eligible: fbBy.get(d.decisionId)!.trainingEligible } : null,
  }));
}
