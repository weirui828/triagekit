import { and, eq, inArray, sql } from "drizzle-orm";
import type { Db } from "@/db";
import { datasets, labelEvents, rows, snapshots } from "@/db/schema";
import { HttpError, newId, now } from "./http";
import { resolveLabels } from "./labels";
import { ml, type S } from "./ml";

export async function createDataset(db: Db, name: string, contract: unknown, splitSeed = 42) {
  const v = await ml("post", "/contract/validate", { body: contract as Record<string, never> });
  if (!v.ok || !v.contract || !v.contract_hash) throw new HttpError(400, "invalid contract", v.errors);
  const id = newId();
  await db.insert(datasets).values({ id, name, contractJson: JSON.stringify(v.contract), contractVersion: v.contract.contract_version, contractHash: v.contract_hash, splitSeed, createdAt: now() });
  return getDataset(db, id);
}

export async function getDataset(db: Db, id: string) {
  const d = await db.select().from(datasets).where(eq(datasets.id, id)).get();
  if (!d) throw new HttpError(404, `dataset ${id} not found`);
  return d;
}

export function contractOf(d: typeof datasets.$inferSelect): S["LabelContract"] {
  return JSON.parse(d.contractJson) as S["LabelContract"];
}

export async function datasetSummary(db: Db, id: string) {
  const d = await getDataset(db, id);
  const resolved = await resolveLabels(db, id);
  const all = await db.select({ id: rows.id, split: rows.split, category: rows.category }).from(rows).where(eq(rows.datasetId, id));
  const count = (f: (r: (typeof all)[number]) => string) => {
    const m: Record<string, number> = {};
    for (const r of all) m[f(r)] = (m[f(r)] ?? 0) + 1;
    return Object.fromEntries(Object.entries(m).sort());
  };
  const labelOf = (r: { id: string }) => String(resolved.get(r.id)?.label ?? "unlabeled");
  const snaps = await db.select({ id: snapshots.id, snapshotHash: snapshots.snapshotHash, createdAt: snapshots.createdAt }).from(snapshots).where(eq(snapshots.datasetId, id));
  return {
    id: d.id, name: d.name, contract_version: d.contractVersion, contract_hash: d.contractHash, created_at: d.createdAt,
    row_count: all.length, label_counts: count(labelOf), split_counts: count((r) => r.split),
    category_counts: count((r) => r.category ?? "none"), snapshots: snaps,
  };
}

/** Validate the whole CSV in Python, then commit rows + imported label events in one transaction. */
export async function importCsv(db: Db, datasetId: string, csv: string, labeler = "import") {
  const d = await getDataset(db, datasetId);
  const res = await ml("post", "/import/validate", { body: { contract: contractOf(d), csv } });
  if (!res.report.ok) return { committed: false, report: res.report };
  const ids = res.rows.map((r) => r.id);
  const existing = ids.length ? await db.select({ id: rows.id }).from(rows).where(and(eq(rows.datasetId, datasetId), inArray(rows.id, ids))) : [];
  if (existing.length) {
    return {
      committed: false,
      report: { ...res.report, ok: false, accepted_count: 0, errors: existing.slice(0, 500).map((e) => ({ line: 0, id: e.id, field: "id", message: "id already exists in dataset" })) },
    };
  }
  const t = now();
  await db.transaction(async (tx) => {
    for (const r of res.rows) {
      await tx.insert(rows).values({ datasetId, id: r.id, text: r.text, category: r.category ?? null, split: r.split, source: r.source ?? null, groupId: r.group_id ?? null, createdAt: t });
      if (r.label !== null && r.label !== undefined) {
        await tx.insert(labelEvents).values({ eventId: newId(), datasetId, rowId: r.id, label: r.label, category: r.category ?? null, labeler, at: t, reason: null, kind: "imported", contractVersion: d.contractVersion, decisionId: null });
      }
    }
  });
  return { committed: true, report: res.report };
}

