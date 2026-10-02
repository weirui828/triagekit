#!/bin/bash
# Demonstrates the human feedback loop through the public API:
#   decision -> human correction (train row) -> label event -> explicit new snapshot -> retrain uses it
#   while the evaluation set (validation/test hashes) stays frozen, so the two runs remain comparable.
# Requires both servers running.
set -euo pipefail
U=${WEB_URL:-http://127.0.0.1:3000}/api
H=(-H "content-type: application/json")
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
j() { python3 -c "import json,sys;d=json.load(sys.stdin);$1"; }
wait_job() { for _ in $(seq 1 300); do S=$(curl -s "${H[@]}" "$U/jobs/$1" | j "print(d['status'],d.get('run_id') or '')"); case "$S" in succeeded*|failed*|canceled*|interrupted*) echo "$S"; return;; esac; sleep 1; done; echo timeout; }

CONTRACT=$("$ROOT/ml/.venv/bin/python" -c "import yaml,json;print(json.dumps(yaml.safe_load(open('$ROOT/ml/examples/support_demo.contract.yaml'))))")
DS=$(curl -s "${H[@]}" -d "{\"name\":\"feedback-loop-$(date +%H%M%S)\",\"contract\":$CONTRACT}" "$U/datasets" | j "print(d['id'])")
curl -s -H "content-type: text/csv" --data-binary @"$ROOT/ml/examples/support_demo.csv" "$U/datasets/$DS/import" | j "assert d['committed'], d; print('1. imported', d['report']['label_counts'])"
S1=$(curl -s "${H[@]}" -X POST "$U/datasets/$DS/snapshots" | j "print(d['snapshot_id'])"); echo "2. snapshot A $S1"
J1=$(curl -s "${H[@]}" -d "{\"snapshot_id\":\"$S1\"}" "$U/jobs" | j "print(d['job_id'])"); R1=$(wait_job "$J1"); R1=${R1#succeeded }; echo "3. run A $R1"
curl -s "${H[@]}" -d "{\"run_id\":\"$R1\",\"initiated_by\":\"feedback-loop\"}" "$U/registry/promote" | j "print('4. promoted version', d['new_version'])"
D=$(curl -s "${H[@]}" -d "{\"text\":\"the app shows my colleague's invoices, is that a privacy problem\",\"request_id\":\"fl-$RANDOM$RANDOM\"}" "$U/triage" | j "print(d['decision_id']); print('5. decision', d['action'], 'p=%.3f'%d['probability'], d['resolved_by'], file=sys.stderr)")
curl -s "${H[@]}" -d "{\"decision_id\":\"$D\",\"label\":1,\"category\":\"technical\",\"labeler\":\"reviewer\",\"reason\":\"privacy breach needs a person\",\"dataset_id\":\"$DS\"}" "$U/feedback" | j "print('6. feedback -> row', d['row_id'], 'training_eligible', d['training_eligible'])"
curl -s "${H[@]}" "$U/datasets/$DS/rows/prod-$D/events" | j "print('7. label events on the new row:', [(e['kind'], e['label'], e['labeler']) for e in d['events']])"
S2=$(curl -s "${H[@]}" -X POST "$U/datasets/$DS/snapshots" | j "print(d['snapshot_id'])"); echo "8. snapshot B $S2 (explicit; nothing retrained automatically)"
curl -s "${H[@]}" "$U/datasets/$DS/snapshots" | j "a,b=d['snapshots'][0],d['snapshots'][1]; print('   training hash changed:', a['training_data_hash']!=b['training_data_hash'], '| evaluation hash frozen:', a['evaluation_hash']==b['evaluation_hash'], '| labeled', a['labeled_count'],'->',b['labeled_count'])"
J2=$(curl -s "${H[@]}" -d "{\"snapshot_id\":\"$S2\"}" "$U/jobs" | j "print(d['job_id'])"); R2=$(wait_job "$J2"); R2=${R2#succeeded }; echo "9. run B $R2 trained on snapshot B"
curl -s "${H[@]}" "$U/runs/$R2" | j "print('   run B training rows:', d['manifest']['training_data_hash'][:8], '| eval hash', d['manifest']['evaluation_hash'][:8])"
curl -s "${H[@]}" -d "{\"run_ids\":[\"$R1\",\"$R2\"]}" "$U/runs/compare" | j "print('10. compare compatible:', d['compatible'], d['mismatches']); [print('   ', r['run_id'][:8], 'train hash', r['manifest']['training_data_hash'][:8], 'test macro F1', round(r['test']['macro_f1'],4)) for r in d['runs']]"
