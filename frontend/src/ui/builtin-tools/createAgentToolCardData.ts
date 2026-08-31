export type ResourceCategory = "skill_hub" | "skill_space" | "knowledge_base" | "tool";
export type ToolExecutionStatus = "running" | "completed" | "failed";

export interface CollectedResourceView {
  ref: string;
  kind: "skill" | "knowledge_base" | "tool";
  category: ResourceCategory;
  name: string;
  description: string;
  source: string;
  version: string;
}

export interface ResourceSourceView {
  source: string;
  category: ResourceCategory;
  label: string;
  status: "ok" | "skipped" | "error";
  count: number;
  message: string;
  searchKeywords: string[];
}

export interface CollectedResourcesView {
  collectionId: string;
  capabilities: {
    googleAdkVersion: string;
    agentTypes: string[];
    maxOrchestrationDepth: number;
  };
  resources: CollectedResourceView[];
  sources: ResourceSourceView[];
  counts: Record<"all" | ResourceCategory, number>;
}

export interface CreatedAgentView {
  name: string;
  description: string;
  task: string;
  rootType: string;
  nodeCount: number;
  subAgentCount: number;
  resourceCount: number;
  pythonToolCount: number;
  skills: CreatedAgentResourceView[];
  knowledgeBases: CreatedAgentResourceView[];
  builtinTools: CreatedAgentResourceView[];
  pythonTools: PythonToolView[];
  subAgents: CreatedSubAgentView[];
  status: ToolExecutionStatus;
  output: string;
  error: string;
}

export interface CreatedAgentResourceView {
  ref: string;
  kind: "skill" | "knowledge_base" | "tool";
  name: string;
  description: string;
  version: string;
  source: string;
}

export interface CreatedSubAgentView {
  id: string;
  type: string;
  description: string;
}

export interface PythonToolView {
  name: string;
  description: string;
  code: string;
  entrypoint: string;
  dependencies: string[];
}

