# Project brief: human-in-the-loop text triage system

## Goal

Build a production-shaped, local-first MLOps application for binary text triage: given a customer message, determine whether it needs human handling. Users bring a dataset and an explicit label contract. The system supports labeling, reproducible training, model promotion, tiered inference, and human feedback that can improve later training snapshots.

Optimize for one developer, a credible end-to-end demo, and trustworthy evaluation. This is a single-user tool, not a multi-tenant platform.

## Research context

This grows out of the completed `human-loop` research repository. That repository remains the case study; this repository is the reusable tool.

Reported findings from that project:
- Zero-shot transfer reached approximately 0.57 macro F1; in-domain DistilBERT reached approximately 0.80 and BERTweet approximately 0.85.
- In-domain labels mattered more than architecture.
- Errors were concentrated around an uncertain score band in the studied data.
- Category metrics need sample counts; thresholds must be selected on validation data; comparisons need identical evaluation examples and labels.

Treat these as historical results to reproduce or hypotheses to validate, not guarantees for arbitrary user datasets. In particular, confidence does not establish correctness under distribution shift.

## Architecture and ownership

1. **Next.js / TypeScript** owns the UI, public API under `app/api`, and application SQLite database using either Prisma or Drizzle. It owns datasets, label events, snapshots, decision logs, and feedback.
2. **Python / FastAPI** owns validation, preprocessing, training, evaluation, scoring, routing, and an MLflow wrapper. All Python operations are also reachable from a CLI; API and CLI call the same service layer.
3. **MLflow** owns experiment tracking, model registry metadata, and packaged model artifacts. Do not embed its UI or use MLflow Projects or MLflow serving in the product.

Only Next.js calls the Python HTTP API. Python does not write the application database. Use a shared local volume for immutable snapshot exports, model artifacts, and durable training-job files. Python has no independent mutable copy of the dataset store.

Pydantic is the canonical source for API and interchange schemas. Export OpenAPI/JSON Schema and generate TypeScript types. Do not hand-maintain duplicate transport types. Database models are internal persistence representations. Static TypeScript types do not replace runtime validation: imports must pass canonical Python validation before commit.

Include explicit schema and contract versions. Provide one command to regenerate types and a check for stale generated output.

## Dataset and label contract

Canonical row fields:
- `id`: stable identifier, unique within a dataset.
- `text`: nonempty input text.
- `label`: `0`, `1`, or null for unlabeled rows.
- `category`: optional, from the contract's allowed categories.
- `split`: train, validation, test, or unassigned.
- `source`: optional provenance.
- `group_id`: optional conversation/thread identifier used to prevent split leakage.

The YAML/JSON label contract defines:
- Positive and negative class meanings, including ambiguous cases.
- Allowed categories and whether category is required.
- Classification-threshold objective and any error constraints.
- Routing-policy objective and allowed fallback behavior.
- Contract version.

Separate the requested policy from the concrete thresholds selected by a run. A semantic contract change requires explicit label compatibility review; never silently reuse old labels under a new definition.

### Import and snapshots

- Support generic CSV first, TWCS next, and Bitext later as worked examples.
- Report exact row/field errors, duplicate IDs, empty text, invalid labels/categories, class balance, category counts, and split/group conflicts.
- Validate the entire import before committing. Failed imports leave no partial dataset.
- Represent imported labels as label events with source provenance.
- Create snapshots explicitly. Each snapshot freezes rows, resolved labels, contract, preprocessing configuration, and split manifest with stable content hashes.
- Assign splits at the first training-ready snapshot. Keep assignments dataset-owned and fixed across runs and subsequent snapshots.
- Preserve supplied valid splits. Otherwise use a deterministic seeded strategy, grouping conversations and exact duplicate texts to prevent leakage. Reject supplied splits that violate group isolation.
- Unlabeled rows remain outside supervised training/evaluation exports until eligible.
- New reviewed production examples default to train; examples belonging to an existing group inherit that group's split. Reject conflicting assignments.

### Label events and feedback

Use an append-only event log containing event ID, dataset/row ID, label, category, labeler, timestamp, reason, event kind, contract version, and optional decision ID.

For the first version, resolve the current label from the latest accepted label-setting event using a stable sequence. Corrections append events; clearing a label appends an explicit clear event. Preserve all history.

LLM suggestions are suggestions, not accepted labels. Only explicit human confirmation creates an accepted human label event. Distinguish imported, LLM-generated, and human-confirmed provenance.

Feedback on train examples may enter the next explicit training snapshot. Validation/test feedback remains an audit annotation by default and must not enter training. Correcting evaluation labels requires an explicit new evaluation version. Preserve prior evaluation versions and results.

