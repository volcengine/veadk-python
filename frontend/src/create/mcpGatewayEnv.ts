// Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import type { AgentDraft } from "./types";

export type McpGatewayEnvErrorReason =
  | "missing_http_tool"
  | "missing_url"
  | "missing_api_key"
  | "conflicting_api_keys";

export type McpGatewayEnvResolution =
  | { ok: true; urls: string[]; apiKey: string }
  | {
      ok: false;
      reason: McpGatewayEnvErrorReason;
      message: string;
    };

const ERROR_MESSAGES: Record<McpGatewayEnvErrorReason, string> = {
  missing_http_tool:
    "请返回“添加 MCP 工具”并添加至少一个 HTTP MCP 服务；MCP 稳定性治理不支持 stdio 服务。",
  missing_url:
    "已添加的 HTTP MCP 工具缺少有效服务地址，请返回“添加 MCP 工具”补充后再发布。",
  missing_api_key:
    "已添加的 HTTP MCP 工具缺少 Bearer Token，请返回“添加 MCP 工具”补充后再发布。",
  conflicting_api_keys:
    "多个 HTTP MCP 工具使用了不同凭证，而 MCP 稳定性治理当前只支持一个共享凭证；请统一凭证或改用统一网关。",
};

function failure(reason: McpGatewayEnvErrorReason): McpGatewayEnvResolution {
  return { ok: false, reason, message: ERROR_MESSAGES[reason] };
}

function isHttpUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

/** Resolve Sidecar gateway inputs from HTTP MCP tools configured earlier. */
export function resolveMcpGatewayEnv(
  root: AgentDraft,
  injectedEnvValues: Record<string, string>,
): McpGatewayEnvResolution {
  const envValues: Record<string, string> = {};
  const nodes: AgentDraft[] = [];
  const visited = new Set<AgentDraft>();

  const visit = (node: AgentDraft) => {
    if (visited.has(node)) return;
    visited.add(node);
    nodes.push(node);
    Object.assign(envValues, node.deployment?.envValues ?? {});
    node.subAgents.forEach(visit);
    node.workflow?.nodes.forEach((workflowNode) => visit(workflowNode.agent));
  };
  visit(root);
  Object.assign(envValues, injectedEnvValues);

  const httpTools = nodes.flatMap((node) =>
    (node.mcpTools ?? []).filter((tool) => tool.transport === "http"),
  );
  if (httpTools.length === 0) return failure("missing_http_tool");

  const urls: string[] = [];
  const credentials = new Set<string>();
  for (const tool of httpTools) {
    const url = tool.url?.trim() ?? "";
    if (!url || !isHttpUrl(url)) return failure("missing_url");

    const envName = tool.authTokenEnv?.trim() ?? "";
    const apiKey = envName ? (envValues[envName] ?? "").trim() : "";
    if (!apiKey) return failure("missing_api_key");

    urls.push(url);
    credentials.add(apiKey);
  }
  if (credentials.size !== 1) return failure("conflicting_api_keys");

  return { ok: true, urls, apiKey: [...credentials][0] };
}
