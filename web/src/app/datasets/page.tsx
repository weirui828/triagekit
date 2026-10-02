import { db } from "@/db";
import { listDatasets } from "@/lib/datasets";
import { DatasetsClient } from "./ui";
import { readFileSync } from "node:fs";
import path from "node:path";

export default async function Datasets() {
  const datasets = await listDatasets(await db());
  let exampleContract = "";
  try { exampleContract = readFileSync(path.join(process.cwd(), "..", "ml", "examples", "support_demo.contract.yaml"), "utf8"); } catch {}
  return <DatasetsClient datasets={datasets} exampleContract={exampleContract} />;
}
