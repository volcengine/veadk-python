import type { CloudProvider } from "../adk/cloudProvider";
import { emptyDraft, type AgentDraft } from "./types";
import { BUILTIN_TOOLS } from "./veadkCatalog";

export interface RuntimeModelConfiguration {
  modelName: string;
  modelProvider: string;
}

export interface RuntimeAgentIntrospection {
  name?: string;
  description?: string;
  instruction?: string;
  type?: AgentDraft["agentType"];
  model?: string;
  tools?: readonly string[];
  skills?: readonly { name: string }[];
  children?: readonly RuntimeAgentIntrospection[];
}

export interface RuntimeCloudAgent extends RuntimeAgentIntrospection {
  appName: string;
  graph?: RuntimeAgentIntrospection;
  draft?: AgentDraft;
}

/** Split the provider-qualified identifier exposed by older runtimes at its
 * first slash, preserving any remaining slashes as part of the model name. */
export function modelConfigurationFromRuntime(
  value: string | undefined,
): RuntimeModelConfiguration {
  const qualifiedName = value?.trim() ?? "";
  const separator = qualifiedName.indexOf("/");
  if (separator <= 0 || separator === qualifiedName.length - 1) {
    return { modelName: qualifiedName, modelProvider: "" };
  }
  return {
    modelName: qualifiedName.slice(separator + 1),
    modelProvider: qualifiedName.slice(0, separator),
  };
}

export function modelNameFromRuntime(value: string | undefined): string {
  return modelConfigurationFromRuntime(value).modelName;
}

/** Apply deployed Agent introspection to the editable builder representation.
 * Runtime identity and model fields are authoritative; the draft only carries
 * builder-only settings that the live Agent does not expose. */
export function applyRuntimeAgentIntrospection(
  editableDraft: AgentDraft,
  runtimeNode: RuntimeAgentIntrospection | undefined,
  fallbackRoot?: Pick<RuntimeAgentIntrospection, "name" | "model">,
): AgentDraft {
  const runtimeModel = modelConfigurationFromRuntime(
    runtimeNode?.model || fallbackRoot?.model,
  );
  const runtimeChildren = runtimeNode?.children ?? [];

  return {
    ...editableDraft,
    name:
      runtimeNode?.name?.trim() ||
      fallbackRoot?.name?.trim() ||
      editableDraft.name,
    description: runtimeNode?.description ?? editableDraft.description,
    instruction: runtimeNode?.instruction ?? editableDraft.instruction,
    agentType: runtimeNode?.type ?? editableDraft.agentType,
    modelName: runtimeModel.modelName || editableDraft.modelName,
    modelProvider: runtimeModel.modelProvider || editableDraft.modelProvider,
    skills: runtimeNode?.skills?.map((skill) => skill.name) ?? editableDraft.skills,
    subAgents: editableDraft.subAgents.map((child, index) =>
      applyRuntimeAgentIntrospection(child, runtimeChildren[index]),
    ),
  };
}

function cloudDraftWithDefaults(
  draft: AgentDraft,
  cloudProvider: CloudProvider,
): AgentDraft {
  const provider = draft.cloudProvider ?? cloudProvider;
  const defaults = emptyDraft(provider);
  const deployment = draft.deployment;
  const network = deployment?.network;
  const cloudEnvironment = draft.cloudEnvironment;
  const a2aRegistry = draft.a2aRegistry;
  return {
    ...defaults,
    ...draft,
    name: draft.name ?? defaults.name,
    description: draft.description ?? defaults.description,
    instruction: draft.instruction ?? defaults.instruction,
    agentType: draft.agentType ?? defaults.agentType,
    cloudProvider: provider,
    maxIterations: draft.maxIterations ?? defaults.maxIterations,
    a2aUrl: draft.a2aUrl ?? defaults.a2aUrl,
    model: draft.model ?? undefined,
    modelSource:
      draft.modelSource === "ark" || draft.modelSource === "custom"
        ? draft.modelSource
        : undefined,
    modelName: draft.modelName ?? defaults.modelName,
    modelProvider: draft.modelProvider ?? defaults.modelProvider,
    modelApiBase: draft.modelApiBase ?? defaults.modelApiBase,
    memory: {
      shortTerm: draft.memory?.shortTerm ?? defaults.memory.shortTerm,
      longTerm: draft.memory?.longTerm ?? defaults.memory.longTerm,
    },
    tools: [...(draft.tools ?? [])],
    skills: [...(draft.skills ?? [])],
    knowledgebase: draft.knowledgebase ?? defaults.knowledgebase,
    tracing: draft.tracing ?? defaults.tracing,
    subAgents: (draft.subAgents ?? []).map((child) =>
      cloudDraftWithDefaults(child, provider),
    ),
    builtinTools: [...(draft.builtinTools ?? [])],
    customTools: [...(draft.customTools ?? [])],
    mcpTools: [...(draft.mcpTools ?? [])],
    a2aRegistry: {
      ...defaults.a2aRegistry!,
      ...(a2aRegistry ?? {}),
      enabled: a2aRegistry?.enabled ?? false,
      registrySpaceId: a2aRegistry?.registrySpaceId ?? "",
      registryTopK: a2aRegistry?.registryTopK ?? "",
      registryRegion: a2aRegistry?.registryRegion ?? "",
      registryEndpoint: a2aRegistry?.registryEndpoint ?? "",
    },
    shortTermBackend: draft.shortTermBackend ?? defaults.shortTermBackend,
    longTermBackend: draft.longTermBackend ?? defaults.longTermBackend,
    autoSaveSession: draft.autoSaveSession ?? defaults.autoSaveSession,
    knowledgebaseBackend:
      draft.knowledgebaseBackend ?? defaults.knowledgebaseBackend,
    knowledgebaseIndex:
      draft.knowledgebaseIndex ?? defaults.knowledgebaseIndex,
    tracingExporters: [...(draft.tracingExporters ?? [])],
    selectedSkills: [...(draft.selectedSkills ?? [])],
    cloudEnvironment: {
      ...defaults.cloudEnvironment!,
      ...(cloudEnvironment ?? {}),
      cliTools: [...(cloudEnvironment?.cliTools ?? [])],
      dockerfile:
        typeof cloudEnvironment?.dockerfile === "string"
          ? cloudEnvironment.dockerfile
          : undefined,
    },
    deployment: {
      ...defaults.deployment!,
      ...(deployment ?? {}),
      feishuEnabled: deployment?.feishuEnabled ?? false,
      runtimeName: deployment?.runtimeName ?? undefined,
      runtimeNameCustomized:
        deployment?.runtimeNameCustomized ??
        defaults.deployment?.runtimeNameCustomized,
      network: network
        ? {
            ...network,
            vpcId: network.vpcId ?? "",
            subnetIds: network.subnetIds ?? "",
            enableSharedInternetAccess:
              network.enableSharedInternetAccess ?? false,
          }
        : undefined,
      modelApiKeyId: deployment?.modelApiKeyId ?? "",
      modelApiKeyName: deployment?.modelApiKeyName ?? "",
      envValues: deployment?.envValues ?? undefined,
    },
    ...(draft.workflow
      ? {
          workflow: {
            ...draft.workflow,
            nodes: draft.workflow.nodes.map((node) => ({
              ...node,
              agent: cloudDraftWithDefaults(node.agent, provider),
            })),
          },
        }
      : {}),
  };
}

