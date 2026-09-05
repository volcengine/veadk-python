import type { AgentDraft, McpTool } from "./types";

const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;
const ENV_REFERENCE = /^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$/;

function envSegment(value: string, fallback: string): string {
  const segment = value
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return segment || fallback;
}

function nextEnvName(base: string, used: Set<string>): string {
  if (!used.has(base)) return base;
  let suffix = 2;
  while (used.has(`${base}_${suffix}`)) suffix += 1;
  return `${base}_${suffix}`;
}

function configuredEnvName(tool: McpTool): string {
  const explicit = tool.authTokenEnv?.trim();
  if (explicit && ENV_NAME.test(explicit)) return explicit;
  return tool.authToken?.trim().match(ENV_REFERENCE)?.[1] ?? "";
}

function walkMcpTools(
  root: AgentDraft,
  visit: (tool: McpTool) => void,
): void {
  for (const tool of root.mcpTools ?? []) visit(tool);
  for (const child of root.subAgents) walkMcpTools(child, visit);
  for (const node of root.workflow?.nodes ?? []) {
    walkMcpTools(node.agent, visit);
  }
}

/** Credential identifiers confirmed by the server for the published draft. */
export function configuredMcpEnvKeys(root: AgentDraft): string[] {
  const keys = new Set<string>();
  walkMcpTools(root, (tool) => {
    const key = configuredEnvName(tool);
    if (tool.credentialConfigured && key) keys.add(key);
  });
  return [...keys];
}

/** Environment identifiers referenced by MCP configuration, never values. */
export function referencedMcpEnvKeys(root: AgentDraft): string[] {
  const keys = new Set<string>();
  walkMcpTools(root, (tool) => {
    const key = configuredEnvName(tool);
    if (key) keys.add(key);
  });
  return [...keys];
}

/** Published MCP credential identifiers no longer referenced by the editor. */
export function removedConfiguredMcpEnvKeys(
  publishedKeys: readonly string[],
  current: AgentDraft,
): string[] {
  const active = new Set(referencedMcpEnvKeys(current));
  return [...new Set(publishedKeys)].filter((key) => !active.has(key));
}

export function mcpAuthTokenInputValue(tool: McpTool): string {
  if (tool.credentialUpdate === "pending") return "";
  if (tool.authToken) return tool.authToken;
  if (tool.credentialConfigured) return "";
  const envName = configuredEnvName(tool);
  return envName ? `\${${envName}}` : "";
}

export function updateMcpAuthTokenInput(tool: McpTool, value: string): McpTool {
  if (!value) {
    if (tool.authToken) {
      const next = { ...tool, credentialConfigured: false };
      delete next.authToken;
      delete next.authTokenEnv;
      return next;
    }
    if (tool.credentialConfigured) {
      const next = { ...tool };
      delete next.authToken;
      return next;
    }
    const next = { ...tool };
    delete next.authToken;
    delete next.authTokenEnv;
    return next;
  }
  const reference = value.trim().match(ENV_REFERENCE);
  if (reference) {
    const next = {
      ...tool,
      authTokenEnv: reference[1],
      credentialConfigured:
        tool.credentialConfigured && configuredEnvName(tool) === reference[1],
      ...(tool.credentialSourceUrl
        ? { credentialUpdate: "replace" as const }
        : {}),
    };
    delete next.authToken;
    return next;
  }
  return {
    ...tool,
    authToken: value,
    credentialConfigured: false,
    ...(tool.credentialSourceUrl
      ? { credentialUpdate: "replace" as const }
      : {}),
  };
}

export function clearMcpConfiguredAuth(tool: McpTool): McpTool {
  const next = { ...tool, credentialConfigured: false };
  delete next.authToken;
  delete next.authTokenEnv;
  return next;
}

export function mcpUrlNeedsPathWarning(value: string): boolean {
  if (!value.trim()) return false;
  try {
    const path = new URL(value).pathname.replace(/\/+$/, "");
    return !path.endsWith("/mcp");
  } catch {
    return false;
  }
}