Do not automatically retrain, create snapshots, or promote models after feedback.

## Training and evaluation

Put model implementations behind one interface:
- TF-IDF + logistic regression.
- `distilbert-base-uncased`.
- `vinai/bertweet-base` in a later milestone.

Use a device helper for CUDA, MPS, or CPU with an explicit override. Keep preprocessing, truncation, and tokenization identical between training and inference. Fit learned preprocessing only on training data.

Each run records:
- Dataset identity, snapshot hash, training-data hash, split-manifest hash, evaluation-data/label hash, and contract version.
- Model/checkpoint revision, preprocessing configuration, hyperparameters, seed, device, code revision, dependency versions, and duration.
- Validation/test macro F1, positive-class precision and recall, confusion matrix, and category metrics with explicit denominators.
- For per-category positive recall, show positive-label support; also show total category count. Undefined metrics are null, not zero.
- Validation threshold sweep, chosen classification threshold, routing bounds, selection objective, and constraint feasibility.
- Per-row test predictions as an artifact.

Select all thresholds and routing bounds on validation data only. Evaluate test data after policies are frozen; never tune toward a target test score.

For each routing policy, report automatic-decision coverage, error rate among automatically decided examples, positives incorrectly auto-handled divided by all positives, and the fraction of model errors captured by the review band. These are empirical measurements, not safety guarantees.

If a constraint cannot be satisfied, report that explicitly and refuse promotion under that policy.

Run comparisons require identical evaluation examples, evaluation labels, split assignments for those examples, contract semantics, and metric definitions. Training snapshots may differ so feedback-driven improvements can be compared. Reject incompatible runs in a single comparison table and explain the mismatch.

## Training jobs

Run training as a subprocess with status polling and log tailing. No task queue infrastructure.

- Allow one active training job at a time; reject additional starts with a clear busy response.
- Persist job ID, configuration, snapshot reference, status, timestamps, process identity, exit code, and logs in local job files.
- Support start, status, logs, and cancellation through API and CLI.
- Use queued/starting, running, succeeded, failed, canceled, and interrupted states as appropriate.
- Reconcile persisted jobs on restart. Mark jobs without a verifiably live worker as interrupted; never leave them running forever or start duplicate workers.
- Failed/canceled runs must not become promotable.

## Model packaging and promotion

Use MLflow Models with a custom pyfunc package containing the fitted pipeline or encoder weights/tokenizer, preprocessing, class mapping, classification threshold, routing bounds, and label contract.

Pin MLflow and define a registry `production` alias/pointer to a concrete model version. Resolve the implementation against the pinned version's supported API. Promotion and rollback are explicit operations; record who/what initiated them and the prior/new versions.

Scoring loads the production version by registered model name and logs the actual resolved version for every decision. In-flight requests keep their resolved version. Reload only after the replacement model loads successfully.

Pruning is an explicit dry-run-first operation. Prune only unpromoted, unreferenced run weights. Preserve metrics, manifests, and predictions; protect current production, previously promoted rollback artifacts, and active jobs. Mark pruned runs as no longer loadable/promotable without retraining.

## Serving and routing

Public endpoints are `POST /api/triage`, `POST /api/triage/batch`, and `POST /api/feedback`; Next.js calls internal Python scoring endpoints.

Separate the predicted class, the mechanism that resolved it, and the business action:
- `probability`: encoder/baseline score for label 1; do not describe it as calibrated unless calibration was evaluated.
- `predicted_label`: model label using the classification threshold.
- `final_label`: resolved label, or null while awaiting human review.
- `resolved_by`: model, rule, llm, or human_pending.
- `action`: auto_handle, escalate, or review.
- `decision_id`, `model_version`, and `policy_version`.
- Optional category, reason, and fallback/error metadata.

For a policy with `low <= classification_threshold <= high`:
- `p < low`: model resolves label 0; action is auto_handle.
- `p >= high`: model resolves label 1; action is escalate.
- Otherwise: use the configured second tier, or action review with human_pending.

A high-confidence positive automatically decides that human handling is needed. This is distinct from asking a human to resolve an uncertain classification.

Claude is optional. Validate its structured output against the contract. Record model ID, prompt/policy version, latency, and available usage metadata. A keyword rule is a separate optional resolver with explicit matches and a no-match outcome; never imply it has LLM-equivalent quality. Timeouts, invalid LLM output, and unresolved rule matches fall back to human review. Do not expose hidden chain-of-thought; reasons are short decision explanations.

