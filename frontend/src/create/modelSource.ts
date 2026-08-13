import { defaultModelApiBase, type CloudProvider } from "../adk/cloudProvider";
import type { AgentDraft } from "./types";
import { isProviderModelApiBase } from "./customModelCredentials";

export type ModelSource = "ark" | "custom";

export interface RuntimeModelEnvironmentVariable {
  key: string;
  value: string;
}

const MODEL_API_KEY_ID_ENV = "MODEL_AGENT_API_KEY_ID";
const MODEL_API_KEY_NAME_ENV = "MODEL_AGENT_API_KEY_NAME";

export function isRuntimeModelSelectionEnv(key: string): boolean {
  return (
    key === "MODEL_AGENT_API_KEY" ||
    key === MODEL_API_KEY_ID_ENV ||
    key === MODEL_API_KEY_NAME_ENV
  );
}

export function resolvedModelSource(
  draft: Pick<
    AgentDraft,
    "modelSource" | "modelProvider" | "modelApiBase" | "deployment"
  >,
  _cloudProvider: CloudProvider,
): ModelSource {
  if (draft.modelSource === "ark" || draft.modelSource === "custom") {
    return draft.modelSource;
  }
  if (draft.deployment?.modelApiKeyId?.trim()) {
    return "ark";
  }
  const apiBase = draft.modelApiBase?.trim();
  if (!apiBase || isProviderModelApiBase(apiBase, defaultModelApiBase(_cloudProvider))) {
    return "ark";
  }
  return "custom";
}

/**
 * Restore the safe ModelArk selection metadata exposed by Runtime capability.
 * Explicit model-source choices always win; only legacy nodes without a source
 * are inferred from the presence of server-managed ModelArk key markers.
 */
export function hydrateRuntimeModelSelection(
  draft: AgentDraft,
  envs: readonly RuntimeModelEnvironmentVariable[],
): AgentDraft {
  const envValues = new Map(envs.map(({ key, value }) => [key, value.trim()]));
  const draftApiKeyId = draft.deployment?.modelApiKeyId?.trim() ?? "";
  const draftApiKeyName = draft.deployment?.modelApiKeyName?.trim() ?? "";
  const runtimeApiKeyId = envValues.get(MODEL_API_KEY_ID_ENV) ?? "";
  const runtimeApiKeyName = envValues.get(MODEL_API_KEY_NAME_ENV) ?? "";
  const modelApiKeyId = draftApiKeyId || runtimeApiKeyId;
  const modelApiKeyName = draftApiKeyId
    ? draftApiKeyName ||
      (runtimeApiKeyId === draftApiKeyId ? runtimeApiKeyName : "")
    : runtimeApiKeyId
      ? runtimeApiKeyName
      : draftApiKeyName || runtimeApiKeyName;
  const inferArkForLegacy = Boolean(modelApiKeyId) && draft.modelSource !== "custom";

  const hydrateNode = (node: AgentDraft): AgentDraft => {
    const provider = node.cloudProvider ?? draft.cloudProvider ?? "volcengine";
    const legacyModelSource =
      node.modelProvider?.trim() || node.modelApiBase?.trim()
        ? resolvedModelSource(node, provider)
        : "custom";
    return {
      ...node,
      modelSource:
        node.modelSource === "ark" || node.modelSource === "custom"
          ? node.modelSource
          : node.agentType === "llm"
            ? inferArkForLegacy
              ? "ark"
              : legacyModelSource
            : node.modelSource,
      subAgents: node.subAgents.map(hydrateNode),
      ...(node.workflow
        ? {
            workflow: {
              ...node.workflow,
              nodes: node.workflow.nodes.map((workflowNode) => ({
                ...workflowNode,
                agent: hydrateNode(workflowNode.agent),
              })),
            },
          }
        : {}),
    };
  };

  const hydrated = hydrateNode(draft);
  return {
    ...hydrated,
    deployment: {
      ...(hydrated.deployment ?? { feishuEnabled: false }),
      modelApiKeyId,
      modelApiKeyName,
    },
  };
}

/** Remove inactive custom endpoint fields before code generation and deployment. */
export function activeModelConfiguration(
  draft: AgentDraft,
  cloudProvider: CloudProvider,
): AgentDraft {
  const provider = draft.cloudProvider ?? cloudProvider;
  const source = resolvedModelSource(draft, provider);
  return {
    ...draft,
    cloudProvider: provider,
    modelSource: source,
    modelProvider: source === "ark" ? "" : draft.modelProvider,
    modelApiBase: source === "ark" ? "" : draft.modelApiBase,
    subAgents: draft.subAgents.map((child) =>
      activeModelConfiguration(child, provider),
    ),
  };
}
