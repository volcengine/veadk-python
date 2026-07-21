import {
  emptyDraft,
  type A2aRegistryConfig,
  type AgentDraft,
  type CustomTool,
  type SelectedSkill,
} from "./types";

const STM_IDS = new Set(["local", "sqlite", "mysql", "postgresql"]);
const LTM_IDS = new Set(["local", "opensearch", "redis", "viking", "mem0"]);
const KB_IDS = new Set(["local", "opensearch", "viking", "context_search"]);
const EXPORTER_IDS = new Set(["apmplus", "cozeloop", "tls"]);
const TOOL_IDS = new Set([
  "web_search",
  "parallel_web_search",
  "link_reader",
  "web_scraper",
  "image_generate",
  "image_edit",
  "video_generate",
  "text_to_speech",
  "vesearch",
]);
const AGENT_TYPES = new Set(["llm", "sequential", "parallel", "loop", "a2a"]);

function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

function asBool(v: unknown): boolean {
  return v === true;
}

function asStringArray(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}

function asCustomTools(v: unknown): CustomTool[] {
  if (!Array.isArray(v)) return [];
  return v
    .map((t) =>
      t && typeof t === "object"
        ? {
            name: asString((t as Record<string, unknown>).name),
            description: asString((t as Record<string, unknown>).description),
          }
        : null,
    )
    .filter((t): t is CustomTool => !!t && !!t.name.trim());
}

function pick<T>(v: unknown, allowed: Set<string>, fallback: T): string | T {
  return typeof v === "string" && allowed.has(v) ? v : fallback;
}

function asAgentType(v: unknown): NonNullable<AgentDraft["agentType"]> {
  return typeof v === "string" && AGENT_TYPES.has(v)
    ? (v as NonNullable<AgentDraft["agentType"]>)
    : "llm";
}

function asMaxIterations(v: unknown): number {
  return typeof v === "number" && Number.isFinite(v) && v > 0 ? Math.floor(v) : 3;
}

function asA2aRegistry(v: unknown): A2aRegistryConfig {
  const o = (v && typeof v === "object" ? v : {}) as Record<string, unknown>;
  return {
    enabled: asBool(o.enabled),
    registrySpaceId: asString(o.registrySpaceId),
    registryTopK: asString(o.registryTopK),
    registryRegion: asString(o.registryRegion),
    registryEndpoint: asString(o.registryEndpoint),
  };
}

function parseSubAgents(v: unknown): AgentDraft[] {
  if (!Array.isArray(v)) return [];
  return v.map((s) => {
    const so = (s && typeof s === "object" ? s : {}) as Record<string, unknown>;
    return {
      ...emptyDraft(),
      name: asString(so.name),
      description: asString(so.description),
      instruction: asString(so.instruction),
      agentType: asAgentType(so.agentType),
      maxIterations: asMaxIterations(so.maxIterations),
      a2aUrl: asString(so.a2aUrl),
      builtinTools: asStringArray(so.builtinTools).filter((t) => TOOL_IDS.has(t)),
      customTools: asCustomTools(so.customTools),
      a2aRegistry: asA2aRegistry(so.a2aRegistry),
      subAgents: parseSubAgents(so.subAgents),
    };
  });
}

function parseSelectedSkills(o: Record<string, unknown>): SelectedSkill[] {
  if (!Array.isArray(o.selectedSkills)) return [];
  const out: SelectedSkill[] = [];
  for (const raw of o.selectedSkills as unknown[]) {
    const so = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
    const src = asString(so.source);
    const source: SelectedSkill["source"] =
      src === "local" || src === "skillspace" || src === "skillhub" ? src : "skillhub";
    const name =
      asString(so.name) ||
      asString(so.slug) ||
      asString(so.skillName) ||
      asString(so.skillId) ||
      "skill";
    const folder = asString(so.folder) || name;
    const description = asString(so.description);
    if (source === "skillhub") {
      const slug = asString(so.slug);
      if (!slug) continue;
      out.push({
        source,
        folder,
        name,
        description,
        slug,
        namespace: asString(so.namespace) || "public",
      });
      continue;
    }
    if (source === "local") {
      const files = Array.isArray(so.localFiles) ? so.localFiles : [];
      const localFiles = files
        .map((f) => {
          const fo = (f && typeof f === "object" ? f : {}) as Record<string, unknown>;
          const path = asString(fo.path);
          const content = asString(fo.content);
          if (!path) return null;
          return { path, content };
        })
        .filter((x): x is { path: string; content: string } => x !== null);
      if (localFiles.length === 0) continue;
      out.push({ source, folder, name, description, localFiles });
      continue;
    }
    const skillSpaceId = asString(so.skillSpaceId);
    const skillId = asString(so.skillId);
    if (!skillSpaceId || !skillId) continue;
    out.push({
      source,
      folder,
      name,
      description,
      skillSpaceId,
      skillSpaceName: asString(so.skillSpaceName),
      skillId,
      version: asString(so.version),
    });
  }
  return out;
}

export function normalizeDraft(raw: unknown): AgentDraft {
  const o = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  const mem = (o.memory && typeof o.memory === "object" ? o.memory : {}) as Record<
    string,
    unknown
  >;
  const deployment = (
    o.deployment && typeof o.deployment === "object" ? o.deployment : {}
  ) as Record<string, unknown>;

  const mcpTools = Array.isArray(o.mcpTools)
    ? (o.mcpTools as unknown[])
        .map((m) => {
          const mo = (m && typeof m === "object" ? m : {}) as Record<string, unknown>;
          const transport = mo.transport === "stdio" ? "stdio" : "http";
          return {
            name: asString(mo.name),
            transport: transport as "http" | "stdio",
            url: asString(mo.url),
            authToken: asString(mo.authToken),
            command: asString(mo.command),
            args: asStringArray(mo.args),
          };
        })
        .filter((m) => (m.transport === "http" ? !!m.url : !!m.command))
    : [];

  return {
    ...emptyDraft(),
    name: asString(o.name) || "my_agent",
    description: asString(o.description),
    instruction: asString(o.instruction) || "You are a helpful assistant.",
    agentType: asAgentType(o.agentType),
    maxIterations: asMaxIterations(o.maxIterations),
    a2aUrl: asString(o.a2aUrl),
    modelName: asString(o.modelName),
    modelProvider: asString(o.modelProvider),
    modelApiBase: asString(o.modelApiBase),
    builtinTools: asStringArray(o.builtinTools).filter((t) => TOOL_IDS.has(t)),
    customTools: asCustomTools(o.customTools),
    mcpTools,
    a2aRegistry: asA2aRegistry(o.a2aRegistry),
    memory: { shortTerm: asBool(mem.shortTerm), longTerm: asBool(mem.longTerm) },
    shortTermBackend: pick(o.shortTermBackend, STM_IDS, "local"),
    longTermBackend: pick(o.longTermBackend, LTM_IDS, "local"),
    autoSaveSession: asBool(o.autoSaveSession),
    knowledgebase: asBool(o.knowledgebase),
    knowledgebaseBackend: pick(o.knowledgebaseBackend, KB_IDS, "local"),
    tracing: asBool(o.tracing),
    tracingExporters: asStringArray(o.tracingExporters).filter((e) =>
      EXPORTER_IDS.has(e),
    ),
    deployment: { feishuEnabled: asBool(deployment.feishuEnabled) },
    subAgents: parseSubAgents(o.subAgents),
    selectedSkills: parseSelectedSkills(o),
  };
}
