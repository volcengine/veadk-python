import { sanitizeTelemetryPayload } from "./privacy";
import {
  TELEMETRY_SCHEMA_VERSION,
  type AgentConnectFailedProps,
  type AgentConnectStartedProps,
  type AgentConnectSucceededProps,
  type AgentDebugFailedProps,
  type AgentDebugStartedProps,
  type AgentDebugSucceededProps,
  type AgentDeployFailedProps,
  type AgentDeployStartedProps,
  type AgentDeploySucceededProps,
  type AgentMessageFailedProps,
  type AgentMessageStartedProps,
  type AgentMessageSucceededProps,
  type AgentSourceDownloadFailedProps,
  type AgentSourceDownloadStartedProps,
  type AgentSourceDownloadSucceededProps,
  type EntryViewedProps,
  type SandboxCreateFailedProps,
  type SandboxCreateStartedProps,
  type SandboxCreateSucceededProps,
  type SessionStartedProps,
  type StudioTelemetryContext,
  type StudioTelemetryEventName,
  type TelemetryIdentity,
  type TelemetryOperation,
  type TelemetryPayload,
} from "./schema";

export interface TelemetrySink {
  emit(name: StudioTelemetryEventName, payload: TelemetryPayload): void;
  identify?(userUniqueId: string): void;
}

export interface TelemetryRuntimeDependencies {
  sink: TelemetrySink;
  createId?: () => string;
  now?: () => number;
}

function defaultCreateId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function defaultNow(): number {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

function compact(input: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(input).filter(([, value]) => value !== undefined),
  );
}

export class TelemetryRuntime {
  private readonly sink: TelemetrySink;
  private readonly createId: () => string;
  private readonly now: () => number;
  private pageInstanceId: string;
  private context: StudioTelemetryContext | undefined;
  private identity: TelemetryIdentity | undefined;
  private entryViewed = false;
  private sessionStarted = false;

  constructor(dependencies: TelemetryRuntimeDependencies) {
    this.sink = dependencies.sink;
    this.createId = dependencies.createId ?? defaultCreateId;
    this.now = dependencies.now ?? defaultNow;
    this.pageInstanceId = this.createId();
  }

  setContext(context: StudioTelemetryContext): void {
    this.context = {
      ...context,
      accountId: context.accountId?.trim() ?? "",
    };
  }

  identify(identity: TelemetryIdentity): void {
    const userUniqueId = identity.userUniqueId.trim();
    if (!userUniqueId) return;
    if (
      this.identity &&
      this.identity.userUniqueId !== userUniqueId
    ) {
      this.pageInstanceId = this.createId();
      this.sessionStarted = false;
    }
    this.identity = {
      ...identity,
      userUniqueId,
      accountId: identity.accountId?.trim() ?? "",
    };
    this.sink.identify?.(userUniqueId);
  }

  /** Records one authenticated, page-ready Studio visit, not an Agent chat session. */
  trackStudioSessionStarted(props: SessionStartedProps): void {
    if (this.sessionStarted || !this.context || !this.identity) return;
    this.sessionStarted = true;
    this.emit("studio_session_started", {
      agents_source: props.agentsSource,
    });
  }

  /** Records one anonymous Studio page entry as soon as the SPA is loaded. */
  trackStudioEntryViewed(props: EntryViewedProps): void {
    if (this.entryViewed || !this.context) return;
    this.entryViewed = true;
    const payload = sanitizeTelemetryPayload("studio_entry_viewed", compact({
      schema_version: TELEMETRY_SCHEMA_VERSION,
      event_id: this.createId(),
      user_pool_id: this.context.userPoolId,
      studio_deploy_id: this.context.studioDeployId,
      vefaas_application_id: this.context.applicationId,
      vefaas_function_id: this.context.functionId,
      studio_region: this.context.studioRegion,
      studio_project: this.context.studioProject,
      studio_version: this.context.studioVersion,
      environment: this.context.environment,
      cloud_provider: this.context.cloudProvider,
      account_id: this.context.accountId,
      page_instance_id: this.pageInstanceId,
      auth_state: props.authState,
    }));
    this.sink.emit("studio_entry_viewed", payload);
  }

  beginAgentDeploy(
    props: AgentDeployStartedProps,
  ): TelemetryOperation<AgentDeploySucceededProps, AgentDeployFailedProps> {
    return this.beginOperation("studio_agent_deploy", {
      agent_id: props.agentId,
      deploy_action: props.deployAction,
      deploy_source: props.deploySource,
      create_mode: props.createMode,
      ai_assisted: props.aiAssisted,
      deploy_region: props.deployRegion,
      runtime_network_type: props.runtimeNetworkType,
      feishu_enabled: props.feishuEnabled,
    }, (result) => ({ runtime_id: result.runtimeId }), (result) => ({
      failed_phase: result.failedPhase,
      error_kind: result.errorKind,
      error_code: result.errorCode,
    }));
  }

