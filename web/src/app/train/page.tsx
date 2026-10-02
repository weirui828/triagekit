import { db } from "@/db";
import { listDatasets, listSnapshots } from "@/lib/datasets";
import { TrainClient } from "./ui";

export default async function Train() {
  const dbc = await db();
  const datasets = await listDatasets(dbc);
  const snapshots = (await Promise.all(datasets.map(async (d) => (await listSnapshots(dbc, d.id)).map((s) => ({ id: s.snapshot_id, dataset: d.name, hash: s.snapshot_hash.slice(0, 8), labeled: s.labeled_count, splits: s.split_counts, created: s.created_at }))))).flat();
  return <TrainClient snapshots={snapshots} />;
}
