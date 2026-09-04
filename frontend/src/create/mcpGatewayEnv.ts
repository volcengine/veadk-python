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
import { createT } from "./i18n";

export type McpGatewayEnvErrorReason =
  | "missing_http_tool"
  | "missing_url";

export type McpGatewayEnvResolution =
  | { ok: true; urls: string[] }
  | {
      ok: false;
      reason: McpGatewayEnvErrorReason;
      message: string;
    };

const ERROR_MESSAGE_KEYS: Record<McpGatewayEnvErrorReason, string> = {
  missing_http_tool: "helpers.mcpGateway.missingHttpTool",
  missing_url: "helpers.mcpGateway.missingUrl",
};

function failure(reason: McpGatewayEnvErrorReason): McpGatewayEnvResolution {
  return { ok: false, reason, message: createT(ERROR_MESSAGE_KEYS[reason]) };
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
): McpGatewayEnvResolution {
  const nodes: AgentDraft[] = [];
  const visited = new Set<AgentDraft>();

  const visit = (node: AgentDraft) => {
    if (visited.has(node)) return;
    visited.add(node);
    nodes.push(node);
    node.subAgents.forEach(visit);
    node.workflow?.nodes.forEach((workflowNode) => visit(workflowNode.agent));
  };
  visit(root);

  const httpTools = nodes.flatMap((node) =>
    (node.mcpTools ?? []).filter((tool) => tool.transport === "http"),
  );
  if (httpTools.length === 0) return failure("missing_http_tool");

  const urls: string[] = [];
  for (const tool of httpTools) {
    const url = tool.url?.trim() ?? "";
    if (!url || !isHttpUrl(url)) return failure("missing_url");

    urls.push(url);
  }

  return { ok: true, urls };
}
