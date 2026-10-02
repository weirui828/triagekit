import { afterEach, describe, expect, it, vi } from "vitest";
import { rows } from "@/db/schema";
import { createDataset, datasetSummary, importCsv } from "@/lib/datasets";
import { contract, freshDb, stubMl } from "./helpers";

afterEach(() => vi.restoreAllMocks());

const validated = (ok: boolean) => ({
  report: { ok, row_count: 2, accepted_count: ok ? 2 : 0, errors: ok ? [] : [{ line: 3, id: "b", field: "text", message: "empty text" }], duplicate_ids: [], label_counts: {}, category_counts: {}, split_counts: {}, group_split_conflicts: [] },
  rows: ok ? [{ id: "a", text: "hello", label: 1, category: "billing", split: "unassigned", source: null, group_id: null }, { id: "b", text: "world", label: null, category: null, split: "unassigned", source: null, group_id: null }] : [],
});

describe("import", () => {
  it("commits nothing when validation fails and everything when it passes", async () => {
    const db = await freshDb();
    let ok = false;
    stubMl({ "/contract/validate": () => ({ ok: true, errors: [], contract, contract_hash: "h" }), "/import/validate": () => validated(ok) });
    const ds = await createDataset(db, "d", contract);
    const bad = await importCsv(db, ds.id, "id,text\na,hello\nb,\n");
    expect(bad.committed).toBe(false);
    expect(await db.select().from(rows)).toHaveLength(0);
    ok = true;
    const good = await importCsv(db, ds.id, "id,text,label\na,hello,1\nb,world,\n");
    expect(good.committed).toBe(true);
    const s = await datasetSummary(db, ds.id);
    expect(s.row_count).toBe(2);
    expect(s.label_counts).toEqual({ "1": 1, unlabeled: 1 });
    // re-importing the same ids is rejected before any write
    const dup = await importCsv(db, ds.id, "id,text\na,again\n");
    expect(dup.committed).toBe(false);
    expect(dup.report.errors[0].message).toMatch(/already exists/);
    expect(await db.select().from(rows)).toHaveLength(2);
  });
});