export async function listRows(db: Db, datasetId: string, opts: { split?: string; labeled?: "labeled" | "unlabeled"; limit?: number; offset?: number } = {}) {
  await getDataset(db, datasetId);
  const resolved = await resolveLabels(db, datasetId);
  const where = opts.split ? and(eq(rows.datasetId, datasetId), eq(rows.split, opts.split)) : eq(rows.datasetId, datasetId);
  let rs = (await db.select().from(rows).where(where).orderBy(rows.id)).map((r) => ({ id: r.id, text: r.text, label: resolved.get(r.id)?.label ?? null, category: resolved.get(r.id)?.category ?? r.category, split: r.split, source: r.source, group_id: r.groupId }));
  if (opts.labeled === "labeled") rs = rs.filter((r) => r.label !== null);
  if (opts.labeled === "unlabeled") rs = rs.filter((r) => r.label === null);
  const total = rs.length;
  return { total, rows: rs.slice(opts.offset ?? 0, (opts.offset ?? 0) + (opts.limit ?? 100)) };
}

async function canonicalRows(db: Db, datasetId: string): Promise<S["Row"][]> {
  const resolved = await resolveLabels(db, datasetId);
  return (await db.select().from(rows).where(eq(rows.datasetId, datasetId)).orderBy(rows.id)).map((r) => ({
    id: r.id, text: r.text, label: resolved.get(r.id)?.label ?? null, category: r.category, split: r.split as S["Row"]["split"], source: r.source, group_id: r.groupId,
  }));
}

/** Splits are assigned once (first training-ready snapshot) and persisted on the dataset; later snapshots reuse them. */
export async function assignMissingSplits(db: Db, datasetId: string) {
  const d = await getDataset(db, datasetId);
  const all = await canonicalRows(db, datasetId);
  if (!all.some((r) => r.split === "unassigned")) return { assigned: 0 };
  const res = await ml("post", "/splits/assign", { body: { rows: all, seed: d.splitSeed } });
  if (!res.ok) throw new HttpError(409, "split assignment rejected", res.errors);
  const current = new Map(all.map((r) => [r.id, r.split]));
  let assigned = 0;
  await db.transaction(async (tx) => {
    for (const a of res.assignments) {
      const cur = current.get(a.id);
      if (cur !== "unassigned") {
        if (cur !== a.split) throw new HttpError(409, `split assignment would change fixed split of row ${a.id}`);
        continue;
      }
      await tx.update(rows).set({ split: a.split }).where(and(eq(rows.datasetId, datasetId), eq(rows.id, a.id)));
      assigned++;
    }
  });
  return { assigned, strategy: res.strategy };
}

export async function createSnapshot(db: Db, datasetId: string, preprocessing?: S["PreprocessingConfig"]) {
  const d = await getDataset(db, datasetId);
  await assignMissingSplits(db, datasetId);
  const all = await canonicalRows(db, datasetId);
  const id = newId();
  const res = await ml("post", "/snapshots/export", { body: { snapshot_id: id, dataset_id: datasetId, contract: contractOf(d), preprocessing, rows: all } });
  await db.insert(snapshots).values({ id, datasetId, snapshotHash: res.manifest.snapshot_hash, manifestJson: JSON.stringify(res.manifest), createdAt: now() });
  return res.manifest;
}

export async function listSnapshots(db: Db, datasetId: string) {
  await getDataset(db, datasetId);
  return (await db.select().from(snapshots).where(eq(snapshots.datasetId, datasetId))).map((s) => JSON.parse(s.manifestJson) as S["SnapshotManifest"]);
}

export function listDatasets(db: Db) {
  return db
    .select({ id: datasets.id, name: datasets.name, contract_version: datasets.contractVersion, created_at: datasets.createdAt, row_count: sql<number>`(select count(*) from rows where rows.dataset_id = datasets.id)` })
    .from(datasets);
}