Log each successful decision in Next.js with input provenance, score, labels, resolver, action, model/policy versions, timestamp, and latency. Use stable request/decision identifiers to avoid duplicate decisions or feedback on retries. Batch responses preserve input order and include per-item failures.

Feedback references the original decision and model version. For previously unseen production text, create a dataset row when feedback is accepted, retaining its provenance and applying the split rules above.

## Product pages

Build functional pages in this order:
1. **Datasets**: import, validation report, counts, split inspection, snapshot creation.
2. **Label**: label from scratch or audit existing labels, optional LLM suggestion, explicit human confirmation, event history. Writes events only.
3. **Train**: choose snapshot/model/configuration, start/cancel a job, view logs/results, compare compatible runs, promote/rollback.
4. **Triage**: single/batch input, score and action display, explanation when available, human override.
5. **Monitor**: decision volume, score distributions against a fixed reference, uncertain-band fraction, and override rate over time.

Stratify monitoring by model/policy version. Show counts and denominators. Distinguish overrides divided by reviewed decisions from review coverage over all decisions; unreviewed decisions are not confirmed correct. Score-distribution changes are drift indicators, not proof of accuracy degradation.

Defer Cohen's kappa until independent paired labeling exists. Do not calculate it from an audit workflow where reviewers saw the prior label.

## Operational constraints

- One developer; prefer SQLite and plain files. No Celery, Kubernetes, SageMaker, feature store, or distributed queue.
- `docker compose up` runs the local stack with persistent volumes and a working CPU demo. Document host-based GPU/MPS training separately.
- Track a small example dataset and tiny trained TF-IDF artifact with provenance so scoring works without an LLM key or transformer download after dependencies are installed. Clearly label demo metrics.
- No authentication: the tool runs on one person's laptop. Bind the local stack to localhost by default and keep Python/MLflow internal; that binding is the whole access-control story. Keep service secrets (LLM keys) on the Python service only, never in browser bundles.
- State in the README that this is a single-user local tool without accounts, roles, verified labeler identities, or tenant isolation, and that exposing it beyond localhost is out of scope.
- Do not log secrets. Send user text to an external LLM only when that tier is explicitly enabled.
- Keep dependencies pinned and configuration explicit. Do not upload arbitrary serialized model artifacts through the public API.

## Milestones and acceptance

### 1. Complete baseline path

Scaffold `/web`, `/ml`, compose, and schema/type generation. Implement contract validation, CSV import, immutable snapshots, durable training jobs, TF-IDF training with MLflow logging, promotion, and scoring with an uncertainty band that falls back to human review.

Acceptance: a fresh clone can import the example data, create a snapshot, train, inspect metrics, promote, and score through the public API. Python compute operations also work through the CLI. The bundled artifact enables immediate demo scoring.

### 2. Research replication

Add the TWCS adapter and DistilBERT. First inspect the original `human-loop` experiment and capture its exact dataset/split hashes, labels, preprocessing, checkpoint, hyperparameters, seed, metric definition, and execution environment in a replication manifest.

Target approximately 0.80 macro F1 only when reproducing the same evaluation protocol. Define a justified tolerance from the original run evidence before testing. If required data/configuration are unavailable, report the missing prerequisites; do not substitute data or claim replication.

If the original split has conversation leakage, preserve it only as a clearly labeled historical replication. Separately evaluate a corrected grouped split, without claiming the old score must carry over.

### 3. Human feedback loop

Build Datasets, Label, Train, and Triage pages. Demonstrate: an eligible train-row correction creates a label event, an explicit new snapshot captures it, and retraining uses it while the evaluation set remains frozen. Add optional Claude and rule resolvers.

### 4. Extensions

Add Monitor, Bitext, BERTweet, and artifact pruning. Independent double-labeling and agreement metrics are optional later work.

## Working style and verification

- Terse code, short responses, results over narrative. Avoid narrative comments; document non-obvious invariants where needed.
- Treat `/web`, `/ml`, and dependencies explicitly named in this brief as authorized. Choose either Prisma or Drizzle and state the choice. Ask before adding other dependencies or top-level directories.
- Start with milestone 1; do not build later milestones speculatively.
- Test meaningful invariants: no partial imports, immutable snapshots, split isolation, validation-only threshold selection, compatible comparisons, job recovery, routing boundaries/fallbacks, and feedback idempotency.
- Use a tiny CPU smoke test for routine checks. Run full TWCS replication when changes affect preprocessing, splits, training, or evaluation; do not retrain DistilBERT for unrelated UI refactors.
- Never invent benchmark numbers or weaken evaluation to achieve a target.
- At each milestone, report what works, commands/checks actually run, and concrete remaining blockers.
