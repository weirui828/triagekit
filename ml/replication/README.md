# Replication: human-loop TWCS DistilBERT

`twcs_distilbert.json` captures the original experiment exactly as found in the `human-loop`
checkout (commit `dd256a6`): dataset hash, split protocol and per-split id hashes, preprocessing,
checkpoint, hyperparameters, selection rules, metric definition, reported figures, execution environment,
and the tolerance used to judge a replication. Everything in it was read from the original notebooks,
source and tracked metrics files, and then verified by reconstructing the split and re-scoring the saved
weights in the original environment (exact match: 0.7842 macro F1, confusion 630/64/111/195).

## Prerequisites

- `data/twcs/llm_labeled_5k.csv` from the human-loop repo (sha256 `b94f9cf9…334f11`). The 5000 LLM-labeled
  threads are the whole evaluation protocol; without this exact file the command refuses to run rather than
  substitute data.
- `distilbert-base-uncased` from the Hugging Face hub (downloaded on first use).
- `torch` + `transformers` (installed by default via the `encoders` dependency group).

## Run

```bash
cd ml
uv run triagekit replicate --data ~/dev/human-loop/data/twcs/llm_labeled_5k.csv --seeds 42          # one seed, ~4 min on MPS
uv run triagekit replicate --data ~/dev/human-loop/data/twcs/llm_labeled_5k.csv --seeds 42 1337 2024 # three seeds
```

The command verifies the data and split hashes, exports the immutable snapshot `twcs-replication-<hash>`
(no preprocessing outside the tokenizer; contract `examples/twcs.contract.yaml` with a fixed 0.5
threshold), trains with the original hyperparameters under MLflow experiment `twcs-replication`, and writes
a report to `data/replication/`. Per-seed results are compared to that seed's reported figure with an
absolute tolerance of 0.02; a three-seed mean is compared to 0.7969 with 0.015. See the `tolerance`
block in the manifest for the derivation.

## What a pass means

The score measures agreement with `claude-opus-5` labels on the original row-level split. Environment
differences from the original run (Python, torch, transformers, scikit-learn versions, device) are listed
in the report; a pass under a different environment replicates the protocol, not the bits.

## Leakage check

The original split is row-level stratified. Reconstructing it shows every duplicate opening message
(2 texts, 5 rows) inside train and one thread per row, so it has no conversation or duplicate-text
leakage and is used as-is. A grouped seeded split is therefore not needed for correctness; it can still be
produced with `triagekit adapt-twcs … && triagekit snapshot-create …` for a separate, clearly different
evaluation set, whose numbers are not comparable to the replication (different evaluation hash).

## Result (2026-09-13, this machine)

Same protocol, same data and split hashes, MPS. Environment differs from the original in Python
(3.12.13 vs 3.14.6) and scikit-learn (1.9.1 vs 1.8.0); torch 2.13.0 and transformers 5.14.1 match.

| seed | test macro F1 | reported | delta |
|-----:|--------------:|---------:|------:|
| 42   | 0.7927 | 0.7842 | +0.0085 |
| 1337 | 0.7959 | 0.7967 | -0.0008 |
| 2024 | 0.8100 | 0.8097 | +0.0003 |
| mean | 0.7995 | 0.7969 | +0.0026 |

All seeds within the 0.02 per-seed tolerance; the three-seed mean is within 0.015 of the reported mean.
Full report: `data/replication/twcs_distilbert_2026-09-13T201934+0000.json` (gitignored data volume).
Runs live in MLflow experiment `twcs-replication`. Under the TWCS contract's routing constraints, two of
the three runs have no feasible routing band on validation and are therefore not promotable; that is a
property of the contract, not of the replication.
