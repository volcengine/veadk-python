import type { ComponentPreferences, EvaluationPreferences, GeneratedDataset, GeneratedEvaluators } from "../adk/quality";

export interface PreferenceOutput<T> {
  value: T;
  signature: string;
}

export interface QualityPreferenceRecord {
  id: string;
  overall: EvaluationPreferences;
  components: ComponentPreferences | null;
  dataset?: PreferenceOutput<GeneratedDataset>;
  evaluators?: PreferenceOutput<GeneratedEvaluators>;
  errors?: Partial<Record<"dataset" | "evaluators", { code: string; diagnostics: string }>>;
  updatedAt: string;
}

export function preferenceSignature(overall: EvaluationPreferences, components: ComponentPreferences) {
  return JSON.stringify([overall, components]);
}

export function outputState(record: QualityPreferenceRecord, kind: "dataset" | "evaluators") {
  const output = record[kind];
  if (!output) return "pending";
  return record.components && output.signature === preferenceSignature(record.overall, record.components) ? "ready" : "outdated";
}

export function hasPreferenceSuggestion(value: string, suggestion: string) {
  return value.split("\n").some(line => line.trim() === suggestion.trim());
}

export function togglePreferenceSuggestion(value: string, suggestion: string) {
  if (hasPreferenceSuggestion(value, suggestion)) {
    return value.split("\n").filter(line => line.trim() !== suggestion.trim()).join("\n");
  }
  const next = value.trim() ? `${value}${value.endsWith("\n") ? "" : "\n"}${suggestion}` : suggestion;
  return next.length <= 6000 ? next : value;
}
