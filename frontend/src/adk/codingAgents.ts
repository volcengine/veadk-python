import { studioFetch } from "./client";
import { adkT } from "./i18n";
import { BOOT_REQUEST_TIMEOUT_MS, DEFAULT_REQUEST_TIMEOUT_MS } from "./timeout";

export type CodingAgentId = "trae" | "claude-code" | "codex";
export type BundledCodingAgentSkillId =
  | "veadk-agent-development"
  | "agentkit-cli";

export interface CodingAgentCapability {
  id: CodingAgentId;
  name: string;
  available: boolean;
  version: string;
  reason: string;
  globalSkillsPath: string;
}

export interface BundledCodingAgentSkill {
  id: BundledCodingAgentSkillId;
  name: string;
  description: string;
}

export interface CodingAgentCapabilities {
  platform: "macos" | "linux" | "windows" | "other";
  agents: CodingAgentCapability[];
  skills: BundledCodingAgentSkill[];
}

export interface CodingAgentSkillPreviewFile {
  path: string;
  size: number;
  previewable: boolean;
  content: string | null;
}

export interface CodingAgentSkillPreview {
  id: BundledCodingAgentSkillId;
  name: string;
  files: CodingAgentSkillPreviewFile[];
}

export interface CodingAgentInstallRequest {
  agents: CodingAgentId[];
  skills: BundledCodingAgentSkillId[];
}

export interface CodingAgentInstallation {
  agent: CodingAgentId;
  agentName: string;
  skill: string;
  skillId: BundledCodingAgentSkillId;
  displayPath: string;
}

async function codingAgentFetch<T>(
  url: string,
  init: RequestInit,
  signal: AbortSignal,
  timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
): Promise<T> {
  const response = await studioFetch(url, {
    ...init,
    headers: {
      accept: "application/json",
      ...init.headers,
    },
    signal,
  }, timeoutMs);
  if (!response.ok) {
    let detail = "";
    try {
      const body = await response.json() as { detail?: string };
      detail = body.detail?.trim() || "";
    } catch {
      // The status below is still useful when the server returns no JSON body.
    }
    throw new Error(detail || adkT("common.requestFailed", { status: response.status }));
  }
  return response.json() as Promise<T>;
}

export function getCodingAgentCapabilities(
  signal: AbortSignal,
): Promise<CodingAgentCapabilities> {
  return codingAgentFetch<CodingAgentCapabilities>(
    "/web/coding-agents/capabilities",
    { method: "GET" },
    signal,
    BOOT_REQUEST_TIMEOUT_MS,
  );
}

export function getCodingAgentSkillPreview(
  skillId: BundledCodingAgentSkillId,
  signal: AbortSignal,
): Promise<CodingAgentSkillPreview> {
  return codingAgentFetch<CodingAgentSkillPreview>(
    `/web/coding-agents/skills/${encodeURIComponent(skillId)}/preview`,
    { method: "GET" },
    signal,
  );
}

export function installCodingAgentSkills(
  body: CodingAgentInstallRequest,
  signal: AbortSignal,
): Promise<{ installations: CodingAgentInstallation[] }> {
  return codingAgentFetch(
    "/web/coding-agents/install",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    signal,
  );
}
