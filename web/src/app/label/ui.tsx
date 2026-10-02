"use client";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/client";
import { Msg } from "@/components/Msg";

type Row = { id: string; text: string; label: 0 | 1 | null; category: string | null; split: string; source: string | null };
type Ev = { eventId: string; label: number | null; category: string | null; labeler: string; at: string; reason: string | null; kind: string; decisionId: string | null };
type Contract = { categories: { allowed: string[]; required: boolean }; positive: { name: string; definition: string }; negative: { name: string; definition: string } };

export function LabelClient({ datasets, datasetId, contract, llmEnabled }: { datasets: { id: string; name: string }[]; datasetId: string; contract: Contract; llmEnabled: boolean }) {
  const router = useRouter();
  const [mode, setMode] = useState<"unlabeled" | "labeled" | "all">("unlabeled");
  const [split, setSplit] = useState("");
  const [rows, setRows] = useState<Row[]>([]); const [total, setTotal] = useState(0); const [i, setI] = useState(0);
  const [labeler, setLabeler] = useState("me");
  const [err, setErr] = useState<string | null>(null);
  const row = rows[i];

  const load = useCallback(async () => {
    const q = new URLSearchParams({ limit: "200" }); if (mode !== "all") q.set("labeled", mode); if (split) q.set("split", split);
    const r = await api<{ total: number; rows: Row[] }>(`/api/datasets/${datasetId}/rows?${q}`);
    setRows(r.rows); setTotal(r.total); setI(0);
  }, [datasetId, mode, split]);
  useEffect(() => { const t = setTimeout(() => load().catch((e) => setErr(String(e))), 0); return () => clearTimeout(t); }, [load]);

  function onLabeled(label: 0 | 1 | null, category: string | null) {
    if (!row) return;
    if (mode === "unlabeled" && label !== null) { const rest = rows.filter((_, k) => k !== i); setRows(rest); setTotal((t) => t - 1); setI(Math.min(i, Math.max(0, rest.length - 1))); }
    else setRows(rows.map((x, k) => (k === i ? { ...x, label, category } : x)));
  }
  return (
    <>
      <h1>Label</h1>
      <div className="row">
        <select value={datasetId} onChange={(e) => router.push(`/label?dataset=${e.target.value}`)}>{datasets.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
        <select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}><option value="unlabeled">unlabeled (label from scratch)</option><option value="labeled">labeled (audit)</option><option value="all">all</option></select>
        <select value={split} onChange={(e) => setSplit(e.target.value)}><option value="">any split</option><option>train</option><option>validation</option><option>test</option><option>unassigned</option></select>
        <label>labeler <input value={labeler} onChange={(e) => setLabeler(e.target.value)} style={{ width: 110 }} /></label>
        <span className="muted">{total} rows · {rows.length ? i + 1 : 0}/{rows.length} loaded</span>
      </div>
      <div className="grid">
        <div className="card"><h3>{contract.positive.name} = 1</h3><p className="muted">{contract.positive.definition}</p></div>
        <div className="card"><h3>{contract.negative.name} = 0</h3><p className="muted">{contract.negative.definition}</p></div>
      </div>
      <Msg error={err} />
      {!row ? <p>No rows match.</p> : (
        <RowEditor key={row.id} row={row} datasetId={datasetId} contract={contract} llmEnabled={llmEnabled} labeler={labeler} onLabeled={onLabeled}
          prev={i > 0 ? () => setI(i - 1) : undefined} next={i < rows.length - 1 ? () => setI(i + 1) : undefined} />
      )}
    </>
  );
}

