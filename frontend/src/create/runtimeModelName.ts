import type { AgentDraft } from "./types";

export interface RuntimeModelConfiguration {
  modelName: string;
  modelProvider: string;
}

export interface RuntimeAgentIntrospection {
  name?: string;
  model?: string;
  children?: readonly RuntimeAgentIntrospection[];
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
    modelName: runtimeModel.modelName || editableDraft.modelName,
    modelProvider: runtimeModel.modelProvider || editableDraft.modelProvider,
    subAgents: editableDraft.subAgents.map((child, index) =>
      applyRuntimeAgentIntrospection(child, runtimeChildren[index]),
    ),
  };
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
