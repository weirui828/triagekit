import { describe, expect, it } from "vitest";
import { datasets, labelEvents, rows } from "@/db/schema";
import { resolveLabels } from "@/lib/labels";
import { contract, freshDb } from "./helpers";

describe("label resolution", () => {
  it("uses the latest label-setting event and ignores suggestions and audit annotations", async () => {
    const db = await freshDb();
    await db.insert(datasets).values({ id: "d", name: "d", contractJson: JSON.stringify(contract), contractVersion: "1.0", contractHash: "h", createdAt: "t" });
    await db.insert(rows).values({ datasetId: "d", id: "r", text: "x", split: "train", createdAt: "t" });
    const ev = (kind: string, label: number | null) => ({ eventId: `${kind}-${label}-${Math.random()}`, datasetId: "d", rowId: "r", label, category: null, labeler: "t", at: "t", reason: null, kind, contractVersion: "1.0", decisionId: null });
    await db.insert(labelEvents).values(ev("imported", 0));
    expect((await resolveLabels(db, "d")).get("r")?.label).toBe(0);
    await db.insert(labelEvents).values(ev("llm_suggestion", 1));
    expect((await resolveLabels(db, "d")).get("r")?.label).toBe(0);
    await db.insert(labelEvents).values(ev("human_audit", 1));
    expect((await resolveLabels(db, "d")).get("r")?.label).toBe(0);
    await db.insert(labelEvents).values(ev("human", 1));
    expect((await resolveLabels(db, "d")).get("r")?.label).toBe(1);
    await db.insert(labelEvents).values(ev("clear", null));
    expect((await resolveLabels(db, "d")).get("r")?.label).toBeNull();
    expect(await db.select().from(labelEvents)).toHaveLength(5); // history preserved
  });
});
