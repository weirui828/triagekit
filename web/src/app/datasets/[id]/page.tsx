import { db } from "@/db";
import { datasetSummary, listRows } from "@/lib/datasets";
import { DatasetClient } from "./ui";

export default async function Dataset({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ split?: string }> }) {
  const { id } = await params; const { split } = await searchParams;
  const dbc = await db();
  const summary = await datasetSummary(dbc, id);
  const rows = await listRows(dbc, id, { split, limit: 50 });
  return <DatasetClient summary={summary} rows={rows.rows} total={rows.total} split={split ?? ""} />;
}
