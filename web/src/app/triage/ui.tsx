"use client";
import { useState } from "react";
import { api, fmt } from "@/lib/client";
import { Msg } from "@/components/Msg";

type Decision = { decision_id: string; request_id: string | null; text: string; probability: number; predicted_label: number; final_label: number | null; resolved_by: string; action: string; model_version: string; policy_version: string; reason: string | null; created_at: string; feedback: { label: number; labeler: string; training_eligible: boolean } | null };

export function TriageClient({ initial, datasets }: { initial: Decision[]; datasets: { id: string; name: string }[] }) {
  const [text, setText] = useState(""); const [batch, setBatch] = useState("");
  const [decisions, setDecisions] = useState<Decision[]>(initial);
  const [datasetId, setDatasetId] = useState(datasets[0]?.id ?? ""); const [labeler, setLabeler] = useState("me");
  const [err, setErr] = useState<string | null>(null); const [info, setInfo] = useState<string | null>(null); const [busy, setBusy] = useState(false);

  const reload = async () => setDecisions((await api<{ decisions: Decision[] }>("/api/decisions?limit=30")).decisions);
  async function one(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null); setInfo(null);
    try { const d = await api<Decision & { duplicate: boolean }>("/api/triage", { method: "POST", json: { text, request_id: `ui-${crypto.randomUUID()}`, source: "ui" } }); setInfo(`${d.action} · p=${fmt(d.probability)} · ${d.resolved_by}`); setText(""); await reload(); }
    catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }
  async function many(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null); setInfo(null);
    const items = batch.split("\n").map((t) => t.trim()).filter(Boolean).map((t) => ({ text: t, source: "ui-batch" }));
    try { const r = await api<{ items: { error: string | null }[] }>("/api/triage/batch", { method: "POST", json: { items } }); setInfo(`${r.items.filter((i) => !i.error).length}/${r.items.length} scored`); setBatch(""); await reload(); }
    catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }
  async function override(d: Decision, label: 0 | 1) {
    setBusy(true); setErr(null); setInfo(null);
    try { const f = await api<{ training_eligible: boolean; row_id: string; duplicate: boolean }>("/api/feedback", { method: "POST", json: { decision_id: d.decision_id, label, labeler, dataset_id: datasetId || null } });
      setInfo(`feedback recorded → row ${f.row_id}${f.training_eligible ? " (eligible for the next training snapshot)" : " (evaluation row: audit only)"}`); await reload(); }
    catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }
  return (
    <>
      <h1>Triage</h1>
      <div className="grid">
        <form onSubmit={one} className="card"><h3>Single message</h3><textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="customer message" required /><div className="row"><button className="primary" disabled={busy}>Score</button></div></form>
        <form onSubmit={many} className="card"><h3>Batch (one per line)</h3><textarea rows={4} value={batch} onChange={(e) => setBatch(e.target.value)} required /><div className="row"><button disabled={busy}>Score all</button></div></form>
      </div>
      <Msg error={err} info={info} />
      <h2>Recent decisions</h2>
      <div className="row muted">Human override writes feedback against the decision and model version. <label>labeler <input value={labeler} onChange={(e) => setLabeler(e.target.value)} style={{ width: 100 }} /></label>
        {datasets.length > 1 && <label>dataset for new rows <select value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>{datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>}</div>
      <table><thead><tr><th>text</th><th>p(1)</th><th>action</th><th>final</th><th>resolved by</th><th>reason</th><th>model · policy</th><th>human</th></tr></thead>
        <tbody>{decisions.map((d) => <tr key={d.decision_id}>
          <td style={{ maxWidth: 360 }}>{d.text.slice(0, 160)}</td><td>{fmt(d.probability)}</td><td><span className={`pill ${d.action}`}>{d.action}</span></td><td>{d.final_label ?? "pending"}</td><td>{d.resolved_by}</td><td className="muted">{d.reason}</td>
          <td className="muted"><code>{d.model_version}</code><br /><code>{d.policy_version}</code></td>
          <td>{d.feedback ? <span className="pill">{d.feedback.label} by {d.feedback.labeler}{d.feedback.training_eligible ? "" : " (audit)"}</span> : <span className="row"><button className="pos" disabled={busy} onClick={() => override(d, 1)}>1</button><button className="neg" disabled={busy} onClick={() => override(d, 0)}>0</button></span>}</td>
        </tr>)}</tbody></table>
    </>
  );
}
