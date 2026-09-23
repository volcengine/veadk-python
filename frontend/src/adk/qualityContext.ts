import type { AgentComponent, AgentInfo, AgentNode, EnvironmentManifest } from "./client";
import type { AgentDraft, SelectedSkill } from "../create/types";
import { BUILTIN_TOOLS } from "../create/veadkCatalog";

export interface QualityCapabilityContext {
  name: string;
  description: string;
}

export interface QualitySkillContext extends QualityCapabilityContext {
  instructions: string;
  source: string;
  version: string;
}

export interface QualityComponentContext extends QualityCapabilityContext {
  kind: string;
  backend: string;
  source: string;
  provenance: "runtime" | "draft";
}

export interface QualityEnvironmentReference {
  id: string;
  version: string;
}

export interface QualityEnvironmentContext extends QualityEnvironmentReference {
  name: string;
  description: string;
  capabilities: string[];
  skills: { name: string; version: string }[];
}

export interface QualityNodeContext {
  id: string;
  parentId: string;
  path: string[];
  children: string[];
  name: string;
  description: string;
  instruction: string;
  model: string;
  type: string;
  tools: string[];
  skills: string[];
  subAgents: string[];
  toolDetails: QualityCapabilityContext[];
  skillDetails: QualitySkillContext[];
  components: QualityComponentContext[];
  searchSources: string[];
  configuration: { name: string; value: string }[];
  mcpServers: { name: string; transport: string }[];
  configuredWorkflow: { type: string; edges: { from: string; to: string }[] } | null;
  environment: QualityEnvironmentReference | null;
}

export interface QualityAgentContext extends QualityNodeContext {
  metadataSource: "runtime" | "draft";
  subAgentDetails: QualityNodeContext[];
  environments: QualityEnvironmentContext[];
  contextNotes: string[];
}

export interface QualitySkillReference {
  target: QualitySkillContext;
  selected: SelectedSkill;
}

