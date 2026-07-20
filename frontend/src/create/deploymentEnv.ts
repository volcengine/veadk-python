export interface RuntimeEnvSpec {
  key: string;
  required: boolean;
}

/** Convert only the currently active feature settings into runtime env rows. */
export function runtimeEnvVars(
  specs: RuntimeEnvSpec[],
  values: Record<string, string>,
): { key: string; value: string }[] {
  const env = new Map<string, string>();
  for (const spec of specs) {
    const value = values[spec.key] ?? "";
    if (value.trim()) env.set(spec.key, value);
  }
  return [...env].map(([key, value]) => ({ key, value }));
}

export function firstMissingRuntimeEnv(
  specs: RuntimeEnvSpec[],
  values: Record<string, string>,
): RuntimeEnvSpec | undefined {
  return specs.find((spec) => spec.required && !values[spec.key]?.trim());
}
