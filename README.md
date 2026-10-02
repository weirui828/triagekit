# triagekit

Local-first, human-in-the-loop text triage: given a customer message, decide whether it needs a human.
Bring a dataset and an explicit label contract; label, snapshot, train, promote, score, and feed corrections
back into the next snapshot. Single developer, single user, SQLite and plain files.

Status: **milestones 1-4 complete** (baseline path, research replication, human feedback loop with product
pages and optional resolvers, extensions: Monitor, Bitext, BERTweet, pruning). See `project-brief.md`.

## Layout

```
ml/        Python 3.12 / FastAPI / CLI: validation, splits, snapshots, training, evaluation, registry, scoring
web/       Next.js 16 / TypeScript / Drizzle (libsql): datasets, label events, snapshots, decisions, feedback, public API
data/      shared local volume (gitignored): app.db, snapshots/, jobs/, mlflow.db, mlruns/, registry/
```

Ownership: Next.js owns the application database and the public API. Python owns everything ML and never
writes the app database. Only Next.js calls the Python API. MLflow (pinned 3.16.0, sqlite backend) owns
experiment tracking, the model registry and packaged pyfunc models.

Schemas: `ml/triagekit/schemas.py` (Pydantic) is canonical. `make gen-types` exports `ml/openapi.json` and
generates `web/src/generated/ml-api.d.ts`; `make check-types` fails when either is stale. Schema version `1`.

ORM choice: **Drizzle** with `@libsql/client` (prebuilt binaries, no native build step; better-sqlite3 has no
prebuilt binary for current Node releases).

## Quick start (host, CPU)

Requirements: `uv`, Node 20+, `pnpm`.

```bash
make install
make ml-serve      # terminal 1: http://127.0.0.1:8000 (internal)
make web-dev       # terminal 2: http://127.0.0.1:3000 — open it in a browser
make mlflow-ui     # optional terminal 3: http://127.0.0.1:5000 — MLflow's own tracking UI
```

`make mlflow-ui` runs MLflow's UI against the same local `data/mlflow.db` store the CLI and API write, so
experiment history is browsable without Docker. It is a developer tool: the product never embeds it.

Then the baseline path through the public API (no authentication; everything binds to localhost):

```bash
U=http://127.0.0.1:3000/api; H='-H content-type:application/json'
CONTRACT=$(ml/.venv/bin/python -c "import yaml,json;print(json.dumps(yaml.safe_load(open('ml/examples/support_demo.contract.yaml'))))")
DS=$(curl -s $H -H content-type:application/json -d "{\"name\":\"demo\",\"contract\":$CONTRACT}" $U/datasets | jq -r .id)
curl -s -H content-type:text/csv --data-binary @ml/examples/support_demo.csv $U/datasets/$DS/import | jq .report
SNAP=$(curl -s $H -X POST $U/datasets/$DS/snapshots | jq -r .snapshot_id)
JOB=$(curl -s $H -H content-type:application/json -d "{\"snapshot_id\":\"$SNAP\"}" $U/jobs | jq -r .job_id)
curl -s $H $U/jobs/$JOB | jq '{status,run_id}'            # poll until succeeded
RUN=$(curl -s $H $U/jobs/$JOB | jq -r .run_id)
curl -s $H $U/runs/$RUN | jq '{policy,validation,test,test_routing,promotable}'
curl -s $H -H content-type:application/json -d "{\"run_id\":\"$RUN\"}" $U/registry/promote
curl -s $H -H content-type:application/json -d '{"text":"I was charged twice, refund me now","request_id":"r1"}' $U/triage
curl -s $H -H content-type:application/json -d '{"decision_id":"<decision_id>","label":1,"labeler":"me"}' $U/feedback
```

Scoring works before any training: with no promoted model the Python API serves the tracked demo artifact
`ml/bundled_model` (`model_version` starts with `bundled:`). See `ml/bundled_model/provenance.json`.

### CLI (same service layer as the API)

```bash
cd ml
uv run triagekit contract-validate examples/support_demo.contract.yaml
uv run triagekit import-validate examples/support_demo.csv --contract examples/support_demo.contract.yaml
uv run triagekit snapshot-create examples/support_demo.csv --contract examples/support_demo.contract.yaml --snapshot-id snap1
uv run triagekit train snap1 --wait          # subprocess job; --sync runs in-process
uv run triagekit jobs list|status|logs|cancel <job_id>
uv run triagekit runs list|show <run_id>|compare <run_id> <run_id>
uv run triagekit promote <run_id> ; uv run triagekit rollback ; uv run triagekit production
uv run triagekit score "where is my order"
uv run triagekit bundle                      # rebuild the demo artifact
```