/** Select behavior metadata explicitly; never serialize a Draft or runtime object wholesale. */
export function buildQualityAgentContext(info: AgentInfo | null | undefined, draft?: AgentDraft) {
  const contextNotes: string[] = [];
  const nodes: QualityNodeContext[] = [];
  const skillReferences: QualitySkillReference[] = [];
  const visited = new Set<AgentNode | Partial<AgentDraft>>();
  function note(message: string) {
    if (contextNotes.length < 200 && !contextNotes.includes(message)) contextNotes.push(message);
  }
  function text(value: string | undefined, limit: number, field: string): string {
    if (value && value.length > limit) note(`${field}: text truncated at ${limit} characters`);
    return (value || "").slice(0, limit);
  }
  function list<T>(values: readonly T[], field: string): T[] {
    if (values.length > 100) note(`${field}: only the first 100 entries are available in this context`);
    return values.slice(0, 100);
  }
  function names(values: readonly string[], field: string): string[] {
    return list([...new Set(values.map(value => text(value.trim(), 300, field)).filter(Boolean))], field);
  }
  function childrenOf(value?: Partial<AgentDraft>): AgentDraft[] {
    const children = [...(value?.subAgents ?? [])];
    for (const node of value?.workflow?.nodes ?? []) {
      if (!children.some(child => child.name === node.agent.name)) children.push(node.agent);
    }
    return children;
  }
  function configuredComponents(value: Partial<AgentDraft>): AgentComponent[] {
    const result: AgentComponent[] = [];
    if (value.knowledgebase) result.push({ kind: "knowledgebase", name: value.knowledgebaseIndex || "knowledgebase", backend: value.knowledgebaseBackend, source: "knowledgebase" });
    if (value.memory?.shortTerm) result.push({ kind: "memory", name: "short_term_memory", backend: value.shortTermBackend, source: "short_term_memory" });
    if (value.memory?.longTerm) result.push({ kind: "memory", name: value.longTermMemoryIndex || "long_term_memory", backend: value.longTermBackend, source: "long_term_memory" });
    if (value.tracing) for (const name of value.tracingExporters ?? []) result.push({ kind: "tracer", name });
    return result;
  }
  function configuration(value: Partial<AgentDraft> | undefined, field: string) {
    const entries: [string, string | number | boolean | undefined][] = value ? [
      ["modelProvider", value.modelProvider], ["modelSource", value.modelSource],
      ["modelFallbacks", value.modelFallbacks?.map(model => typeof model === "string" ? model : model.modelName).join(", ")],
      ["maxIterations", value.agentType === "loop" ? value.maxIterations : undefined],
      ["dynamicAgentDelegation", value.dynamicAgentDelegation],
      ["memory.shortTerm", value.memory?.shortTerm], ["memory.longTerm", value.memory?.longTerm],
      ["shortTermBackend", value.shortTermBackend], ["longTermBackend", value.longTermBackend],
      ["longTermMemoryIndex", value.longTermMemoryIndex], ["autoSaveSession", value.autoSaveSession],
      ["knowledgebase", value.knowledgebase], ["knowledgebaseBackend", value.knowledgebaseBackend],
      ["knowledgebaseIndex", value.knowledgebaseIndex], ["tracing", value.tracing],
      ["tracingExporters", value.tracingExporters?.join(", ")],
      ["a2aRegistry.enabled", value.a2aRegistry?.enabled], ["a2aRegistry.topK", value.a2aRegistry?.registryTopK],
      ["feishuEnabled", value.deployment?.feishuEnabled],
      ["harnessSidecar.enabled", value.harnessSidecar?.enabled], ["harnessSidecar.profile", value.harnessSidecar?.profile],
    ] : [];
    for (const key of ["context_engine", "compressor", "verifier", "long_run_control", "mcp_resilience"] as const) {
      entries.push([`harnessSidecar.${key}`, value?.harnessSidecar?.componentOverrides?.[key]]);
    }
    return entries.filter(([, value]) => value !== undefined && value !== "").map(([name, value]) => ({ name, value: text(String(value), 6000, `${field}.${name}`) }));
  }
  function visit(graph: AgentNode | undefined, value: Partial<AgentDraft> | undefined, parent: QualityNodeContext | null, position: number): QualityNodeContext | undefined {
    const identity = graph ?? value;
    if (nodes.length >= 100 || (parent?.path.length ?? 0) >= 32 || (identity && visited.has(identity))) {
      note("topology: additional nodes were omitted because of a size/depth limit or repeated node reference");
      return undefined;
    }
    if (identity) visited.add(identity);
    const id = parent ? `${parent.id}/${position}` : "root";
    const rootInfo = parent ? undefined : info;
    const name = text(graph?.name || rootInfo?.name || value?.name || "Agent", 300, `${id}.name`);
    const draftTools = [...(value?.tools ?? []), ...(value?.builtinTools ?? []), ...(value?.customTools?.map(tool => tool.name) ?? [])];
    const tools = names(graph?.tools ?? rootInfo?.tools ?? draftTools, `${id}.tools`);
    const knownSkills = graph?.skills ?? (rootInfo?.skillsPreviewSupported !== false ? rootInfo?.skills : undefined);
    const skills = names(knownSkills?.map(skill => skill.name) ?? [...(value?.skills ?? []), ...(value?.selectedSkills?.map(skill => skill.name) ?? [])], `${id}.skills`);
    const skillDetails = skills.map(skillName => {
      const selected = value?.selectedSkills?.find(skill => [skill.name, skill.folder].includes(skillName));
      const localFile = selected?.localFiles?.find(file => file.path === "SKILL.md" || file.path === `skills/${selected.folder}/SKILL.md` || file.path === `${selected.folder}/SKILL.md`);
      const target: QualitySkillContext = {
        name: skillName,
        description: text(knownSkills?.find(skill => skill.name === skillName)?.description || selected?.description, 3000, `${id}.skills.${skillName}.description`),
        instructions: text(localFile?.content, 30000, `${id}.skills.${skillName}.instructions`),
        source: selected?.source || (knownSkills ? "runtime" : "draft"),
        version: text(selected?.version, 300, `${id}.skills.${skillName}.version`),
      };
      if (selected?.source === "skillspace" && !localFile && selected.skillSpaceId && selected.skillId && selected.version) skillReferences.push({ target, selected });
      else if (!localFile) note(`${id}.skills.${skillName}: full Skill instructions are not exposed; use the supplied name and description only`);
      return target;
    });
    const runtimeComponents = graph?.components ?? (rootInfo?.componentsPreviewSupported !== false ? rootInfo?.components : undefined);
    const components = list(runtimeComponents ?? (value ? configuredComponents(value) : []), `${id}.components`).map(component => ({
      name: text(component.name, 300, `${id}.components.name`),
      description: text(component.description, 3000, `${id}.components.description`),
      kind: text(component.kind, 100, `${id}.components.kind`),
      backend: text(component.backend, 300, `${id}.components.backend`),
      source: text(component.source, 300, `${id}.components.source`),
      provenance: runtimeComponents ? "runtime" as const : "draft" as const,
    }));
    if (!runtimeComponents && info) note(`${id}.components: runtime component metadata is unavailable; any listed components come from the configuration snapshot`);
    const node: QualityNodeContext = {
      id, parentId: parent?.id || "", path: [...(parent?.path ?? []), name], children: [], name,
      description: text(graph?.description ?? rootInfo?.description ?? value?.description, 12000, `${id}.description`),
      instruction: text(graph?.instruction ?? value?.instruction, 60000, `${id}.instruction`),
      model: text(graph?.model ?? rootInfo?.model ?? value?.modelName ?? value?.model, 300, `${id}.model`),
      type: graph?.type || rootInfo?.type || value?.agentType || "",
      tools, skills, subAgents: [],
      toolDetails: tools.map(toolName => ({
        name: toolName,
        description: text(value?.customTools?.find(tool => tool.name === toolName)?.description || BUILTIN_TOOLS.find(tool => tool.id === toolName || tool.toolNames.includes(toolName))?.desc, 3000, `${id}.tools.${toolName}.description`),
      })),
      skillDetails, components,
      searchSources: names(rootInfo?.searchSources ?? [], `${id}.searchSources`),
      configuration: configuration(value, `${id}.configuration`),
      mcpServers: list(value?.mcpTools ?? [], `${id}.mcpServers`).map(server => ({ name: text(server.name, 300, `${id}.mcpServers.name`), transport: server.transport })),
      configuredWorkflow: null,
      environment: value?.cloudEnvironment?.environmentId && value.cloudEnvironment.environmentVersionId
        ? { id: text(value.cloudEnvironment.environmentId, 300, `${id}.environment.id`), version: text(value.cloudEnvironment.environmentVersionId, 300, `${id}.environment.version`) }
        : null,
    };
    const undocumentedTools = node.toolDetails.filter(tool => !tool.description).map(tool => tool.name);
    if (undocumentedTools.length) note(`${id}.tools: descriptions and parameter schemas are unavailable for ${undocumentedTools.join(", ")}; do not infer their contracts from their names`);
    nodes.push(node);
    const draftChildren = childrenOf(value);
    const children = graph?.children;
    if (children) {
      children.forEach((child, index) => {
        const childDraft = draftChildren.find(candidate => candidate.name === child.id || candidate.name === child.name);
        const added = visit(child, childDraft, node, index);
        if (added) node.children.push(added.id);
      });
    } else {
      const inventory = rootInfo?.subAgents;
      const childNames = inventory ?? draftChildren.map(child => child.name);
      childNames.forEach((childName, index) => {
        const childDraft = draftChildren.find(child => child.name === childName);
        const added = visit(undefined, childDraft ?? { name: childName }, node, index);
        if (added) node.children.push(added.id);
        if (!childDraft) note(`${node.id}/${index}: only the sub-Agent name is available`);
      });
      if (info) note(`${id}.topology: runtime topology is unavailable; relationships are based on available names and configuration`);
    }
    node.subAgents = node.children.map(childId => nodes.find(child => child.id === childId)!.name);
    if (value?.workflow) {
      const ids = new Map(value.workflow.nodes.map(workflowNode => [workflowNode.id, nodes.find(child => child.parentId === node.id && child.name === workflowNode.agent.name)?.id]));
      node.configuredWorkflow = { type: value.workflow.type, edges: [] };
      for (const edge of list(value.workflow.edges, `${id}.workflow.edges`)) {
        const from = ids.get(edge.from), to = ids.get(edge.to);
        if (from && to) node.configuredWorkflow.edges.push({ from, to });
        else note(`${id}.workflow: an edge could not be matched to the available topology`);
      }
    }
    return node;
  }
  const root = visit(info?.graph, draft, null, 0)!;
  const context: QualityAgentContext = { ...root, metadataSource: info ? "runtime" : "draft", subAgentDetails: nodes.slice(1), environments: [], contextNotes };
  return { context, skillReferences };
}

export function qualityEnvironmentContext(reference: QualityEnvironmentReference, manifest: EnvironmentManifest): QualityEnvironmentContext {
  return {
    ...reference,
    name: manifest.metadata.name.slice(0, 300),
    description: manifest.metadata.description.slice(0, 3000),
    capabilities: manifest.spec.capabilities.slice(0, 100).map(value => value.slice(0, 300)),
    skills: manifest.spec.skills.slice(0, 100).map(skill => ({ name: skill.name.slice(0, 300), version: skill.version.slice(0, 300) })),
  };
}
