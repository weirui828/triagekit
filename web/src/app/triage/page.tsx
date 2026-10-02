import { db } from "@/db";
import { listDatasets } from "@/lib/datasets";
import { recentDecisions } from "@/lib/monitor";
import { TriageClient } from "./ui";

export default async function Triage() {
  const dbc = await db();
  const [decisions, datasets] = await Promise.all([recentDecisions(dbc, 30), listDatasets(dbc)]);
  return <TriageClient initial={decisions} datasets={datasets.map((d) => ({ id: d.id, name: d.name }))} />;
}
