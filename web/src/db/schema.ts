import { index, integer, primaryKey, real, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

// Internal persistence shapes. Transport types come from src/generated/ml-api.d.ts (Pydantic is canonical).

export const datasets = sqliteTable("datasets", {
  id: text("id").primaryKey(),
  name: text("name").notNull(),
  contractJson: text("contract_json").notNull(),
  contractVersion: text("contract_version").notNull(),
  contractHash: text("contract_hash").notNull(),
  splitSeed: integer("split_seed").notNull().default(42),
  createdAt: text("created_at").notNull(),
});

export const rows = sqliteTable(
  "rows",
  {
    datasetId: text("dataset_id").notNull().references(() => datasets.id),
    id: text("id").notNull(),
    text: text("text").notNull(),
    category: text("category"),
    split: text("split").notNull().default("unassigned"), // dataset-owned; fixed once assigned
    source: text("source"),
    groupId: text("group_id"),
    createdAt: text("created_at").notNull(),
  },
  (t) => [primaryKey({ columns: [t.datasetId, t.id] }), index("rows_split").on(t.datasetId, t.split)],
);

// Append-only. Resolved label = latest label-setting event by seq.
export const labelEvents = sqliteTable(
  "label_events",
  {
    seq: integer("seq").primaryKey({ autoIncrement: true }),
    eventId: text("event_id").notNull().unique(),
    datasetId: text("dataset_id").notNull(),
    rowId: text("row_id").notNull(),
    label: integer("label"),
    category: text("category"),
    labeler: text("labeler").notNull(),
    at: text("at").notNull(),
    reason: text("reason"),
    // imported | human | human_audit | llm_suggestion | clear
    kind: text("kind").notNull(),
    contractVersion: text("contract_version").notNull(),
    decisionId: text("decision_id"),
  },
  (t) => [index("events_row").on(t.datasetId, t.rowId)],
);

export const snapshots = sqliteTable("snapshots", {
  id: text("id").primaryKey(),
  datasetId: text("dataset_id").notNull().references(() => datasets.id),
  snapshotHash: text("snapshot_hash").notNull(),
  manifestJson: text("manifest_json").notNull(),
  createdAt: text("created_at").notNull(),
});

export const decisions = sqliteTable(
  "decisions",
  {
    decisionId: text("decision_id").primaryKey(),
    requestId: text("request_id"),
    text: text("text").notNull(),
    source: text("source"),
    datasetId: text("dataset_id"),
    rowId: text("row_id"),
    probability: real("probability").notNull(),
    predictedLabel: integer("predicted_label").notNull(),
    finalLabel: integer("final_label"),
    resolvedBy: text("resolved_by").notNull(),
    action: text("action").notNull(),
    modelVersion: text("model_version").notNull(),
    policyVersion: text("policy_version").notNull(),
    reason: text("reason"),
    latencyMs: integer("latency_ms").notNull(),
    createdAt: text("created_at").notNull(),
  },
  (t) => [uniqueIndex("decisions_request").on(t.requestId), index("decisions_model").on(t.modelVersion, t.createdAt)],
);

export const feedback = sqliteTable(
  "feedback",
  {
    feedbackId: text("feedback_id").primaryKey(),
    decisionId: text("decision_id").notNull().references(() => decisions.decisionId),
    modelVersion: text("model_version").notNull(),
    label: integer("label").notNull(),
    category: text("category"),
    labeler: text("labeler").notNull(),
    reason: text("reason"),
    datasetId: text("dataset_id").notNull(),
    rowId: text("row_id").notNull(),
    eventId: text("event_id").notNull(),
    trainingEligible: integer("training_eligible", { mode: "boolean" }).notNull(),
    createdAt: text("created_at").notNull(),
  },
  (t) => [index("feedback_decision").on(t.decisionId)],
);
