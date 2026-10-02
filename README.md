# TriageKit

Decide which customer messages need a human.

TriageKit is a local, human-in-the-loop text classifier. You bring a dataset and a **label contract** that
defines what "needs a human" means. You then label, train, review the metrics and promote a model. Every
message the model scores is routed one of three ways:

- **auto_handle**: confident it's routine
- **escalate**: confident it needs a person
- **review**: uncertain, so a human decides

Human corrections are recorded as new labels for the next training run. Nothing retrains or deploys
without you asking.

Runs on one machine with SQLite and plain files. No cloud services required.

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/), Node 20+, [pnpm](https://pnpm.io/).

```bash
git clone git@github.com:weirui828/triagekit.git
cd triagekit
make install

make ml-serve     # terminal 1: ML service on 127.0.0.1:8000
make web-dev      # terminal 2: app on http://127.0.0.1:3000
```

Open http://127.0.0.1:3000. Scoring works straight away: until you promote your own model, a small demo model
trained on synthetic data is used.

To try the full loop, create a dataset from `ml/examples/support_demo.contract.yaml` and import
`ml/examples/support_demo.csv`. Then create a snapshot, train and promote. On CPU this takes seconds.

## The app

| Page | What it's for |
| --- | --- |
| **Datasets** | Create a dataset from a contract, import a CSV (fully validated, all-or-nothing), inspect splits, create snapshots |
| **Label** | Label unlabeled rows or audit existing ones, with optional LLM suggestions and per-row history |
| **Train** | Start and cancel training jobs, follow logs, compare runs, promote or roll back, prune old weights |
| **Triage** | Score one message or a batch, see the routing decision, override it |
| **Monitor** | Volume, action mix, review rate, override rate and score drift against the production model |

## Bring your own data

**CSV.** Required columns are `id` and `text`. Optional columns:

| Column | Meaning |
| --- | --- |
| `label` | `1` = needs a human, `0` = can be auto-handled, empty = unlabeled |
| `category` | One of the contract's allowed categories |
| `split` | `train` / `validation` / `test`. If omitted, assigned once and then fixed |
| `group_id` | Rows sharing a group never end up in different splits (e.g. one conversation thread) |
| `source` | Free text describing where the label came from |

**Label contract.** A YAML file that defines:

- the two classes, with examples and rules for ambiguous cases
- the allowed categories
- how the decision threshold is chosen
- the limits for automatic routing, such as maximum auto-error rate and maximum missed positives

Copy `ml/examples/support_demo.contract.yaml` as a starting point.

Optionally, the contract can set a second tier that resolves the uncertain band before it reaches a
human. The tier is either regex rules or an LLM.

## How decisions are made

- **Snapshots** are immutable copies of the dataset at a point in time. Every training run uses one.
- **The threshold and routing band are chosen on validation data only.** The test set is scored once,
  after the policy is fixed. If no policy meets the contract's limits, the run can't be promoted.
- **Routing:** a score below `low` is auto-handled, a score at or above `high` is escalated, and anything
  in between goes to review.
- **Runs are only compared** when they were evaluated on identical data under the same contract.
- **Promotion and rollback** are explicit and logged. Every decision records the model version that made it.
- **Feedback** on a decision becomes a label event. Feedback on validation or test rows is kept for audit
  only and never used for training.

## API

The app exposes a JSON API at `http://127.0.0.1:3000/api`. A full walkthrough with
[jq](https://jqlang.org/):

```bash
API=http://127.0.0.1:3000/api
JSON='content-type: application/json'

# Create a dataset and import the demo CSV
CONTRACT=$(ml/.venv/bin/python -c "import yaml,json;print(json.dumps(yaml.safe_load(open('ml/examples/support_demo.contract.yaml'))))")
DS=$(curl -s -H "$JSON" -d "{\"name\":\"demo\",\"contract\":$CONTRACT}" $API/datasets | jq -r .id)
curl -s -H 'content-type: text/csv' --data-binary @ml/examples/support_demo.csv $API/datasets/$DS/import | jq .report

# Snapshot and train
SNAP=$(curl -s -X POST $API/datasets/$DS/snapshots | jq -r .snapshot_id)
JOB=$(curl -s -H "$JSON" -d "{\"snapshot_id\":\"$SNAP\"}" $API/jobs | jq -r .job_id)
curl -s $API/jobs/$JOB | jq '{status, run_id}'          # repeat until "succeeded"

# Inspect and promote
RUN=$(curl -s $API/jobs/$JOB | jq -r .run_id)
curl -s $API/runs/$RUN | jq '{policy, validation, test, test_routing, promotable}'
curl -s -H "$JSON" -d "{\"run_id\":\"$RUN\"}" $API/registry/promote

# Score a message, then correct it
curl -s -H "$JSON" -d '{"text":"I was charged twice, refund me now","request_id":"r1"}' $API/triage
curl -s -H "$JSON" -d '{"decision_id":"<decision_id>","label":1,"labeler":"me"}' $API/feedback
```

Other endpoints: `/triage/batch`, `/decisions`, `/runs/compare`, `/registry/rollback`,
`/registry/production`, `/monitor`, `/prune`.

`make feedback-loop` runs a scripted demo with both servers up. It scores a message, records a correction,
snapshots, retrains, and shows that the training data changed while the evaluation data stayed fixed.

## CLI

The ML service also has a CLI:

```bash
cd ml
uv run triagekit contract-validate examples/support_demo.contract.yaml
uv run triagekit snapshot-create examples/support_demo.csv --contract examples/support_demo.contract.yaml --snapshot-id snap1
uv run triagekit train snap1 --wait
uv run triagekit runs list
uv run triagekit promote <run_id>
uv run triagekit score "where is my order"
uv run triagekit --help                      # all commands
```

## Models

| Model | Notes |
| --- | --- |
| `tfidf_lr` (default) | TF-IDF + logistic regression. Trains in seconds on CPU |
| `distilbert` | Fine-tuned DistilBERT. Use a GPU or Apple Silicon (`--device cuda` / `mps`) |
| `bertweet` | Same training loop with `vinai/bertweet-base`, suited to short social-media text |

```bash
uv run triagekit train <snapshot_id> --model distilbert --device mps --params '{"epochs": 2}'
```

Adapters convert two public datasets into the CSV format: `triagekit adapt-twcs` for Customer Support on
Twitter, and `triagekit adapt-bitext` for the Bitext customer-support dataset. Matching contracts are in
`ml/examples/`. `ml/replication/` reproduces a published DistilBERT result on TWCS.

## Optional: LLM tier

Claude can resolve uncertain messages and suggest labels on the Label page. It is off by default, and no
text leaves your machine unless you enable it. To enable it, set these in the ML service's environment:

```bash
TRIAGEKIT_LLM_ENABLED=1
ANTHROPIC_API_KEY=sk-ant-...
TRIAGEKIT_LLM_MODEL=claude-opus-5   # optional
```

LLM suggestions are never accepted as labels until a human confirms them. Timeouts, refusals and invalid
output fall back to human review.

## Docker

```bash
cp .env.example .env    # only needed for the LLM tier
docker compose up --build
```

This starts the app on `127.0.0.1:3000` and the MLflow UI on `127.0.0.1:5000`. Data is stored in the
`triagekit-data` volume. The image is CPU-only; train transformer models on the host.

## Security

TriageKit is built for a single user on a single machine. It has no login, no API keys and no user
accounts, and everything binds to `127.0.0.1`. **Do not expose it to a network.** The only secret is the
optional Anthropic key, which only the ML service holds. It is never sent to the browser.

## Development

```
ml/    Python 3.12, FastAPI, scikit-learn, MLflow: validation, training, evaluation, registry, scoring
web/   Next.js, TypeScript, Drizzle + SQLite: app database, UI, public API
data/  local state (gitignored): app.db, snapshots, jobs, MLflow store
```

The web app owns the application database and the public API. The ML service owns everything model-related
and is only called by the web app.

```bash
make test          # Python tests, web tests, and a check that generated types are current
make gen-types     # after changing ml/triagekit/schemas.py: regenerate OpenAPI + TypeScript types
make mlflow-ui     # browse experiments at http://127.0.0.1:5000
make bundle        # rebuild the demo model
```

## License

[MIT](LICENSE)