Set `TRIAGEKIT_DATA_DIR` (default `./data` relative to cwd; the Makefile points it at the repo `data/`).

### Docker

Optional, for running without installing uv, Node and pnpm: `docker compose up --build` (copy
`.env.example` to `.env` first only if you want the LLM tier). Web on `127.0.0.1:3000`, MLflow UI on
`127.0.0.1:5000`; the Python API is not published. Data lives in the `triagekit-data` volume. **Unverified**:
this machine has no Docker. The host path above is the primary one and needs nothing from Docker.

GPU/MPS training runs on the host, not in compose: `cd ml && uv run triagekit train <snapshot> --device mps`
(the device flag is recorded now and used by the transformer models in milestone 2).

## Milestone 2: TWCS adapter, DistilBERT, replication

- `triagekit adapt-twcs <llm_labeled_5k.csv> <out.csv> [--original-splits]` converts the human-loop labeled
  TWCS sample to the canonical CSV (id = thread id, text = opening customer message, group_id = thread id,
  source = `llm:<labeler>`). `examples/twcs.contract.yaml` is the matching label contract.
- Model `distilbert` (`DistilbertParams`: checkpoint, epochs, batch size, learning rate, max length, warmup,
  weight decay, gradient clip, balanced class weights). Epoch selection uses validation macro F1 at 0.5, as
  in the original; the classification threshold and routing bounds are then selected on validation like
  any other run. Device: `--device auto|cpu|cuda|mps`.
- `triagekit replicate --data … --seeds 42 1337 2024` reproduces the original experiment against
  `ml/replication/twcs_distilbert.json`. Details and results: `ml/replication/README.md`.
- Contracts may fix the threshold (`classification_threshold: {objective: fixed, fixed_threshold: 0.5}`)
  for protocol replication; the sweep is still logged.
- `uv run triagekit train <snapshot> --model distilbert --params '{"epochs": 2}'` for ad-hoc runs.
  Transformer training runs on the host; the compose image is CPU-only and excludes torch.

## Milestone 3: pages, feedback loop, resolvers

Open `http://127.0.0.1:3000`. There is no login. The UI uses the Snorkel Blue theme tokens from
`@wei/design-system` (vendored into `web/src/app/theme.css`, light and dark; no Tailwind or package
dependency so a fork runs as-is). Pages:

- **Datasets** `/datasets`: create with a contract (YAML/JSON, validated by Python), import CSV with the full
  validation report, counts, split inspection, snapshot creation.
- **Label** `/label`: label from scratch (unlabeled rows) or audit existing labels, optional LLM suggestion,
  explicit confirmation, clear, per-row event history. Writes label events only.
- **Train** `/train`: start/cancel jobs, tail logs, runs table with validation/test metrics and routing
  figures, compare compatible runs, promote/rollback, prune (dry run first).
- **Triage** `/triage`: single and batch scoring, action/explanation, human override (writes feedback).
- **Monitor** `/monitor`: volume, action mix, uncertain-band fraction, review coverage and override rate with
  denominators, score histograms against the production run's held-out test distribution, per day and per
  model/policy version.

Feedback loop demonstration: `make feedback-loop` (both servers running) scores a message, records a human
correction as a label event on a new train row, creates an explicit new snapshot, retrains, and shows that the
training hash changed while the evaluation hash stayed frozen so the runs compare.

Resolvers for the uncertainty band (`routing_policy.second_tier` in the contract, frozen into the packaged
model at training time):

- `rule`: explicit case-insensitive regex rules with a label and optional category; no match falls back to
  human review (`fallback: rule:no_match`). The demo contract ships two rules. A rule is not an LLM.
- `llm`: Claude (`claude-opus-5` by default, `TRIAGEKIT_LLM_MODEL` to change) with a structured verdict
  validated against the contract; records model id, prompt version, latency and token usage on the decision.
  Enable with `TRIAGEKIT_LLM_ENABLED=1` plus Anthropic credentials on the **ML service** only; text is sent to
  the API only when enabled. Timeouts, refusals, invalid output or unknown categories fall back to review.
  The same tier powers "Suggest with LLM" on the Label page; suggestions are `llm_suggestion` events and
  never accepted labels.

## Milestone 4: Monitor, Bitext, BERTweet, pruning

- `triagekit adapt-bitext <Bitext csv> <out.csv>` maps the 27 intents to the human-loop escalation rule
  (7 intents = 1), category = intent; `examples/bitext.contract.yaml`.
