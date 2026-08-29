export type ResourceCategory = "skill_hub" | "skill_space" | "knowledge_base";
export type ToolExecutionStatus = "running" | "completed" | "failed";

export interface CollectedResourceView {
  ref: string;
  kind: "skill" | "knowledge_base";
  category: ResourceCategory;
  name: string;
  description: string;
  source: string;
  version: string;
}

export interface ResourceSourceView {
  source: string;
  label: string;
  status: "ok" | "skipped" | "error";
  count: number;
  message: string;
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
  task: string;
  rootType: string;
  nodeCount: number;
  resourceCount: number;
  pythonToolCount: number;
  status: ToolExecutionStatus;
  output: string;
  error: string;
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

function resourceCategory(resource: Record<string, unknown>): ResourceCategory {
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
  if (source === "agentkit_knowledge") return "AgentKit 知识库";
  if (source.startsWith("skill_hub:")) return `Skill Hub ${source.slice(10)}`;
  if (source.startsWith("skill_space:")) return `私域 Skill ${source.slice(12)}`;
  return source || "未知来源";
}

export function parseCollectedResources(response: unknown): CollectedResourcesView {
  const payload = unwrapPayload(response);
  const capabilities = asRecord(payload.capabilities) ?? {};
  const resources = asArray(payload.resources).flatMap((value) => {
    const resource = asRecord(value);
    if (!resource) return [];
    const kind = resource.kind === "knowledge_base" ? "knowledge_base" : "skill";
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
      label: sourceLabel(name),
      status,
      count: asNumber(source.count),
      message: asString(source.message),
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
    },
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
    const result = results.get(name);
    const resultStatus = asString(result?.status);
    const status: ToolExecutionStatus = resultStatus === "failed"
      ? "failed"
      : resultStatus === "completed" ? "completed" : "running";
    const resourceCount = nodes.reduce(
      (total, node) => total + asArray(node.resources).length,
      0,
    );
    const pythonToolCount = nodes.reduce(
      (total, node) => total + asArray(node.python_tools).length,
      0,
    );

    return {
      name,
      task: asString(blueprint.task),
      rootType: asString(result?.root_type) || asString(rootNode?.type) || "llm",
      nodeCount: nodes.length,
      resourceCount,
      pythonToolCount,
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