export interface CreatedAgentsView {
  collectionId: string;
  agents: CreatedAgentView[];
  completedCount: number;
  failedCount: number;
  runningCount: number;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function unwrapPayload(value: unknown): Record<string, unknown> {
  let parsed = value;
  if (typeof parsed === "string") {
    try {
      parsed = JSON.parse(parsed);
    } catch {
      return {};
    }
  }
  const record = asRecord(parsed) ?? {};
  const nested = asRecord(record.result);
  return nested ?? record;
}

export function toolResponseError(response: unknown): string {
  if (typeof response === "string") {
    try {
      return toolResponseError(JSON.parse(response));
    } catch {
      return response;
    }
  }
  const record = asRecord(response);
  if (!record) return "";
  const nested = asRecord(record.result);
  return asString(record.error)
    || asString(record.message)
    || asString(nested?.error)
    || asString(nested?.message);
}

function resourceCategory(resource: Record<string, unknown>): ResourceCategory {
  if (resource.kind === "tool") return "tool";
  if (resource.kind === "knowledge_base") return "knowledge_base";
  const metadata = asRecord(resource.metadata);
  const sourceType = asString(metadata?.source_type).toLowerCase();
  const source = asString(resource.source).toLowerCase();
  if (sourceType === "skillhub" || source.startsWith("skill_hub:")) {
    return "skill_hub";
  }
  return "skill_space";
}

function sourceLabel(source: string): string {
  if (source === "veadk_builtin_tools") return "工具";
  if (source === "agentkit_knowledge") return "AgentKit 知识库";
  if (source.startsWith("skill_hub:")) return `Skill Hub ${source.slice(10)}`;
  if (source.startsWith("skill_space:")) return `AgentKit 技能中心 ${source.slice(12)}`;
  return source || "未知来源";
}

function sourceCategory(source: string): ResourceCategory {
  if (source === "veadk_builtin_tools") return "tool";
  if (source === "agentkit_knowledge") return "knowledge_base";
  if (source.startsWith("skill_hub:")) return "skill_hub";
  return "skill_space";
}

export function parseCollectedResources(response: unknown): CollectedResourcesView {
  const payload = unwrapPayload(response);
  const capabilities = asRecord(payload.capabilities) ?? {};
  const resources = asArray(payload.resources).flatMap((value) => {
    const resource = asRecord(value);
    if (!resource) return [];
    const kind = resource.kind === "tool"
      ? "tool"
      : resource.kind === "knowledge_base" ? "knowledge_base" : "skill";
    return [{
      ref: asString(resource.ref),
      kind,
      category: resourceCategory(resource),
      name: asString(resource.name) || asString(resource.ref) || "未命名资源",
      description: asString(resource.description),
      source: asString(resource.source),
      version: asString(resource.version),
    } satisfies CollectedResourceView];
  });
  const sources = asArray(payload.sources).flatMap((value) => {
    const source = asRecord(value);
    if (!source) return [];
    const name = asString(source.source);
    const rawStatus = asString(source.status);
    const status: ResourceSourceView["status"] = rawStatus === "error"
      ? "error"
      : rawStatus === "skipped" ? "skipped" : "ok";
    return [{
      source: name,
      category: sourceCategory(name),
      label: sourceLabel(name),
      status,
      count: asNumber(source.count),
      message: asString(source.message),
      searchKeywords: asArray(source.search_keywords).map(asString).filter(Boolean),
    } satisfies ResourceSourceView];
  });

  return {
    collectionId: asString(payload.collection_id),
    capabilities: {
      googleAdkVersion: asString(capabilities.google_adk_version),
      agentTypes: asArray(capabilities.agent_types).map(asString).filter(Boolean),
      maxOrchestrationDepth: asNumber(capabilities.max_orchestration_depth),
    },
    resources,
    sources,
    counts: {
      all: resources.length,
      skill_hub: resources.filter((resource) => resource.category === "skill_hub").length,
      skill_space: resources.filter((resource) => resource.category === "skill_space").length,
      knowledge_base: resources.filter((resource) => resource.category === "knowledge_base").length,
      tool: resources.filter((resource) => resource.category === "tool").length,
    },
  };
}

export function filterCollectedResourcesByCategory(
  data: CollectedResourcesView,
  category: ResourceCategory,
) {
  return {
    resources: data.resources.filter((resource) => resource.category === category),
    sources: data.sources.filter((source) => source.category === category),
  };
}

export function parseCreatedAgents(args: unknown, response: unknown): CreatedAgentsView {
  const input = unwrapPayload(args);
  const output = unwrapPayload(response);
  const results = new Map(
    asArray(output.results).flatMap((value) => {
      const result = asRecord(value);
      const name = asString(result?.name);
      return result && name ? [[name, result] as const] : [];
    }),
  );

  const blueprints = asArray(input.agents).flatMap((value) => {
    const blueprint = asRecord(value);
    const name = asString(blueprint?.name);
    return blueprint && name ? [blueprint] : [];
  });
  const knownNames = new Set(blueprints.map((blueprint) => asString(blueprint.name)));
  const resultOnlyAgents = [...results.entries()]
    .filter(([name]) => !knownNames.has(name))
    .map(([name]): Record<string, unknown> => ({ name }));

  const agents = [...blueprints, ...resultOnlyAgents].map((blueprint) => {
    const name = asString(blueprint.name);
    const nodes = asArray(blueprint.nodes).flatMap((value) => {
      const node = asRecord(value);
      return node ? [node] : [];
    });
    const rootId = asString(blueprint.root_node);
    const rootNode = nodes.find((node) => asString(node.id) === rootId);
    const subAgents = nodes
      .filter((node) => asString(node.id) !== rootId)
      .map((node) => ({
        id: asString(node.id) || "未命名 Agent",
        type: asString(node.type) || "llm",
        description: asString(node.description),
      } satisfies CreatedSubAgentView));
    const result = results.get(name);
    const resultStatus = asString(result?.status);
    const status: ToolExecutionStatus = resultStatus === "failed"
      ? "failed"
      : resultStatus === "completed" ? "completed" : "running";
    const responseResources = normalizeAgentResources(result?.resources);
    const resources = responseResources.length > 0
      ? responseResources
      : normalizeAgentResources(nodes.flatMap((node) => asArray(node.resources)));
    const responsePythonTools = normalizePythonTools(result?.python_tools);
    const pythonTools = responsePythonTools.length > 0
      ? responsePythonTools
      : normalizePythonTools(nodes.flatMap((node) => asArray(node.python_tools)));

    return {
      name,
      description: asString(result?.description)
        || asString(rootNode?.description)
        || asString(blueprint.task),
      task: asString(blueprint.task),
      rootType: asString(result?.root_type) || asString(rootNode?.type) || "llm",
      nodeCount: nodes.length,
      subAgentCount: subAgents.length,
      resourceCount: resources.length,
      pythonToolCount: pythonTools.length,
      skills: resources.filter((resource) => resource.kind === "skill"),
      knowledgeBases: resources.filter((resource) => resource.kind === "knowledge_base"),
      builtinTools: resources.filter((resource) => resource.kind === "tool"),
      pythonTools,
      subAgents,
      status,
      output: asString(result?.output),
      error: asString(result?.error),
    } satisfies CreatedAgentView;
  });

  return {
    collectionId: asString(output.collection_id) || asString(input.collection_id),
    agents,
    completedCount: agents.filter((agent) => agent.status === "completed").length,
    failedCount: agents.filter((agent) => agent.status === "failed").length,
    runningCount: agents.filter((agent) => agent.status === "running").length,
  };
}

export function createdAgentsHaveFailure(args: unknown, response: unknown): boolean {
  return Boolean(toolResponseError(response))
    || parseCreatedAgents(args, response).failedCount > 0;
}

function normalizeAgentResources(value: unknown): CreatedAgentResourceView[] {
  const seen = new Set<string>();
  return asArray(value).flatMap((item) => {
    const resource = asRecord(item);
    const ref = resource ? asString(resource.ref) : asString(item);
    if (!ref || seen.has(ref)) return [];
    seen.add(ref);
    const rawKind = asString(resource?.kind);
    const kind: CreatedAgentResourceView["kind"] = rawKind === "tool"
      || ref.startsWith("veadk_tool:")
      ? "tool"
      : rawKind === "knowledge_base" || ref.startsWith("agentkit_kb:")
        ? "knowledge_base"
        : "skill";
    const refParts = ref.split(":");
    return [{
      ref,
      kind,
      name: asString(resource?.name) || refParts[refParts.length - 1] || ref,
      description: asString(resource?.description),
      version: asString(resource?.version),
      source: asString(resource?.source),
    } satisfies CreatedAgentResourceView];
  });
}

function normalizePythonTools(value: unknown): PythonToolView[] {
  const seen = new Set<string>();
  return asArray(value).flatMap((item) => {
    const tool = asRecord(item);
    const name = asString(tool?.name);
    const code = asString(tool?.code);
    const key = `${name}\u0000${code}`;
    if (!tool || !name || seen.has(key)) return [];
    seen.add(key);
    return [{
      name,
      description: asString(tool.description),
      code,
      entrypoint: asString(tool.entrypoint) || name,
      dependencies: asArray(tool.dependencies).map(asString).filter(Boolean),
    } satisfies PythonToolView];
  });
}
