"use client";
import { useCallback, useEffect, useState } from "react";
import { api, fmt } from "@/lib/client";
import { Msg } from "@/components/Msg";
import type { S } from "@/lib/ml";

type Snap = { id: string; dataset: string; hash: string; labeled: number; splits: Record<string, number>; created: string };
const ACTIVE = new Set(["queued", "starting", "running"]);

export function TrainClient({ snapshots }: { snapshots: Snap[] }) {
  const [snapshot, setSnapshot] = useState(snapshots[0]?.id ?? ""); const [model, setModel] = useState<S["TrainConfig"]["model"]>("tfidf_lr");
  const [params, setParams] = useState("{}"); const [seed, setSeed] = useState(42); const [device, setDevice] = useState("auto");
  const [jobs, setJobs] = useState<S["JobRecord"][]>([]); const [runs, setRuns] = useState<S["RunSummary"][]>([]); const [prod, setProd] = useState<S["ProductionInfo"] | null>(null);
  const [selJob, setSelJob] = useState<string | null>(null); const [logs, setLogs] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]); const [cmp, setCmp] = useState<S["CompareResponse"] | null>(null);
  const [prune, setPrune] = useState<S["PruneResponse"] | null>(null);
  const [err, setErr] = useState<string | null>(null); const [info, setInfo] = useState<string | null>(null); const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const [j, r, p] = await Promise.all([api<S["JobListResponse"]>("/api/jobs"), api<S["RunListResponse"]>("/api/runs"), api<S["ProductionInfo"]>("/api/registry/production")]);
    setJobs(j.jobs); setRuns(r.runs); setProd(p);
  }, []);
  useEffect(() => { const t = setTimeout(() => refresh().catch((e) => setErr(String(e))), 0); return () => clearTimeout(t); }, [refresh]);
  useEffect(() => {
    const active = jobs.some((j) => ACTIVE.has(j.status));
    if (!active && !selJob) return;
    const t = setInterval(async () => {
      if (active) refresh().catch(() => {});
      if (selJob) api<S["JobLogsResponse"]>(`/api/jobs/${selJob}/logs?limit=2000`).then((l) => setLogs(l.lines)).catch(() => {});
    }, 2000);
    return () => clearInterval(t);
  }, [jobs, selJob, refresh]);

  const act = (fn: () => Promise<string | void>) => async () => { setBusy(true); setErr(null); setInfo(null); try { const m = await fn(); if (m) setInfo(m); await refresh(); } catch (e) { setErr(String(e)); } finally { setBusy(false); } };
  const start = act(async () => { const j = await api<S["JobRecord"]>("/api/jobs", { method: "POST", json: { snapshot_id: snapshot, model, params: JSON.parse(params || "{}"), seed, device } }); setSelJob(j.job_id); return `job ${j.job_id} started`; });
  const cancel = (id: string) => act(async () => { await api(`/api/jobs/${id}/cancel`, { method: "POST" }); return `job ${id} canceled`; });
  const promote = (run_id: string) => act(async () => { const p = await api<S["PromotionRecord"]>("/api/registry/promote", { method: "POST", json: { run_id, initiated_by: "web" } }); return `promoted run ${run_id.slice(0, 8)} as version ${p.new_version} (prior ${p.prior_version ?? "none"})`; });
  const rollback = act(async () => { const p = await api<S["PromotionRecord"]>("/api/registry/rollback", { method: "POST", json: { initiated_by: "web" } }); return `rolled back to version ${p.new_version}`; });
  const compare = act(async () => { setCmp(await api<S["CompareResponse"]>("/api/runs/compare", { method: "POST", json: { run_ids: selected } })); });
  const doPrune = (dry: boolean) => act(async () => { const r = await api<S["PruneResponse"]>("/api/prune", { method: "POST", json: { dry_run: dry } }); setPrune(r); return dry ? `dry run: ${r.pruned.length} runs prunable` : `pruned ${r.pruned.length} runs, ${(r.bytes_freed / 1e6).toFixed(1)} MB freed`; });

  const prodRun = prod?.run_id ?? null;
  return (
    <>
      <h1>Train</h1>
      <div className="card"><h3>Production</h3>
        {prod ? <p>version <b>{prod.version ?? "none"}</b> · loaded <code>{prod.loaded_version ?? "–"}</code> · run <code>{prod.run_id?.slice(0, 8) ?? "–"}</code> · source {prod.source} <button onClick={rollback} disabled={busy || prod.history.length < 2}>Roll back</button></p> : null}
        {prod && prod.history.length > 0 && <p className="muted">history: {prod.history.map((h) => `${h.kind} ${h.prior_version ?? "∅"}→${h.new_version} by ${h.initiated_by}`).join(" · ")}</p>}
      </div>

      <h2>Start a training job</h2>
      <div className="card">
        <div className="row">
          <select value={snapshot} onChange={(e) => setSnapshot(e.target.value)}>{snapshots.map((s) => <option key={s.id} value={s.id}>{s.dataset} · {s.id.slice(0, 8)} · {s.labeled} labeled · {JSON.stringify(s.splits)}</option>)}</select>
          <select value={model} onChange={(e) => setModel(e.target.value as S["TrainConfig"]["model"])}><option value="tfidf_lr">tfidf_lr</option><option value="distilbert">distilbert</option><option value="bertweet">bertweet</option></select>
          <label>seed <input type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} style={{ width: 80 }} /></label>
          <select value={device} onChange={(e) => setDevice(e.target.value)}><option>auto</option><option>cpu</option><option>mps</option><option>cuda</option></select>
        </div>
        <div className="row"><input className="mono" value={params} onChange={(e) => setParams(e.target.value)} placeholder='params JSON, e.g. {"epochs": 2}' style={{ flex: 1 }} /><button className="primary" onClick={start} disabled={busy || !snapshot || jobs.some((j) => ACTIVE.has(j.status))}>Start</button></div>
        <Msg error={err} info={info} />
      </div>

      <h2>Jobs</h2>
      <table><thead><tr><th>job</th><th>status</th><th>snapshot</th><th>model</th><th>created</th><th>run</th><th></th></tr></thead>
        <tbody>{jobs.slice(0, 15).map((j) => <tr key={j.job_id}><td><a href="#logs" onClick={() => setSelJob(j.job_id)}><code>{j.job_id}</code></a></td><td>{j.status}</td><td><code>{j.config.snapshot_id.slice(0, 8)}</code></td><td>{j.config.model}</td><td className="muted">{j.created_at.slice(0, 19)}</td><td><code>{j.run_id?.slice(0, 8) ?? "–"}</code>{j.error && <span className="err"> {j.error.slice(0, 80)}</span>}</td><td>{ACTIVE.has(j.status) && <button onClick={cancel(j.job_id)} disabled={busy}>Cancel</button>}</td></tr>)}</tbody></table>
      {selJob && <div id="logs"><h3>Logs · {selJob} <button onClick={() => setSelJob(null)}>close</button></h3><pre>{logs.join("\n") || "(no output yet)"}</pre></div>}

      <h2>Runs</h2>
      <div className="row"><button onClick={compare} disabled={busy || selected.length < 2}>Compare selected ({selected.length})</button><button onClick={doPrune(true)} disabled={busy}>Prune (dry run)</button>{prune?.dry_run && prune.pruned.length > 0 && <button onClick={doPrune(false)} disabled={busy}>Apply prune: delete weights of {prune.pruned.length} runs</button>}</div>
      <table><thead><tr><th></th><th>run</th><th>model</th><th>snapshot</th><th>val F1</th><th>test F1</th><th>pos P / R</th><th>thr · band</th><th>coverage / auto err</th><th>status</th><th></th></tr></thead>
        <tbody>{runs.map((r) => <tr key={r.run_id} style={r.run_id === prodRun ? { fontWeight: 600 } : undefined}>
          <td><input type="checkbox" checked={selected.includes(r.run_id)} onChange={(e) => setSelected(e.target.checked ? [...selected, r.run_id] : selected.filter((x) => x !== r.run_id))} /></td>
          <td><code>{r.run_id.slice(0, 8)}</code>{r.run_id === prodRun ? " ★" : ""}</td><td>{r.manifest?.model ?? "?"}</td><td><code>{r.manifest?.snapshot_id.slice(0, 8)}</code></td>
          <td>{fmt(r.validation?.macro_f1)}</td><td>{fmt(r.test?.macro_f1)} <span className="muted">n={r.test?.n ?? 0}</span></td><td>{fmt(r.test?.positive_precision, 2)} / {fmt(r.test?.positive_recall, 2)}</td>
          <td>{r.policy ? `${r.policy.classification_threshold} · [${r.policy.routing_low}, ${r.policy.routing_high}]` : "–"}</td>
          <td>{r.test_routing ? `${fmt(r.test_routing.coverage, 2)} / ${fmt(r.test_routing.auto_error_rate, 2)}` : "–"}</td>
          <td>{r.status}{r.pruned ? " · pruned" : ""}{!r.promotable && r.status === "FINISHED" && <span className="muted" title={r.not_promotable_reason ?? ""}> · not promotable</span>}</td>
          <td>{r.promotable && r.run_id !== prodRun && <button onClick={promote(r.run_id)} disabled={busy}>Promote</button>}</td></tr>)}</tbody></table>
      {cmp && <div className="card"><h3>Comparison {cmp.compatible ? <span className="info">compatible</span> : <span className="err">incompatible</span>}</h3>
        {cmp.mismatches.length > 0 && <ul>{cmp.mismatches.map((m, i) => <li key={i} className="err">{m}</li>)}</ul>}
        {cmp.compatible && <table><thead><tr><th>run</th><th>model</th><th>training hash</th><th>val F1</th><th>test F1</th><th>test pos recall</th><th>coverage</th><th>auto error</th><th>errors in band</th></tr></thead>
          <tbody>{cmp.runs.map((r) => <tr key={r.run_id}><td><code>{r.run_id.slice(0, 8)}</code></td><td>{r.manifest?.model}</td><td><code>{r.manifest?.training_data_hash.slice(0, 8)}</code></td><td>{fmt(r.validation?.macro_f1)}</td><td>{fmt(r.test?.macro_f1)}</td><td>{fmt(r.test?.positive_recall)}</td><td>{fmt(r.test_routing?.coverage)}</td><td>{fmt(r.test_routing?.auto_error_rate)}</td><td>{fmt(r.test_routing?.errors_captured_by_band)}</td></tr>)}</tbody></table>}
        <p className="muted">Comparable runs share evaluation examples and labels, split assignments, contract and metric definitions; training snapshots may differ.</p></div>}
      {prune && <div className="card"><h3>Prune {prune.dry_run ? "(dry run)" : "(applied)"}</h3>
        <p>{prune.pruned.length} prunable ({(prune.bytes_freed / 1e6).toFixed(1)} MB) · {prune.protected.length} protected</p>
        <table><tbody>{[...prune.pruned.map((c) => ({ ...c, kind: "prune" })), ...prune.protected.map((c) => ({ ...c, kind: "keep" }))].map((c) => <tr key={c.run_id}><td>{c.kind}</td><td><code>{c.run_id.slice(0, 8)}</code></td><td>{(c.bytes / 1e6).toFixed(1)} MB</td><td className="muted">{c.reason}</td></tr>)}</tbody></table></div>}
    </>
  );
}
