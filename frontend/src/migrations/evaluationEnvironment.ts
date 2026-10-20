import type { MigrationEvaluationStatus } from "../adk/migrations";

type EvaluationEnvironment = NonNullable<
  MigrationEvaluationStatus["environment"]
>;

export function initialEvaluationEnvironmentValues(
  environment: EvaluationEnvironment | undefined,
): Record<string, string> {
  if (!environment) return {};
  const declared = new Set([...environment.required, ...environment.optional]);
  return Object.fromEntries(
    Object.entries(environment.defaults).filter(([key]) => declared.has(key)),
  );
}
