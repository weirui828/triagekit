"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Msg } from "@/components/Msg";

type Summary = { id: string; name: string; contract_version: string; contract_hash: string; row_count: number; label_counts: Record<string, number>; split_counts: Record<string, number>; category_counts: Record<string, number>; snapshots: { id: string; snapshotHash: string; createdAt: string }[] };
type Row = { id: string; text: string; label: 0 | 1 | null; category: string | null; split: string; source: string | null; group_id: string | null };
type Report = { ok: boolean; row_count: number; accepted_count: number; errors: { line: number; id: string | null; field: string | null; message: string }[]; duplicate_ids: string[]; label_counts: Record<string, number>; category_counts: Record<string, number>; split_counts: Record<string, number>; group_split_conflicts: string[] };

const Counts = ({ title, c }: { title: string; c: Record<string, number> }) => (
  <div className="card"><h3>{title}</h3><table><tbody>{Object.entries(c).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}</tbody></table></div>
);

export function DatasetClient({ summary, rows, total, split }: { summary: Summary; rows: Row[]; total: number; split: string }) {
  const router = useRouter();
  const [report, setReport] = useState<Report | null>(null); const [committed, setCommitted] = useState<boolean | null>(null);
  const [err, setErr] = useState<string | null>(null); const [info, setInfo] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  async function importFile(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault(); setErr(null); setReport(null); setBusy(true);
    const file = (e.currentTarget.elements.namedItem("file") as HTMLInputElement).files?.[0];
    if (!file) { setBusy(false); return; }
    try {
      const res = await fetch(`/api/datasets/${summary.id}/import`, { method: "POST", headers: { "content-type": "text/csv" }, body: await file.text() });
      const data = await res.json();
      if (!res.ok && !data.report) throw new Error(data.detail ?? data.error);
      setReport(data.report); setCommitted(data.committed);
      if (data.committed) router.refresh();
    } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }
  async function snapshot() {
    setBusy(true); setErr(null); setInfo(null);
    try {
      const m = await api<{ snapshot_id: string; split_counts: Record<string, number>; labeled_count: number }>(`/api/datasets/${summary.id}/snapshots`, { method: "POST", json: {} });
      setInfo(`snapshot ${m.snapshot_id} created: ${JSON.stringify(m.split_counts)}, ${m.labeled_count} labeled`); router.refresh();
    } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }
  return (
    <>
      <h1>{summary.name} <span className="muted">contract {summary.contract_version} · {summary.contract_hash.slice(0, 8)}</span></h1>
      <div className="row"><Link href={`/label?dataset=${summary.id}`}>Label this dataset →</Link><Link href="/train">Train →</Link></div>
      <div className="grid"><Counts title={`Labels (${summary.row_count} rows)`} c={summary.label_counts} /><Counts title="Splits" c={summary.split_counts} /><Counts title="Categories" c={summary.category_counts} /></div>

      <h2>Import CSV</h2>
      <form onSubmit={importFile} className="card">
        <p className="muted">Columns: id, text, label (0/1/empty), category, split, source, group_id. The whole file is validated first; any error means nothing is written.</p>
        <div className="row"><input type="file" name="file" accept=".csv,text/csv" required /><button className="primary" disabled={busy}>Validate &amp; import</button><Msg error={err} /></div>
      </form>
      {report && (
        <div className="card">
          <h3>{committed ? <span className="info">Import committed</span> : <span className="err">Import rejected — nothing written</span>}</h3>
          <p>rows {report.row_count} · accepted {report.accepted_count} · errors {report.errors.length} · duplicate ids {report.duplicate_ids.length} · split/group conflicts {report.group_split_conflicts.length}</p>
          <p className="muted">labels {JSON.stringify(report.label_counts)} · categories {JSON.stringify(report.category_counts)} · splits {JSON.stringify(report.split_counts)}</p>
          {report.errors.length > 0 && <table><thead><tr><th>line</th><th>id</th><th>field</th><th>message</th></tr></thead><tbody>{report.errors.slice(0, 100).map((e, i) => <tr key={i}><td>{e.line || "–"}</td><td>{e.id ?? "–"}</td><td>{e.field ?? "–"}</td><td>{e.message}</td></tr>)}</tbody></table>}
        </div>
      )}

      <h2>Snapshots</h2>
      <div className="card">
        <p className="muted">A snapshot freezes rows, resolved labels, contract, preprocessing and splits with content hashes. Splits are assigned at the first snapshot and never change afterwards.</p>
        <div className="row"><button className="primary" onClick={snapshot} disabled={busy}>Create snapshot</button><Msg error={null} info={info} /></div>
        {summary.snapshots.length > 0 && <table><thead><tr><th>id</th><th>hash</th><th>created</th></tr></thead><tbody>{summary.snapshots.map((s) => <tr key={s.id}><td><code>{s.id}</code></td><td><code>{s.snapshotHash.slice(0, 12)}</code></td><td className="muted">{s.createdAt.slice(0, 19)}</td></tr>)}</tbody></table>}
      </div>

      <h2>Rows <span className="muted">({total}{split ? ` in ${split}` : ""}, first 50)</span></h2>
      <div className="row">{["", "train", "validation", "test", "unassigned"].map((s) => <Link key={s} href={`/datasets/${summary.id}${s ? `?split=${s}` : ""}`} className="pill">{s || "all"}</Link>)}</div>
      <table><thead><tr><th>id</th><th>text</th><th>label</th><th>category</th><th>split</th><th>source</th><th>group</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.id}><td><code>{r.id}</code></td><td>{r.text.slice(0, 140)}</td><td>{r.label ?? "–"}</td><td>{r.category ?? "–"}</td><td>{r.split}</td><td className="muted">{r.source ?? ""}</td><td className="muted">{r.group_id ?? ""}</td></tr>)}</tbody></table>
    </>
  );
}
