# Host-based development. Docker: `docker compose up --build`.
SHELL := /bin/bash
export TRIAGEKIT_DATA_DIR ?= $(CURDIR)/data
export TRIAGEKIT_DB ?= $(CURDIR)/data/app.db
export ML_API_URL ?= http://127.0.0.1:8000
export MLFLOW_DISABLE_AGENT_HINT = 1

.PHONY: install ml-serve mlflow-ui web-dev test test-ml test-web gen-types check-types bundle lint replicate feedback-loop

install:
	cd ml && uv sync
	cd web && pnpm install

ml-serve:
	cd ml && uv run triagekit serve --port 8000

# MLflow's own tracking UI over the same local sqlite store the CLI and API write.
# Read-only in practice; the product never embeds it. http://127.0.0.1:5000
mlflow-ui:
	cd ml && uv run mlflow ui --host 127.0.0.1 --port 5000 \
		--backend-store-uri sqlite:///$(TRIAGEKIT_DATA_DIR)/mlflow.db \
		--default-artifact-root $(TRIAGEKIT_DATA_DIR)/mlruns

web-dev:
	cd web && pnpm dev -p 3000

test: test-ml test-web check-types

test-ml:
	cd ml && uv run pytest -q

test-web:
	cd web && pnpm typecheck && pnpm test

lint:
	cd web && pnpm lint

# Pydantic -> OpenAPI -> TypeScript. Commit the outputs.
gen-types:
	cd ml && uv run triagekit openapi --out openapi.json
	cd web && pnpm gen:types

# Fails when ml/openapi.json or the generated .d.ts is stale.
check-types:
	cd ml && uv run triagekit openapi --out /tmp/triagekit-openapi.json && diff -q /tmp/triagekit-openapi.json openapi.json
	cd web && pnpm check:types

# Full TWCS replication (host, MPS/CUDA/CPU). TWCS=/path/to/llm_labeled_5k.csv SEEDS="42 1337 2024"
TWCS ?= $(HOME)/dev/human-loop/data/twcs/llm_labeled_5k.csv
SEEDS ?= 42
replicate:
	cd ml && uv run triagekit replicate --data $(TWCS) --seeds $(SEEDS)

# Human feedback loop demonstration through the public API (both servers running).
feedback-loop:
	bash web/scripts/feedback_loop.sh

# Rebuild the tracked demo artifact from the example data.
bundle:
	cd ml && uv run triagekit bundle --out bundled_model
