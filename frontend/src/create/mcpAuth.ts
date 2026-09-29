import type { AgentDraft, McpCredentialValue, McpTool } from "./types";

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

export type McpConfigurationConflict = "duplicateName" | "duplicateUrl";

function canonicalMcpUrl(value: string | undefined): string | null {
  try {
    const raw = (value ?? "").trim();
    const url = new URL(raw);
    if (
      (url.protocol !== "http:" && url.protocol !== "https:") ||
      url.username ||
      url.password ||
      url.search ||
      url.hash
    ) {
      return null;
    }
    const authorityStart = raw.indexOf("://") + 3;
    const pathStart = raw.indexOf("/", authorityStart);
    const path = (pathStart >= 0 ? raw.slice(pathStart) : "").replace(/\/+$/, "");
    return `${url.protocol}//${url.host}${path}`;
  } catch {
    return null;
  }
}

function canonicalMcpName(tool: McpTool, index: number): string {
  let candidate = tool.name.trim();
  if (!candidate) {
    const url = canonicalMcpUrl(tool.url);
    const segments = url?.split("/").filter(Boolean) ?? [];
    candidate = segments[segments.length - 1] ?? "";
  }
  candidate = candidate
    .replace(/[^A-Za-z0-9_.-]+/g, "_")
    .replace(/^[_.-]+|[_.-]+$/g, "");
  return candidate || `mcp_${index + 1}`;
}

/** Match the Sidecar's global name/URL uniqueness checks before deployment. */
export function mcpConfigurationConflict(
  root: AgentDraft,
): McpConfigurationConflict | null {
  const names = new Set<string>();
  const urls = new Set<string>();
  let conflict: McpConfigurationConflict | null = null;
  const visit = (node: AgentDraft) => {
    (node.mcpTools ?? []).forEach((tool, index) => {
      if (conflict || tool.transport !== "http") return;
      const name = canonicalMcpName(tool, index);
      const url = canonicalMcpUrl(tool.url);
      if (names.has(name)) {
        conflict = "duplicateName";
        return;
      }
      if (url && urls.has(url)) {
        conflict = "duplicateUrl";
        return;
      }
      names.add(name);
      if (url) urls.add(url);
    });
    if (conflict) return;
    node.subAgents.forEach(visit);
    node.workflow?.nodes.forEach((workflowNode) => visit(workflowNode.agent));
  };
  visit(root);
  return conflict;
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
    const next = { ...tool, credentialConfigured: false };
    delete next.authToken;
    delete next.authTokenEnv;
    delete next.credentialSourceUrl;
    delete next.credentialSourceAuthTokenEnv;
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
  return {
    ...tool,
    authToken: value,
    credentialConfigured: false,
  };
}

export function mcpUrlNeedsPathWarning(value: string): boolean {
  if (!value.trim()) return false;
  try {
    const path = new URL(value).pathname.replace(/\/+$/, "");
    return path === "";
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

function normalizedMcpIdentityUrl(value: string | undefined): string {
  return (value ?? "").trim().replace(/\/+$/, "");
}

/** Change an MCP URL while retaining the explicit token shown in the editor. */
export function updateMcpUrlInput(tool: McpTool, value: string): McpTool {
  return { ...tool, url: value };
}

/** Add authorized credential values to the editor without mutating the source. */
export function hydrateMcpCredentialValues(
  root: AgentDraft,
  credentials: readonly McpCredentialValue[],
): AgentDraft {
  const bySlot = new Map(
    credentials.map((credential) => [
      [
        credential.agentName.trim(),
        credential.authTokenEnv.trim(),
        normalizedMcpIdentityUrl(credential.url),
      ].join("\u0000"),
      credential.value,
    ]),
  );

  const visit = (node: AgentDraft): AgentDraft => ({
    ...node,
    mcpTools: (node.mcpTools ?? []).map((tool) => {
      const reference = configuredEnvName(tool);
      if (!reference) return tool;
      const value = bySlot.get(
        [
          node.name.trim(),
          reference,
          normalizedMcpIdentityUrl(tool.url),
        ].join("\u0000"),
      );
      return value
        ? {
            ...tool,
            authToken: value,
            credentialConfigured: true,
            credentialSourceUrl: tool.url?.trim() ?? "",
            credentialSourceAuthTokenEnv: reference,
          }
        : tool;
    }),
    subAgents: node.subAgents.map(visit),
    ...(node.workflow
      ? {
          workflow: {
            ...node.workflow,
            nodes: node.workflow.nodes.map((workflowNode) => ({
              ...workflowNode,
              agent: visit(workflowNode.agent),
            })),
          },
        }
      : {}),
  });

  return visit(root);
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
