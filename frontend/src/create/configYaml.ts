// Serialize an AgentDraft to / from a human-readable "agent structure" YAML.
// The YAML mirrors the AgentDraft config shape, so it round-trips cleanly and
// can be imported back into the custom-mode wizard.

import { parse, stringify } from "yaml";
import { A2A_REGISTRY_DEFAULTS } from "./veadkCatalog";
import { normalizeDraft } from "./normalizeDraft";
import type { AgentDraft } from "./types";

/** Build a clean, minimal config object (omit empty/false fields). */
function toConfig(draft: AgentDraft): Record<string, unknown> {
  const o: Record<string, unknown> = {
    name: draft.name,
    description: draft.description,
    instruction: draft.instruction,
  };
  if (draft.modelName?.trim()) o.modelName = draft.modelName.trim();
  if (draft.modelProvider?.trim()) o.modelProvider = draft.modelProvider.trim();
  if (draft.modelApiBase?.trim()) o.modelApiBase = draft.modelApiBase.trim();
  if (draft.builtinTools?.length) o.builtinTools = [...draft.builtinTools];
  if (draft.customTools?.length)
    o.customTools = draft.customTools.map((t) => ({ name: t.name, description: t.description }));
  if (draft.mcpTools?.length)
    o.mcpTools = draft.mcpTools.map((m) => {
      const e: Record<string, unknown> = { name: m.name, transport: m.transport };
      if (m.url?.trim()) e.url = m.url.trim();
      if (m.authToken?.trim()) e.authToken = m.authToken.trim();
      if (m.command?.trim()) e.command = m.command.trim();
      if (m.args?.length) e.args = m.args;
      return e;
    });
  if (draft.a2aRegistry?.enabled) {
    const registry: Record<string, unknown> = { enabled: true };
    if (draft.a2aRegistry.registrySpaceId?.trim())
      registry.registrySpaceId = draft.a2aRegistry.registrySpaceId.trim();
    registry.registryTopK =
      draft.a2aRegistry.registryTopK?.trim() || A2A_REGISTRY_DEFAULTS.topK;
    registry.registryRegion =
      draft.a2aRegistry.registryRegion?.trim() || A2A_REGISTRY_DEFAULTS.region;
    registry.registryEndpoint =
      draft.a2aRegistry.registryEndpoint?.trim() ||
      A2A_REGISTRY_DEFAULTS.endpoint;
    o.a2aRegistry = registry;
  }
  if (draft.memory?.shortTerm || draft.memory?.longTerm) {
    o.memory = { shortTerm: !!draft.memory.shortTerm, longTerm: !!draft.memory.longTerm };
    if (draft.memory.shortTerm) o.shortTermBackend = draft.shortTermBackend || "local";
    if (draft.memory.longTerm) {
      o.longTermBackend = draft.longTermBackend || "local";
      o.autoSaveSession = !!draft.autoSaveSession;
    }
  }
  if (draft.knowledgebase) {
    o.knowledgebase = true;
    o.knowledgebaseBackend = draft.knowledgebaseBackend || "local";
  }
  if (draft.tracing && draft.tracingExporters?.length) {
    o.tracing = true;
    o.tracingExporters = [...draft.tracingExporters];
  }
  if (draft.deployment?.feishuEnabled) {
    o.deployment = { feishuEnabled: true };
  }
  if (draft.selectedSkills?.length)
    o.selectedSkills = draft.selectedSkills.map((s) => {
      const base: Record<string, unknown> = { source: s.source, name: s.name, folder: s.folder };
      if (s.description) base.description = s.description;
      if (s.source === "skillhub") {
        base.slug = s.slug;
        base.namespace = s.namespace ?? "public";
      } else if (s.source === "local") {
        base.localFiles = s.localFiles ?? [];
      } else {
        base.skillSpaceId = s.skillSpaceId;
        base.skillSpaceName = s.skillSpaceName;
        base.skillId = s.skillId;
        if (s.version) base.version = s.version;
      }
      return base;
    });
  if (draft.subAgents?.length)
    o.subAgents = draft.subAgents.map((sa) => {
      const s: Record<string, unknown> = { name: sa.name, description: sa.description, instruction: sa.instruction };
      if (sa.builtinTools?.length) s.builtinTools = [...sa.builtinTools];
      if (sa.customTools?.length) s.customTools = sa.customTools.map((t) => ({ name: t.name, description: t.description }));
      if (sa.a2aRegistry?.enabled) s.a2aRegistry = toConfig(sa).a2aRegistry;
      return s;
    });
  return o;
}

export function draftToYaml(draft: AgentDraft): string {
  return (
    "# VeADK Agent 结构配置\n" +
    "# 可在「创建 Agent」页通过「导入 YAML」重新载入。\n" +
    stringify(toConfig(draft))
  );
}

/** Parse an agent-structure YAML back into a normalized AgentDraft. Throws on
 *  invalid YAML. */
export function yamlToDraft(text: string): AgentDraft {
  const obj = parse(text);
  return normalizeDraft(obj);
}
