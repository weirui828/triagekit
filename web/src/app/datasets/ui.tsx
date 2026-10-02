"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Msg } from "@/components/Msg";

type Ds = { id: string; name: string; contract_version: string; created_at: string; row_count: number };

export function DatasetsClient({ datasets, exampleContract }: { datasets: Ds[]; exampleContract: string }) {
  const router = useRouter();
  const [name, setName] = useState(""); const [contract, setContract] = useState(exampleContract); const [seed, setSeed] = useState(42);
  const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  async function create(e: React.FormEvent) {
    e.preventDefault(); setErr(null); setBusy(true);
    try {
      const parsed = await api<{ ok: boolean; contract: unknown; errors: string[] }>("/api/contract/parse", { method: "POST", json: { text: contract } });
      if (!parsed.ok) throw new Error(parsed.errors.join("; "));
      const d = await api<Ds>("/api/datasets", { method: "POST", json: { name, contract: parsed.contract, split_seed: seed } });
      router.push(`/datasets/${d.id}`);
    } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }
  return (
    <>
      <h1>Datasets</h1>
      {datasets.length === 0 ? <p className="muted">No datasets yet.</p> : (
        <table><thead><tr><th>name</th><th>contract</th><th>rows</th><th>created</th></tr></thead>
          <tbody>{datasets.map((d) => <tr key={d.id}><td><Link href={`/datasets/${d.id}`}>{d.name}</Link></td><td>{d.contract_version}</td><td>{d.row_count}</td><td className="muted">{d.created_at.slice(0, 19)}</td></tr>)}</tbody></table>)}
      <h2>Create dataset</h2>
      <form onSubmit={create} className="card">
        <div className="row"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="name" required /> <label>split seed <input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} style={{ width: 90 }} /></label></div>
        <p className="muted">Label contract (YAML or JSON). The contract is validated by the Python service before the dataset is created.</p>
        <textarea className="mono" rows={18} value={contract} onChange={(e) => setContract(e.target.value)} />
        <div className="row"><button className="primary" disabled={busy}>Create</button><Msg error={err} /></div>
      </form>
    </>
  );
}
