import { db } from "@/db";
import { getDataset, listDatasets } from "@/lib/datasets";
import { ml } from "@/lib/ml";
import { LabelClient } from "./ui";

export default async function Label({ searchParams }: { searchParams: Promise<{ dataset?: string }> }) {
  const { dataset } = await searchParams;
  const dbc = await db();
  const datasets = await listDatasets(dbc);
  const id = dataset ?? datasets[0]?.id;
  if (!id) return <><h1>Label</h1><p>No datasets yet.</p></>;
  const d = await getDataset(dbc, id);
  const contract = JSON.parse(d.contractJson) as { categories: { allowed: string[]; required: boolean }; positive: { name: string; definition: string }; negative: { name: string; definition: string } };
  const health = await ml("get", "/health").catch(() => null);
  return <LabelClient datasets={datasets.map((x) => ({ id: x.id, name: x.name }))} datasetId={id} contract={contract} llmEnabled={!!health?.llm_enabled} />;
}
