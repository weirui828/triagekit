import Link from "next/link";
import { db } from "@/db";
import { listDatasets } from "@/lib/datasets";
import { ml } from "@/lib/ml";

export default async function Home() {
  const [health, prod, datasets] = await Promise.all([
    ml("get", "/health").catch((e) => ({ error: String(e) })),
    ml("get", "/registry/production").catch(() => null),
    db().then(listDatasets).catch(() => []),
  ]);
  return (
    <>
      <h1>Overview</h1>
      <div className="grid">
        <div className="card"><h3>ML service</h3><pre>{JSON.stringify(health, null, 1)}</pre></div>
        <div className="card"><h3>Production model</h3>
          {prod ? <p>version <b>{prod.version ?? "none"}</b> · loaded <code>{prod.loaded_version ?? "–"}</code> · source {prod.source}</p> : <p className="err">unavailable</p>}
          <p className="muted">Promote and roll back on the <Link href="/train">Train</Link> page.</p></div>
        <div className="card"><h3>Datasets</h3>
          {datasets.length === 0 ? <p>None yet. <Link href="/datasets">Create one</Link>.</p> :
            <ul>{datasets.map((d) => <li key={d.id}><Link href={`/datasets/${d.id}`}>{d.name}</Link> · {d.row_count} rows · contract {d.contract_version}</li>)}</ul>}
        </div>
      </div>
      <p className="muted">Local single-user tool: no accounts. Workflow: Datasets (import, snapshot) → Label (events only) → Train (jobs, runs, promote) → Triage (score, override) → Monitor.</p>
    </>
  );
}
