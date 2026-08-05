export interface RuntimeEnvSpec {
  key: string;
  required: boolean;
  comment?: string;
  placeholder?: string;
  defaultValue?: string;
  help?: string;
  link?: { label: string; url: string };
  multiline?: boolean;
  format?: "json";
}

export interface RuntimeEnvSelection {
  env: RuntimeEnvSpec[];
  enableFlag?: string;
}

export interface RuntimeEnvConfiguration {
  specs: RuntimeEnvSpec[];
  fixedValues: Record<string, string>;
}

export interface RuntimeEnvDisplayRow extends RuntimeEnvSpec {
  value: string;
}

function runtimeEnvValue(
  spec: RuntimeEnvSpec,
  values: Record<string, string>,
): string {
  return values[spec.key] ?? spec.defaultValue ?? "";
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

/** Build the complete, including empty values, summary shown before deploy. */
export function runtimeEnvDisplayRows(
  specs: RuntimeEnvSpec[],
  values: Record<string, string>,
): RuntimeEnvDisplayRow[] {
  const deduped = runtimeEnvConfiguration([{ env: specs }]).specs;
  return deduped.map((spec) => ({
    ...spec,
    value: runtimeEnvValue(spec, values),
  }));
}

/** Convert only the currently active feature settings into runtime env rows. */
export function runtimeEnvVars(
  specs: RuntimeEnvSpec[],
  values: Record<string, string>,
): { key: string; value: string }[] {
  const env = new Map<string, string>();
  for (const spec of specs) {
    const value = runtimeEnvValue(spec, values);
    if (value.trim()) env.set(spec.key, value);
  }
  return [...env].map(([key, value]) => ({ key, value }));
}

export function firstMissingRuntimeEnv(
  specs: RuntimeEnvSpec[],
  values: Record<string, string>,
): RuntimeEnvSpec | undefined {
  return specs.find(
    (spec) => spec.required && !runtimeEnvValue(spec, values).trim(),
  );
}

export function runtimeEnvJsonError(
  spec: RuntimeEnvSpec,
  values: Record<string, string>,
): string | undefined {
  if (spec.format !== "json") return undefined;
  const value = runtimeEnvValue(spec, values).trim();
  if (!value) return undefined;
  try {
    JSON.parse(value);
    return undefined;
  } catch {
    return "JSON 格式不正确";
  }
}

export function firstInvalidRuntimeEnv(
  specs: RuntimeEnvSpec[],
  values: Record<string, string>,
): { spec: RuntimeEnvSpec; error: string } | undefined {
  for (const spec of specs) {
    const error = runtimeEnvJsonError(spec, values);
    if (error) return { spec, error };
  }
  return undefined;
}
