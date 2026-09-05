import type {
  AgentDraft,
  HarnessSidecarIntent,
  HarnessSidecarOptionId,
  HarnessSidecarProfileId,
} from "./types";
import { createT } from "./i18n";

export interface HarnessSidecarOption {
  id: HarnessSidecarOptionId;
  displayName: string;
  description: string;
}

export interface HarnessSidecarProfile {
  id: HarnessSidecarProfileId;
  displayName: string;
  description: string;
  defaultComponents: readonly HarnessSidecarOptionId[];
  autoAddedComponents: readonly string[];
}

export interface HarnessSidecarOptionGroup {
  id: "quality" | "cost" | "stability";
  displayName: string;
  componentIds: readonly HarnessSidecarOptionId[];
}

function localizedOption(id: HarnessSidecarOptionId): HarnessSidecarOption {
  return {
    id,
    get displayName() {
      return createT(`traditional.optimization.options.${id}.label`);
    },
    get description() {
      return createT(`traditional.optimization.options.${id}.description`);
    },
  };
}

export const HARNESS_SIDECAR_OPTIONS: readonly HarnessSidecarOption[] = [
  localizedOption("context_engine"),
  localizedOption("compressor"),
  localizedOption("verifier"),
  localizedOption("long_run_control"),
  localizedOption("mcp_resilience"),
];

export const HARNESS_SIDECAR_OPTION_GROUPS: readonly HarnessSidecarOptionGroup[] = [
  {
    id: "quality",
    get displayName() {
      return createT("traditional.optimization.groups.quality");
    },
    componentIds: ["context_engine", "verifier"],
  },
  {
    id: "cost",
    get displayName() {
      return createT("traditional.optimization.groups.cost");
    },
    componentIds: ["compressor"],
  },
  {
    id: "stability",
    get displayName() {
      return createT("traditional.optimization.groups.stability");
    },
    componentIds: ["long_run_control", "mcp_resilience"],
  },
];

export const HARNESS_SIDECAR_OPTION_IDS: HarnessSidecarOptionId[] =
  HARNESS_SIDECAR_OPTIONS.map((item) => item.id);

export function harnessSidecarProviderNotice(
  cloudProvider: "volcengine" | "byteplus",
): string | null {
  return cloudProvider === "byteplus"
    ? createT("traditional.optimization.bytePlusUnavailable")
    : null;
}

const HARNESS_MODEL_PROXY_OPTION_IDS: readonly HarnessSidecarOptionId[] = [
  "context_engine",
  "compressor",
  "verifier",
  "long_run_control",
];

const ENABLED_RUNTIME_ENV_VALUES = new Set(["1", "true", "yes", "on"]);

export const HARNESS_SIDECAR_PROFILES: readonly HarnessSidecarProfile[] = [
  {
    id: "default",
    get displayName() {
      return createT("traditional.optimization.profiles.default.label");
    },
    get description() {
      return createT("traditional.optimization.profiles.default.description");
    },
    defaultComponents: [],
    autoAddedComponents: [],
  },
  {
    id: "ops",
    get displayName() {
      return createT("traditional.optimization.profiles.ops.label");
    },
    get description() {
      return createT("traditional.optimization.profiles.ops.description");
    },
    defaultComponents: [
      "context_engine",
      "verifier",
      "long_run_control",
      "mcp_resilience",
    ],
    autoAddedComponents: ["sql_readonly"],
  },
];

export function harnessSidecarOptionLabel(id: string): string {
  return HARNESS_SIDECAR_OPTIONS.find((item) => item.id === id)?.displayName ?? id;
}

export function harnessSidecarProfileLabel(id: string): string {
  return HARNESS_SIDECAR_PROFILES.find((item) => item.id === id)?.displayName ?? id;
}

export function harnessProfileDefaultOptimizations(
  profile: HarnessSidecarProfileId,
): HarnessSidecarOptionId[] {
  const metadata = HARNESS_SIDECAR_PROFILES.find((item) => item.id === profile);
  if (!metadata) return [];
  return [...metadata.defaultComponents];
}

export function harnessIntentFromOptimizations(
  optimizations: readonly HarnessSidecarOptionId[],
  profile: HarnessSidecarProfileId = "default",
): HarnessSidecarIntent {
  const selected = new Set(optimizations);
  const intent: HarnessSidecarIntent = {
    enabled: selected.size > 0,
    profile,
    componentOverrides: Object.fromEntries(
      HARNESS_SIDECAR_OPTION_IDS.map((id) => [id, selected.has(id)]),
    ) as HarnessSidecarIntent["componentOverrides"],
  };
  return intent;
}

