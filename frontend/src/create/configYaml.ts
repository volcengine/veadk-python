// Serialize an AgentDraft to / from a human-readable "agent structure" YAML.
// The YAML mirrors the AgentDraft config shape, so it round-trips cleanly and
// can be imported back into the custom-mode wizard.

import { parse, stringify } from "yaml";
import { a2aRegistryDefaults } from "./veadkCatalog";
import { normalizeDraft } from "./normalizeDraft";
import { prepareMcpAuth } from "./mcpAuth";
import type { AgentDraft } from "./types";

/** Build a clean, minimal config object (omit empty/false fields). */
function toConfig(draft: AgentDraft, root = true): Record<string, unknown> {
  const o: Record<string, unknown> = {
    agentType: draft.agentType ?? "llm",
  };
  if (draft.agentType === "a2a") {
    if (draft.a2aRegistry?.enabled) {
      const defaults = a2aRegistryDefaults(
        draft.cloudProvider ?? "volcengine",
      );
      const registry: Record<string, unknown> = { enabled: true };
      if (draft.a2aRegistry.registrySpaceId?.trim())
        registry.registrySpaceId = draft.a2aRegistry.registrySpaceId.trim();
      registry.registryTopK =
        draft.a2aRegistry.registryTopK?.trim() || defaults.topK;
      registry.registryRegion =
        draft.a2aRegistry.registryRegion?.trim() || defaults.region;
      registry.registryEndpoint =
        draft.a2aRegistry.registryEndpoint?.trim() || defaults.endpoint;
      o.a2aRegistry = registry;
    }
    return o;
  }
  o.name = draft.name;
  o.description = draft.description;
  o.instruction = draft.instruction;
  if (draft.agentType === "loop") o.maxIterations = draft.maxIterations ?? 3;
  if (draft.modelName?.trim()) o.modelName = draft.modelName.trim();
  if (draft.modelSource) o.modelSource = draft.modelSource;
  if (draft.modelSource !== "ark") {
    if (draft.modelProvider?.trim()) o.modelProvider = draft.modelProvider.trim();
    if (draft.modelApiBase?.trim()) o.modelApiBase = draft.modelApiBase.trim();
  }
  if (draft.builtinTools?.length) o.builtinTools = [...draft.builtinTools];
  if (draft.customTools?.length)
    o.customTools = draft.customTools.map((t) => ({
      name: t.name,
      description: t.description,
    }));
  if (draft.mcpTools?.length)
    o.mcpTools = draft.mcpTools.map((m) => {
      const e: Record<string, unknown> = {
        name: m.name,
        transport: m.transport,
      };
      if (m.url?.trim()) e.url = m.url.trim();
      if (m.authTokenEnv?.trim()) e.authTokenEnv = m.authTokenEnv.trim();
      if (m.command?.trim()) e.command = m.command.trim();
      if (m.args?.length) e.args = m.args;
      return e;
    });
  if (draft.memory?.shortTerm || draft.memory?.longTerm) {
    o.memory = {
      shortTerm: !!draft.memory.shortTerm,
      longTerm: !!draft.memory.longTerm,
    };
    if (draft.memory.shortTerm)
      o.shortTermBackend = draft.shortTermBackend || "local";
    if (draft.memory.longTerm) {
      o.longTermBackend = draft.longTermBackend || "local";
      if (draft.longTermMemoryIndex?.trim()) {
        o.longTermMemoryIndex = draft.longTermMemoryIndex.trim();
      }
      o.autoSaveSession = !!draft.autoSaveSession;
    }
  }
  if (draft.knowledgebase) {
    o.knowledgebase = true;
    o.knowledgebaseBackend = draft.knowledgebaseBackend || "viking";
    if (draft.knowledgebaseIndex?.trim()) {
      o.knowledgebaseIndex = draft.knowledgebaseIndex.trim();
    }
  }
  if (draft.tracing && draft.tracingExporters?.length) {
    o.tracing = true;
    o.tracingExporters = [...draft.tracingExporters];
  }
  if (root && draft.harnessSidecar?.enabled) {
    o.harnessSidecar = {
      enabled: true,
      profile: draft.harnessSidecar.profile,
      componentOverrides: { ...draft.harnessSidecar.componentOverrides },
    };
  }
  if (
    draft.cloudEnvironment?.environmentId ||
    draft.cloudEnvironment?.environmentVersionId ||
    draft.cloudEnvironment?.cliTools?.length ||
    draft.cloudEnvironment?.dockerfile !== undefined
  ) {
    o.cloudEnvironment = {
      environmentId: draft.cloudEnvironment.environmentId,
      environmentVersionId: draft.cloudEnvironment.environmentVersionId,
      ...(draft.cloudEnvironment.cliTools?.length
        ? { cliTools: [...draft.cloudEnvironment.cliTools] }
        : {}),
      ...(draft.cloudEnvironment.dockerfile !== undefined
        ? { dockerfile: draft.cloudEnvironment.dockerfile }
        : {}),
    };
  }
  if (
    draft.deployment?.feishuEnabled ||
    draft.deployment?.runtimeName?.trim() ||
    draft.deployment?.runtimeNameCustomized ||
    draft.deployment?.modelApiKeyId?.trim() ||
    draft.deployment?.modelApiKeyName?.trim() ||
    Object.keys(draft.deployment?.envValues ?? {}).length > 0
  ) {
    const deployment: Record<string, unknown> = {
      feishuEnabled: !!draft.deployment?.feishuEnabled,
    };
    if (draft.deployment?.runtimeName?.trim()) {
      deployment.runtimeName = draft.deployment.runtimeName.trim();
    }
    if (draft.deployment?.runtimeNameCustomized) {
      deployment.runtimeNameCustomized = true;
    }
    if (draft.deployment?.modelApiKeyId?.trim()) {
      deployment.modelApiKeyId = draft.deployment.modelApiKeyId.trim();
    }
    if (draft.deployment?.modelApiKeyName?.trim()) {
      deployment.modelApiKeyName = draft.deployment.modelApiKeyName.trim();
    }
    if (Object.keys(draft.deployment?.envValues ?? {}).length > 0) {
      deployment.envValues = { ...draft.deployment?.envValues };
    }
    o.deployment = deployment;
  }
  if (draft.selectedSkills?.length)
    o.selectedSkills = draft.selectedSkills.map((s) => {
      const base: Record<string, unknown> = {
        source: s.source,
        name: s.name,
        folder: s.folder,
      };
      if (s.description) base.description = s.description;
      if (s.source === "skillhub") {
        base.slug = s.slug;
        base.namespace = s.namespace ?? "public";
      } else if (s.source === "local") {
        base.localFiles = s.localFiles ?? [];
      } else if (s.source === "skillspace") {
        base.skillSpaceId = s.skillSpaceId;
        base.skillSpaceName = s.skillSpaceName;
        base.skillId = s.skillId;
        if (s.version) base.version = s.version;
      }
      return base;
    });
  if (draft.subAgents?.length) {
    o.subAgents = draft.subAgents.map((child) => toConfig(child, false));
  }
  return o;
}

export function draftToYaml(draft: AgentDraft): string {
  const prepared = prepareMcpAuth(draft);
  const envValues = {
    ...(prepared.draft.deployment?.envValues ?? {}),
    ...prepared.envValues,
  };
  const exportDraft: AgentDraft = {
    ...prepared.draft,
    deployment: {
      ...(prepared.draft.deployment ?? { feishuEnabled: false }),
      envValues,
    },
  };
  return (
    "# VeADK Agent 结构配置\n" +
    "# 可在「创建 Agent」页通过「导入 YAML」重新载入。\n" +
    stringify(toConfig(exportDraft))
  );
}

/** Parse an agent-structure YAML back into a normalized AgentDraft. Throws on
 *  invalid YAML. */
export function yamlToDraft(text: string): AgentDraft {
  const obj = parse(text);
  return normalizeDraft(obj);
}