  beginSandboxCreate(
    props: SandboxCreateStartedProps,
  ): TelemetryOperation<SandboxCreateSucceededProps, SandboxCreateFailedProps> {
    return this.beginOperation("studio_sandbox_create", {
      sandbox_kind: props.sandboxKind,
      sandbox_source: props.sandboxSource,
    }, (result) => ({ sandbox_id: result.sandboxId }), (result) => ({
      error_kind: result.errorKind,
      error_code: result.errorCode,
    }));
  }

  beginAgentDebug(
    props: AgentDebugStartedProps,
  ): TelemetryOperation<AgentDebugSucceededProps, AgentDebugFailedProps> {
    return this.beginOperation("studio_agent_debug", {
      agent_id: props.agentId,
      variant_type: props.variantType,
    }, (result) => ({ debug_run_id: result.debugRunId }), (result) => ({
      failed_phase: result.failedPhase,
      error_kind: result.errorKind,
      error_code: result.errorCode,
    }));
  }

  beginAgentConnect(
    props: AgentConnectStartedProps,
  ): TelemetryOperation<AgentConnectSucceededProps, AgentConnectFailedProps> {
    return this.beginOperation("studio_agent_connect", {
      target_id: props.targetId,
      agent_kind: props.agentKind,
      connect_source: props.connectSource,
    }, (result) => compact({
      runtime_region: result.runtimeRegion,
      runtime_is_mine: result.runtimeIsMine,
      sandbox_status: result.sandboxStatus,
    }), (result) => compact({
      error_kind: result.errorKind,
      error_code: result.errorCode,
    }));
  }

  beginAgentMessage(
    props: AgentMessageStartedProps,
  ): TelemetryOperation<AgentMessageSucceededProps, AgentMessageFailedProps> {
    return this.beginOperation("studio_agent_message", compact({
      agent_id: props.agentId,
      agent_kind: props.agentKind,
      message_source: props.messageSource,
      session_state: props.sessionState,
      session_id: props.sessionId,
    }), (result) => ({ session_id: result.sessionId }), (result) => compact({
      session_id: result.sessionId,
      failed_phase: result.failedPhase,
      error_kind: result.errorKind,
      error_code: result.errorCode,
    }));
  }

  beginAgentSourceDownload(
    props: AgentSourceDownloadStartedProps,
  ): TelemetryOperation<
    AgentSourceDownloadSucceededProps,
    AgentSourceDownloadFailedProps
  > {
    return this.beginOperation("studio_agent_source_download", {
      agent_id: props.agentId,
      deploy_action: props.deployAction,
      deploy_source: props.deploySource,
      create_mode: props.createMode,
      ai_assisted: props.aiAssisted,
    }, (result) => ({
      file_count: result.fileCount,
      zip_size_bytes: result.zipSizeBytes,
    }), (result) => ({
      file_count: result.fileCount,
      error_kind: result.errorKind,
      error_code: result.errorCode,
    }));
  }

  private beginOperation<Succeeded, Failed>(
    name: Exclude<
      StudioTelemetryEventName,
      "studio_entry_viewed" | "studio_session_started"
    >,
    startedProps: Record<string, unknown>,
    successProps: (props: Succeeded) => Record<string, unknown>,
    failureProps: (props: Failed) => Record<string, unknown>,
  ): TelemetryOperation<Succeeded, Failed> {
    const operationId = this.createId();
    const startedAt = this.now();
    const active = Boolean(this.context && this.identity);
    let finished = false;
    if (active) {
      this.emit(name, { ...startedProps, status: "started" }, operationId);
    }

    const finish = (
      status: "succeeded" | "failed",
      props: Record<string, unknown>,
    ): void => {
      if (finished) return;
      finished = true;
      if (!active) return;
      this.emit(name, {
        ...startedProps,
        ...props,
        status,
        duration_ms: Math.max(0, this.now() - startedAt),
      }, operationId);
    };

    return {
      operationId,
      succeed: (props) => finish("succeeded", successProps(props)),
      fail: (props) => finish("failed", failureProps(props)),
    };
  }

  private emit(
    name: StudioTelemetryEventName,
    eventProps: Record<string, unknown>,
    operationId?: string,
  ): void {
    if (!this.context || !this.identity) return;
    const payload = sanitizeTelemetryPayload(name, compact({
      schema_version: TELEMETRY_SCHEMA_VERSION,
      event_id: this.createId(),
      operation_id: operationId,
      user_pool_id: this.context.userPoolId,
      studio_deploy_id: this.context.studioDeployId,
      vefaas_application_id: this.context.applicationId,
      vefaas_function_id: this.context.functionId,
      studio_region: this.context.studioRegion,
      studio_project: this.context.studioProject,
      studio_version: this.context.studioVersion,
      environment: this.context.environment,
      cloud_provider: this.context.cloudProvider,
      account_id: this.identity.accountId,
      user_role: this.identity.userRole,
      user_source: this.identity.userSource,
      page_instance_id: this.pageInstanceId,
      ...eventProps,
    }));
    this.sink.emit(name, payload);
  }
}
