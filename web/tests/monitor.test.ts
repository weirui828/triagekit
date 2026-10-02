import { describe, expect, it } from "vitest";
import { decisions, feedback } from "@/db/schema";
import { histogram, monitor } from "@/lib/monitor";
import { freshDb } from "./helpers";

describe("monitor", () => {
  it("bins scores and reports rates with denominators per version", async () => {
    expect(histogram([0, 0.05, 0.95, 1.0])).toEqual([2, 0, 0, 0, 0, 0, 0, 0, 0, 2]);
    const db = await freshDb();
    const now = new Date().toISOString();
    const mk = (id: string, p: number, action: string, final: number | null, mv = "m:1") => ({ decisionId: id, requestId: id, text: "t", probability: p, predictedLabel: p >= 0.5 ? 1 : 0, finalLabel: final, resolvedBy: final === null ? "human_pending" : "model", action, modelVersion: mv, policyVersion: "p", latencyMs: 1, createdAt: now });
    await db.insert(decisions).values([mk("a", 0.1, "auto_handle", 0), mk("b", 0.5, "review", null), mk("c", 0.9, "escalate", 1), mk("d", 0.2, "auto_handle", 0, "m:2")]);
    const fb = (id: string, label: number) => ({ feedbackId: `f${id}`, decisionId: id, modelVersion: "m:1", label, labeler: "x", datasetId: "d", rowId: "r", eventId: "e", trainingEligible: true, createdAt: now });
    await db.insert(feedback).values([fb("a", 1), fb("c", 1)]); // a overridden, c confirmed
    const m = await monitor(db, 1);
    const v1 = m.by_version.find((b) => b.model_version === "m:1")!;
    expect(v1.decisions).toBe(3);
    expect(v1.review_fraction).toBeCloseTo(1 / 3);
    expect(v1.reviewed).toBe(2); expect(v1.review_coverage).toBeCloseTo(2 / 3);
    expect(v1.overrides).toBe(1); expect(v1.override_rate).toBeCloseTo(0.5);
    const v2 = m.by_version.find((b) => b.model_version === "m:2")!;
    expect(v2.override_rate).toBeNull(); // zero reviewed: undefined, not 0
  });
});
