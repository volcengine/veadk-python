import {
  agentDeployErrorKind,
  sandboxCreateErrorKind,
} from "./telemetryClassifiers";
import { trackStudioEvent } from "./telemetry";
import type { SandboxAgentKind } from "./sandbox";

export type DeploymentTelemetrySource =
  | "custom_create"
  | "intelligent_create"
  | "code_package"
  | "unknown";

export interface StudioLoadedTelemetry {
  agentsSource: "local" | "cloud";
}

export type SandboxTelemetryKind = "codex" | SandboxAgentKind;

export interface AgentDeployTelemetryBase {
  source: DeploymentTelemetrySource;
  action: "create" | "update";
  region: string;
  networkType: string;
  feishuEnabled: boolean;
}

export interface AgentDeploySucceededTelemetry extends AgentDeployTelemetryBase {
  runtimeId: string;
}

export interface AgentDeployFailedTelemetry extends AgentDeployTelemetryBase {
  phase: string;
  error: unknown;
}

export interface SandboxCreateTelemetryBase {
  kind: SandboxTelemetryKind;
  source: "my_agents" | "new_chat";
}

export interface SandboxCreateSucceededTelemetry extends SandboxCreateTelemetryBase {
  sessionId: string;
}

export interface SandboxCreateFailedTelemetry extends SandboxCreateTelemetryBase {
  error: unknown;
}

function agentDeployCategories(args: AgentDeployTelemetryBase) {
  return {
    deploy_source: args.source,
    deploy_action: args.action,
    deploy_region: args.region,
    runtime_network_type: args.networkType,
    feishu_enabled: args.feishuEnabled,
  };
}

export function trackStudioLoaded(args: StudioLoadedTelemetry): void {
  trackStudioEvent(
    "studio_instance_loaded",
    {
      agents_source: args.agentsSource,
    },
    undefined,
    { dedupeKey: "studio_instance_loaded" },
  );
}

export function trackAgentDeploySucceeded(
  args: AgentDeploySucceededTelemetry,
): void {
  trackStudioEvent("studio_agent_deploy_succeeded", {
    ...agentDeployCategories(args),
    runtime_id: args.runtimeId,
  });
}

export function trackAgentDeployFailed(args: AgentDeployFailedTelemetry): void {
  trackStudioEvent("studio_agent_deploy_failed", {
    ...agentDeployCategories(args),
    failed_phase: args.phase,
    error_kind: agentDeployErrorKind(args.error, args.phase),
  });
}

export function trackSandboxCreateSucceeded(
  args: SandboxCreateSucceededTelemetry,
): void {
  trackStudioEvent("studio_sandbox_create_succeeded", {
    sandbox_kind: args.kind,
    sandbox_source: args.source,
    sandbox_session_id: args.sessionId,
  });
}

export function trackSandboxCreateFailed(args: SandboxCreateFailedTelemetry): void {
  trackStudioEvent("studio_sandbox_create_failed", {
    sandbox_kind: args.kind,
    sandbox_source: args.source,
    error_kind: sandboxCreateErrorKind(args.error),
  });
}
