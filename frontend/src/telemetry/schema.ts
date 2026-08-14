export const TEA_APP_ID = 1050062 as const;
export const TELEMETRY_SCHEMA_VERSION = "1.0" as const;

export type TelemetryValue = string | number;
export type TelemetryPayload = Record<string, TelemetryValue>;

export type StudioTelemetryEventName =
  | "studio_session_started"
  | "studio_agent_deploy"
  | "studio_sandbox_create"
  | "studio_agent_debug"
  | "studio_agent_connect"
  | "studio_agent_message"
  | "studio_agent_source_download";

export type TelemetryEnvironment = "prod" | "staging" | "dev";
export type UserRole = "admin" | "member" | "unknown";
export type UserSource = "sso" | "local" | "unknown";

export interface StudioTelemetryContext {
  userPoolId: string;
  studioDeployId: string;
  applicationId: string;
  functionId: string;
  studioRegion: string;
  studioProject: string;
  studioVersion: string;
  environment: TelemetryEnvironment;
  cloudProvider: "volcengine" | "byteplus";
}

export interface TelemetryIdentity {
  userUniqueId: string;
  accountId?: string;
  userRole: UserRole;
  userSource: UserSource;
}

export type OperationStatus = "started" | "succeeded" | "failed";
export type BinaryFlag = 0 | 1;
export type ErrorKind =
  | "abort"
  | "timeout"
  | "network"
  | "auth"
  | "validation"
  | "server"
  | "build_failed"
  | "runtime_probe_error"
  | "unknown";

export interface SessionStartedProps {
  agentsSource: "local" | "cloud";
}

export type DeploySource =
  | "scratch"
  | "code_package"
  | "feishu_automation"
  | "unknown";
export type CreateMode =
  | "custom"
  | "intelligent"
  | "template"
  | "workflow"
  | "yaml_import"
  | "code_package"
  | "feishu_template"
  | "unknown";

export interface AgentDeployStartedProps {
  agentId: string;
  deployAction: "create" | "update";
  deploySource: DeploySource;
  createMode: CreateMode;
  aiAssisted: BinaryFlag;
  deployRegion: string;
  runtimeNetworkType: "public" | "private" | "both" | "unknown";
  feishuEnabled: BinaryFlag;
}

export interface AgentDeploySucceededProps {
  runtimeId: string;
}

export interface AgentDeployFailedProps {
  failedPhase:
    | "prepare"
    | "upload"
    | "build"
    | "deploy"
    | "publish"
    | "update"
    | "evaluation"
    | "unknown";
  errorKind: ErrorKind;
  errorCode?: string;
}

export type SandboxKind = "codex" | "openclaw" | "hermes";

export interface SandboxCreateStartedProps {
  sandboxKind: SandboxKind;
  sandboxSource: "my_agents" | "new_chat";
}

export interface SandboxCreateSucceededProps {
  sandboxId: string;
}

export interface SandboxCreateFailedProps {
  errorKind: ErrorKind;
  errorCode?: string;
}

export interface AgentDebugStartedProps {
  agentId: string;
  variantType: "baseline" | "comparison" | "unknown";
}

export interface AgentDebugSucceededProps {
  debugRunId: string;
}

export interface AgentDebugFailedProps {
  failedPhase: "create_test_run" | "create_test_session" | "unknown";
  errorKind: ErrorKind;
  errorCode?: string;
}

export type AgentConnectKind =
  | "runtime"
  | "local"
  | "codex"
  | "openclaw"
  | "hermes";
export type AgentConnectSource =
  | "new_chat_picker"
  | "my_agents"
  | "agent_workspace"
  | "navbar_picker"
  | "sandbox_detail";

export interface AgentConnectStartedProps {
  targetId: string;
  agentKind: AgentConnectKind;
  connectSource: AgentConnectSource;
}

export interface AgentConnectSucceededProps {
  runtimeRegion?: string;
  runtimeIsMine?: BinaryFlag;
  sandboxStatus?:
    | "creating"
    | "starting"
    | "initializing"
    | "pending"
    | "running"
    | "ready"
    | "failed"
    | "error"
    | "stopped"
    | "expired"
    | "deleting"
    | "deleted"
    | "unknown";
}

export interface AgentConnectFailedProps {
  errorKind: ErrorKind;
  errorCode?: string;
}

export interface AgentMessageStartedProps {
  agentId: string;
  agentKind: "runtime" | "codex" | "openclaw" | "hermes";
  messageSource: "composer" | "a2ui_action";
  sessionState: "new" | "existing";
  sessionId?: string;
}

export interface AgentMessageSucceededProps {
  sessionId: string;
}

export interface AgentMessageFailedProps {
  sessionId?: string;
  failedPhase:
    | "create_session"
    | "mount_task_capabilities"
    | "run_sse"
    | "sandbox_send"
    | "unknown";
  errorKind: ErrorKind;
  errorCode?: string;
}

export interface AgentSourceDownloadStartedProps {
  agentId: string;
  deployAction: "create" | "update";
  deploySource: DeploySource;
  createMode: CreateMode;
  aiAssisted: BinaryFlag;
}

export interface AgentSourceDownloadSucceededProps {
  fileCount: number;
  zipSizeBytes: number;
}

export interface AgentSourceDownloadFailedProps {
  fileCount: number;
  errorKind: ErrorKind;
  errorCode?: string;
}

export interface TelemetryOperation<Succeeded, Failed> {
  readonly operationId: string;
  succeed(props: Succeeded): void;
  fail(props: Failed): void;
}
