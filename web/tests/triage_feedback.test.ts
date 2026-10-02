import { afterEach, describe, expect, it, vi } from "vitest";
import { datasets, labelEvents, rows } from "@/db/schema";
import { submitFeedback } from "@/lib/feedback";
import { triageBatch, triageOne } from "@/lib/triage";
import { contract, freshDb, score, stubMl } from "./helpers";

afterEach(() => vi.restoreAllMocks());

async function seed(db: Awaited<ReturnType<typeof freshDb>>) {
  await db.insert(datasets).values({ id: "d", name: "d", contractJson: JSON.stringify(contract), contractVersion: "1.0", contractHash: "h", createdAt: "t" });
  await db.insert(rows).values({ datasetId: "d", id: "t1", text: "test text", split: "test", createdAt: "t" });
}

describe("triage", () => {
  it("is idempotent on request_id and preserves batch order with per-item failures", async () => {
    const db = await freshDb();
    let calls = 0;
    stubMl({
      "/score": () => { calls++; return score(0.9); },
      "/score/batch": (b) => ({ model_version: "triagekit:1", items: (b as { items: { text: string; request_id: string | null }[] }).items.map((it, index) => it.text === "boom" ? { index, request_id: it.request_id, result: null, error: "bad" } : { index, request_id: it.request_id, result: score(0.1), error: null }) }),
    });
    const a = await triageOne(db, { text: "refund", request_id: "req-1" });
    const b = await triageOne(db, { text: "refund", request_id: "req-1" });
    expect(a.decision_id).toBe(b.decision_id);
    expect(b.duplicate).toBe(true);
    expect(calls).toBe(1);
    expect(a.action).toBe("escalate");
    const batch = await triageBatch(db, [{ text: "x", request_id: "req-1" }, { text: "boom" }, { text: "" }, { text: "ok" }]);
    expect(batch.items.map((i) => i.index)).toEqual([0, 1, 2, 3]);
    expect(batch.items[0].decision?.decision_id).toBe(a.decision_id);
    expect(batch.items[1].error).toBe("bad");
    expect(batch.items[2].error).toMatch(/required/);
    expect(batch.items[3].decision?.action).toBe("auto_handle");
  });
});

describe("feedback", () => {
  it("is idempotent, creates a train row for unseen text, and audits evaluation rows", async () => {
    const db = await freshDb();
    await seed(db);
    stubMl({ "/score": () => score(0.5) });
    const d = await triageOne(db, { text: "brand new production text", request_id: "r1" });
    expect(d.action).toBe("review");
    const f1 = await submitFeedback(db, { decision_id: d.decision_id, label: 1, labeler: "me", category: "billing" });
    const f2 = await submitFeedback(db, { decision_id: d.decision_id, label: 1, labeler: "me", category: "billing" });
    expect(f1.feedback_id).toBe(f2.feedback_id);
    expect(f2.duplicate).toBe(true);
    expect(f1.training_eligible).toBe(true);
    expect(await db.select().from(labelEvents)).toHaveLength(1);
    const r = (await db.select().from(rows)).find((x) => x.id === f1.row_id)!;
    expect(r.split).toBe("train");
    expect(r.source).toMatch(/^production:/);
    await expect(submitFeedback(db, { decision_id: d.decision_id, label: 1, category: "nope" })).rejects.toThrow(/category/);

    // text identical to a test-split row inherits that split and only produces an audit event
    const d2 = await triageOne(db, { text: "test text", request_id: "r2" });
    const f3 = await submitFeedback(db, { decision_id: d2.decision_id, label: 0 });
    expect(f3.training_eligible).toBe(false);
    const evs = await db.select().from(labelEvents);
    expect(evs.find((e) => e.eventId === f3.event_id)?.kind).toBe("human_audit");
  });
});