export interface PreparedMcpAuth {
  draft: AgentDraft;
  envValues: Record<string, string>;
}

export interface SourcePreservingMcpSecretValue {
  agentName: string;
  name: string;
  url: string;
  value: string;
}

export interface McpCredentialReuseValue {
  agentName: string;
  name: string;
  url: string;
  sourceAuthTokenEnv: string;
}

function normalizedMcpIdentityUrl(value: string | undefined): string {
  return (value ?? "").trim().replace(/\/+$/, "");
}

/** Whether a changed published endpoint still needs an explicit auth choice. */
export function mcpCredentialActionRequired(tool: McpTool): boolean {
  return tool.credentialUpdate === "pending";
}

/** Change an MCP URL without silently replaying a published credential. */
export function updateMcpUrlInput(tool: McpTool, value: string): McpTool {
  const sourceUrl =
    tool.credentialSourceUrl ??
    (tool.credentialConfigured ? tool.url?.trim() ?? "" : "");
  const sourceAuthTokenEnv =
    tool.credentialSourceAuthTokenEnv ??
    (tool.credentialConfigured ? configuredEnvName(tool) : "");
  if (!sourceUrl || !sourceAuthTokenEnv) return { ...tool, url: value };

  if (
    normalizedMcpIdentityUrl(value) === normalizedMcpIdentityUrl(sourceUrl)
  ) {
    const restored: McpTool = {
      ...tool,
      url: value,
      authTokenEnv: sourceAuthTokenEnv,
      credentialConfigured: true,
      credentialSourceUrl: sourceUrl,
      credentialSourceAuthTokenEnv: sourceAuthTokenEnv,
    };
    delete restored.authToken;
    delete restored.credentialUpdate;
    return restored;
  }

  const changed: McpTool = {
    ...tool,
    url: value,
    authTokenEnv: sourceAuthTokenEnv,
    credentialConfigured: false,
    credentialSourceUrl: sourceUrl,
    credentialSourceAuthTokenEnv: sourceAuthTokenEnv,
    credentialUpdate: "pending",
  };
  delete changed.authToken;
  return changed;
}

export function confirmMcpCredentialReuse(tool: McpTool): McpTool {
  if (!tool.credentialSourceAuthTokenEnv) return tool;
  return {
    ...tool,
    authTokenEnv: tool.credentialSourceAuthTokenEnv,
    credentialConfigured: false,
    credentialUpdate: "reuse",
  };
}

export function replaceMcpCredentialForChangedUrl(tool: McpTool): McpTool {
  const next: McpTool = {
    ...tool,
    credentialConfigured: false,
    credentialUpdate: "replace",
  };
  delete next.authToken;
  delete next.authTokenEnv;
  return next;
}

export function removeMcpCredentialForChangedUrl(tool: McpTool): McpTool {
  const next = replaceMcpCredentialForChangedUrl(tool);
  next.credentialUpdate = "remove";
  return next;
}

/** New deployment credentials resolved from the MCP editor's prior inputs. */
export function deploymentMcpSecretValues(
  root: AgentDraft,
): SourcePreservingMcpSecretValue[] {
  const prepared = prepareMcpAuth(root);
  const envValues: Record<string, string> = {};
  const collectEnv = (node: AgentDraft) => {
    Object.assign(envValues, node.deployment?.envValues ?? {});
    node.subAgents.forEach(collectEnv);
    node.workflow?.nodes.forEach((workflowNode) => collectEnv(workflowNode.agent));
  };
  collectEnv(root);
  Object.assign(envValues, prepared.envValues);

  const values: SourcePreservingMcpSecretValue[] = [];
  const visit = (node: AgentDraft) => {
    for (const tool of node.mcpTools ?? []) {
      const reference = tool.authTokenEnv?.trim() ?? "";
      const value = reference ? (envValues[reference] ?? "").trim() : "";
      if (tool.transport !== "http" || !value) continue;
      values.push({
        agentName: node.name.trim(),
        name: tool.name.trim(),
        url: tool.url?.trim() ?? "",
        value,
      });
    }
    node.subAgents.forEach(visit);
    node.workflow?.nodes.forEach((workflowNode) => visit(workflowNode.agent));
  };
  visit(prepared.draft);
  return values;
}