- Model `bertweet` = the DistilBERT loop with checkpoint `vinai/bertweet-base` (135M parameters).
- `triagekit prune [--apply]` / Train page: deletes weights of unpromoted, unreferenced runs after a dry run.
  Current production, every previously promoted version and active jobs are protected; metrics, manifests
  and predictions stay; pruned runs are marked not promotable.
- Cohen's kappa is deliberately absent: labels here come from an audit flow where the reviewer saw the prior
  label, so no independent paired labeling exists yet.

## Concepts

- **Label contract** (`examples/support_demo.contract.yaml`): class meanings, ambiguous cases, categories,
  threshold objective and constraints, routing objective and constraints, contract version. A contract change
  needs an explicit label review; labels are never silently reused under a new definition.
- **Import**: the whole CSV is validated by Python (`/import/validate`) before Next.js commits anything in one
  transaction. Any error means no partial dataset. Imported labels become `imported` label events.
- **Label events**: append-only. Resolved label = latest `imported`/`human`/`clear` event. `llm_suggestion`
  and `human_audit` never set the accepted label.
- **Splits** are assigned once (first snapshot) by a seeded, grouped strategy (group_id and exact duplicate
  text never straddle splits), stored on the dataset and fixed afterwards. Supplied valid splits are kept;
  conflicting ones are rejected.
- **Snapshots** are immutable directories under `data/snapshots/<id>` with `rows.jsonl`, `contract.json`,
  `manifest.json` and content hashes: rows, training data, split manifest, evaluation data, contract.
- **Training jobs** are subprocesses (`data/jobs/<id>`); one at a time; status/logs/cancel via API and CLI;
  orphaned jobs are marked `interrupted` on reconcile. Failed/canceled/interrupted jobs are never promotable.
- **Policy selection** uses validation data only: threshold by the contract objective (optionally with a
  positive-recall floor), then routing bounds `low <= threshold <= high` maximising automatic coverage
  subject to `max_auto_error_rate`, `max_missed_positive_rate` and `min_band_width`. Infeasible policies are
  reported and block promotion. Test metrics are computed once, after the policy is frozen.
- **Routing**: `p < low` -> `auto_handle` (label 0, resolved by model); `p >= high` -> `escalate` (label 1,
  resolved by model, a human handles the case); otherwise `review` with `final_label = null` and
  `resolved_by = human_pending`. `probability` is the raw model score; calibration is not evaluated.
- **Promotion/rollback** set the MLflow `production` alias explicitly and append to
  `data/registry/promotions.jsonl` with initiator, prior and new version. Scoring resolves the alias, logs the
  concrete version on every decision, and only swaps models after the replacement loads.
- **Feedback** references a decision; identical retries are idempotent (`feedback_id`, or a hash of
  decision+label+category+labeler). Unseen production text becomes a dataset row (default split `train`,
  identical text inherits the existing row's split). Feedback on validation/test rows is recorded as
  `human_audit` and never enters training. Nothing retrains, snapshots or promotes automatically.
- **Run comparison** requires an identical evaluation hash (evaluation ids, their splits, labels and text),
  contract hash/version and metric definitions version; mismatches are listed and the comparison is marked
  incompatible. Training snapshots may differ.

## Security model

This is a single-user tool for one laptop. There are **no accounts, no API keys, no roles, no verified
labeler identities and no tenant isolation**: `labeler` is a free-text claim. Everything binds to
`127.0.0.1`; the Python API and MLflow are internal to the stack. Exposing it beyond localhost is out of
scope. The only secret is an optional Anthropic key, held by the Python service and never sent to the
browser; text leaves the machine only when the LLM tier is explicitly enabled.

## Tests

```bash
make test        # pytest (32 tests, ~8 s CPU incl. a full train/promote/score smoke test), vitest (5), stale-type check
```

Covered invariants: no partial imports, immutable snapshots and hash separation, grouped split isolation
and determinism, validation-only policy selection, forced review band, infeasible policy refusal, undefined
metrics as null, routing boundary semantics, single active job, orphan reconcile, cancel, failed job
recording, run compatibility, promote/rollback history, batch order and per-item failures, decision and
feedback idempotency, label resolution, audit-only evaluation feedback.

## Demo data

`ml/examples/support_demo.csv` is synthetic (161 templated rows). Metrics on it are demo metrics, not
evidence about real data. The bundled artifact reports its own split counts and metrics in
`provenance.json`.