function RowEditor({ row, datasetId, contract, llmEnabled, labeler, onLabeled, prev, next }: { row: Row; datasetId: string; contract: Contract; llmEnabled: boolean; labeler: string; onLabeled: (l: 0 | 1 | null, c: string | null) => void; prev?: () => void; next?: () => void }) {
  const [events, setEvents] = useState<Ev[]>([]);
  const [category, setCategory] = useState(row.category ?? ""); const [reason, setReason] = useState("");
  const [suggestion, setSuggestion] = useState<{ label: 0 | 1; category: string | null; reason: string | null; llm: { model_id: string; latency_ms: number } | null } | null>(null);
  const [err, setErr] = useState<string | null>(null); const [info, setInfo] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const loadEvents = useCallback(() => api<{ events: Ev[] }>(`/api/datasets/${datasetId}/rows/${encodeURIComponent(row.id)}/events`).then((r) => setEvents(r.events)).catch(() => setEvents([])), [datasetId, row.id]);
  useEffect(() => { const t = setTimeout(loadEvents, 0); return () => clearTimeout(t); }, [loadEvents]);

  async function submit(label: 0 | 1 | null) {
    setBusy(true); setErr(null); setInfo(null);
    try {
      if (contract.categories.required && label !== null && !category) throw new Error("category is required by the contract");
      const r = await api<{ training_eligible: boolean; event: { kind: string } }>("/api/labels", { method: "POST", json: { dataset_id: datasetId, row_id: row.id, label, category: category || null, labeler, reason: reason || null } });
      setInfo(`${r.event.kind} event written${r.training_eligible ? "" : " (evaluation row: audit annotation only, not used for training)"}`);
      await loadEvents();
      onLabeled(label, category || null);
    } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }
  async function suggest() {
    setBusy(true); setErr(null);
    try {
      const s = await api<{ ok: boolean; error?: string; label: 0 | 1; category: string | null; reason: string | null; llm: { model_id: string; latency_ms: number } | null }>("/api/labels/suggest", { method: "POST", json: { dataset_id: datasetId, row_id: row.id } });
      if (!s.ok) throw new Error(s.error ?? "no suggestion");
      setSuggestion(s); if (s.category) setCategory(s.category); if (s.reason) setReason(s.reason);
      await loadEvents();
    } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }
  return (
        <div className="card">
          <div className="row"><code>{row.id}</code><span className="pill">{row.split}</span>{row.label !== null && <span className="pill">current label {row.label}</span>}{row.source && <span className="muted">{row.source}</span>}</div>
          <div className="text">{row.text}</div>
          <div className="row" style={{ marginTop: 12 }}>
            {contract.categories.allowed.length > 0 && <select value={category} onChange={(e) => setCategory(e.target.value)}><option value="">category{contract.categories.required ? " (required)" : ""}</option>{contract.categories.allowed.map((c) => <option key={c}>{c}</option>)}</select>}
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="reason (optional)" style={{ flex: 1, minWidth: 220 }} />
          </div>
          <div className="row">
            <button className="pos" disabled={busy} onClick={() => submit(1)}>Confirm 1 · {contract.positive.name}</button>
            <button className="neg" disabled={busy} onClick={() => submit(0)}>Confirm 0 · {contract.negative.name}</button>
            {row.label !== null && <button disabled={busy} onClick={() => submit(null)}>Clear label</button>}
            <button disabled={busy || !llmEnabled} onClick={suggest} title={llmEnabled ? "" : "enable with TRIAGEKIT_LLM_ENABLED on the ML service"}>Suggest with LLM</button>
            <button disabled={!prev} onClick={prev}>← prev</button><button disabled={!next} onClick={next}>skip →</button>
          </div>
          {suggestion && <p className="info">LLM suggests <b>{suggestion.label}</b>{suggestion.category ? ` · ${suggestion.category}` : ""} — {suggestion.reason} <span className="muted">({suggestion.llm?.model_id}, {suggestion.llm?.latency_ms} ms). A suggestion is not a label until you confirm it.</span></p>}
          <Msg error={err} info={info} />
          {events.length > 0 && <><h3>Event history</h3><table><thead><tr><th>kind</th><th>label</th><th>category</th><th>labeler</th><th>reason</th><th>at</th></tr></thead>
            <tbody>{events.map((e) => <tr key={e.eventId}><td>{e.kind}</td><td>{e.label ?? "–"}</td><td>{e.category ?? "–"}</td><td>{e.labeler}</td><td className="muted">{e.reason ?? ""}</td><td className="muted">{e.at.slice(0, 19)}</td></tr>)}</tbody></table></>}
        </div>
  );
}
