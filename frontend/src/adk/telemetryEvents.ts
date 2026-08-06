import {
  agentDeployErrorKind,
  sandboxCreateErrorKind,
  telemetryErrorSummary,
} from "./telemetryClassifiers";
import { trackStudioEvent } from "./telemetry";
import type { SandboxAgentKind } from "./sandbox";

export type DeploymentTelemetrySource =
  | "scratch"
  | "code_package"
  | "feishu_automation"
  | "unknown";

export type DeploymentCreateMode =
  | "custom"
  | "intelligent"
  | "template"
  | "workflow"
  | "yaml_import"
  | "code_package"
  | "feishu_template"
  | "unknown";

export interface DeploymentTelemetryOrigin {
  source: DeploymentTelemetrySource;
  createMode: DeploymentCreateMode;
  aiAssisted: boolean;
}

export interface StudioLoadedTelemetry {
  agentsSource: "local" | "cloud";
}

export type SandboxTelemetryKind = "codex" | SandboxAgentKind;

export interface AgentDeployTelemetryBase {
  telemetry: DeploymentTelemetryOrigin;
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
    deploy_source: args.telemetry.source,
    create_mode: args.telemetry.createMode,
    ai_assisted: args.telemetry.aiAssisted,
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
  trackStudioEvent("studio_agent_deploy", {
    ...agentDeployCategories(args),
    deploy_status: "succeeded",
    runtime_id: args.runtimeId,
  });
}

export function trackAgentDeployFailed(args: AgentDeployFailedTelemetry): void {
  trackStudioEvent("studio_agent_deploy", {
    ...agentDeployCategories(args),
    deploy_status: "failed",
    failed_phase: args.phase,
    error_kind: agentDeployErrorKind(args.error, args.phase),
    error_summary: telemetryErrorSummary(args.error),
  });
}

export function trackSandboxCreateSucceeded(
  args: SandboxCreateSucceededTelemetry,
): void {
  trackStudioEvent("studio_sandbox_create", {
    sandbox_status: "succeeded",
    sandbox_kind: args.kind,
    sandbox_source: args.source,
    sandbox_session_id: args.sessionId,
  });
}

export function trackSandboxCreateFailed(args: SandboxCreateFailedTelemetry): void {
  trackStudioEvent("studio_sandbox_create", {
    sandbox_status: "failed",
    sandbox_kind: args.kind,
    sandbox_source: args.source,
    error_kind: sandboxCreateErrorKind(args.error),
    error_summary: telemetryErrorSummary(args.error),
  });
}