/** Keep named profiles deterministic across new drafts, YAML imports and
 * legacy Runtime snapshots. A named profile describes a fixed preset; once a
 * user changes an individual option the editor switches the draft to the
 * custom profile instead. */
export function normalizeHarnessSidecarIntent(
  intent: HarnessSidecarIntent | undefined,
): HarnessSidecarIntent | undefined {
  if (!intent) return undefined;
  const profile: HarnessSidecarProfileId =
    intent.profile === "ops" ? "ops" : "default";
  const optimizations =
    profile === "ops"
      ? harnessProfileDefaultOptimizations(profile)
      : HARNESS_SIDECAR_OPTION_IDS.filter(
          (id) => intent.componentOverrides?.[id] === true,
        );
  return {
    ...harnessIntentFromOptimizations(optimizations, profile),
    ...(intent.catalogVersion ? { catalogVersion: intent.catalogVersion } : {}),
    ...(intent.planHash ? { planHash: intent.planHash } : {}),
  };
}

function runtimeEnvEnabled(value: string | undefined): boolean {
  return ENABLED_RUNTIME_ENV_VALUES.has(value?.trim().toLowerCase() ?? "");
}

function runtimeComponentOverrides(value: string | undefined): Record<string, unknown> | null {
  if (!value) return null;
  try {
    const parsed: unknown = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : null;
  } catch {
    return null;
  }
}

export function harnessIntentFromRuntimeEnvs(
  envs: readonly { key: string; value: string }[] | null | undefined,
): HarnessSidecarIntent | null {
  const values = new Map(envs?.map(({ key, value }) => [key, value]) ?? []);
  const enabledValue = values.get("HARNESS_SIDECAR_ENABLED");
  if (enabledValue === undefined) return null;

  const profile: HarnessSidecarProfileId =
    values.get("HARNESS_PROFILE")?.trim() === "ops" ? "ops" : "default";
  if (!runtimeEnvEnabled(enabledValue)) {
    return harnessIntentFromOptimizations([], profile);
  }
  const exactOverrides = runtimeComponentOverrides(
    values.get("HARNESS_SIDECAR_COMPONENT_OVERRIDES"),
  );
  if (exactOverrides) {
    const restored = {
      ...harnessIntentFromOptimizations(
        HARNESS_SIDECAR_OPTION_IDS.filter((id) => exactOverrides[id] === true),
        profile,
      ),
      enabled: true,
    };
    return profile === "ops"
      ? normalizeHarnessSidecarIntent(restored) ?? restored
      : restored;
  }
  if (profile === "ops") {
    return harnessIntentFromOptimizations(
      harnessProfileDefaultOptimizations(profile),
      profile,
    );
  }

  const selected = [
    ...(runtimeEnvEnabled(values.get("HARNESS_MODEL_PROXY_ENABLED"))
      ? HARNESS_MODEL_PROXY_OPTION_IDS
      : []),
    ...(runtimeEnvEnabled(values.get("HARNESS_MCP_GATEWAY_ENABLED"))
      ? ["mcp_resilience" as const]
      : []),
  ];
  return {
    ...harnessIntentFromOptimizations(selected, profile),
    enabled: true,
  };
}

export interface HarnessSidecarDebugVariant {
  modelName: string;
  description: string;
  instruction: string;
}

export function releaseDraftFromDebugVariant(
  draft: AgentDraft,
  variant: HarnessSidecarDebugVariant,
): AgentDraft {
  return {
    ...draft,
    modelName: variant.modelName || draft.modelName,
    description: variant.description,
    instruction: variant.instruction,
  };
}

export function selectedHarnessProfile(
  draft: AgentDraft,
): HarnessSidecarProfileId {
  return draft.harnessSidecar?.profile ?? "default";
}

export function selectedHarnessOptimizations(
  draft: AgentDraft,
): HarnessSidecarOptionId[] {
  const overrides = draft.harnessSidecar?.componentOverrides;
  return overrides
    ? HARNESS_SIDECAR_OPTION_IDS.filter((id) => overrides[id])
    : [];
}

export function selectedHarnessModelProxyOptimizations(
  draft: AgentDraft,
): HarnessSidecarOptionId[] {
  const selected = new Set(selectedHarnessOptimizations(draft));
  return HARNESS_MODEL_PROXY_OPTION_IDS.filter((id) => selected.has(id));
}