function cloudGraphToDraft(
  node: RuntimeAgentIntrospection,
  cloudProvider: CloudProvider,
): AgentDraft {
  const defaults = emptyDraft(cloudProvider);
  const runtimeTools = [...(node.tools ?? [])];
  const builtinTools = BUILTIN_TOOLS.filter((tool) =>
    tool.toolNames.some((name) => runtimeTools.includes(name)),
  );
  const builtinToolNames = new Set(
    builtinTools.flatMap((tool) => tool.toolNames),
  );
  const runtimeModel = modelConfigurationFromRuntime(node.model);
  return {
    ...defaults,
    modelSource: undefined,
    name: node.name?.trim() ?? "",
    description: node.description ?? "",
    instruction: node.instruction || defaults.instruction,
    agentType: node.type ?? "llm",
    modelName: runtimeModel.modelName,
    modelProvider: runtimeModel.modelProvider,
    tools: runtimeTools.filter((name) => !builtinToolNames.has(name)),
    builtinTools: builtinTools.map((tool) => tool.id),
    skills: node.skills?.map((skill) => skill.name) ?? [],
    subAgents: (node.children ?? []).map((child) =>
      cloudGraphToDraft(child, cloudProvider),
    ),
  };
}

/** Rebuild an editable Runtime configuration exclusively from data returned by
 * the deployed Agent and Runtime control plane. New Studio deployments expose
 * the complete sanitized builder snapshot as `draft`; legacy deployments fall
 * back to their introspected graph and explicit editor defaults. */
export function runtimeAgentDraftFromCloud(
  agent: RuntimeCloudAgent,
  cloudProvider: CloudProvider,
): AgentDraft {
  const provider = agent.draft?.cloudProvider ?? cloudProvider;
  const runtimeModel = modelConfigurationFromRuntime(agent.model);
  const cloudDraft = agent.draft
    ? cloudDraftWithDefaults(agent.draft, provider)
    : agent.graph
      ? cloudGraphToDraft(agent.graph, provider)
      : {
          ...emptyDraft(provider),
          modelSource: undefined,
          name: agent.name?.trim() || agent.appName.trim(),
          description: agent.description ?? "",
          instruction: agent.instruction || emptyDraft(provider).instruction,
          agentType: agent.type ?? "llm",
          modelName: runtimeModel.modelName,
          modelProvider: runtimeModel.modelProvider,
          tools: [...(agent.tools ?? [])],
          skills: agent.skills?.map((skill) => skill.name) ?? [],
        };

  return applyRuntimeAgentIntrospection(cloudDraft, agent.graph, {
    name: agent.name?.trim() || agent.appName.trim(),
    model: agent.model,
  });
}

/** Classify live Runtime models against the ModelArk catalog selected for the
 * update. A catalog hit is ModelArk; every other live model is custom. */
export function classifyRuntimeModelSources(
  draft: AgentDraft,
  arkModelIds: ReadonlySet<string>,
): AgentDraft {
  const classifyNode = (node: AgentDraft): AgentDraft => {
    const modelName = node.modelName?.trim() ?? "";
    return {
      ...node,
      modelSource:
        node.agentType === "llm" || !node.agentType
          ? arkModelIds.has(modelName)
            ? "ark"
            : "custom"
          : node.modelSource,
      subAgents: node.subAgents.map(classifyNode),
      ...(node.workflow
        ? {
            workflow: {
              ...node.workflow,
              nodes: node.workflow.nodes.map((workflowNode) => ({
                ...workflowNode,
                agent: classifyNode(workflowNode.agent),
              })),
            },
          }
        : {}),
    };
  };

  return classifyNode(draft);
}
