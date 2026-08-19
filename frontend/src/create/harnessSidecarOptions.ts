import type {
  AgentDraft,
  HarnessSidecarIntent,
  HarnessSidecarOptionId,
  HarnessSidecarProfileId,
} from "./types";

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

export const HARNESS_SIDECAR_OPTIONS: readonly HarnessSidecarOption[] = [
  {
    id: "context_engine",
    displayName: "上下文治理",
    description: "治理上下文组装、任务锚定和上下文预算。",
  },
  {
    id: "compressor",
    displayName: "上下文与结果压缩",
    description: "压缩长上下文和大型工具结果，降低 Token 成本。",
  },
  {
    id: "verifier",
    displayName: "回答校验与修复",
    description: "校验证据和回答，在失败时执行修复或告警。",
  },
  {
    id: "long_run_control",
    displayName: "Goal任务控制",
    description: "管理 Goal 任务的进度、续跑和结束条件。",
  },
  {
    id: "mcp_resilience",
    displayName: "MCP 稳定性治理",
    description: "治理连接、超时、空结果、大返回和调用预算；默认包含 SQL 只读保护。",
  },
];

export const HARNESS_SIDECAR_OPTION_GROUPS: readonly HarnessSidecarOptionGroup[] = [
  {
    id: "quality",
    displayName: "提升回答质量",
    componentIds: ["context_engine", "verifier"],
  },
  {
    id: "cost",
    displayName: "降低运行成本",
    componentIds: ["compressor"],
  },
  {
    id: "stability",
    displayName: "增强运行稳定性",
    componentIds: ["long_run_control", "mcp_resilience"],
  },
];

export const HARNESS_SIDECAR_OPTION_IDS: HarnessSidecarOptionId[] =
  HARNESS_SIDECAR_OPTIONS.map((item) => item.id);

export const BYTEPLUS_HARNESS_SIDECAR_UNAVAILABLE_MESSAGE =
  "BytePlus 账号暂不支持 Harness Sidecar 优化项。请保持优化项为空后继续部署，普通 BytePlus 智能体不受影响。";

export function harnessSidecarProviderNotice(
  cloudProvider: "volcengine" | "byteplus",
): string | null {
  return cloudProvider === "byteplus"
    ? BYTEPLUS_HARNESS_SIDECAR_UNAVAILABLE_MESSAGE
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
    displayName: "自定义",
    description: "按需选择组件，不勾选时不启动 Sidecar。",
    defaultComponents: [],
    autoAddedComponents: [],
  },
  {
    id: "ops",
    displayName: "运维场景",
    description: "适用于运维诊断、数据库、日志和监控 MCP。",
    defaultComponents: [
      "context_engine",
      "compressor",
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
  if (profile === "ops") {
    return harnessIntentFromOptimizations(
      harnessProfileDefaultOptimizations(profile),
      profile,
    );
  }

  const exactOverrides = runtimeComponentOverrides(
    values.get("HARNESS_SIDECAR_COMPONENT_OVERRIDES"),
  );
  const selected = exactOverrides
    ? HARNESS_SIDECAR_OPTION_IDS.filter((id) => exactOverrides[id] === true)
    : [
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
