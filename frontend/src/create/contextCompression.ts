import type { ContextCompressionDraft } from "./types";

export const capacityFields = ["context_window", "input_limit", "output_reserve"] as const;
export const ratioDefaults = { trigger_ratio: 0.8, summary_trigger_ratio: 0.95, target_ratio: 0.6 } as const;
export const ratioFields = ["trigger_ratio", "target_ratio", "summary_trigger_ratio"] as const;

/** The same policy is used by imported drafts, YAML and generated Python. */
export function normalizeContextCompression(value: unknown): ContextCompressionDraft {
  if (value === undefined) return { mode: "auto" };
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("contextCompression must be an object");
  }
  const raw = value as Record<string, unknown>;
  const fields = [...capacityFields, ...ratioFields];
  if (Object.keys(raw).some((key) => key !== "mode" && !fields.some((field) => field === key))) {
    throw new Error("contextCompression contains an unsupported field");
  }
  const mode = raw.mode === undefined ? "auto" : raw.mode;
  if (mode !== "auto" && mode !== "off") throw new Error("contextCompression.mode must be auto or off");
  const result: ContextCompressionDraft = { mode };
  for (const field of capacityFields) {
    if (raw[field] === undefined || raw[field] === null) continue;
    if (typeof raw[field] !== "number" || !Number.isSafeInteger(raw[field]) || raw[field] <= 0) {
      throw new Error(`contextCompression.${field} must be a positive integer`);
    }
    result[field] = raw[field];
  }
  for (const field of ratioFields) {
    if (raw[field] === undefined || raw[field] === null) continue;
    if (typeof raw[field] !== "number" || !Number.isFinite(raw[field]) || raw[field] <= 0 || raw[field] > 1) {
      throw new Error(`contextCompression.${field} must be between zero and one`);
    }
    result[field] = raw[field];
  }
  const ratios = { ...ratioDefaults, ...result };
  if (ratios.target_ratio >= ratios.trigger_ratio || ratios.trigger_ratio > ratios.summary_trigger_ratio) {
    throw new Error("contextCompression requires target_ratio < trigger_ratio <= summary_trigger_ratio");
  }
  return result;
}