/** New/replacement MCP credentials submitted by endpoint identity, never env name. */
export function sourcePreservingMcpSecretValues(
  root: AgentDraft,
): SourcePreservingMcpSecretValue[] {
  const values: SourcePreservingMcpSecretValue[] = [];

  const visit = (node: AgentDraft) => {
    for (const tool of node.mcpTools ?? []) {
      const value = tool.authToken?.trim() ?? "";
      if (
        tool.transport !== "http" ||
        !value ||
        ENV_REFERENCE.test(value)
      ) {
        continue;
      }
      values.push({
        agentName: node.name.trim(),
        name: tool.name.trim(),
        url: tool.url?.trim() ?? "",
        value,
      });
    }
    node.subAgents.forEach(visit);
    node.workflow?.nodes.forEach((workflowNode) => visit(workflowNode.agent));
  };

  visit(root);
  return values;
}

/** Explicitly confirmed reuse decisions; contains references, never secrets. */
export function mcpCredentialReuseValues(
  root: AgentDraft,
): McpCredentialReuseValue[] {
  const values: McpCredentialReuseValue[] = [];
  const visit = (node: AgentDraft) => {
    for (const tool of node.mcpTools ?? []) {
      const sourceAuthTokenEnv =
        tool.credentialSourceAuthTokenEnv?.trim() ?? "";
      if (
        tool.transport === "http" &&
        tool.credentialUpdate === "reuse" &&
        sourceAuthTokenEnv
      ) {
        values.push({
          agentName: node.name.trim(),
          name: tool.name.trim(),
          url: tool.url?.trim() ?? "",
          sourceAuthTokenEnv,
        });
      }
    }
    node.subAgents.forEach(visit);
    node.workflow?.nodes.forEach((workflowNode) => visit(workflowNode.agent));
  };
  visit(root);
  return values;
}

/** Replace transient MCP tokens with stable environment-variable references. */
export function prepareMcpAuth(root: AgentDraft): PreparedMcpAuth {
  const used = new Set<string>();
  const envValues: Record<string, string> = {};

  const visit = (node: AgentDraft): AgentDraft => {
    const agentSegment = envSegment(node.name, "AGENT");
    const mcpTools = node.mcpTools?.map((tool, index) => {
      const rawToken = tool.authToken?.trim() ?? "";
      const reference = rawToken.match(ENV_REFERENCE)?.[1] ?? "";
      const explicit = configuredEnvName(tool);
      let envName = explicit;
      if (!envName && rawToken) {
        const toolSegment = envSegment(tool.name, `TOOL_${index + 1}`);
        envName = nextEnvName(
          `MCP_${agentSegment}_${toolSegment}_AUTH_TOKEN`,
          used,
        );
      }
      if (envName) used.add(envName);
      if (envName && rawToken && !reference) envValues[envName] = rawToken;

      const prepared = { ...tool };
      delete prepared.authToken;
      delete prepared.credentialConfigured;
      delete prepared.credentialSourceUrl;
      delete prepared.credentialSourceAuthTokenEnv;
      delete prepared.credentialUpdate;
      if (envName) prepared.authTokenEnv = envName;
      else delete prepared.authTokenEnv;
      return prepared;
    });
    const subAgents = node.subAgents.map(visit);
    const workflow = node.workflow
      ? {
          ...node.workflow,
          nodes: node.workflow.nodes.map((workflowNode) => ({
            ...workflowNode,
            agent: visit(workflowNode.agent),
          })),
        }
      : undefined;
    return {
      ...node,
      subAgents,
      ...(mcpTools ? { mcpTools } : {}),
      ...(workflow ? { workflow } : {}),
    };
  };

  return { draft: visit(root), envValues };
}
