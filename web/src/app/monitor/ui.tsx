"use client";
import Link from "next/link";
import { fmt } from "@/lib/client";

type Bucket = { model_version: string; policy_version: string; decisions: number; actions: { auto_handle: number; escalate: number; review: number }; review_fraction: number | null; reviewed: number; review_coverage: number | null; overrides: number; override_rate: number | null; score_histogram: number[] };
type Data = { days: number; since: string; total_decisions: number; total_feedback: number; by_version: Bucket[]; by_day: { day: string; versions: Bucket[] }[]; reference: { run_id: string; model_version: string | null; n: number; score_histogram: number[] } | null };

const Bars = ({ h, cls = "" }: { h: number[]; cls?: string }) => { const m = Math.max(1, ...h); return <div className={`bars ${cls}`}>{h.map((v, i) => <div key={i} style={{ height: `${(v / m) * 100}%` }} title={`[${i / 10}, ${(i + 1) / 10}): ${v}`} />)}</div>; };
const pct = (v: number | null, n: number, d: number) => (v === null ? "– (0 denominator)" : `${(v * 100).toFixed(1)}% (${n}/${d})`);

export function MonitorClient({ data }: { data: Data }) {
  return (
    <>
      <h1>Monitor</h1>
      <div className="row">{[7, 30, 90].map((d) => <Link key={d} className="pill" href={`/monitor?days=${d}`}>{d} days</Link>)}<span className="muted">since {data.since.slice(0, 10)} · {data.total_decisions} decisions · {data.total_feedback} feedback</span></div>
      <p className="muted">Rates are shown with their denominators. Override rate = overrides / reviewed decisions; review coverage = reviewed / all decisions. Unreviewed decisions are not confirmed correct. A shifted score distribution indicates drift, not measured accuracy loss.</p>
      {data.by_version.length === 0 && <p>No decisions in this window.</p>}
      <div className="grid">
        {data.by_version.map((b) => (
          <div className="card" key={b.model_version + b.policy_version}>
            <h3><code>{b.model_version}</code> · policy <code>{b.policy_version}</code></h3>
            <table><tbody>
              <tr><td>decisions</td><td>{b.decisions}</td></tr>
              <tr><td>auto_handle / escalate / review</td><td>{b.actions.auto_handle} / {b.actions.escalate} / {b.actions.review}</td></tr>
              <tr><td>uncertain-band fraction</td><td>{pct(b.review_fraction, b.actions.review, b.decisions)}</td></tr>
              <tr><td>review coverage (human feedback)</td><td>{pct(b.review_coverage, b.reviewed, b.decisions)}</td></tr>
              <tr><td>override rate among reviewed</td><td>{pct(b.override_rate, b.overrides, b.reviewed)}</td></tr>
            </tbody></table>
            <h3>Score distribution (production traffic)</h3><Bars h={b.score_histogram} />
            {data.reference && data.reference.model_version === b.model_version && <><h3>Reference: held-out test set of run {data.reference.run_id.slice(0, 8)} (n={data.reference.n})</h3><Bars h={data.reference.score_histogram} cls="ref" /></>}
          </div>
        ))}
        {data.reference && !data.by_version.some((b) => b.model_version === data.reference!.model_version) && <div className="card"><h3>Reference distribution · <code>{data.reference.model_version}</code> (n={data.reference.n})</h3><Bars h={data.reference.score_histogram} cls="ref" /></div>}
      </div>
      {data.by_day.length > 0 && <><h2>Per day</h2>
        <table><thead><tr><th>day</th><th>model · policy</th><th>decisions</th><th>review fraction</th><th>reviewed</th><th>overrides / reviewed</th></tr></thead>
          <tbody>{data.by_day.flatMap((d) => d.versions.map((b) => <tr key={d.day + b.model_version + b.policy_version}><td>{d.day}</td><td><code>{b.model_version}</code> · <code>{b.policy_version}</code></td><td>{b.decisions}</td><td>{fmt(b.review_fraction, 2)} ({b.actions.review}/{b.decisions})</td><td>{b.reviewed}</td><td>{b.overrides}/{b.reviewed}{b.override_rate !== null ? ` = ${fmt(b.override_rate, 2)}` : ""}</td></tr>))}</tbody></table></>}
    </>
  );
}
