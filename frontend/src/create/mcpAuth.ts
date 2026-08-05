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

export function mcpAuthTokenInputValue(tool: McpTool): string {
  if (tool.authToken) return tool.authToken;
  const envName = configuredEnvName(tool);
  return envName ? `\${${envName}}` : "";
}

export function updateMcpAuthTokenInput(tool: McpTool, value: string): McpTool {
  if (!value) {
    const next = { ...tool };
    delete next.authToken;
    delete next.authTokenEnv;
    return next;
  }
  const reference = value.trim().match(ENV_REFERENCE);
  if (reference) {
    const next = { ...tool, authTokenEnv: reference[1] };
    delete next.authToken;
    return next;
  }
  return { ...tool, authToken: value };
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
