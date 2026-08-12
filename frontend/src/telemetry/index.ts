import { TeaClient, type TeaClientConfig } from "./client";
import { TelemetryRuntime } from "./runtime";
export { classifyTelemetryError } from "./privacy";
export type {
  ClassifiedTelemetryError,
  TelemetryErrorContext,
} from "./privacy";
import type {
  AgentConnectFailedProps,
  AgentConnectStartedProps,
  AgentConnectSucceededProps,
  AgentDebugFailedProps,
  AgentDebugStartedProps,
  AgentDebugSucceededProps,
  AgentDeployFailedProps,
  AgentDeployStartedProps,
  AgentDeploySucceededProps,
  AgentMessageFailedProps,
  AgentMessageStartedProps,
  AgentMessageSucceededProps,
  AgentSourceDownloadFailedProps,
  AgentSourceDownloadStartedProps,
  AgentSourceDownloadSucceededProps,
  SandboxCreateFailedProps,
  SandboxCreateStartedProps,
  SandboxCreateSucceededProps,
  SessionStartedProps,
  StudioTelemetryContext,
  TelemetryIdentity,
  TelemetryOperation,
} from "./schema";

const client = new TeaClient();
const runtime = new TelemetryRuntime({ sink: client });

export function initTelemetry(config: TeaClientConfig): Promise<void> {
  return client.init(config);
}

export function setTelemetryContext(context: StudioTelemetryContext): void {
  runtime.setContext(context);
}

export function identifyTelemetryUser(identity: TelemetryIdentity): void {
  runtime.identify(identity);
}

/** Tracks an authenticated, page-ready Studio visit, not an Agent chat session. */
export function trackStudioSessionStarted(props: SessionStartedProps): void {
  runtime.trackStudioSessionStarted(props);
}

export function beginAgentDeploy(
  props: AgentDeployStartedProps,
): TelemetryOperation<AgentDeploySucceededProps, AgentDeployFailedProps> {
  return runtime.beginAgentDeploy(props);
}

export function beginSandboxCreate(
  props: SandboxCreateStartedProps,
): TelemetryOperation<SandboxCreateSucceededProps, SandboxCreateFailedProps> {
  return runtime.beginSandboxCreate(props);
}

export function beginAgentDebug(
  props: AgentDebugStartedProps,
): TelemetryOperation<AgentDebugSucceededProps, AgentDebugFailedProps> {
  return runtime.beginAgentDebug(props);
}

export function beginAgentConnect(
  props: AgentConnectStartedProps,
): TelemetryOperation<AgentConnectSucceededProps, AgentConnectFailedProps> {
  return runtime.beginAgentConnect(props);
}

export function beginAgentMessage(
  props: AgentMessageStartedProps,
): TelemetryOperation<AgentMessageSucceededProps, AgentMessageFailedProps> {
  return runtime.beginAgentMessage(props);
}

export function beginAgentSourceDownload(
  props: AgentSourceDownloadStartedProps,
): TelemetryOperation<
  AgentSourceDownloadSucceededProps,
  AgentSourceDownloadFailedProps
> {
  return runtime.beginAgentSourceDownload(props);
}

export type {
  AgentConnectFailedProps,
  AgentConnectStartedProps,
  AgentConnectSucceededProps,
  AgentDebugFailedProps,
  AgentDebugStartedProps,
  AgentDebugSucceededProps,
  AgentDeployFailedProps,
  AgentDeployStartedProps,
  AgentDeploySucceededProps,
  AgentMessageFailedProps,
  AgentMessageStartedProps,
  AgentMessageSucceededProps,
  AgentSourceDownloadFailedProps,
  AgentSourceDownloadStartedProps,
  AgentSourceDownloadSucceededProps,
  SandboxCreateFailedProps,
  SandboxCreateStartedProps,
  SandboxCreateSucceededProps,
  SessionStartedProps,
  StudioTelemetryContext,
  TelemetryIdentity,
  TelemetryOperation,
} from "./schema";
