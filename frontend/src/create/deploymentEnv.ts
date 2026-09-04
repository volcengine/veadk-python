import { createT } from "./i18n";

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
  /** Render the value as a masked secret in deployment summaries. */
  secret?: boolean;
  /** Value is derived from configuration and cannot be edited on deploy. */
  readOnly?: boolean;
  /** Secret is resolved by the Studio server and never sent to the browser. */
  serverManaged?: boolean;
  /** Value is managed by Studio and should not be shown as a user-facing field. */
  hidden?: boolean;
  /** User-facing optimization names that require this Runtime setting. */
  requiredBy?: string[];
  /** Actionable error shown when a derived required value cannot be produced. */
  missingError?: string;
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
  return deduped
    .filter((spec) => !spec.hidden)
    .map((spec) => ({
      ...spec,
      value: spec.serverManaged
        ? spec.placeholder || createT("helpers.deploymentEnv.serverInjected")
        : runtimeEnvValue(spec, values),
    }));
}

/** Convert only the currently active feature settings into runtime env rows. */
export function runtimeEnvVars(
  specs: RuntimeEnvSpec[],
  values: Record<string, string>,
): { key: string; value: string }[] {
  const env = new Map<string, string>();
  for (const spec of specs) {
    if (spec.serverManaged) continue;
    const value = runtimeEnvValue(spec, values);
    if (value.trim()) env.set(spec.key, value);
  }
  return [...env].map(([key, value]) => ({ key, value }));
}

export function firstMissingRuntimeEnv(
  specs: RuntimeEnvSpec[],
  values: Record<string, string>,
): RuntimeEnvSpec | undefined {
  return missingRuntimeEnvs(specs, values)[0];
}

export function missingRuntimeEnvs(
  specs: RuntimeEnvSpec[],
  values: Record<string, string>,
): RuntimeEnvSpec[] {
  return specs.filter(
    (spec) =>
      spec.required &&
      !spec.serverManaged &&
      !runtimeEnvValue(spec, values).trim(),
  );
}

function runtimeEnvRequirementLabels(spec: RuntimeEnvSpec): string[] {
  return [...new Set((spec.requiredBy ?? []).map((item) => item.trim()).filter(Boolean))];
}

export function runtimeEnvRequirementHint(
  spec: RuntimeEnvSpec,
): string | undefined {
  const labels = runtimeEnvRequirementLabels(spec);
  const requirement = labels.length
    ? createT("helpers.deploymentEnv.requirementHint", {
        labels: labels.join(createT("helpers.deploymentEnv.listSeparator")),
      })
    : "";
  return (
    [requirement, spec.help?.trim()].filter(Boolean).join(" ") || undefined
  );
}

export function runtimeEnvMissingError(spec: RuntimeEnvSpec): string {
  if (spec.missingError?.trim()) return spec.missingError.trim();
  const labels = runtimeEnvRequirementLabels(spec);
  return labels.length
    ? createT("helpers.deploymentEnv.requiredBy", {
        labels: labels.join(createT("helpers.deploymentEnv.listSeparator")),
        key: spec.key,
      })
    : createT("helpers.deploymentEnv.required", {
        label: spec.comment || spec.key,
        key: spec.key,
      });
}

export function runtimeEnvJsonError(
  spec: RuntimeEnvSpec,
  values: Record<string, string>,
  invalidJsonMessage = createT("helpers.deploymentEnv.invalidJson"),
): string | undefined {
  if (spec.format !== "json") return undefined;
  const value = runtimeEnvValue(spec, values).trim();
  if (!value) return undefined;
  try {
    JSON.parse(value);
    return undefined;
  } catch {
    return invalidJsonMessage;
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
