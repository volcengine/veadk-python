export interface RuntimeEnvSpec {
  key: string;
  required: boolean;
}

export interface RuntimeEnvSelection {
  env: RuntimeEnvSpec[];
  enableFlag?: string;
}

export interface RuntimeEnvConfiguration {
  specs: RuntimeEnvSpec[];
  fixedValues: Record<string, string>;
}

/** Merge active component settings and derive selected exporter enable flags. */
export function runtimeEnvConfiguration(
  selections: RuntimeEnvSelection[],
): RuntimeEnvConfiguration {
  const specs = new Map<string, RuntimeEnvSpec>();
  const fixedValues: Record<string, string> = {};
  for (const selection of selections) {
    for (const spec of selection.env) {
      const previous = specs.get(spec.key);
      if (!previous || (spec.required && !previous.required)) {
        specs.set(spec.key, spec);
      }
    }
    if (selection.enableFlag) {
      specs.set(selection.enableFlag, {
        key: selection.enableFlag,
        required: true,
      });
      fixedValues[selection.enableFlag] = "true";
    }
  }
  return { specs: [...specs.values()], fixedValues };
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
