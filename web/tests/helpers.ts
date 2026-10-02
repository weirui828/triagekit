import { vi } from "vitest";
import { openDb, type Db } from "@/db";
import * as mlmod from "@/lib/ml";

export const contract = {
  schema_version: "1", contract_version: "1.0", name: "t",
  positive: { name: "needs_human", definition: "x", examples: [] }, negative: { name: "auto", definition: "y", examples: [] },
  ambiguous_cases: [], categories: { allowed: ["billing", "general"], required: false },
  classification_threshold: { objective: "max_macro_f1", min_positive_recall: null },
  routing_policy: { objective: "max_coverage", max_auto_error_rate: null, max_missed_positive_rate: null, min_band_width: 0, fallback: "review" },
};

export async function freshDb(): Promise<Db> {
  return openDb(":memory:");
}

/** Replace the Python API with an in-process stub keyed by path. */
export function stubMl(handlers: Record<string, (body: unknown) => unknown>) {
  return vi.spyOn(mlmod, "ml").mockImplementation((async (_m: string, p: string, opts?: { body?: unknown }) => {
    const h = handlers[p];
    if (!h) throw new mlmod.MlError(500, { detail: `no stub for ${p}` });
    return h(opts?.body);
  }) as unknown as typeof mlmod.ml);
}

export const score = (probability: number, low = 0.4, high = 0.6) => {
  const action = probability < low ? "auto_handle" : probability >= high ? "escalate" : "review";
  return {
    probability, predicted_label: probability >= 0.5 ? 1 : 0, final_label: action === "review" ? null : action === "escalate" ? 1 : 0,
    resolved_by: action === "review" ? "human_pending" : "model", action, model_version: "triagekit:1", policy_version: "1.0:abc",
    classification_threshold: 0.5, routing_low: low, routing_high: high, category: null, reason: "r", fallback: null,
  };
};
