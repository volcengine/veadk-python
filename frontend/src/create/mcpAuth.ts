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
  if (tool.authToken) return tool.authToken;
  if (tool.credentialConfigured) return "";
  const envName = configuredEnvName(tool);
  return envName ? `\${${envName}}` : "";
}

export function updateMcpAuthTokenInput(tool: McpTool, value: string): McpTool {
  if (!value) {
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
    };
    delete next.authToken;
    return next;
  }
  return { ...tool, authToken: value, credentialConfigured: false };
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
