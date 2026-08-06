import {
  agentConnectErrorKind,
  agentDebugErrorKind,
  agentDeployErrorKind,
  agentMessageErrorKind,
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

export type AgentDebugVariantType = "baseline" | "comparison";
export type AgentDebugFailedPhase = "create_test_run" | "create_test_session";

export interface AgentDebugTelemetryBase {
  durationMs: number;
  variantType?: AgentDebugVariantType;
}

export interface AgentDebugFailedTelemetry extends AgentDebugTelemetryBase {
  phase?: AgentDebugFailedPhase;
  error: unknown;
}

export type AgentConnectKind =
  | "runtime"
  | "local"
  | SandboxTelemetryKind;

export type AgentConnectSource =
  | "new_chat_picker"
  | "my_agents"
  | "agent_workspace"
  | "navbar_picker"
  | "sandbox_detail";

export interface AgentConnectTelemetryBase {
  kind: AgentConnectKind;
  source: AgentConnectSource;
  durationMs: number;
}

export interface AgentConnectSucceededTelemetry extends AgentConnectTelemetryBase {
  runtimeRegion?: string;
  runtimeIsMine?: boolean;
  sandboxStatus?: string;
}

export interface AgentConnectFailedTelemetry extends AgentConnectTelemetryBase {
  error: unknown;
}

export type AgentMessageKind =
  | "runtime"
  | SandboxTelemetryKind;

export type AgentMessageSource = "composer" | "a2ui_action";
export type AgentMessageSessionState = "new" | "existing";
export type AgentMessageFailedPhase =
  | "create_session"
  | "mount_task_capabilities"
  | "run_sse"
  | "sandbox_send";

export interface AgentMessageTelemetryBase {
  kind: AgentMessageKind;
  source: AgentMessageSource;
  sessionState: AgentMessageSessionState;
  durationMs: number;
}

export interface AgentMessageFailedTelemetry extends AgentMessageTelemetryBase {
  phase: AgentMessageFailedPhase;
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

export function trackAgentDebugSucceeded(args: AgentDebugTelemetryBase): void {
  trackStudioEvent(
    "studio_agent_debug",
    {
      debug_status: "succeeded",
      variant_type: args.variantType,
    },
    {
      duration_ms: args.durationMs,
    },
  );
}

export function trackAgentDebugFailed(args: AgentDebugFailedTelemetry): void {
  trackStudioEvent(
    "studio_agent_debug",
    {
      debug_status: "failed",
      variant_type: args.variantType,
      failed_phase: args.phase,
      error_kind: agentDebugErrorKind(args.error),
      error_summary: telemetryErrorSummary(args.error),
    },
    {
      duration_ms: args.durationMs,
    },
  );
}

export function trackAgentConnectSucceeded(
  args: AgentConnectSucceededTelemetry,
): void {
  trackStudioEvent(
    "studio_agent_connect",
    {
      connect_status: "succeeded",
      agent_kind: args.kind,
      connect_source: args.source,
      runtime_region: args.runtimeRegion,
      runtime_is_mine: args.runtimeIsMine,
      sandbox_status: args.sandboxStatus,
    },
    {
      duration_ms: args.durationMs,
    },
  );
}

export function trackAgentConnectFailed(args: AgentConnectFailedTelemetry): void {
  trackStudioEvent(
    "studio_agent_connect",
    {
      connect_status: "failed",
      agent_kind: args.kind,
      connect_source: args.source,
      error_kind: agentConnectErrorKind(args.error),
      error_summary: telemetryErrorSummary(args.error),
    },
    {
      duration_ms: args.durationMs,
    },
  );
}

export function trackAgentMessageSucceeded(
  args: AgentMessageTelemetryBase,
): void {
  trackStudioEvent(
    "studio_agent_message",
    {
      message_status: "succeeded",
      agent_kind: args.kind,
      message_source: args.source,
      session_state: args.sessionState,
    },
    {
      duration_ms: args.durationMs,
    },
  );
}

export function trackAgentMessageFailed(args: AgentMessageFailedTelemetry): void {
  trackStudioEvent(
    "studio_agent_message",
    {
      message_status: "failed",
      agent_kind: args.kind,
      message_source: args.source,
      session_state: args.sessionState,
      failed_phase: args.phase,
      error_kind: agentMessageErrorKind(args.error),
      error_summary: telemetryErrorSummary(args.error),
    },
    {
      duration_ms: args.durationMs,
    },
  );
}
