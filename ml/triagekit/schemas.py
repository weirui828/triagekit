"""Canonical API and interchange schemas. TypeScript types are generated from these."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .settings import SCHEMA_VERSION

Split = Literal["train", "validation", "test", "unassigned"]
Label = Literal[0, 1]
Action = Literal["auto_handle", "escalate", "review"]
ResolvedBy = Literal["model", "rule", "llm", "human_pending"]
JobStatus = Literal["queued", "starting", "running", "succeeded", "failed", "canceled", "interrupted"]
ModelKind = Literal["tfidf_lr", "distilbert", "bertweet"]
ThresholdObjective = Literal["max_macro_f1", "max_positive_f1", "fixed"]
RoutingObjective = Literal["max_coverage"]
Fallback = Literal["review"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- label contract ----------
class ClassDefinition(Strict):
    name: str
    definition: str
    examples: list[str] = Field(default_factory=list)


class CategoryContract(Strict):
    allowed: list[str] = Field(default_factory=list)
    required: bool = False


class ThresholdPolicy(Strict):
    objective: ThresholdObjective = "max_macro_f1"
    fixed_threshold: float | None = Field(default=None, gt=0, lt=1, description="Required when objective is fixed")
    min_positive_recall: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _fixed(self):
        if (self.objective == "fixed") != (self.fixed_threshold is not None):
            raise ValueError("fixed_threshold must be set exactly when objective is 'fixed'")
        return self


class Rule(Strict):
    """Keyword/regex rule. Matches resolve the label; no match falls through to review."""
    name: str
    label: Label
    patterns: list[str] = Field(min_length=1, description="case-insensitive regular expressions; any match fires")
    category: str | None = None


SecondTier = Literal["none", "rule", "llm"]


class RoutingPolicy(Strict):
    objective: RoutingObjective = "max_coverage"
    second_tier: SecondTier = "none"
    rules: list[Rule] = Field(default_factory=list)
    max_auto_error_rate: float | None = Field(default=None, ge=0, le=1)
    max_missed_positive_rate: float | None = Field(default=None, ge=0, le=1)
    min_band_width: float = Field(default=0.0, ge=0, le=1, description="Minimum high-low; forces a review band even when validation is perfect")
    fallback: Fallback = "review"


class LabelContract(Strict):
    schema_version: str = SCHEMA_VERSION
    contract_version: str
    name: str
    positive: ClassDefinition
    negative: ClassDefinition
    ambiguous_cases: list[str] = Field(default_factory=list)
    categories: CategoryContract = Field(default_factory=CategoryContract)
    classification_threshold: ThresholdPolicy = Field(default_factory=ThresholdPolicy)
    routing_policy: RoutingPolicy = Field(default_factory=RoutingPolicy)


class ContractValidateResponse(Strict):
    ok: bool
    errors: list[str]
    contract: LabelContract | None = None
    contract_hash: str | None = None


# ---------- rows ----------
class Row(Strict):
    id: str = Field(min_length=1)
    text: str
    label: Label | None = None
    category: str | None = None
    split: Split = "unassigned"
    source: str | None = None
    group_id: str | None = None


class RawRow(Strict):
    """Unvalidated row as parsed from CSV; every field is an optional string."""
    id: str | None = None
    text: str | None = None
    label: str | None = None
    category: str | None = None
    split: str | None = None
    source: str | None = None
    group_id: str | None = None


class RowError(Strict):
    line: int
    id: str | None
    field: str | None
    message: str


class ValidationReport(Strict):
    ok: bool
    row_count: int
    accepted_count: int
    errors: list[RowError]
    duplicate_ids: list[str]
    label_counts: dict[str, int]
    category_counts: dict[str, int]
    split_counts: dict[str, int]
    group_split_conflicts: list[str]


class ImportValidateRequest(Strict):
    contract: LabelContract
    rows: list[RawRow] | None = None
    csv: str | None = None

    @model_validator(mode="after")
    def _one_source(self):
        if (self.rows is None) == (self.csv is None):
            raise ValueError("provide exactly one of rows or csv")
        return self


class ImportValidateResponse(Strict):
    report: ValidationReport
    rows: list[Row]


# ---------- splits ----------
class SplitAssignRequest(Strict):
    rows: list[Row]
    seed: int = 42
    train_fraction: float = Field(default=0.7, gt=0, lt=1)
    validation_fraction: float = Field(default=0.15, gt=0, lt=1)

    @model_validator(mode="after")
    def _fractions(self):
        if self.train_fraction + self.validation_fraction >= 1:
            raise ValueError("train_fraction + validation_fraction must be < 1")
        return self


class SplitAssignment(Strict):
    id: str
    split: Split
    group_key: str


class SplitAssignResponse(Strict):
    ok: bool
    errors: list[str]
    assignments: list[SplitAssignment]
    strategy: Literal["supplied", "seeded_grouped", "mixed"]
    seed: int
    split_counts: dict[str, int]


# ---------- preprocessing ----------
class PreprocessingConfig(Strict):
    lowercase: bool = True
    collapse_whitespace: bool = True
    strip_urls: bool = False
    max_chars: int = Field(default=2000, ge=1, le=1_000_000)


# ---------- snapshots ----------
class SnapshotExportRequest(Strict):
    snapshot_id: str = Field(min_length=1)
    dataset_id: str
    contract: LabelContract
    preprocessing: PreprocessingConfig = Field(default_factory=PreprocessingConfig)
    rows: list[Row]


class SnapshotManifest(Strict):
    schema_version: str = SCHEMA_VERSION
    snapshot_id: str
    dataset_id: str
    created_at: str
    contract_version: str
    contract_hash: str
    preprocessing: PreprocessingConfig
    row_count: int
    labeled_count: int
    split_counts: dict[str, int]
    rows_hash: str
    training_data_hash: str
    split_manifest_hash: str
    evaluation_hash: str
    snapshot_hash: str
    path: str


class SnapshotExportResponse(Strict):
    manifest: SnapshotManifest
    created: bool


# ---------- training ----------
class TfidfLrParams(Strict):
    ngram_max: int = Field(default=2, ge=1, le=3)
    min_df: int = Field(default=1, ge=1)
    max_features: int | None = Field(default=50000, ge=100)
    C: float = Field(default=1.0, gt=0)
    class_weight: Literal["balanced", "none"] = "balanced"


class DistilbertParams(Strict):
    checkpoint: str = "distilbert-base-uncased"
    epochs: int = Field(default=4, ge=1, le=50)
    batch_size: int = Field(default=16, ge=1)
    learning_rate: float = Field(default=3e-5, gt=0)
    max_length: int = Field(default=128, ge=8, le=512)
    warmup_ratio: float = Field(default=0.1, ge=0, le=1)
    weight_decay: float = Field(default=0.01, ge=0)
    grad_clip_norm: float = Field(default=1.0, gt=0)
    class_weighted_loss: bool = True


PARAMS_FOR_MODEL: dict[str, type[Strict]] = {"tfidf_lr": TfidfLrParams, "distilbert": DistilbertParams, "bertweet": DistilbertParams}


class TrainConfig(Strict):
    snapshot_id: str
    model: ModelKind = "tfidf_lr"
    params: TfidfLrParams | DistilbertParams = Field(default_factory=TfidfLrParams)

    @model_validator(mode="before")
    @classmethod
    def _params_by_model(cls, data):
        if isinstance(data, dict):
            kind = data.get("model", "tfidf_lr")
            p = data.get("params")
            klass = PARAMS_FOR_MODEL.get(kind)
            if klass is not None and (p is None or isinstance(p, dict)):
                p = dict(p or {})
                if kind == "bertweet":
                    p.setdefault("checkpoint", "vinai/bertweet-base")
                data = {**data, "params": klass.model_validate(p)}
        return data

    @model_validator(mode="after")
    def _params_match(self):
        want = PARAMS_FOR_MODEL[self.model]
        if not isinstance(self.params, want):
            raise ValueError(f"model {self.model} needs {want.__name__}")
        return self
    seed: int = 42
    device: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    experiment: str = "triagekit"


class JobStartResponse(Strict):
    job: JobRecord


class JobRecord(Strict):
    schema_version: str = SCHEMA_VERSION
    job_id: str
    config: TrainConfig
    status: JobStatus
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    pid: int | None = None
    process_start: str | None = None
    exit_code: int | None = None
    run_id: str | None = None
    error: str | None = None


class JobLogsResponse(Strict):
    job_id: str
    status: JobStatus
    lines: list[str]
    offset: int
    next_offset: int


class JobListResponse(Strict):
    jobs: list[JobRecord]


# ---------- runs / evaluation ----------
class ConfusionMatrix(Strict):
    tn: int
    fp: int
    fn: int
    tp: int


class CategoryMetrics(Strict):
    category: str
    count: int
    positive_support: int
    positive_recall: float | None
    accuracy: float | None


class ClassificationMetrics(Strict):
    n: int
    macro_f1: float | None
    positive_precision: float | None
    positive_recall: float | None
    positive_f1: float | None
    accuracy: float | None
    confusion: ConfusionMatrix
    categories: list[CategoryMetrics]


class RoutingMetrics(Strict):
    """Empirical measurements on one evaluation set. Not safety guarantees."""
    n: int
    low: float
    high: float
    auto_decided: int
    coverage: float | None
    auto_errors: int
    auto_error_rate: float | None
    positives_total: int
    positives_auto_handled: int
    missed_positive_rate: float | None
    model_errors_total: int
    model_errors_in_band: int
    errors_captured_by_band: float | None
    review_count: int


class ThresholdSweepPoint(Strict):
    threshold: float
    macro_f1: float | None
    positive_precision: float | None
    positive_recall: float | None
    positive_f1: float | None


class PolicySelection(Strict):
    classification_threshold: float
    threshold_objective: ThresholdObjective
    threshold_feasible: bool
    routing_low: float
    routing_high: float
    routing_objective: RoutingObjective
    routing_feasible: bool
    notes: list[str]


class RunManifest(Strict):
    schema_version: str = SCHEMA_VERSION
    run_id: str
    job_id: str | None
    dataset_id: str
    snapshot_id: str
    snapshot_hash: str
    training_data_hash: str
    split_manifest_hash: str
    evaluation_hash: str
    contract_version: str
    contract_hash: str
    model: ModelKind
    checkpoint: str | None
    preprocessing: PreprocessingConfig
    params: dict[str, Any]
    seed: int
    device: str
    code_revision: str | None
    dependency_versions: dict[str, str]
    duration_seconds: float
    metric_definitions_version: str


class RunSummary(Strict):
    run_id: str
    status: str
    start_time: str | None
    manifest: RunManifest | None
    policy: PolicySelection | None
    validation: ClassificationMetrics | None
    test: ClassificationMetrics | None
    validation_routing: RoutingMetrics | None
    test_routing: RoutingMetrics | None
    promotable: bool
    not_promotable_reason: str | None
    pruned: bool = False


class RunDetail(RunSummary):
    threshold_sweep: list[ThresholdSweepPoint]


class RunListResponse(Strict):
    runs: list[RunSummary]


class CompareRequest(Strict):
    run_ids: list[str] = Field(min_length=2)


class CompareResponse(Strict):
    compatible: bool
    mismatches: list[str]
    runs: list[RunSummary]


# ---------- registry ----------
class PromoteRequest(Strict):
    run_id: str
    initiated_by: str = "api"
    reason: str | None = None


class RollbackRequest(Strict):
    initiated_by: str = "api"
    reason: str | None = None


class PromotionRecord(Strict):
    event_id: str
    kind: Literal["promote", "rollback"]
    at: str
    initiated_by: str
    reason: str | None
    prior_version: str | None
    new_version: str
    run_id: str | None


class ProductionInfo(Strict):
    model_name: str
    version: str | None
    run_id: str | None
    source: Literal["registry", "bundled", "none"]
    loaded_version: str | None
    history: list[PromotionRecord]


# ---------- scoring ----------
class ScoreRequest(Strict):
    text: str = Field(min_length=1)
    request_id: str | None = None


class ScoreBatchRequest(Strict):
    items: list[ScoreRequest] = Field(min_length=1, max_length=500)


class LlmMeta(Strict):
    model_id: str
    prompt_version: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    stop_reason: str | None = None


class ScoreResult(Strict):
    """`probability` is the raw model score for label 1; calibration is not evaluated."""
    probability: float
    predicted_label: Label
    final_label: Label | None
    resolved_by: ResolvedBy
    action: Action
    model_version: str
    policy_version: str
    classification_threshold: float
    routing_low: float
    routing_high: float
    category: str | None = None
    reason: str | None = None
    fallback: str | None = None
    llm: LlmMeta | None = None


class SuggestRequest(Strict):
    contract: LabelContract
    text: str = Field(min_length=1)


class SuggestResponse(Strict):
    ok: bool
    label: Label | None
    category: str | None
    reason: str | None
    llm: LlmMeta | None
    error: str | None = None


class PruneCandidate(Strict):
    run_id: str
    model_id: str | None
    bytes: int
    reason: str


class PruneRequest(Strict):
    dry_run: bool = True
    experiment: str | None = None


class PruneResponse(Strict):
    dry_run: bool
    pruned: list[PruneCandidate]
    protected: list[PruneCandidate]
    bytes_freed: int


class PredictionRow(Strict):
    id: str
    label: Label
    probability: float
    predicted_label: Label
    category: str | None = None


class PredictionsResponse(Strict):
    run_id: str
    split: Literal["test"]
    rows: list[PredictionRow]


class ScoreBatchItem(Strict):
    index: int
    request_id: str | None
    result: ScoreResult | None
    error: str | None


class ScoreBatchResponse(Strict):
    items: list[ScoreBatchItem]
    model_version: str | None


class HealthResponse(Strict):
    ok: bool
    schema_version: str
    version: str
    mlflow_uri: str
    data_dir: str
    llm_enabled: bool = False
    llm_model: str | None = None


class ErrorResponse(Strict):
    error: str
    detail: Any = None


JobStartResponse.model_rebuild()
