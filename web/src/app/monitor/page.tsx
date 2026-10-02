import { db } from "@/db";
import { monitor, referenceDistribution } from "@/lib/monitor";
import { MonitorClient } from "./ui";

export default async function Monitor({ searchParams }: { searchParams: Promise<{ days?: string }> }) {
  const days = Number((await searchParams).days ?? 30);
  const [m, ref] = await Promise.all([monitor(await db(), days), referenceDistribution().catch(() => null)]);
  return <MonitorClient data={{ ...m, reference: ref }} />;
}
