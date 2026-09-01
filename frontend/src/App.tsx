import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type MouseEventHandler,
  type WheelEvent,
} from "react";
import { Share } from "@openai/apps-sdk-ui/components/Icon";
import {
  ArrowLeft,
  Check,
  Copy,
  CornerDownRight,
  Loader2,
} from "lucide-react";
import { motion } from "motion/react";
import {
  clearMessageFeedbackCache,
  createSession,
  DEFAULT_STUDIO_ACCESS,
  DEFAULT_SITE_BRANDING,
  deleteRuntime,
  deleteMedia,
  deleteSessionMedia,
  deleteSession,
  downloadArtifact,
  previewArtifact,
  getAgentInfo,
  getAutomaticEvaluationStatuses,
  getSessionTrace,
  getSession,
  getStudioAccess,
  getRuntimeStudioToolCapabilities,
  getRuntimes,
  listApps,
  listEnvironments,
  listWorkspaces,
  listModelOptions,
  listSessions,
  RUN_SSE_INCOMPLETE_RESPONSE_ERROR,
  runSSE,
  refreshAgentFeedbackCases,
  submitIssueFeedback,
  submitMessageFeedback,
  upsertCachedAgentFeedbackCase,
  uploadMedia,
  getUiConfig,
  type AdkEvent,
  type AgentInfo,
  type AutomaticEvaluationStatusesResponse,
  type AgentNode,
  type AgentTarget,
  type AgentFeedbackCase,
  type AdkSession,
  type Attachment,
  type FrontendInvocation,
  type CloudRuntime,
  type MessageFeedbackRating,
  type SiteBranding,
  type RuntimeStudioToolCapabilities,
  type SessionEnvironmentMountSelection,
  type StudioAccess,
  type StudioEnvironment,
  type StudioWorkspace,
  type UiConfig,
  type UiFeatures,
} from "./adk/client";
import type { RuntimeLogTarget } from "./adk/runtimeLogs";
import {
  addTokenUsage,
  aggregateTokenUsage,
  EMPTY_SESSION_TOKEN_USAGE,
  estimateSystemContextTokens,
  type SessionTokenUsage,
} from "./adk/tokenUsage";
import {
  issueFeedbackToolCalls,
  traceForInvocation,
  type IssueFeedbackIssue,
  type IssueFeedbackModule,
} from "./adk/issueFeedback";
import {
  applyEvent,
  emptyAcc,
  eventsToTurns,
  sessionTitle,
  type Block,
  type IntelligentDevelopmentReleaseRef,
  type Turn,
  type TurnActivityDetail,
} from "./blocks";
import { Sidebar, type SidebarPage } from "./ui/Sidebar";
import { AgentInfoPanel } from "./ui/AgentTopology";
import type { SkillCenterWorkspaceLaunch } from "./ui/SkillCenter";
import { LibraryView, type LibraryTab } from "./ui/LibraryView";
import { AddAgentKitView } from "./ui/AddAgentKit";
import { AgentWorkspace } from "./ui/AgentWorkspace";
import {
  MyAgents,
  invalidateRuntimeAgentCache,
  type AgentType,
  type MyAgentCardData,
} from "./ui/MyAgents";
import { EnvironmentCenter } from "./ui/EnvironmentCenter";
import { WorkspaceCenter } from "./ui/WorkspaceCenter";
import { Applications, type ApplicationId } from "./ui/Applications";
import { CronJobs } from "./cronjobs/CronJobs";
import { getAutomation } from "./automations/registry";
import { SystemInfo } from "./ui/SystemInfo";
import { GitHubIntegration } from "./ui/GitHubIntegration";
import { FeishuBotIntegration } from "./automations/feishu/FeishuBotIntegration";
import { CodingAgentsIntegration } from "./automations/coding-agents/CodingAgentsIntegration";
import { WebsiteIntegration } from "./automations/website-integration/WebsiteIntegration";
import { SearchView } from "./ui/Search";
import {
  formatStudioDocumentTitle,
  type StudioDocumentTitleTarget,
} from "./ui/documentTitle";
import {
  buildAgentEntries,
  connectRuntime,
  loadConnections,
  registerConnections,
  removeRuntimeConnection,
  remoteAppId,
  type AgentEntry,
  type RemoteConnection,
} from "./adk/connections";
import { defaultCloudRegion, formatCloudRegion } from "./adk/cloudProvider";
import { Blocks, ThinkingPlaceholder } from "./ui/Blocks";
import { Composer } from "./ui/Composer";
import { InvocationChips } from "./ui/InvocationChips";
import { MediaGroup } from "./ui/Media";
import { StackCards } from "./ui/AddAgentMenu";
import {
  IntelligentCreate,
  type IntelligentCreateBaseVersion,
  type IntelligentDevelopmentCapabilities,
  type IntelligentPreparationStage,
} from "./create/IntelligentCreate";
import { IntelligentDeployment } from "./create/IntelligentDeployment";
import { CustomCreate } from "./create/CustomCreate";
import { AgentCreationModePicker } from "./create/AgentCreationModePicker";
import { CodePackageCreate } from "./create/CodePackageCreate";
import { MigrationWorkspace } from "./migrations/MigrationWorkspace";
import type { AgentDraft } from "./create/types";
import { configuredMcpEnvKeys } from "./create/mcpAuth";
import {
  hydrateRuntimeModelSelection,
  isRuntimeModelSelectionEnv,
} from "./create/modelSource";
import {
  classifyRuntimeModelSources,
  hydrateA2aRegistryFromRuntime,
  modelConfigurationFromRuntime,
  modelNameFromRuntime,
  runtimeAgentDraftFromCloud,
} from "./create/runtimeModelName";
import {
  loadWorkspaceDrafts,
  workspaceAgentCreationMode,
  workspaceDraftsKey,
  writeWorkspaceDrafts,
  type WorkspaceAgentDraft,
} from "./create/agentDraftStorage";
import type { DeployResult, DeploymentTaskUpdate } from "./ui/ProjectPreview";
import type {
  NewChatMode,
  NewChatSkillAction,
  NewChatSkillTarget,
  NewChatTask,
  NewChatWorkspaceMode,
} from "./ui/new-chat-modes/types";
import { NewChatFeatureNotice } from "./ui/new-chat-modes/NewChatFeatureNotice";
import {
  NEW_CHAT_TASK_OPTIONAL_TOOLS,
  NEW_CHAT_TASK_TOOLS,
} from "./ui/new-chat-modes/taskTools";
import {
  intelligentDevelopmentErrorMessage,
  intelligentDevelopmentClient,
  sandboxClient,
  SandboxServiceError,
  type SandboxApproval,
  type SandboxApprovalDecision,
  type SandboxAgentResource,
  type SandboxAgentKind,
  type SandboxAgentWorkspace as SandboxAgentWorkspaceData,
  type SandboxPermissions,
  type SandboxSession as SandboxSessionInfo,
  type SandboxSkill,
  type SandboxThreadSnapshot,
  type SandboxThreadSummary,
  type SandboxToolLaunch,
} from "./adk/sandbox";
import {
  downloadIntelligentDevelopmentRelease,
  fetchIntelligentDevelopmentRelease,
  fetchIntelligentDevelopmentProjectRelease,
  fetchIntelligentDevelopmentVersions,
  fetchIntelligentDevelopmentVersionSource,
} from "./adk/intelligentDevelopment";
import {
  getSandboxAgentCapability,
  getSandboxCapability,
} from "./adk/newChatCapabilities";
import { getSkillWorkbenchCapability } from "./ui/skill-workbench/api";
import {
  createVideoTask,
  downloadVideoTask,
  enhanceVideoPrompt,
  getVideoTask,
  uploadVideoAsset,
  videoResultPreviewUrl,
  type VideoAssetKind,
  type VideoCapabilities,
} from "./adk/video";
import type { NewChatVideoConfig } from "./ui/new-chat-modes/video-types";
import {
  createVideoGenerationTask,
  isVideoTaskRunning,
  updateVideoGenerationTask,
  type VideoGenerationTask,
  type VideoTaskErrorStage,
  type VideoTaskEvent,
} from "./ui/new-chat-modes/video-task";
import { NewChatVideoTaskDialog } from "./ui/new-chat-modes/NewChatVideoTaskDialog";
import { AgentKitCliDialog } from "./ui/AgentKitCliDialog";
import {
  SandboxLaunchDialog,
  type SandboxLaunchState,
} from "./ui/SandboxLaunchDialog";
import {
  SandboxActivityRecord,
  SandboxSessionWarning,
  SandboxTokenUsageRow,
} from "./ui/SandboxSession";
import {
  SandboxApprovalDialog,
  SandboxPermissionsDialog,
  SandboxThreadsDialog,
  SandboxToolDialog,
  SandboxWorkspaceDialog,
} from "./ui/SandboxControls";
import { SandboxAgentDetails } from "./ui/SandboxAgentDetails";
import { SandboxAgentWorkspace } from "./ui/SandboxAgentWorkspace";
import { SandboxComposer } from "./ui/SandboxComposer";
import { SandboxProjectUploadDialog } from "./ui/SandboxProjectUploadDialog";
import { sandboxSnapshotTurns } from "./ui/sandboxCommands";
import { useSandboxCodexCommands } from "./ui/useSandboxCodexCommands";
import { StudioConfirmDialog } from "./ui/StudioConfirmDialog";
import byteplusLogo from "./assets/byteplus.svg";
import defaultSiteLogo from "./assets/logo.svg";
import {
  FeedbackDownIcon,
  FeedbackUpIcon,
  IssueFeedbackIcon,
} from "./ui/icons/FeedbackIcons";

interface IssueFeedbackTarget {
  turn: Turn;
  input: string;
}

interface ShareMessageTarget {
  targetTurn: HTMLElement;
}

interface ResponseAnnotationTarget {
  selectionId: number;
  turn: Turn;
  input: string;
  selectedText: string;
  anchor: ResponseAnnotationAnchor;
}

interface ResponseAnnotationContext {
  enabled: boolean;
  turn: Turn;
  input: string;
}

function issueFeedbackModuleForPage(page: string): IssueFeedbackModule {
  if (page === "agents") return "agents";
  if (page === "applications") return "applications";
  if (page === "search") return "search";
  if (["conversation", "new-chat", "sandbox"].includes(page)) {
    return "conversation";
  }
  return "other";
}

interface NewChatCapabilitiesState {
  agentId?: string;
  ready?: boolean;
  temporaryEnabled?: boolean;
  deepseekHarnessEnabled?: boolean;
  sandboxEndpointExportEnabled?: boolean;
  skillCustomizationEnabled?: boolean;
}

interface PreparedAgentSelection {
  agentId: string;
  userId: string;
  automaticEvaluationStatuses?: AutomaticEvaluationStatusesResponse;
}

async function probeNewChatCapabilities(
  agentId: string,
): Promise<NewChatCapabilitiesState> {
  const [
    sandboxResult,
    deepseekHarnessResult,
    skillResult,
  ] = await Promise.allSettled([
    getSandboxCapability(),
    getSandboxAgentCapability("deepseek-harness"),
    getSkillWorkbenchCapability(),
  ]);
  return {
    agentId,
    ready: true,
    temporaryEnabled:
      sandboxResult.status === "fulfilled" && sandboxResult.value.enabled,
    deepseekHarnessEnabled:
      deepseekHarnessResult.status === "fulfilled" &&
      deepseekHarnessResult.value.enabled,
    sandboxEndpointExportEnabled:
      sandboxResult.status === "fulfilled" &&
      sandboxResult.value.endpointExportEnabled === true,
    skillCustomizationEnabled:
      skillResult.status === "fulfilled" && skillResult.value.enabled,
  };
}

async function loadHydratedSessions(
  appName: string,
  userId: string,
): Promise<AdkSession[]> {
  const list = await listSessions(appName, userId);
  const results = await Promise.allSettled(
    list.map((session) =>
      session.events?.length
        ? Promise.resolve(session)
        : getSession(appName, userId, session.id),
    ),
  );
  const failed = results.find(
    (result) =>
      result.status === "rejected" &&
      !/get session failed:\s*404\b/i.test(String(result.reason)),
  );
  if (failed?.status === "rejected") throw failed.reason;
  return results.flatMap((result) =>
    result.status === "fulfilled" ? [result.value] : [],
  );
}

type CreateView = "custom" | "package" | "migration" | null;
type AppView = CreateView | "intelligent";
type CustomCreateMode = "custom" | "yaml_import";
type StudioPageId =
  | "new-chat"
  | "conversation"
  | "sandbox"
  | "create"
  | "library"
  | "search"
  | "applications"
  | "cronjobs"
  | "agents"
  | "workspaces"
  | "environments"
  | "agent-detail"
  | "sandbox-agent-detail"
  | "sandbox-agent-workspace"
  | "feedback";
type StudioStackPage = "system-info" | "agent-detail" | "sandbox-agent-detail";

interface StudioPageStackEntry {
  page: StudioStackPage;
  returnTo: StudioPageId;
}

// Persist the last view so a page refresh restores where the user was.
const LS = { app: "veadk.appName", view: "veadk.view", session: "veadk.sessionId" } as const;
const DRAFT_AUTOSAVE_DELAY_MS = 600;
const AUTO_EVALUATION_RUNNING_POLL_MS = 1_000;
const AUTO_EVALUATION_RETRY_POLL_MS = 5_000;
const AUTO_EVALUATION_MIN_PENDING_POLL_MS = 500;
const EMPTY_STRING_SET: Set<string> = new Set<string>();
const EMPTY_STRING_ARR: string[] = [];
const ENVIRONMENT_STUDIO_TOOL_IDS = [
  "list_envs",
  "get_env_manifest",
  "execute_in_sandbox",
] as const;

function emptyInvocation(): FrontendInvocation {
  return { skills: [] };
}

function studioToolSelectionKey(
  appName: string,
  userId: string,
  sessionId: string,
): string {
  return `${appName}\u0000${userId}\u0000${sessionId}`;
}

async function loadSandboxThreadHistory(
  session: SandboxSessionInfo,
): Promise<SandboxThreadSnapshot | null> {
  let readError: unknown;
  if (session.threadId) {
    try {
      const snapshot = await sandboxClient.readThread(session.id, session.threadId);
      if (snapshot.messages.length > 0) return snapshot;
    } catch (cause) {
      readError = cause;
    }
  }

  const page = await sandboxClient.listThreads(session.id);
  const latest = page.threads.find((thread) => thread.id !== session.threadId) ??
    page.threads[0];
  if (!latest) {
    if (readError) throw readError;
    return null;
  }
  return sandboxClient.resumeThread(session.id, latest.id);
}

function sandboxSnapshotTurnsForStatus(
  snapshot: SandboxThreadSnapshot,
  busy: boolean,
): Turn[] {
  const snapshotTurns = sandboxSnapshotTurns(snapshot);
  const lastTurn = snapshotTurns[snapshotTurns.length - 1];
  if (!busy || lastTurn?.role !== "user") return snapshotTurns;
  return [
    ...snapshotTurns,
    {
      role: "assistant",
      blocks: [],
      meta: { localId: `sandbox-background-${snapshot.threadId}` },
    },
  ];
}

function activeWorkspaceDraftKey(userId: string): string {
  return `${workspaceDraftsKey(userId)}.active`;
}

function workspaceAgentOrderKey(userId: string): string {
  return `veadk.agentOrder.${encodeURIComponent(userId)}`;
}

function loadWorkspaceAgentOrder(userId: string): string[] {
  if (!userId) return [];
  try {
    const value = JSON.parse(localStorage.getItem(workspaceAgentOrderKey(userId)) || "[]");
    return Array.isArray(value)
      ? value.filter((item): item is string => typeof item === "string")
      : [];
  } catch {
    return [];
  }
}

function findAgentNode(node: AgentNode, name: string): AgentNode | undefined {
  if (node.name === name || node.id === name) return node;
  for (const child of node.children) {
    const found = findAgentNode(child, name);
    if (found) return found;
  }
  return undefined;
}

function displayAgentName(name: string): string {
  return name.replace(/__[0-9a-f]{10}(?:__.*)?$/i, "");
}

function mentionableDescendants(node: AgentNode): AgentTarget[] {
  const targets: AgentTarget[] = [];
  for (const child of node.children) {
    if (!child.mentionable) continue;
    targets.push({
      name: child.name,
      description: child.description,
      type: child.type,
      path: child.path,
    });
    targets.push(...mentionableDescendants(child));
  }
  return targets;
}

function loadView(): AppView {
  const v = typeof localStorage !== "undefined" ? localStorage.getItem(LS.view) : null;
  if (v === "intelligent") return v;
  if (["menu", "custom", "template", "workflow"].includes(v ?? "")) {
    return "custom";
  }
  return v === "package" || v === "migration" ? v : null;
}
import { TraceDrawer } from "./ui/TraceDrawer";
import { LoginPage } from "./ui/LoginPage";
import { AuthExpiredDialog } from "./ui/AuthExpiredDialog";
import { IssueFeedbackDialog } from "./ui/IssueFeedbackDialog";
import { ShareMessageDialog } from "./ui/ShareMessageDialog";
import { ResponseAnnotationPopover } from "./ui/ResponseAnnotationPopover";
import {
  formatResponseAnnotationComment,
  responseSelectionWithin,
  type ResponseAnnotationAnchor,
} from "./ui/responseAnnotation";
import { PlatformFeedback } from "./ui/PlatformFeedback";
import { Markdown } from "./ui/Markdown";
import { withAuth } from "./adk/auth";
import { withLocalUser } from "./adk/identity";
import {
  clearLocalUser,
  logout,
  openLoginWindow,
  resolveIdentity,
  setLocalUser,
  type AuthStatus,
} from "./adk/identity";
import {
  AUTHENTICATION_REQUIRED_EVENT,
  authenticationRestored,
  isAuthenticationPending,
} from "./adk/authSession";
import {
  beginAgentConnect,
  beginAgentMessage,
  beginAgentSourceDownload,
  beginSandboxCreate,
  classifyTelemetryError,
  identifyTelemetryUser,
  initTelemetry,
  setTelemetryContext,
  trackStudioEntryViewed,
  trackStudioSessionStarted,
  type AgentConnectStartedProps,
  type AgentConnectSucceededProps,
  type AgentMessageStartedProps,
} from "./telemetry";
import type { A2uiAction, A2uiComponent } from "./a2ui/types";
import { buildSurfaces } from "./a2ui/Surface";

type AgentConnectSource = AgentConnectStartedProps["connectSource"];
type AgentMessageSource = AgentMessageStartedProps["messageSource"];

function telemetrySandboxStatus(
  status: string,
): AgentConnectSucceededProps["sandboxStatus"] {
  const normalized = status.trim().toLowerCase();
  switch (normalized) {
    case "creating":
    case "starting":
    case "initializing":
    case "pending":
    case "running":
    case "ready":
    case "failed":
    case "error":
    case "stopped":
    case "expired":
    case "deleting":
    case "deleted":
      return normalized;
    default:
      return "unknown";
  }
}

/** Hand-drawn "from zero" mark: a blank Agent canvas ready to create. */
function ScratchIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.45"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="3.75" y="3.75" width="16.5" height="16.5" rx="3.25" />
      <path d="M12 8.5v7M8.5 12h7" />
      <path d="M6.75 6.75h1M16.25 17.25h1" opacity="0.6" />
    </svg>
  );
}

/** Hand-drawn code package mark: an archive with source inside. */
function PackageIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.45"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="3.5" y="5" width="17" height="14.75" rx="2.25" />
      <path d="M3.5 9h17M9.25 12.25 7.1 14.4l2.15 2.15M14.75 12.25l2.15 2.15-2.15 2.15M12.8 11.85l-1.6 5.1" />
    </svg>
  );
}

/** Hand-drawn migration mark: an existing project moving into a new runtime. */
function MigrationIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.45"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="2.75" y="5" width="6.5" height="14" rx="1.6" />
      <path d="M5.25 8.5h1.5M5.25 11.5h1.5" />
      <rect x="14.75" y="5" width="6.5" height="14" rx="1.6" />
      <path d="M17.25 15.5h1.5M17.25 12.5h1.5M8.75 12h6.5m-2.5-2.5 2.5 2.5-2.5 2.5" />
    </svg>
  );
}

/** Hand-drawn "tracing / observability" icon (stacked spans). */
function TraceIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
      <rect x="3" y="4" width="14" height="3.2" rx="1.2" fill="currentColor" stroke="none" />
      <rect x="6" y="10.4" width="13" height="3.2" rx="1.2" fill="currentColor" stroke="none" opacity="0.7" />
      <rect x="9" y="16.8" width="9" height="3.2" rx="1.2" fill="currentColor" stroke="none" opacity="0.45" />
    </svg>
  );
}

/** Format an epoch-seconds timestamp as Beijing (Asia/Shanghai) time. */
function fmtTime(ts?: number): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString("zh-CN", {
    timeZone: "Asia/Shanghai",
    hour12: false,
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function fmtMeta(meta?: { tokens?: number; ts?: number }): string {
  if (!meta) return "";
  const parts: string[] = [];
  if (meta.ts) parts.push(fmtTime(meta.ts));
  if (meta.tokens != null) parts.push(`${meta.tokens.toLocaleString()} tokens`);
  return parts.join(" · ");
}

/** Plain-text content of a turn (answer text only), for copying. */
function turnText(turn: Turn): string {
  return turn.blocks
    .map((b) => (b.kind === "text" ? b.text : ""))
    .join("")
    .trim();
}

function previousUserTurnText(turns: Turn[], turnIndex: number): string {
  for (let index = turnIndex - 1; index >= 0; index -= 1) {
    if (turns[index].role === "user") return turnText(turns[index]);
  }
  return "";
}

const A2UI_TOOL_NAME = "send_a2ui_json_to_client";

/** Whether a finalized assistant turn has anything visible to render — non-empty
 *  text, media, a renderable A2UI surface, or a non-A2UI tool. Thinking, the hidden
 *  (done) A2UI tool, and empty A2UI surfaces don't count, so a reply that was
 *  ONLY thinking + an empty surface returns false (→ we show a fallback). */
function turnHasVisibleContent(turn: Turn): boolean {
  return turn.blocks.some((b) => {
    if (b.kind === "text") return b.text.trim().length > 0;
    if (b.kind === "attachment") return b.files.length > 0;
    if (b.kind === "artifact") return b.files.length > 0;
    if (b.kind === "delivery") return true;
    if (b.kind === "tool") return !(b.name === A2UI_TOOL_NAME && b.done);
    if (b.kind === "agent-transfer") return false;
    if (b.kind === "a2ui") return buildSurfaces(b.messages).some((s) => s.components[s.rootId]);
    if (b.kind === "auth") return true; // the OAuth card counts as content
    return false; // thinking is not an answer
  });
}

/** True while a turn is paused on an unresolved OAuth card — like streaming, we
 *  hide the actions/timestamp row until authorization completes. */
function turnAwaitingAuth(turn: Turn): boolean {
  return turn.blocks.some((b) => b.kind === "auth" && !b.done);
}

/** Open the OAuth authorize URL in a popup and resolve with the full callback
 *  URL. Auto-captures when the provider redirects back to our origin (poll +
 *  postMessage); if the popup closes without capture (cross-origin redirect),
 *  falls back to asking the user to paste the callback URL. */
function runOAuthPopup(authUri: string): Promise<string> {
  return new Promise((resolve, reject) => {
    let protocol = "";
    try {
      protocol = new URL(authUri, window.location.href).protocol;
    } catch {
      // Invalid URLs are rejected with unsupported schemes below.
    }
    if (protocol !== "http:" && protocol !== "https:") {
      reject(new Error("授权链接不是 http/https 地址，已阻止打开。"));
      return;
    }
    const popup = window.open(authUri, "veadk_oauth", "width=520,height=720");
    if (!popup) {
      reject(new Error("弹窗被拦截，请允许弹窗后重试。"));
      return;
    }
    let done = false;
    const cleanup = () => {
      clearInterval(timer);
      window.removeEventListener("message", onMsg);
    };
    const finish = (url: string) => {
      if (done) return;
      done = true;
      cleanup();
      try {
        popup.close();
      } catch {
        /* ignore */
      }
      resolve(url);
    };
    const onMsg = (e: MessageEvent) => {
      if (e.origin !== window.location.origin) return;
      const d = e.data as { veadkOAuth?: boolean; url?: string } | null;
      if (d && d.veadkOAuth && typeof d.url === "string") finish(d.url);
    };
    window.addEventListener("message", onMsg);
    const timer = setInterval(() => {
      if (done) return;
      if (popup.closed) {
        cleanup();
        const pasted = window.prompt(
          "授权完成后，请粘贴回调页面（浏览器地址栏）的完整 URL：",
        );
        if (pasted && pasted.trim()) {
          done = true;
          resolve(pasted.trim());
        } else {
          reject(new Error("授权已取消。"));
        }
        return;
      }
      try {
        const href = popup.location.href; // throws while cross-origin
        if (
          href &&
          href !== "about:blank" &&
          new URL(href).origin === window.location.origin &&
          /[?&](code|state|error)=/.test(href)
        ) {
          finish(href);
        }
      } catch {
        /* still on the provider's origin — keep polling */
      }
    }, 500);
  });
}

/** Clone an ADK AuthConfig and set the OAuth2 callback URL, so ADK can exchange
 *  the code for a token when we send it back as the credential response. */
function withAuthResponseUri(authConfig: unknown, callbackUrl: string): unknown {
  const cfg = JSON.parse(JSON.stringify(authConfig ?? {})) as Record<string, any>;
  const cred = cfg.exchangedAuthCredential ?? cfg.exchanged_auth_credential ?? {};
  const o = cred.oauth2 ?? {};
  o.authResponseUri = callbackUrl;
  o.auth_response_uri = callbackUrl;
  cred.oauth2 = o;
  cfg.exchangedAuthCredential = cred;
  return cfg;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className="icon-btn"
      title={copied ? "已复制" : "复制"}
      disabled={!text}
      onClick={async () => {
        if (!text) return;
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          /* clipboard unavailable */
        }
      }}
    >
      {copied ? <Check className="icon" /> : <Copy className="icon" />}
    </button>
  );
}

function ShareMessageButton({
  onClick,
}: {
  onClick: MouseEventHandler<HTMLButtonElement>;
}) {
  return (
    <button
      type="button"
      className="icon-btn"
      aria-label="导出会话"
      title="导出会话"
      onClick={onClick}
    >
      <Share className="icon" aria-hidden="true" />
    </button>
  );
}

// Side-effect import: registers all A2UI components under a2ui/components/*.
import "./a2ui/components";


const GREETINGS = [
  "今天想做点什么？",
  "有什么可以帮你的？",
  "需要我帮你查点什么吗？",
  "有问题尽管问我",
  "嗨，我们开始吧",
  "开始一段新对话吧",
  "今天想先解决哪件事？",
  "把你的想法告诉我吧",
  "我们从哪里开始？",
  "有什么任务交给我？",
  "准备好一起推进了吗？",
  "说说你现在最关心的问题",
  "今天也一起把事情做好",
  "我在，随时可以开始",
];
const pickGreeting = () => GREETINGS[Math.floor(Math.random() * GREETINGS.length)];

function releaseAttachmentPreviews(items: Attachment[]) {
  for (const item of items) {
    if (item.previewUrl?.startsWith("blob:")) URL.revokeObjectURL(item.previewUrl);
  }
}

function attachmentDraftId() {
  return `draft-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function browserMimeType(file: File) {
  if (file.type) return file.type;
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (extension === "md" || extension === "markdown") return "text/markdown";
  if (extension === "txt") return "text/plain";
  return "application/octet-stream";
}

const SANDBOX_MODE_LABELS: Record<SandboxPermissions["sandboxMode"], string> = {
  "read-only": "只读",
  "workspace-write": "工作区写入",
  "danger-full-access": "完全访问",
};

const SANDBOX_APPROVAL_POLICY_LABELS: Record<
  SandboxPermissions["approvalPolicy"],
  string
> = {
  untrusted: "仅不可信命令",
  "on-request": "按需审批",
  never: "不审批",
};

const SANDBOX_REVIEWER_LABELS: Record<
  SandboxPermissions["approvalsReviewer"],
  string
> = {
  user: "由我审批",
  auto_review: "自动审查",
};

function approvalActivityTitle(
  approval: SandboxApproval,
  decision: SandboxApprovalDecision,
): string {
  const subject = approval.kind === "file" ? "文件修改" : "命令执行";
  if (decision === "accept") return `已允许本次${subject}`;
  if (decision === "acceptForSession") return `已在本会话中允许${subject}`;
  if (decision === "decline") return `已拒绝${subject}`;
  return `已取消${subject}审批`;
}

function approvalActivityDetails(
  approval: SandboxApproval,
): TurnActivityDetail[] {
  const details: TurnActivityDetail[] = [];
  if (approval.command?.trim()) {
    details.push({ label: "命令", value: approval.command.trim(), code: true });
  }
  if (approval.grantRoot?.trim()) {
    details.push({
      label: "授权路径",
      value: approval.grantRoot.trim(),
      code: true,
    });
  }
  if (approval.cwd?.trim()) {
    details.push({ label: "执行目录", value: approval.cwd.trim(), code: true });
  }
  return details;
}

function remoteSelectionIds(connections: RemoteConnection[]) {
  return connections.flatMap((connection) =>
    connection.apps.map((app) => remoteAppId(connection.id, app)),
  );
}

function runtimeIdForSelection(
  connections: RemoteConnection[],
  selectedAppName: string,
) {
  return connections.find(
    (connection) =>
      connection.runtimeId &&
      connection.apps.some(
        (app) => remoteAppId(connection.id, app) === selectedAppName,
      ),
  )?.runtimeId ?? "";
}

interface AutomaticEvaluationTarget {
  runtimeId: string;
  region: string;
  appName: string;
}

function automaticEvaluationTargetForSelection(
  connections: RemoteConnection[],
  selectedAppName: string,
): AutomaticEvaluationTarget | null {
  for (const connection of connections) {
    const runtimeApp = connection.apps.find(
      (app) => remoteAppId(connection.id, app) === selectedAppName,
    );
    if (runtimeApp && connection.runtimeId) {
      return {
        runtimeId: connection.runtimeId,
        region: connection.region ?? "cn-beijing",
        appName: runtimeApp,
      };
    }
  }
  return null;
}

function videoAssetsForConfig(
  config: NewChatVideoConfig,
): Array<{ file: File; kind: VideoAssetKind }> {
  if (config.taskMode === "text_to_video") return [];
  const candidates = config.taskMode === "first_last_frame"
    ? [
        config.firstFrame
          ? { file: config.firstFrame, kind: "first_frame" as const }
          : null,
        config.lastFrame
          ? { file: config.lastFrame, kind: "last_frame" as const }
          : null,
      ]
    : [
        config.referenceImage
          ? { file: config.referenceImage, kind: "reference_image" as const }
          : null,
        config.referenceVideo
          ? { file: config.referenceVideo, kind: "reference_video" as const }
          : null,
      ];
  return candidates.filter(
    (item): item is { file: File; kind: VideoAssetKind } => item !== null,
  );
}

function videoTaskFileName(taskId: string, outputFormat: "mp4" | "mov"): string {
  const safeId = taskId.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 36);
  return `video-${safeId || "result"}.${outputFormat}`;
}

function sessionUsageKey(app: string, session: string): string {
  return `${app}\u0001${session}`;
}

export default function App() {
  const [apps, setApps] = useState<string[]>([]);
  const [appName, setAppName] = useState("");
  const [sessions, setSessions] = useState<AdkSession[]>([]);
  const [sessionId, setSessionId] = useState("");
  const creatingSessionRef = useRef<Promise<string> | null>(null);
  const sessionRefreshRequestRef = useRef(0);
  const agentSelectionPreparationRequestRef = useRef(0);
  const preparedAgentSelectionRef = useRef<PreparedAgentSelection | null>(null);
  const [initializingSession, setInitializingSession] = useState(false);
  const [pendingTurns, setPendingTurns] = useState<Turn[]>([]);
  const [sandboxSession, setSandboxSession] =
    useState<SandboxSessionInfo | null>(null);
  const [sandboxTurns, setSandboxTurns] = useState<Turn[]>([]);
  const [sandboxBusy, setSandboxBusy] = useState(false);
  const [sandboxSettingsBusy, setSandboxSettingsBusy] = useState(false);
  const [sandboxSettingsError, setSandboxSettingsError] = useState("");
  const [sandboxPermissionsOpen, setSandboxPermissionsOpen] = useState(false);
  const [sandboxWorkspaceOpen, setSandboxWorkspaceOpen] = useState(false);
  const [sandboxToolKind, setSandboxToolKind] =
    useState<"terminal" | "browser" | null>(null);
  const [sandboxToolLaunch, setSandboxToolLaunch] =
    useState<SandboxToolLaunch | null>(null);
  const [sandboxToolLoading, setSandboxToolLoading] = useState(false);
  const [sandboxToolError, setSandboxToolError] = useState("");
  const [sandboxApproval, setSandboxApproval] =
    useState<SandboxApproval | null>(null);
  const [sandboxApprovalBusy, setSandboxApprovalBusy] = useState(false);
  const [sandboxApprovalError, setSandboxApprovalError] = useState("");
  const [sandboxUploadBusy, setSandboxUploadBusy] = useState(false);
  const [sandboxEndpointCopyState, setSandboxEndpointCopyState] =
    useState<"idle" | "copying" | "copied">("idle");
  const [sandboxLaunchOpen, setSandboxLaunchOpen] = useState(false);
  const [sandboxLaunchState, setSandboxLaunchState] =
    useState<SandboxLaunchState>("confirm");
  const [sandboxLaunchError, setSandboxLaunchError] = useState("");
  const [sandboxLaunchKind, setSandboxLaunchKind] =
    useState<"codex" | SandboxAgentKind>("codex");
  const [sandboxLaunchFromAgents, setSandboxLaunchFromAgents] = useState(false);
  const [sandboxProjectUploadOpen, setSandboxProjectUploadOpen] = useState(false);
  const [sandboxAgentRefreshKey, setSandboxAgentRefreshKey] = useState(0);
  const [myAgentsActiveType, setMyAgentsActiveType] = useState<AgentType>("general");
  const [sandboxAgentDetailTarget, setSandboxAgentDetailTarget] =
    useState<SandboxAgentResource | null>(null);
  const [sandboxAgentWorkspace, setSandboxAgentWorkspace] =
    useState<SandboxAgentWorkspaceData | null>(null);
  const [sandboxThreadDeleteTarget, setSandboxThreadDeleteTarget] =
    useState<SandboxThreadSummary | null>(null);
  const sandboxLaunchAbortRef = useRef<AbortController | null>(null);
  const intelligentCreateAbortRef = useRef<AbortController | null>(null);
  const sandboxMessageAbortRef = useRef<AbortController | null>(null);
  const pendingIntelligentNavigationRef = useRef<(() => void) | null>(null);
  const [intelligentLeaveOpen, setIntelligentLeaveOpen] = useState(false);
  const sandboxStopWaitRef = useRef<{
    controller: AbortController;
    promise: Promise<boolean>;
  } | null>(null);
  const sandboxSessionIdRef = useRef(sandboxSession?.id ?? "");
  const sandboxActiveAssistantTurnIdRef = useRef("");
  const sandboxUploadRunRef = useRef(0);
  const sandboxEndpointCopyTimerRef = useRef<number | undefined>(undefined);
  const sandboxPreviewUrlsRef = useRef<Set<string>>(new Set());
  sandboxSessionIdRef.current = sandboxSession?.id ?? "";
  useEffect(() => () => {
    if (sandboxEndpointCopyTimerRef.current !== undefined) {
      window.clearTimeout(sandboxEndpointCopyTimerRef.current);
    }
    for (const previewUrl of sandboxPreviewUrlsRef.current) {
      URL.revokeObjectURL(previewUrl);
    }
    sandboxPreviewUrlsRef.current.clear();
  }, []);

  function createSandboxPreviewUrl(file: File) {
    const previewUrl = URL.createObjectURL(file);
    sandboxPreviewUrlsRef.current.add(previewUrl);
    return previewUrl;
  }

  function releaseSandboxPreviewUrl(previewUrl?: string) {
    if (!previewUrl || !sandboxPreviewUrlsRef.current.delete(previewUrl)) return;
    URL.revokeObjectURL(previewUrl);
  }

  function releaseAllSandboxPreviews() {
    for (const previewUrl of sandboxPreviewUrlsRef.current) {
      URL.revokeObjectURL(previewUrl);
    }
    sandboxPreviewUrlsRef.current.clear();
  }

  const resetSandboxEndpointCopyState = useCallback(() => {
    if (sandboxEndpointCopyTimerRef.current !== undefined) {
      window.clearTimeout(sandboxEndpointCopyTimerRef.current);
      sandboxEndpointCopyTimerRef.current = undefined;
    }
    setSandboxEndpointCopyState("idle");
  }, []);

  useEffect(() => {
    resetSandboxEndpointCopyState();
  }, [resetSandboxEndpointCopyState, sandboxSession?.id]);

  // Turns are stored PER SESSION, so a background stream can keep updating its
  // own session's transcript while you view another one — no cross-session
  // leak, no data loss, and no re-fetch when you switch back (its entry is
  // already live). The view shows the active session's entry.
  const [turnsBySession, setTurnsBySession] = useState<Record<string, Turn[]>>(
    {},
  );
  const [tokenUsageBySession, setTokenUsageBySession] = useState<
    Record<string, SessionTokenUsage>
  >({});
  const persistentTurns = sessionId
    ? turnsBySession[sessionId] ?? []
    : pendingTurns;
  const turns = sandboxSession ? sandboxTurns : persistentTurns;
  const activeTokenUsage = sessionId
    ? tokenUsageBySession[sessionUsageKey(appName, sessionId)] ??
      EMPTY_SESSION_TOKEN_USAGE
    : EMPTY_SESSION_TOKEN_USAGE;
  const setTurnsFor = (
    sid: string,
    updater: Turn[] | ((prev: Turn[]) => Turn[]),
  ) =>
    setTurnsBySession((m) => ({
      ...m,
      [sid]: typeof updater === "function" ? updater(m[sid] ?? []) : updater,
    }));

  const addTokenUsageFor = (
    app: string,
    sid: string,
    event: AdkEvent,
  ) => {
    const key = sessionUsageKey(app, sid);
    setTokenUsageBySession((current) => {
      const previous = current[key] ?? EMPTY_SESSION_TOKEN_USAGE;
      const next = addTokenUsage(previous, event);
      return next === previous ? current : { ...current, [key]: next };
    });
  };

  function appendSandboxActivity(
    activeSessionId: string,
    title: string,
    details: TurnActivityDetail[] = [],
    beforeTurnId = "",
  ) {
    if (sandboxSessionIdRef.current !== activeSessionId) return;
    const activityId = crypto.randomUUID();
    const activityTurn: Turn = {
      role: "system",
      blocks: [],
      activity: {
        id: activityId,
        title,
        ...(details.length > 0 ? { details } : {}),
      },
      meta: { localId: activityId, ts: Date.now() / 1000 },
    };
    setSandboxTurns((current) => {
      if (!beforeTurnId) return [...current, activityTurn];
      const beforeIndex = current.findIndex(
        (turn) => turn.meta?.localId === beforeTurnId,
      );
      if (beforeIndex < 0) return [...current, activityTurn];
      return [
        ...current.slice(0, beforeIndex),
        activityTurn,
        ...current.slice(beforeIndex),
      ];
    });
  }
  const [input, setInput] = useState("");
  const [newChatMode, setNewChatMode] = useState<NewChatMode>("agent");
  const [newChatWorkspaceMode, setNewChatWorkspaceMode] =
    useState<NewChatWorkspaceMode>("agent");
  const [newChatSkillAction, setNewChatSkillAction] =
    useState<NewChatSkillAction>("create");
  const [newChatSkillTarget, setNewChatSkillTarget] =
    useState<NewChatSkillTarget | null>(null);
  const [newChatTask, setNewChatTask] = useState<NewChatTask | null>(null);
  const [intelligentCapabilities, setIntelligentCapabilities] =
    useState<IntelligentDevelopmentCapabilities | null>(null);
  const [intelligentCapabilitiesLoading, setIntelligentCapabilitiesLoading] =
    useState(true);
  const [intelligentCapabilitiesError, setIntelligentCapabilitiesError] =
    useState("");
  const [intelligentPreparationStage, setIntelligentPreparationStage] =
    useState<IntelligentPreparationStage | null>(null);
  const [migrationProjectReturn, setMigrationProjectReturn] = useState<{
    projectId: string;
  }>();
  const [intelligentDeployment, setIntelligentDeploymentState] =
    useState<IntelligentDevelopmentReleaseRef | null>(null);
  const setIntelligentDeployment = useCallback(
    (delivery: IntelligentDevelopmentReleaseRef | null) => {
      setIntelligentDeploymentState(delivery);
      const url = new URL(window.location.href);
      if (delivery) {
        url.searchParams.set("view", "runtime-deploy");
        url.searchParams.set("source", "intelligent-development");
        url.searchParams.set("sessionId", delivery.sessionId);
        url.searchParams.set("artifactSha256", delivery.artifactSha256);
        url.searchParams.set(
          "validationReportSha256",
          delivery.validationReportSha256,
        );
        if (delivery.projectId && delivery.versionId) {
          url.searchParams.set("projectId", delivery.projectId);
          url.searchParams.set("versionId", delivery.versionId);
        } else {
          url.searchParams.delete("projectId");
          url.searchParams.delete("versionId");
        }
      } else {
        for (const key of [
          "view",
          "source",
          "sessionId",
          "artifactSha256",
          "validationReportSha256",
          "projectId",
          "versionId",
        ]) url.searchParams.delete(key);
      }
      window.history.replaceState(null, "", url);
    },
    [],
  );
  const resolveIntelligentDelivery = useCallback(
    (delivery: IntelligentDevelopmentReleaseRef) => delivery.projectId && delivery.versionId
      ? fetchIntelligentDevelopmentProjectRelease(
          delivery.projectId,
          delivery.versionId,
          delivery.sessionId,
          delivery.artifactSha256,
          delivery.validationReportSha256,
        )
      : fetchIntelligentDevelopmentRelease(
          delivery.sessionId,
          delivery.artifactSha256,
          delivery.validationReportSha256,
        ),
    [],
  );
  const resolveIntelligentDeliveryComparison = useCallback(
    async (delivery: IntelligentDevelopmentReleaseRef) => {
      if (!delivery.projectId || !delivery.versionId || !delivery.parentVersionId) {
        throw new Error("当前版本没有可对比的优化前版本。");
      }
      const versions = await fetchIntelligentDevelopmentVersions(delivery.projectId);
      const targetVersion = versions.find(
        (version) => version.versionId === delivery.versionId,
      );
      const baseVersion = versions.find(
        (version) => version.versionId === delivery.parentVersionId,
      );
      if (!targetVersion || !baseVersion) {
        throw new Error("无法找到本次优化对应的项目版本，可能已被删除。");
      }
      const [base, target] = await Promise.all([
        fetchIntelligentDevelopmentVersionSource(baseVersion),
        fetchIntelligentDevelopmentVersionSource(targetVersion),
      ]);
      return { base, target };
    },
    [],
  );
  const downloadIntelligentDelivery = useCallback(
    async (delivery: IntelligentDevelopmentReleaseRef) => {
      const operation = beginAgentSourceDownload({
        agentId: delivery.agentName,
        deployAction: "create",
        deploySource: "intelligent_development",
        createMode: "intelligent",
        aiAssisted: 1,
      });
      try {
        const { blob, filename } = await downloadIntelligentDevelopmentRelease(delivery);
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        link.hidden = true;
        try {
          document.body.appendChild(link);
          link.click();
        } finally {
          link.remove();
          window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
        }
        operation.succeed({
          fileCount: delivery.fileCount,
          zipSizeBytes: blob.size,
        });
      } catch (cause) {
        operation.fail({
          fileCount: delivery.fileCount,
          ...classifyTelemetryError(cause),
        });
        throw cause;
      }
    },
    [],
  );
  const [videoTask, setVideoTask] = useState<VideoGenerationTask | null>(null);
  const [videoTaskDialogOpen, setVideoTaskDialogOpen] = useState(false);
  const [agentKitCliOpen, setAgentKitCliOpen] = useState(false);
  const videoTaskRef = useRef<VideoGenerationTask | null>(null);
  const videoTaskAbortRef = useRef<AbortController | null>(null);
  const [newChatCapabilities, setNewChatCapabilities] =
    useState<NewChatCapabilitiesState>({});
  const newChatCapabilitiesCacheRef = useRef(
    new Map<string, NewChatCapabilitiesState>(),
  );
  const newChatCapabilitiesReady =
    newChatCapabilities.ready === true && newChatCapabilities.agentId === appName;
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [invocation, setInvocation] = useState<FrontendInvocation>(emptyInvocation);
  const [studioToolCapabilities, setStudioToolCapabilities] =
    useState<RuntimeStudioToolCapabilities | null>(null);
  const [studioToolsLoading, setStudioToolsLoading] = useState(false);
  const [studioToolsError, setStudioToolsError] = useState("");
  const [draftStudioRuntime, setDraftStudioRuntime] = useState<{
    appName: string;
    runtimeId: string;
    name: string;
    region: string;
  } | null>(null);
  const [draftStudioToolIds, setDraftStudioToolIds] = useState<string[]>([]);
  const [studioToolIdsBySession, setStudioToolIdsBySession] = useState<
    Record<string, string[]>
  >({});
  const [sessionEnvironments, setSessionEnvironments] = useState<StudioEnvironment[]>([]);
  const [sessionWorkspaces, setSessionWorkspaces] = useState<StudioWorkspace[]>([]);
  const [sessionEnvironmentsLoading, setSessionEnvironmentsLoading] = useState(false);
  const [sessionEnvironmentsError, setSessionEnvironmentsError] = useState("");
  const [environmentMountsBySession, setEnvironmentMountsBySession] = useState<
    Record<string, SessionEnvironmentMountSelection[]>
  >({});
  const [environmentWorkspaceIdsBySession, setEnvironmentWorkspaceIdsBySession] = useState<
    Record<string, string[]>
  >({});
  const [runtimeLogTargetsBySession, setRuntimeLogTargetsBySession] = useState<
    Record<string, RuntimeLogTarget>
  >({});
  const [agentInfo, setAgentInfo] = useState<AgentInfo | null>(null);
  const [agentInfoRefreshKey, setAgentInfoRefreshKey] = useState(0);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(false);
  const removedAttachmentIdsRef = useRef<Set<string>>(new Set());
  // Streaming state is PER SESSION so multiple sessions can stream at once
  // (each /run_sse is an independent request). `streamingSids` = which sessions
  // are currently streaming; the AbortControllers let unmount / delete cancel
  // a specific session's stream. A normal switch does NOT abort — the stream
  // keeps running and persisting.
  const [streamingSids, setStreamingSids] = useState<Set<string>>(
    () => new Set(),
  );
  const [streamPresentationSids, setStreamPresentationSids] = useState<Set<string>>(
    () => new Set(),
  );
  const [evaluatingSids, setEvaluatingSids] = useState<Set<string>>(
    () => new Set(),
  );
  const streamAbortsRef = useRef<Map<string, AbortController>>(new Map());
  const streamPresentationTimersRef = useRef<Map<string, number>>(new Map());
  const automaticEvaluationStatusTimerRef = useRef<number | undefined>(undefined);
  const automaticEvaluationStatusRefreshRef = useRef<() => void>(() => {});
  const setStreaming = (sid: string, on: boolean) =>
    setStreamingSids((s) => {
      const n = new Set(s);
      if (on) n.add(sid);
      else n.delete(sid);
      return n;
    });
  const startStreamPresentation = (sid: string) => {
    const timer = streamPresentationTimersRef.current.get(sid);
    if (timer !== undefined) window.clearTimeout(timer);
    streamPresentationTimersRef.current.delete(sid);
    setStreamPresentationSids((current) => new Set(current).add(sid));
  };
  const completeStreamPresentation = (sid: string) => {
    const timer = streamPresentationTimersRef.current.get(sid);
    if (timer !== undefined) window.clearTimeout(timer);
    streamPresentationTimersRef.current.delete(sid);
    setStreamPresentationSids((current) => {
      if (!current.has(sid)) return current;
      const next = new Set(current);
      next.delete(sid);
      return next;
    });
  };
  const finishStreamPresentation = (sid: string) => {
    const previousTimer = streamPresentationTimersRef.current.get(sid);
    if (previousTimer !== undefined) window.clearTimeout(previousTimer);
    const timer = window.setTimeout(() => {
      completeStreamPresentation(sid);
    }, 2400);
    streamPresentationTimersRef.current.set(sid, timer);
  };
  const setEvaluating = (sid: string, on: boolean) => {
    setEvaluatingSids((current) => {
      if (current.has(sid) === on) return current;
      const next = new Set(current);
      if (on) next.add(sid);
      else next.delete(sid);
      return next;
    });
  };
  // The session currently on screen — used to gate the single global error
  // banner (per-session transcripts/topology don't need it).
  const viewSidRef = useRef("");
  const [error, setError] = useState("");

  function commitVideoTask(
    localId: string,
    runId: number,
    event: VideoTaskEvent,
  ): VideoGenerationTask | null {
    const current = videoTaskRef.current;
    if (!current || current.localId !== localId || current.runId !== runId) {
      return null;
    }
    const next = updateVideoGenerationTask(current, event);
    videoTaskRef.current = next;
    setVideoTask(next);
    return next;
  }

  async function executeVideoTask(
    localId: string,
    runId: number,
    startingStage: VideoTaskErrorStage,
  ) {
    videoTaskAbortRef.current?.abort();
    const controller = new AbortController();
    videoTaskAbortRef.current = controller;
    let stage = startingStage;

    try {
      let current = videoTaskRef.current;
      if (!current || current.localId !== localId || current.runId !== runId) return;

      if (stage === "optimization" && current.assetIds.length === 0) {
        const assets = videoAssetsForConfig(current.config);
        if (assets.length > 0) {
          const uploaded = await Promise.all(
            assets.map((asset) => uploadVideoAsset(asset.file, asset.kind, controller.signal)),
          );
          if (controller.signal.aborted) return;
          current = commitVideoTask(localId, runId, {
            type: "assets_uploaded",
            assetIds: uploaded.map((asset) => asset.assetId),
          });
          if (!current) return;
        }
      }

      if (stage === "optimization") {
        const enhancement = await enhanceVideoPrompt({
          prompt: current.requestedPrompt,
          taskMode: current.requestedMode,
          assetIds: current.assetIds,
          ratio: current.config.aspectRatio,
          resolution: current.config.resolution,
          durationSeconds: current.config.durationSeconds,
        }, controller.signal);
        if (controller.signal.aborted) return;
        current = commitVideoTask(localId, runId, {
          type: "optimization_succeeded",
          optimizedPrompt: enhancement.enhancedPrompt,
          resolvedMode: enhancement.resolvedTaskMode,
          enhancerModel: enhancement.enhancerModel,
        });
        if (!current) return;
        stage = "generation";
      }

      if (!current.optimizedPrompt || !current.resolvedMode) {
        throw new Error("提示词优化结果不完整，请重新优化后再试。");
      }

      const created = await createVideoTask({
        enhancedPrompt: current.optimizedPrompt,
        resolvedTaskMode: current.resolvedMode,
        assetIds: current.assetIds,
        ratio: current.config.aspectRatio,
        resolution: current.config.resolution,
        durationSeconds: current.config.durationSeconds,
      }, controller.signal);
      if (controller.signal.aborted) return;
      current = commitVideoTask(localId, runId, {
        type: "generation_started",
        remoteTaskId: created.taskId,
        generationModel: created.generationModel,
        startedAt: Date.now(),
      });
      if (!current) return;

      while (!controller.signal.aborted) {
        const remote = await getVideoTask(created.taskId, controller.signal);
        if (controller.signal.aborted) return;
        if (remote.status === "queued" || remote.status === "running") {
          commitVideoTask(localId, runId, {
            type: "generation_status_changed",
            providerStatus: remote.status,
          });
        }
        if (remote.status === "failed") {
          throw new Error(remote.error || "视频生成失败，请稍后重试。");
        }
        if (remote.status === "succeeded") {
          if (!remote.videoUrl) {
            throw new Error("视频任务已完成，但服务端未返回预览地址。");
          }
          commitVideoTask(localId, runId, {
            type: "generation_succeeded",
            output: {
              previewUrl: videoResultPreviewUrl(remote.videoUrl),
              fileName: videoTaskFileName(created.taskId, remote.outputFormat),
              mimeType: remote.outputFormat === "mov" ? "video/quicktime" : "video/mp4",
            },
          });
          return;
        }
        await new Promise<void>((resolve) => window.setTimeout(resolve, 1800));
      }
    } catch (cause) {
      if (controller.signal.aborted) return;
      commitVideoTask(localId, runId, {
        type: "failed",
        stage,
        error: cause instanceof Error ? cause.message : String(cause),
      });
    }
  }

  function startVideoTask(
    prompt: string,
    config: NewChatVideoConfig,
    capabilities: VideoCapabilities,
  ) {
    if (isVideoTaskRunning(videoTaskRef.current)) {
      setVideoTaskDialogOpen(true);
      return;
    }
    if (config.taskMode === "video_editing" && !config.referenceVideo) {
      setError("视频编辑需要先添加待编辑视频。");
      return;
    }
    if (config.taskMode === "video_extension" && !config.referenceVideo) {
      setError("视频续写需要先添加基础视频。");
      return;
    }
    if (
      config.taskMode === "reference_to_video" &&
      !config.referenceImage &&
      !config.referenceVideo
    ) {
      setError("参考素材生视频需要至少添加一项参考图片或参考视频。");
      return;
    }
    if (
      config.taskMode === "text_to_video" &&
      (config.referenceImage || config.referenceVideo || config.firstFrame || config.lastFrame)
    ) {
      setError("文生视频不使用参考素材，请先移除已添加的图片或视频。");
      return;
    }
    if (config.taskMode === "first_last_frame" && !config.firstFrame) {
      setError("首尾帧生成需要先添加首帧图片。");
      return;
    }
    if (
      capabilities.supportedModes.length > 0 &&
      config.taskMode !== "auto" &&
      !capabilities.supportedModes.includes(config.taskMode)
    ) {
      setError("当前平台暂不支持所选视频任务模式。");
      return;
    }
    const assets = videoAssetsForConfig(config);
    if (assets.length > 0 && !capabilities.assetStorageAvailable) {
      setError(
        capabilities.assetStorageUnavailableReason ||
          "管理员未配置持久化存储",
      );
      return;
    }
    const oversized = assets.find(
      ({ file }) => capabilities.maxAssetBytes > 0 && file.size > capabilities.maxAssetBytes,
    );
    if (oversized) {
      setError(`${oversized.file.name} 超出当前平台允许的素材大小。`);
      return;
    }

    const next = createVideoGenerationTask({
      prompt,
      config,
      enhancerModel: capabilities.enhancerModel,
      generationModel: capabilities.generationModel,
    });
    videoTaskRef.current = next;
    setVideoTask(next);
    setVideoTaskDialogOpen(true);
    setInput("");
    setError("");
    void executeVideoTask(next.localId, next.runId, "optimization");
  }

  function retryVideoTask() {
    const current = videoTaskRef.current;
    if (!current || current.status !== "error" || !current.errorStage) return;
    const stage = current.errorStage;
    const next = updateVideoGenerationTask(current, { type: "retry", stage });
    videoTaskRef.current = next;
    setVideoTask(next);
    setVideoTaskDialogOpen(true);
    void executeVideoTask(next.localId, next.runId, stage);
  }

  async function downloadCurrentVideoTask() {
    const current = videoTaskRef.current;
    if (!current?.remoteTaskId || !current.output) return;
    try {
      const blob = await downloadVideoTask(current.remoteTaskId);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = current.output.fileName;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1_000);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  useEffect(() => () => {
    videoTaskAbortRef.current?.abort();
  }, []);

  const [draftStorageError, setDraftStorageError] = useState("");
  const [feedbackPendingIds, setFeedbackPendingIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [issueFeedbackTarget, setIssueFeedbackTarget] =
    useState<IssueFeedbackTarget | null>(null);
  const [shareMessageTarget, setShareMessageTarget] =
    useState<ShareMessageTarget | null>(null);
  const [responseAnnotationTarget, setResponseAnnotationTarget] =
    useState<ResponseAnnotationTarget | null>(null);
  const [platformFeedbackOrigin, setPlatformFeedbackOrigin] =
    useState<string | null>(null);

  useEffect(() => {
    setResponseAnnotationTarget(null);
  }, [appName, sessionId]);
  const [traceOpen, setTraceOpen] = useState(false);
  const [traceEndTimeMs, setTraceEndTimeMs] = useState<number>();
  const [greeting, setGreeting] = useState(pickGreeting);
  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
  const [authExpired, setAuthExpired] = useState(false);
  const [authRecoveryChecking, setAuthRecoveryChecking] = useState(false);
  const [authRecoveryError, setAuthRecoveryError] = useState("");
  const authRecoveryActiveRef = useRef(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [userId, setUserId] = useState("");
  const [userInfo, setUserInfo] = useState<Record<string, unknown> | undefined>();
  // Null while the server-derived role is unresolved. Privileged UI remains
  // hidden until this has loaded; failures fall back to the ordinary user.
  const [access, setAccess] = useState<StudioAccess | null>(null);
  const grantedRuntimeScope = access?.capabilities.runtimeScope ?? "mine";
  // Per-module feature gates (studio mode disables chat-centric modules).
  // Defaults to all-enabled until /web/ui-config resolves.
  const [features, setFeatures] = useState<UiFeatures>({
    newChat: true,
    search: true,
    skillCenter: true,
    history: true,
    addAgent: true,
    manageAgents: true,
    agentUsage: false,
    addAgentkit: true,
  });
  const [agentsSource, setAgentsSource] = useState<"local" | "cloud">("cloud");
  const [siteBranding, setSiteBranding] = useState<SiteBranding>(DEFAULT_SITE_BRANDING);
  const [cloudProvider, setCloudProvider] =
    useState<UiConfig["provider"]>("volcengine");
  const [version, setVersion] = useState("");
  const [studioRegion, setStudioRegion] = useState("");
  const [uiConfigLoaded, setUiConfigLoaded] = useState(false);
  const [localMode, setLocalMode] = useState(false);
  const [loadingSession, setLoadingSession] = useState(false);
  // The executing sub-agent (ADK event.author) and everyone who emitted this
  // turn — PER SESSION, so each session's topology highlights its own stream.
  const [activeAgentBySession, setActiveAgentBySession] = useState<
    Record<string, string>
  >({});
  const [seenAgentsBySession, setSeenAgentsBySession] = useState<
    Record<string, Set<string>>
  >({});
  // The current delegation chain (root → … → executing agent) per session,
  // built from event.actions.transfer_to_agent / end_of_agent.
  const [execPathBySession, setExecPathBySession] = useState<
    Record<string, string[]>
  >({});

  // Everything the view needs for the ACTIVE session, derived from the
  // per-session maps above.
  const busy = streamingSids.has(sessionId);
  const presentingStream = streamPresentationSids.has(sessionId);
  const conversationBusy = busy || initializingSession;
  const activeConversationBusy = sandboxSession
    ? sandboxBusy
    : conversationBusy;
  const activeConversationPresenting =
    activeConversationBusy || (!sandboxSession && presentingStream);
  const sandboxClientForSession = sandboxSession?.intelligentDevelopment === true
    ? intelligentDevelopmentClient
    : sandboxClient;
  const sandboxCommands = useSandboxCodexCommands({
    client: sandboxClientForSession,
    allowSkillSelection: sandboxSession?.intelligentDevelopment !== true,
    allowThreadManagement: sandboxSession?.intelligentDevelopment !== true,
    session: sandboxSession,
    conversationBusy: sandboxBusy,
    onInputChange: setInput,
    onSessionPatch: (patch) => {
      const activeSessionId = sandboxSessionIdRef.current;
      setSandboxSession((current) =>
        current?.id === activeSessionId ? { ...current, ...patch } : current
      );
    },
    onSnapshot: (snapshot) => {
      const activeSessionId = sandboxSessionIdRef.current;
      releaseAllSandboxPreviews();
      setSandboxTurns(sandboxSnapshotTurns(snapshot));
      setSandboxSession((current) =>
        current?.id === activeSessionId
          ? {
              ...current,
              threadId: snapshot.threadId,
              cwd: snapshot.cwd ?? current.cwd,
              model: snapshot.model ?? current.model,
              workspaceLocked: snapshot.workspaceLocked,
              permissions: snapshot.permissions,
              busy: false,
            }
          : current
      );
    },
    onActivity: (title, details = []) => {
      const activeSessionId = sandboxSessionIdRef.current;
      if (activeSessionId) appendSandboxActivity(activeSessionId, title, details);
    },
    onError: setError,
  });
  useEffect(() => {
    const activeSession = sandboxSession;
    if (!activeSession || !sandboxBusy || sandboxMessageAbortRef.current) return;
    let stopped = false;
    let timer: number | undefined;
    const controller = new AbortController();

    const syncBackgroundTurn = async () => {
      try {
        const backgroundClient = activeSession.intelligentDevelopment
          ? intelligentDevelopmentClient
          : sandboxClient;
        const status = await backgroundClient.getStatus(activeSession.id, {
          signal: controller.signal,
        });
        if (stopped || sandboxSessionIdRef.current !== activeSession.id) return;
        const snapshot = status.threadId
          ? await backgroundClient.readThread(activeSession.id, status.threadId, {
              signal: controller.signal,
            })
          : null;
        if (stopped || sandboxSessionIdRef.current !== activeSession.id) return;
        if (snapshot) {
          setSandboxTurns(sandboxSnapshotTurnsForStatus(snapshot, status.busy));
        }
        setSandboxSession((current) =>
          current?.id === activeSession.id
            ? {
                ...current,
                ...status,
                ...(snapshot
                  ? {
                      threadId: snapshot.threadId,
                      cwd: snapshot.cwd ?? status.cwd,
                      model: snapshot.model ?? status.model,
                      workspaceLocked: snapshot.workspaceLocked,
                      permissions: snapshot.permissions,
                    }
                  : {}),
              }
            : current
        );
        setSandboxBusy(status.busy);
        if (!status.busy) {
          const lastMessage = snapshot?.messages[snapshot.messages.length - 1];
          if (lastMessage?.role === "user") {
            setError("云端 Codex 已结束，但没有生成回复，请重新发送任务。");
          }
          return;
        }
      } catch (cause) {
        if ((cause as Error)?.name === "AbortError" || stopped) return;
        if (activeSession.intelligentDevelopment) {
          setError(intelligentDevelopmentErrorMessage(cause));
          timer = window.setTimeout(syncBackgroundTurn, 1500);
          return;
        }
        setSandboxBusy(false);
        setSandboxSession((current) =>
          current?.id === activeSession.id ? { ...current, busy: false } : current
        );
        setError(cause instanceof Error ? cause.message : String(cause));
        return;
      }
      timer = window.setTimeout(syncBackgroundTurn, 1500);
    };

    timer = window.setTimeout(syncBackgroundTurn, 1500);
    return () => {
      stopped = true;
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [sandboxBusy, sandboxSession?.id]);
  const activeAgent = activeAgentBySession[sessionId] ?? "";
  const seenAgents = seenAgentsBySession[sessionId] ?? EMPTY_STRING_SET;
  const execPath = execPathBySession[sessionId] ?? EMPTY_STRING_ARR;
  const rootCapabilityNode = agentInfo?.graph;
  const rootAgentNames = [
    agentInfo?.name,
    rootCapabilityNode?.name,
    rootCapabilityNode?.id,
  ].filter((name): name is string => Boolean(name));
  const skillCapabilityNode = invocation.targetAgent && rootCapabilityNode
    ? findAgentNode(rootCapabilityNode, invocation.targetAgent.name)
    : rootCapabilityNode;
  const availableSkills = skillCapabilityNode?.skills ??
    (invocation.targetAgent ? [] : agentInfo?.skills ?? []);
  const availableAgents = rootCapabilityNode
    ? mentionableDescendants(rootCapabilityNode)
    : [];
  const systemInstruction =
    rootCapabilityNode?.instruction ?? agentInfo?.draft?.instruction;
  const systemTokenEstimate = agentInfo && systemInstruction !== undefined
    ? estimateSystemContextTokens({
        instruction: systemInstruction,
        tools: [
          ...new Set([
            ...(rootCapabilityNode?.tools ?? agentInfo.tools),
            ...(sessionId
              ? (studioToolIdsBySession[
                  studioToolSelectionKey(appName, userId, sessionId)
                ] ?? [])
              : draftStudioToolIds),
          ]),
        ],
        skills: rootCapabilityNode?.skills ?? agentInfo.skills,
      })
    : null;

  function discardDraftAttachments(items: Attachment[]) {
    releaseAttachmentPreviews(items);
    for (const item of items) {
      if (item.status === "uploading") {
        removedAttachmentIdsRef.current.add(item.id);
      } else if (item.uri) {
        void deleteMedia(appName, item.uri).catch((e) => setError(String(e)));
      }
    }
  }

  async function abandonDraftSession(sid: string) {
    try {
      await deleteSessionMedia(appName, userId, sid);
      await deleteSession(appName, userId, sid);
      setSessions((current) => current.filter((session) => session.id !== sid));
      setTurnsBySession((current) => {
        const { [sid]: _drop, ...rest } = current;
        return rest;
      });
    } catch (e) {
      setError(String(e));
    }
  }

  function removeDraftAttachment(id: string) {
    const removed = attachments.find((item) => item.id === id);
    if (!removed) return;
    const remaining = attachments.filter((item) => item.id !== id);
    releaseAttachmentPreviews([removed]);
    if (removed.status === "uploading") {
      removedAttachmentIdsRef.current.add(id);
    }
    setAttachments(remaining);

    const shouldAbandonSession =
      remaining.length === 0 && !input.trim() && !!sessionId && turns.length === 0;
    if (shouldAbandonSession) {
      viewSidRef.current = "";
      setSessionId("");
      void abandonDraftSession(sessionId);
    } else if (removed.uri) {
      void deleteMedia(appName, removed.uri).catch((e) => setError(String(e)));
    }
  }

  // Apply a stream event's control-flow signals to a session's live state:
  // author = who's executing now; transfer_to_agent pushes the delegation
  // chain; end_of_agent / escalate pops it. `author` always wins for highlight.
  const applyStreamSignals = (sid: string, ev: AdkEvent) => {
    const who = ev.author && ev.author !== "user" ? ev.author : undefined;
    if (who) {
      setActiveAgentBySession((m) => ({ ...m, [sid]: who }));
      setSeenAgentsBySession((m) => ({
        ...m,
        [sid]: new Set(m[sid] ?? []).add(who),
      }));
      // Seed the path with the entry (root) agent on the first event.
      setExecPathBySession((m) =>
        m[sid]?.length ? m : { ...m, [sid]: [who] },
      );
    }
    const transferTo =
      ev.actions?.transferToAgent ?? ev.actions?.transfer_to_agent;
    if (transferTo) {
      setExecPathBySession((m) => {
        const cur = m[sid] ?? [];
        return cur[cur.length - 1] === transferTo
          ? m
          : { ...m, [sid]: [...cur, transferTo] };
      });
    }
    const ended =
      ev.actions?.endOfAgent ?? ev.actions?.end_of_agent ?? ev.actions?.escalate;
    if (ended) {
      setExecPathBySession((m) => {
        const cur = m[sid] ?? [];
        return cur.length <= 1 ? m : { ...m, [sid]: cur.slice(0, -1) };
      });
    }
  };
  const [createView, setCreateView] = useState<AppView>(loadView);
  const [deploymentTasks, setDeploymentTasks] = useState<
    DeploymentTaskUpdate[]
  >([]);
  const [draftDeploymentTaskIds, setDraftDeploymentTaskIds] = useState<
    Record<string, string>
  >({});
  const updateDeploymentTask = useCallback((task: DeploymentTaskUpdate) => {
    setDeploymentTasks((current) => {
      const existingIndex = current.findIndex((item) => item.id === task.id);
      if (existingIndex === -1) return [task, ...current];
      const next = [...current];
      next[existingIndex] = { ...next[existingIndex], ...task };
      return next;
    });
  }, []);
  // Whether the server has cloud AK/SK. The agent-creation workbench needs
  // them; assume present until the runtime-config check says otherwise (avoids
  // flashing the notice in the common, configured case).
  const [hasCreds, setHasCreds] = useState(true);
  const [skillCenter, setSkillCenter] = useState(false);
  const [libraryTab, setLibraryTab] = useState<LibraryTab>("skills");
  const [libraryPageTitle, setLibraryPageTitle] = useState("技能库");
  const [skillCenterLaunch, setSkillCenterLaunch] =
    useState<SkillCenterWorkspaceLaunch | null>(null);
  const [addAgent, setAddAgent] = useState(false);
  // The "添加 Agent" chooser (two cards: AgentKit / 从 0 快速创建).
  const [addMenu, setAddMenu] = useState(false);
  const [addMenuSurface, setAddMenuSurface] =
    useState<"entry" | "traditional">("entry");
  const [customCreationSurface, setCustomCreationSurface] =
    useState<"vulcan" | "traditional">("traditional");
  // A draft imported from YAML, used to pre-fill the custom wizard once.
  const [importedDraft, setImportedDraft] = useState<AgentDraft | null>(null);
  const [customCreateMode, setCustomCreateMode] =
    useState<CustomCreateMode>("custom");
  const [savedAgentDrafts, setSavedAgentDrafts] = useState<WorkspaceAgentDraft[]>([]);
  const savedAgentDraftsRef = useRef<WorkspaceAgentDraft[]>([]);
  const pendingWorkspaceDraftRef = useRef<WorkspaceAgentDraft | null>(null);
  const workspaceDraftTimerRef = useRef<number | null>(null);
  const [workspaceAgentOrder, setWorkspaceAgentOrder] = useState<string[]>([]);
  const [editingDraftId, setEditingDraftId] = useState("");
  const editingDraftBaselineRef = useRef<WorkspaceAgentDraft | null>(null);
  const [searchView, setSearchView] = useState(false);
  // The #748 Agent workspace: library, evaluation groups, and draft management.
  const [manageAgents, setManageAgents] = useState(false);
  const [feedbackCaseReturnAgentId, setFeedbackCaseReturnAgentId] = useState("");
  const [feedbackCaseReturnKind, setFeedbackCaseReturnKind] =
    useState<"good" | "bad">("good");
  const [focusedWorkspaceAgentSection, setFocusedWorkspaceAgentSection] =
    useState<"basic" | "evaluations">("basic");
  const [focusedWorkspaceCaseKind, setFocusedWorkspaceCaseKind] =
    useState<"good" | "bad">("good");
  const [feedbackTargetEventId, setFeedbackTargetEventId] = useState("");
  const [feedbackCasePreview, setFeedbackCasePreview] =
    useState<AgentFeedbackCase | null>(null);
  const [myAgents, setMyAgents] = useState(false);
  const [environmentView, setEnvironmentView] = useState(false);
  const [workspaceView, setWorkspaceView] = useState(false);
  const [pageStack, setPageStack] = useState<StudioPageStackEntry[]>([]);
  const activeStackEntry = pageStack[pageStack.length - 1];
  const activeStackPage = activeStackEntry?.page;
  const systemInfo = activeStackPage === "system-info";
  const pushStudioPage = useCallback((entry: StudioPageStackEntry) => {
    setPageStack((current) =>
      current[current.length - 1]?.page === entry.page
        ? current
        : [...current, entry],
    );
  }, []);
  const popStudioPage = useCallback((page: StudioStackPage) => {
    setPageStack((current) => {
      if (current[current.length - 1]?.page === page) return current.slice(0, -1);
      const index = current.findIndex((entry) => entry.page === page);
      if (index === -1) return current;
      return current.filter((_, entryIndex) => entryIndex !== index);
    });
  }, []);
  const [applicationsView, setApplicationsView] =
    useState<"catalog" | ApplicationId | null>(null);
  const [cronJobsView, setCronJobsView] = useState(false);
  // A search result may belong to a different agent; remember it so the
  // agent-switch effect opens it instead of resetting to a fresh chat.
  const pendingOpenRef = useRef<{ app: string; sid: string } | null>(null);
  // Remote AgentKit connections (persisted); register them into the ADK client
  // routing table once, synchronously, so remote app ids resolve immediately.
  const [connections, setConnections] = useState<RemoteConnection[]>(() => {
    const c = loadConnections();
    registerConnections(c);
    return c;
  });
  const [agentLibraryLoading, setAgentLibraryLoading] = useState(false);
  const [agentLibraryError, setAgentLibraryError] = useState("");
  const [libraryRuntimeIds, setLibraryRuntimeIds] = useState<Set<string> | null>(
    null,
  );
  const [libraryRuntimePermissions, setLibraryRuntimePermissions] = useState<
    Record<string, { canDelete: boolean }>
  >({});
  const [hiddenRuntimeIds, setHiddenRuntimeIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [runtimeUpdateTarget, setRuntimeUpdateTarget] = useState<{
    runtimeId: string;
    name: string;
    region: string;
    appName?: string;
    currentVersion?: number | null;
    etag?: string;
    editMode?: "source-preserving" | "regenerate";
    configuredMcpEnvKeys?: string[];
  } | null>(null);
  const [newRuntimeRegion, setNewRuntimeRegion] = useState<string>(
    defaultCloudRegion(cloudProvider),
  );
  const [focusedDeploymentTaskId, setFocusedDeploymentTaskId] = useState("");
  const [focusedWorkspaceAgentId, setFocusedWorkspaceAgentId] = useState("");
  const [agentDetailTarget, setAgentDetailTarget] =
    useState<MyAgentCardData | null>(null);
  const exitAgentDetailContext = useCallback(() => {
    popStudioPage("agent-detail");
    setAgentDetailTarget(null);
    setMyAgents(false);
    setManageAgents(false);
  }, [popStudioPage]);
  // Shown when the user clicks the breadcrumb root to leave a create mode;
  // warns that the in-progress draft will be discarded.
  const [confirmLeave, setConfirmLeave] = useState(false);
  // Restore the previously-open session only once, after apps/user resolve.
  const restoredRef = useRef(false);
  const agentSelectionClearedRef = useRef(false);

  const commitWorkspaceDrafts = useCallback(
    (next: WorkspaceAgentDraft[]): boolean => {
      if (!userId) return false;
      try {
        writeWorkspaceDrafts(localStorage, userId, next);
      } catch (cause) {
        setDraftStorageError(
          cause instanceof Error ? cause.message : "浏览器拒绝保存草稿，请稍后重试。",
        );
        return false;
      }
      savedAgentDraftsRef.current = next;
      setSavedAgentDrafts(next);
      setDraftStorageError("");
      return true;
    },
    [userId],
  );

  const cancelPendingWorkspaceDraft = useCallback((id?: string) => {
    if (id && pendingWorkspaceDraftRef.current?.id !== id) return;
    pendingWorkspaceDraftRef.current = null;
    if (workspaceDraftTimerRef.current !== null) {
      window.clearTimeout(workspaceDraftTimerRef.current);
      workspaceDraftTimerRef.current = null;
    }
  }, []);

  const flushPendingWorkspaceDraft = useCallback((): boolean => {
    const pending = pendingWorkspaceDraftRef.current;
    if (!pending) return true;
    const committed = commitWorkspaceDrafts([
      pending,
      ...savedAgentDraftsRef.current.filter((item) => item.id !== pending.id),
    ]);
    if (committed) cancelPendingWorkspaceDraft();
    return committed;
  }, [cancelPendingWorkspaceDraft, commitWorkspaceDrafts]);

  const saveWorkspaceDraft = useCallback(
    (
      id: string,
      draft: AgentDraft,
      deploymentTarget?: WorkspaceAgentDraft["deploymentTarget"],
      creationMode?: WorkspaceAgentDraft["creationMode"],
    ) => {
      if (!id || !userId) return;
      if (
        pendingWorkspaceDraftRef.current &&
        pendingWorkspaceDraftRef.current.id !== id
      ) {
        flushPendingWorkspaceDraft();
      }
      pendingWorkspaceDraftRef.current = {
        id,
        draft,
        updatedAt: Date.now(),
        deploymentTarget,
        creationMode,
      };
      if (workspaceDraftTimerRef.current !== null) {
        window.clearTimeout(workspaceDraftTimerRef.current);
      }
      workspaceDraftTimerRef.current = window.setTimeout(
        flushPendingWorkspaceDraft,
        DRAFT_AUTOSAVE_DELAY_MS,
      );
    },
    [flushPendingWorkspaceDraft, userId],
  );

  const removeWorkspaceDraft = useCallback((id: string) => {
    if (!id || !userId) return;
    cancelPendingWorkspaceDraft(id);
    commitWorkspaceDrafts(
      savedAgentDraftsRef.current.filter((item) => item.id !== id),
    );
  }, [cancelPendingWorkspaceDraft, commitWorkspaceDrafts, userId]);

  const deleteWorkspaceDrafts = useCallback((draftsToDelete: WorkspaceAgentDraft[]) => {
    if (!userId || draftsToDelete.length === 0) return;
    const deletedDraftIds = new Set(draftsToDelete.map((item) => item.id));
    if (
      pendingWorkspaceDraftRef.current &&
      deletedDraftIds.has(pendingWorkspaceDraftRef.current.id)
    ) {
      cancelPendingWorkspaceDraft();
    }
    commitWorkspaceDrafts(
      savedAgentDraftsRef.current.filter((item) => !deletedDraftIds.has(item.id)),
    );
    setDraftDeploymentTaskIds((current) => Object.fromEntries(
      Object.entries(current).filter(([id]) => !deletedDraftIds.has(id)),
    ));
    if (deletedDraftIds.has(editingDraftId)) {
      setEditingDraftId("");
      setImportedDraft(null);
      setRuntimeUpdateTarget(null);
      editingDraftBaselineRef.current = null;
      localStorage.removeItem(activeWorkspaceDraftKey(userId));
    }
  }, [cancelPendingWorkspaceDraft, commitWorkspaceDrafts, editingDraftId, userId]);

  const restoreWorkspaceDraftBaseline = useCallback((id: string) => {
    if (!id || !userId) return;
    cancelPendingWorkspaceDraft(id);
    const baseline = editingDraftBaselineRef.current;
    const remaining = savedAgentDraftsRef.current.filter((item) => item.id !== id);
    commitWorkspaceDrafts(
      baseline?.id === id ? [baseline, ...remaining] : remaining,
    );
  }, [cancelPendingWorkspaceDraft, commitWorkspaceDrafts, userId]);

  useEffect(() => {
    window.addEventListener("pagehide", flushPendingWorkspaceDraft);
    return () => {
      window.removeEventListener("pagehide", flushPendingWorkspaceDraft);
    };
  }, [flushPendingWorkspaceDraft]);

  useEffect(() => {
    if (!userId) {
      cancelPendingWorkspaceDraft();
      savedAgentDraftsRef.current = [];
      setSavedAgentDrafts([]);
      setWorkspaceAgentOrder([]);
      setEditingDraftId("");
      setDraftStorageError("");
      editingDraftBaselineRef.current = null;
      return;
    }
    let nextDrafts: WorkspaceAgentDraft[] = [];
    let activeId = "";
    try {
      nextDrafts = loadWorkspaceDrafts(localStorage, userId);
      if (localStorage.getItem(workspaceDraftsKey(userId)) !== null) {
        writeWorkspaceDrafts(localStorage, userId, nextDrafts);
      }
      activeId = localStorage.getItem(activeWorkspaceDraftKey(userId)) || "";
      setDraftStorageError("");
    } catch (cause) {
      setDraftStorageError(
        cause instanceof Error ? cause.message : "无法读取本机草稿，请稍后重试。",
      );
    }
    savedAgentDraftsRef.current = nextDrafts;
    setSavedAgentDrafts(nextDrafts);
    setWorkspaceAgentOrder(loadWorkspaceAgentOrder(userId));
    const activeDraft = nextDrafts.find((item) => item.id === activeId);
    editingDraftBaselineRef.current = activeDraft ?? null;
    if (createView === "custom" && activeDraft) {
      setEditingDraftId(activeDraft.id);
      setImportedDraft(activeDraft.draft);
      setCustomCreationSurface(
        workspaceAgentCreationMode(activeDraft) === "quick"
          ? "vulcan"
          : "traditional",
      );
      setRuntimeUpdateTarget(activeDraft.deploymentTarget ?? null);
    }
    // Restore only when identity changes; later edits are already in state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cancelPendingWorkspaceDraft, userId]);

  useEffect(() => {
    if (!userId) return;
    const key = activeWorkspaceDraftKey(userId);
    try {
      if (createView === "custom" && editingDraftId) {
        localStorage.setItem(key, editingDraftId);
      } else {
        localStorage.removeItem(key);
      }
    } catch {
      setDraftStorageError(
        "浏览器拒绝保存当前草稿位置，请检查站点存储权限后重试。",
      );
    }
  }, [createView, editingDraftId, userId]);

  const saveWorkspaceAgentOrder = useCallback((nextOrder: string[]) => {
    if (!userId) return;
    const deduped = [...new Set(nextOrder.filter(Boolean))];
    setWorkspaceAgentOrder(deduped);
    localStorage.setItem(workspaceAgentOrderKey(userId), JSON.stringify(deduped));
  }, [userId]);

  const deleteWorkspaceAgents = useCallback(async (agentsToDelete: AgentEntry[]) => {
    const targets = agentsToDelete.filter(
      (agent): agent is AgentEntry & { runtimeId: string } =>
        Boolean(agent.runtimeId) && agent.canDelete === true,
    );
    if (targets.length === 0) return;

    const selectedRuntimeId = runtimeIdForSelection(connections, appName);
    const pendingRuntimeIds = new Set(targets.map((agent) => agent.runtimeId));
    setHiddenRuntimeIds((current) => {
      const next = new Set(current);
      for (const runtimeId of pendingRuntimeIds) next.add(runtimeId);
      return next;
    });
    invalidateRuntimeAgentCache(pendingRuntimeIds);

    const deletedRuntimeIds = new Set<string>();
    const deletedAgentIds = new Set<string>();
    const failedRuntimeIds = new Set<string>();
    const failures: string[] = [];
    for (const agent of targets) {
      try {
        if (!agent.region) throw new Error("Runtime 缺少地域信息，无法删除");
        await deleteRuntime(agent.runtimeId, agent.region);
        removeRuntimeConnection(agent.runtimeId);
        deletedRuntimeIds.add(agent.runtimeId);
        deletedAgentIds.add(agent.id);
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : String(cause);
        failedRuntimeIds.add(agent.runtimeId);
        failures.push(`${agent.label}: ${message}`);
      }
    }

    if (deletedRuntimeIds.size > 0) {
      invalidateRuntimeAgentCache(deletedRuntimeIds);
      setConnections(loadConnections());
      setLibraryRuntimeIds((current) => {
        if (!current) return current;
        const next = new Set(current);
        for (const runtimeId of deletedRuntimeIds) next.delete(runtimeId);
        return next;
      });
      setLibraryRuntimePermissions((current) =>
        Object.fromEntries(
          Object.entries(current).filter(([runtimeId]) => !deletedRuntimeIds.has(runtimeId)),
        ),
      );
      setWorkspaceAgentOrder((current) => {
        const next = current.filter((id) => !deletedAgentIds.has(id));
        if (userId) {
          localStorage.setItem(workspaceAgentOrderKey(userId), JSON.stringify(next));
        }
        return next;
      });
      commitWorkspaceDrafts(
        savedAgentDraftsRef.current.filter(
          (item) =>
            !item.deploymentTarget?.runtimeId ||
            !deletedRuntimeIds.has(item.deploymentTarget.runtimeId),
        ),
      );
      const deletedCurrentSelection = selectedRuntimeId
        ? deletedRuntimeIds.has(selectedRuntimeId)
        : targets.some((agent) => agent.id === appName);
      if (deletedCurrentSelection) {
        clearSelectedAgentAfterRemoval();
        setCreateView(null);
        setSkillCenter(false);
        setAddAgent(false);
        setAddMenu(false);
        setSearchView(false);
        setManageAgents(false);
        setAgentDetailTarget(null);
        setFocusedDeploymentTaskId("");
        setFocusedWorkspaceAgentId("");
        setMyAgents(true);
        setError("");
      }
      if (
        agentDetailTarget?.runtime &&
        deletedRuntimeIds.has(agentDetailTarget.runtime.runtimeId)
      ) {
        setCreateView(null);
        setSkillCenter(false);
        setAddAgent(false);
        setAddMenu(false);
        setSearchView(false);
        exitAgentDetailContext();
        setFocusedDeploymentTaskId("");
        setFocusedWorkspaceAgentId("");
        setMyAgents(true);
        setError("");
      }
    }

    if (failedRuntimeIds.size > 0) {
      setHiddenRuntimeIds((current) => {
        const next = new Set(current);
        for (const runtimeId of failedRuntimeIds) next.delete(runtimeId);
        return next;
      });
    }

    if (failures.length > 0) {
      const shown = failures.slice(0, 3).join("；");
      const suffix = failures.length > 3 ? `；另有 ${failures.length - 3} 个失败` : "";
      throw new Error(`${failures.length} 个 Agent 删除失败：${shown}${suffix}`);
    }
  }, [agentDetailTarget, appName, commitWorkspaceDrafts, connections, exitAgentDetailContext, userId]);

  const refreshAgentLibrary = useCallback(async () => {
    setAgentLibraryLoading(true);
    setAgentLibraryError("");
    try {
      const runtimes: CloudRuntime[] = [];
      let nextToken = "";
      do {
        const page = await getRuntimes({
          scope: grantedRuntimeScope,
          region: "all",
          pageSize: 100,
          nextToken,
        });
        runtimes.push(...page.runtimes);
        nextToken = page.nextToken;
      } while (nextToken && runtimes.length < 2000);

      setLibraryRuntimeIds(new Set(runtimes.map((runtime) => runtime.runtimeId)));
      setLibraryRuntimePermissions(
        Object.fromEntries(
          runtimes.map((runtime) => [
            runtime.runtimeId,
            { canDelete: runtime.canDelete },
          ]),
        ),
      );
    } catch (cause) {
      setAgentLibraryError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setAgentLibraryLoading(false);
    }
  }, [grantedRuntimeScope]);

  // Placeholder: persisting/registering the created agent is a follow-up.
  function onCreate(draft: AgentDraft) {
    console.log("create agent draft:", draft);
    setCreateView(null);
    startNewChat();
  }

  // Navigate to a newly added agent: switch app, close create view, start fresh chat.
  function onAgentAdded(agentId: string, agentName: string) {
    console.log("Agent added, navigating to:", agentId, agentName);
    setConnections(loadConnections()); // Refresh connections to pick up the new agent
    setLibraryRuntimeIds(null);
    invalidateRuntimeAgentCache();
    removeWorkspaceDraft(editingDraftId);
    setEditingDraftId("");
    editingDraftBaselineRef.current = null;
    setRuntimeUpdateTarget(null);
    setFocusedDeploymentTaskId("");
    setFocusedWorkspaceAgentId(agentId);
    setFocusedWorkspaceAgentSection("basic");
    setCreateView(null);
    setManageAgents(true);
    setAppName(agentId);
    // startNewChat will be called automatically by the appName change effect
  }

  const openDeploymentDetail = useCallback((task: DeploymentTaskUpdate) => {
    setCreateView(null);
    setAddMenu(false);
    exitAgentDetailContext();
    setManageAgents(true);
    setFocusedWorkspaceAgentId("");
    setFocusedWorkspaceAgentSection("basic");
    setFocusedDeploymentTaskId(task.id);
    setError("");
  }, [exitAgentDetailContext]);

  const startDeployment = useCallback((task: DeploymentTaskUpdate) => {
    flushPendingWorkspaceDraft();
    const linkedTask = editingDraftId
      ? { ...task, draftId: editingDraftId }
      : task;
    if (editingDraftId) {
      setDraftDeploymentTaskIds((current) => ({
        ...current,
        [editingDraftId]: task.id,
      }));
    }
    updateDeploymentTask(linkedTask);
    openDeploymentDetail(linkedTask);
  }, [editingDraftId, flushPendingWorkspaceDraft, openDeploymentDetail, updateDeploymentTask]);

  const finishDeployment = useCallback(
    async (result: DeployResult) => {
      if (!result.runtimeId) throw new Error("部署完成，但未返回 Runtime ID。");
      const completedDraftId = editingDraftId;
      if (completedDraftId) {
        removeWorkspaceDraft(completedDraftId);
        setDraftDeploymentTaskIds((current) => {
          if (!current[completedDraftId]) return current;
          const next = { ...current };
          delete next[completedDraftId];
          return next;
        });
      }
      setEditingDraftId("");
      editingDraftBaselineRef.current = null;
      setRuntimeUpdateTarget(null);
      const fallbackRegion = runtimeUpdateTarget?.region ?? newRuntimeRegion;
      const agentId = await connectRuntime(
        result.runtimeId,
        result.runtimeName,
        result.region ?? fallbackRegion,
        result.version,
        { waitForReady: true, agentName: result.agentName },
      );
      setConnections(loadConnections());
      setAgentInfoRefreshKey((key) => key + 1);
      const capabilities = await probeNewChatCapabilities(agentId);
      newChatCapabilitiesCacheRef.current.set(agentId, capabilities);
      setNewChatCapabilities(capabilities);
      setLibraryRuntimeIds((current) => {
        const next = new Set(current ?? []);
        next.add(result.runtimeId!);
        return next;
      });
      invalidateRuntimeAgentCache();
      setFocusedWorkspaceAgentId(agentId);
      setFocusedWorkspaceAgentSection("basic");
      setFocusedDeploymentTaskId("");
      setCreateView(null);
      setManageAgents(true);
      setAppName(agentId);
    },
    [editingDraftId, newRuntimeRegion, removeWorkspaceDraft, runtimeUpdateTarget],
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  const turnNodeRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const responseAnnotationSelectionIdRef = useRef(0);
  const responseAnnotationContextsRef = useRef<
    Map<number, ResponseAnnotationContext>
  >(new Map());
  const responseAnnotationRuntimeAvailable = connections.some(
    (connection) =>
      Boolean(connection.runtimeId && connection.region) &&
      connection.apps.some((app) => remoteAppId(connection.id, app) === appName),
  );
  useLayoutEffect(() => {
    const contexts = new Map<number, ResponseAnnotationContext>();
    turns.forEach((turn, index) => {
      const feedbackEventId = turn.meta?.eventId ?? "";
      const canRate = Boolean(
        responseAnnotationRuntimeAvailable && feedbackEventId && turnText(turn),
      );
      const turnIsStreaming = index === turns.length - 1 && (
        activeConversationBusy || presentingStream
      );
      contexts.set(index, {
        enabled: Boolean(
          canRate &&
          cloudProvider !== "byteplus" &&
          !turnIsStreaming &&
          !turnAwaitingAuth(turn)
        ),
        turn,
        input: canRate ? previousUserTurnText(turns, index) : "",
      });
    });
    responseAnnotationContextsRef.current = contexts;
  }, [
    activeConversationBusy,
    cloudProvider,
    presentingStream,
    responseAnnotationRuntimeAvailable,
    turns,
  ]);
  const openResponseAnnotation = useCallback(() => {
    const selection = window.getSelection();
    const anchorElement = selection?.anchorNode instanceof Element
      ? selection.anchorNode
      : selection?.anchorNode?.parentElement;
    const container = anchorElement?.closest<HTMLDivElement>(".turn--assistant");
    if (!container) return;
    const turnIndex = Number(container.dataset.responseAnnotationIndex);
    if (!Number.isInteger(turnIndex)) return;
    const context = responseAnnotationContextsRef.current.get(turnIndex);
    if (!context?.enabled) return;
    const selected = responseSelectionWithin(container, selection);
    if (!selected) return;
    setResponseAnnotationTarget({
      selectionId: ++responseAnnotationSelectionIdRef.current,
      turn: context.turn,
      input: context.input,
      selectedText: selected.text,
      anchor: selected.anchor,
    });
  }, []);
  useEffect(() => {
    let selectionFrame: number | null = null;
    const queueSelection = (event: MouseEvent | KeyboardEvent) => {
      if (
        event.target instanceof Element &&
        event.target.closest(".response-annotation-popover")
      ) {
        return;
      }
      if (selectionFrame !== null) window.cancelAnimationFrame(selectionFrame);
      selectionFrame = window.requestAnimationFrame(() => {
        selectionFrame = null;
        openResponseAnnotation();
      });
    };
    document.addEventListener("mouseup", queueSelection, true);
    document.addEventListener("keyup", queueSelection, true);
    return () => {
      if (selectionFrame !== null) window.cancelAnimationFrame(selectionFrame);
      document.removeEventListener("mouseup", queueSelection, true);
      document.removeEventListener("keyup", queueSelection, true);
    };
  }, [openResponseAnnotation]);
  const conversationAutoFollowRef = useRef(true);
  const conversationSmoothScrollRef = useRef(false);
  const conversationSmoothTimerRef = useRef<number | null>(null);
  const conversationScrollStateRef = useRef({ key: "", turnCount: 0 });
  const conversationScrollKey = sandboxSession?.id ?? sessionId;
  useLayoutEffect(() => {
    const el = scrollRef.current;
    const previous = conversationScrollStateRef.current;
    const conversationChanged = previous.key !== conversationScrollKey;
    const turnAppended = !conversationChanged && turns.length > previous.turnCount;
    conversationScrollStateRef.current = {
      key: conversationScrollKey,
      turnCount: turns.length,
    };
    if (!el || turns.length === 0 || (!conversationChanged && !turnAppended)) return;

    conversationAutoFollowRef.current = true;
    conversationSmoothScrollRef.current = false;
    if (conversationSmoothTimerRef.current !== null) {
      window.clearTimeout(conversationSmoothTimerRef.current);
      conversationSmoothTimerRef.current = null;
    }

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (conversationChanged || reduceMotion) {
      el.scrollTop = el.scrollHeight;
      return;
    }

    conversationSmoothScrollRef.current = true;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    conversationSmoothTimerRef.current = window.setTimeout(() => {
      conversationSmoothScrollRef.current = false;
      conversationSmoothTimerRef.current = null;
      const current = scrollRef.current;
      if (current && conversationAutoFollowRef.current) {
        current.scrollTop = current.scrollHeight;
      }
    }, 450);
  }, [conversationScrollKey, turns.length]);
  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (
      !el ||
      !conversationAutoFollowRef.current ||
      conversationSmoothScrollRef.current
    ) return;
    el.scrollTop = el.scrollHeight;
  }, [activeConversationBusy, turns]);
  useEffect(() => {
    if (!feedbackTargetEventId || manageAgents || turns.length === 0) return;
    const node = turnNodeRefs.current.get(feedbackTargetEventId);
    if (!node) return;
    conversationAutoFollowRef.current = false;
    node.scrollIntoView({ behavior: "smooth", block: "center" });
    const timer = window.setTimeout(() => {
      setFeedbackTargetEventId("");
    }, 2600);
    return () => window.clearTimeout(timer);
  }, [feedbackTargetEventId, manageAgents, turns]);
  useEffect(() => () => {
    if (conversationSmoothTimerRef.current !== null) {
      window.clearTimeout(conversationSmoothTimerRef.current);
    }
  }, []);
  const onConversationScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el || conversationSmoothScrollRef.current) return;
    conversationAutoFollowRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < 32;
  }, []);
  const onConversationWheel = useCallback((event: WheelEvent<HTMLDivElement>) => {
    if (event.deltaY < 0) {
      conversationSmoothScrollRef.current = false;
      conversationAutoFollowRef.current = false;
    }
  }, []);
  const onConversationTouchMove = useCallback(() => {
    conversationSmoothScrollRef.current = false;
    conversationAutoFollowRef.current = false;
  }, []);
  const followConversationStreamFrame = useCallback(() => {
    const el = scrollRef.current;
    if (
      !el ||
      !conversationAutoFollowRef.current ||
      conversationSmoothScrollRef.current
    ) return;
    el.scrollTop = el.scrollHeight;
  }, []);

  // Resolve SSO identity first; it provides the ADK user_id.
  const resolveAuth = useCallback(() => {
    setAuthError(null);
    resolveIdentity()
      .then((id) => {
        setUserId(id.userId);
        setUserInfo(id.info);
        setLocalMode(!!id.local);
        setAuthStatus(id.status);
        if (id.status === "authenticated") {
          restoredRef.current = true;
          agentSelectionClearedRef.current = true;
          localStorage.removeItem(LS.app);
          setAppName("");
          setCreateView(null);
          setSkillCenter(false);
          setAddAgent(false);
          setAddMenu(false);
          setSearchView(false);
          setManageAgents(false);
          setMyAgents(false);
        }
      })
      .catch((error) => {
        setAuthError(error instanceof Error ? error.message : String(error));
      });
  }, []);
  useEffect(() => {
    resolveAuth();
  }, [resolveAuth]);

  useEffect(() => {
    const showExpiredDialog = () => {
      setAuthRecoveryError("");
      setAuthExpired(true);
    };
    window.addEventListener(AUTHENTICATION_REQUIRED_EVENT, showExpiredDialog);
    if (isAuthenticationPending()) showExpiredDialog();
    return () =>
      window.removeEventListener(
        AUTHENTICATION_REQUIRED_EVENT,
        showExpiredDialog,
      );
  }, []);

  const recoverAuthentication = useCallback(async () => {
    if (authRecoveryActiveRef.current) return;
    authRecoveryActiveRef.current = true;
    const loginWindow = openLoginWindow();
    if (!loginWindow) {
      authRecoveryActiveRef.current = false;
      setAuthRecoveryError("登录窗口被浏览器拦截，请允许弹出窗口后重试。");
      return;
    }
    setAuthRecoveryChecking(true);
    setAuthRecoveryError("");
    try {
      while (true) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        try {
          const identity = await resolveIdentity();
          if (identity.status === "authenticated") {
            setUserId(identity.userId);
            setUserInfo(identity.info);
            setLocalMode(!!identity.local);
            setAuthStatus(identity.status);
            setAuthExpired(false);
            authenticationRestored();
            loginWindow.close();
            return;
          }
        } catch {
          // The gateway may return its login page until the popup completes.
        }
        if (loginWindow.closed) {
          setAuthRecoveryError("登录窗口已关闭，请重新登录以继续当前操作。");
          return;
        }
      }
    } finally {
      authRecoveryActiveRef.current = false;
      setAuthRecoveryChecking(false);
    }
  }, []);

  useEffect(() => {
    if (localMode && userId) setLocalUser(userId);
  }, [localMode, userId]);

  useEffect(() => {
    if (authStatus !== "authenticated" || !userId || intelligentDeployment) return;
    const query = new URLSearchParams(window.location.search);
    if (
      query.get("view") !== "runtime-deploy" ||
      query.get("source") !== "intelligent-development"
    ) return;
    const sessionId = query.get("sessionId") ?? "";
    const artifactSha256 = query.get("artifactSha256") ?? "";
    const validationReportSha256 = query.get("validationReportSha256") ?? "";
    const projectId = query.get("projectId") ?? "";
    const versionId = query.get("versionId") ?? "";
    if (!sessionId || !artifactSha256 || !validationReportSha256) return;
    const controller = new AbortController();
    const load = projectId && versionId
      ? fetchIntelligentDevelopmentProjectRelease(
          projectId,
          versionId,
          sessionId,
          artifactSha256,
          validationReportSha256,
          controller.signal,
        )
      : fetchIntelligentDevelopmentRelease(
          sessionId,
          artifactSha256,
          validationReportSha256,
          controller.signal,
        );
    void load
      .then((delivery) => {
        if (controller.signal.aborted) return;
        if (!delivery.deployable) {
          setIntelligentCapabilitiesError(
            "该源码尚未准备好，请返回对话继续处理。",
          );
          return;
        }
        setIntelligentDeploymentState({
          ...delivery,
          validatedAt: delivery.validatedAt || "",
          gateSummary: delivery.gateSummary || [],
        });
      })
      .catch((cause) => {
        if (!controller.signal.aborted) {
          setIntelligentCapabilitiesError(
            cause instanceof Error ? cause.message : String(cause),
          );
        }
      });
    return () => controller.abort();
  }, [authStatus, intelligentDeployment, userId]);

  useEffect(() => {
    if (!addMenu && !["intelligent", "migration"].includes(createView ?? "")) return;
    if (authStatus !== "authenticated" || !userId) {
      setIntelligentCapabilities(null);
      setIntelligentCapabilitiesError("");
      setIntelligentCapabilitiesLoading(true);
      return;
    }
    const controller = new AbortController();
    setIntelligentCapabilitiesLoading(true);
    setIntelligentCapabilitiesError("");
    void fetch(withAuth("/web/intelligent-development/capabilities"), {
      headers: withLocalUser({ Accept: "application/json" }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(`智能开发能力检查失败（HTTP ${response.status}）`);
        return response.json() as Promise<{
          enabled?: unknown;
          reason?: unknown;
          model?: unknown;
          projectStorageEnabled?: unknown;
          projectStorageReason?: unknown;
        }>;
      })
      .then((value) => {
        if (controller.signal.aborted) return;
        const capability: IntelligentDevelopmentCapabilities = {
          enabled: value.enabled === true,
          reason: typeof value.reason === "string" ? value.reason : "",
          projectStorageEnabled: value.projectStorageEnabled === true,
          projectStorageReason: typeof value.projectStorageReason === "string"
            ? value.projectStorageReason
            : "",
        };
        if (value.model !== undefined) {
          if (typeof value.model !== "object" || value.model === null) {
            throw new Error("智能开发模型能力格式错误。");
          }
          const model = value.model as { configured?: unknown; id?: unknown };
          if (typeof model.configured === "boolean" && typeof model.id === "string") {
            capability.model = {
              configured: model.configured,
              id: model.id,
            };
          } else {
            throw new Error("智能开发模型能力格式错误。");
          }
        }
        setIntelligentCapabilities(capability);
      })
      .catch((cause) => {
        if (!controller.signal.aborted) {
          setIntelligentCapabilitiesError(
            cause instanceof Error ? cause.message : String(cause),
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIntelligentCapabilitiesLoading(false);
      });
    return () => controller.abort();
  }, [addMenu, authStatus, createView, userId]);

  useEffect(() => {
    if (authStatus !== "authenticated" || !userId) {
      setNewChatCapabilities({});
      return;
    }
    const preparedSelection = preparedAgentSelectionRef.current;
    if (
      preparedSelection?.agentId === appName &&
      preparedSelection.userId === userId
    ) {
      return;
    }
    const cached = newChatCapabilitiesCacheRef.current.get(appName);
    if (cached) {
      setNewChatCapabilities(cached);
      return;
    }
    let cancelled = false;
    setNewChatCapabilities({});
    void probeNewChatCapabilities(appName).then((capabilities) => {
      if (cancelled) return;
      newChatCapabilitiesCacheRef.current.set(appName, capabilities);
      setNewChatCapabilities(capabilities);
    });
    return () => {
      cancelled = true;
    };
  }, [appName, authStatus, userId]);

  useLayoutEffect(() => {
    if (
      !newChatCapabilitiesReady ||
      newChatCapabilities.skillCustomizationEnabled !== false ||
      newChatWorkspaceMode !== "skill"
    ) return;
    setNewChatWorkspaceMode("agent");
    setNewChatSkillTarget(null);
    setNewChatTask(null);
  }, [
    newChatCapabilities.skillCustomizationEnabled,
    newChatCapabilitiesReady,
    newChatWorkspaceMode,
  ]);

  useEffect(() => {
    if (authStatus !== "authenticated" || !userId) {
      setAccess(null);
      return;
    }
    let cancelled = false;
    setAccess(null);
    getStudioAccess()
      .then((next) => {
        if (!cancelled) setAccess(next);
      })
      .catch((error) => {
        console.warn("[app] /web/access failed; using ordinary-user access:", error);
        if (!cancelled) setAccess(DEFAULT_STUDIO_ACCESS);
      });
    return () => {
      cancelled = true;
    };
  }, [authStatus, userId]);

  // Load per-module feature gates. Authenticated users always enter a fresh
  // chat; privileged pages remain explicit navigation destinations.
  useEffect(() => {
    getUiConfig().then((cfg) => {
      const environment = import.meta.env.MODE === "development"
        ? "dev"
        : import.meta.env.MODE === "staging"
        ? "staging"
        : "prod";
      void initTelemetry({ enabled: cfg.telemetry.enabled, environment });
      const studio = cfg.telemetry.studio;
      setTelemetryContext({
        userPoolId: studio?.userPoolId ?? "",
        studioDeployId: studio?.deployId ?? "",
        applicationId: studio?.applicationId ?? "",
        functionId: studio?.functionId ?? "",
        studioRegion: studio?.region ?? "",
        studioProject: studio?.project ?? "",
        studioVersion: studio?.version || cfg.version,
        environment,
        cloudProvider: cfg.provider,
        accountId: studio?.accountId ?? "",
        accountIdResolutionError: studio?.accountIdResolutionError ?? "",
      });
      trackStudioEntryViewed({ authState: "anonymous" });
      setFeatures(cfg.features);
      setAgentsSource(cfg.agentsSource);
      setCloudProvider(cfg.provider);
      setStudioRegion(studio?.region || defaultCloudRegion(cfg.provider));
      setSiteBranding(cfg.branding);
      setVersion(cfg.version);
      setUiConfigLoaded(true);
    });
  }, []);

  useEffect(() => {
    if (
      authStatus !== "authenticated" ||
      !userInfo ||
      !access ||
      !uiConfigLoaded
    ) return;
    const userUniqueId = String(access.telemetry.userId).trim();
    if (!userUniqueId) return;
    identifyTelemetryUser({
      userUniqueId,
      accountId: access.telemetry.accountId ?? "",
      userRole: access.role === "admin" ? "admin" : "member",
      userSource: localMode ? "local" : "sso",
    });
    trackStudioSessionStarted({ agentsSource });
  }, [access, agentsSource, authStatus, localMode, uiConfigLoaded, userInfo]);

  useEffect(() => {
    setNewRuntimeRegion((region) => {
      const providerDefault = defaultCloudRegion(cloudProvider);
      if (!region) return providerDefault;
      if (cloudProvider === "byteplus" && region.startsWith("cn-")) {
        return providerDefault;
      }
      if (cloudProvider === "volcengine" && region.startsWith("ap-")) {
        return providerDefault;
      }
      return region;
    });
  }, [cloudProvider]);

  useEffect(() => {
    if (!access) return;
    if (!access.capabilities.createAgents) {
      setCreateView(null);
      setImportedDraft(null);
      setAddAgent(false);
      setAddMenu(false);
      setDeploymentTasks([]);
    }
    if (!access.capabilities.manageAgents) setManageAgents(false);
  }, [access]);

  let documentTitleTarget: StudioDocumentTitleTarget = { kind: "home" };
  if (authStatus === "authenticated") {
    if (platformFeedbackOrigin !== null) {
      documentTitleTarget = { kind: "page", title: "问题反馈" };
    } else if (systemInfo) {
      documentTitleTarget = { kind: "page", title: "系统信息" };
    } else if (cronJobsView) {
      documentTitleTarget = { kind: "page", title: "定时任务" };
    } else if (applicationsView) {
      documentTitleTarget = {
        kind: "page",
        title: applicationsView === "catalog"
          ? "自动化"
          : getAutomation(applicationsView).name,
      };
    } else if (sandboxAgentWorkspace) {
      documentTitleTarget = {
        kind: "page",
        title: sandboxAgentWorkspace.session.displayName || "智能体",
      };
    } else if (sandboxAgentDetailTarget) {
      documentTitleTarget = {
        kind: "page",
        title: sandboxAgentDetailTarget.displayName || "智能体",
      };
    } else if (myAgents || manageAgents) {
      documentTitleTarget = {
        kind: "page",
        title: agentDetailTarget?.name || "智能体",
      };
    } else if (addMenu) {
      documentTitleTarget = { kind: "page", title: "创建智能体" };
    } else if (searchView) {
      documentTitleTarget = { kind: "page", title: "搜索" };
    } else if (addAgent) {
      documentTitleTarget = { kind: "page", title: "添加智能体" };
    } else if (skillCenter) {
      documentTitleTarget = {
        kind: "page",
        title: libraryPageTitle || "资源库",
      };
    } else if (createView) {
      documentTitleTarget = {
        kind: "page",
        title: createView === "custom"
          ? runtimeUpdateTarget?.name
            ? `更新 ${runtimeUpdateTarget.name}`
            : "创建智能体"
          : createView === "package"
            ? "从代码包添加"
            : "迁移智能体",
      };
    } else if (sandboxSession) {
      const activeThread = sandboxCommands.threads.find(
        (thread) => thread.id === sandboxSession.threadId,
      );
      documentTitleTarget = {
        kind: "conversation",
        title: activeThread?.name
          || activeThread?.preview
          || sandboxSession.displayName,
      };
    } else if (sessionId) {
      const activeSession = sessions.find((session) => session.id === sessionId);
      const activeSessionTitle = sessionTitle(activeSession?.events);
      documentTitleTarget = activeSessionTitle === "新会话"
        ? { kind: "home" }
        : { kind: "conversation", title: activeSessionTitle };
    }
  }
  const studioDocumentTitle = formatStudioDocumentTitle(
    siteBranding.title,
    documentTitleTarget,
  );

  useEffect(() => {
    if (
      authStatus !== "authenticated" ||
      agentsSource !== "cloud" ||
      !uiConfigLoaded ||
      !manageAgents ||
      agentDetailTarget
    ) {
      return;
    }
    void refreshAgentLibrary();
  }, [agentDetailTarget, agentsSource, authStatus, manageAgents, refreshAgentLibrary, uiConfigLoaded]);

  useEffect(() => {
    document.title = studioDocumentTitle;
    let favicon = document.querySelector<HTMLLinkElement>('link[rel~="icon"]');
    if (!favicon) {
      favicon = document.createElement("link");
      favicon.rel = "icon";
      document.head.appendChild(favicon);
    }
    favicon.removeAttribute("type");
    favicon.href = siteBranding.logoUrl
      || (cloudProvider === "byteplus" ? byteplusLogo : defaultSiteLogo);
  }, [cloudProvider, siteBranding.logoUrl, studioDocumentTitle]);

  // Check whether the server has cloud AK/SK (needed by the workbench).
  useEffect(() => {
    fetch("/web/runtime-config", { signal: AbortSignal.timeout(10_000) })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) setHasCreds(!!d.credentials);
      })
      .catch((error) => {
        console.warn("[app] /web/runtime-config probe failed; workbench stays hidden:", error);
      });
  }, []);

  function onUsername(name: string) {
    setLocalUser(name);
    // A completed login is a fresh entry into the app. Do not reveal a create
    // or management view that was persisted before the login page appeared.
    restoredRef.current = true;
    agentSelectionClearedRef.current = true;
    localStorage.removeItem(LS.app);
    setAccess(null);
    setCreateView(null);
    setImportedDraft(null);
    setSkillCenter(false);
    setAddAgent(false);
    setAddMenu(false);
    setSearchView(false);
    setManageAgents(false);
    startNewChat();
    setAppName("");
    setMyAgents(false);
    setUserId(name);
    setUserInfo({ name });
    setLocalMode(true);
    setAuthStatus("authenticated");
  }

  function onLogout() {
    setAccess(null);
    if (localMode) {
      clearLocalUser();
      setUserId("");
      setUserInfo(undefined);
      setAuthStatus("unauthenticated");
    } else {
      logout();
    }
  }

  useEffect(() => {
    if (authStatus !== "authenticated") return;
    if (agentsSource === "cloud") {
      const remoteIds = remoteSelectionIds(connections);
      setAppName((current) => {
        if (current && remoteIds.includes(current)) return current;
        if (current) {
          agentSelectionClearedRef.current = true;
          localStorage.removeItem(LS.app);
          return "";
        }
        return "";
      });
      return;
    }
    listApps()
      .then((list) => {
        setApps(list);
        const remoteIds = remoteSelectionIds(connections);
        setAppName((current) => {
          if (current && (list.includes(current) || remoteIds.includes(current))) {
            return current;
          }
          if (current) {
            agentSelectionClearedRef.current = true;
            localStorage.removeItem(LS.app);
          }
          return "";
        });
      })
      .catch((e) => setError(String(e)));
  }, [authStatus, agentsSource, connections]);

  // Persist the current view/agent/session so a refresh restores them.
  useEffect(() => {
    if (appName) {
      agentSelectionClearedRef.current = false;
      localStorage.setItem(LS.app, appName);
    } else {
      localStorage.removeItem(LS.app);
    }
  }, [appName]);
  useEffect(() => {
    const preparedSelection = preparedAgentSelectionRef.current;
    if (
      preparedSelection?.agentId === appName &&
      preparedSelection.userId === userId
    ) {
      setCapabilitiesLoading(false);
      return;
    }
    let cancelled = false;
    setAgentInfo(null);
    setInvocation(emptyInvocation());
    if (authStatus !== "authenticated" || myAgents || agentDetailTarget || !appName) {
      setCapabilitiesLoading(false);
      return;
    }
    setCapabilitiesLoading(true);
    getAgentInfo(appName)
      .then((info) => {
        if (!cancelled) setAgentInfo(info);
      })
      .catch(() => {
        if (!cancelled) setAgentInfo(null);
      })
      .finally(() => {
        if (!cancelled) setCapabilitiesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [agentDetailTarget, appName, agentInfoRefreshKey, authStatus, myAgents]);
  useEffect(() => {
    if (!access) return;
    localStorage.setItem(
      LS.view,
      access.capabilities.createAgents ? createView ?? "chat" : "chat",
    );
  }, [access, createView]);
  useEffect(() => {
    localStorage.setItem(LS.session, sessionId);
    // Keep the stream-write guard in sync with the displayed session (backup for
    // any navigation path that doesn't set it synchronously).
    viewSidRef.current = sessionId;
  }, [sessionId]);
  useEffect(
    () => {
      const target = automaticEvaluationTargetForSelection(connections, appName);
      if (!target || !userId) {
        automaticEvaluationStatusRefreshRef.current = () => {};
        setEvaluatingSids((current) =>
          current.size === 0 ? current : new Set(),
        );
        return;
      }
      const {
        runtimeId: evaluationRuntimeId,
        region: evaluationRegion,
        appName: evaluationAppName,
      } = target;

      let disposed = false;
      let requestGeneration = 0;

      function clearTimer() {
        if (automaticEvaluationStatusTimerRef.current === undefined) return;
        window.clearTimeout(automaticEvaluationStatusTimerRef.current);
        automaticEvaluationStatusTimerRef.current = undefined;
      }

      function schedulePoll(delayMs: number) {
        clearTimer();
        automaticEvaluationStatusTimerRef.current = window.setTimeout(
          () => void poll(),
          delayMs,
        );
      }

      function applyStatuses(response: AutomaticEvaluationStatusesResponse) {
        const nextEvaluating = new Set(
          response.items
            .filter((status) => status.state === "running")
            .map((status) => status.sessionId),
        );
        setEvaluatingSids((current) => {
          if (
            current.size === nextEvaluating.size &&
            [...nextEvaluating].every((sid) => current.has(sid))
          ) {
            return current;
          }
          return nextEvaluating;
        });

        if (nextEvaluating.size > 0) {
          schedulePoll(AUTO_EVALUATION_RUNNING_POLL_MS);
          return;
        }
        const pendingDueTimes = response.items
          .filter((status) => status.state === "pending")
          .map((status) => Date.parse(status.dueAt))
          .filter(Number.isFinite);
        if (pendingDueTimes.length > 0) {
          schedulePoll(Math.max(
            AUTO_EVALUATION_MIN_PENDING_POLL_MS,
            Math.min(...pendingDueTimes) - Date.now(),
          ));
        }
      }

      async function poll() {
        const generation = ++requestGeneration;
        try {
          const response = await getAutomaticEvaluationStatuses({
            runtimeId: evaluationRuntimeId,
            region: evaluationRegion,
            appName: evaluationAppName,
            userId,
          });
          if (disposed || generation !== requestGeneration) return;
          applyStatuses(response);
        } catch {
          if (!disposed && generation === requestGeneration) {
            schedulePoll(AUTO_EVALUATION_RETRY_POLL_MS);
          }
        }
      }

      const refresh = () => {
        clearTimer();
        void poll();
      };
      automaticEvaluationStatusRefreshRef.current = refresh;
      const preparedSelection = preparedAgentSelectionRef.current;
      if (
        preparedSelection?.agentId === appName &&
        preparedSelection.userId === userId
      ) {
        if (preparedSelection.automaticEvaluationStatuses) {
          applyStatuses(preparedSelection.automaticEvaluationStatuses);
        } else {
          schedulePoll(AUTO_EVALUATION_RETRY_POLL_MS);
        }
      } else {
        refresh();
      }

      return () => {
        disposed = true;
        requestGeneration += 1;
        clearTimer();
        if (automaticEvaluationStatusRefreshRef.current === refresh) {
          automaticEvaluationStatusRefreshRef.current = () => {};
        }
      };
    },
    [appName, connections, userId],
  );
  // Abort the in-flight stream when the whole view unmounts.
  useEffect(
    () => () => {
      agentSelectionPreparationRequestRef.current += 1;
      preparedAgentSelectionRef.current = null;
    },
    [],
  );
  useEffect(
    () => () => streamAbortsRef.current.forEach((c) => c.abort()),
    [],
  );
  useEffect(
    () => () => streamPresentationTimersRef.current.forEach((timer) => {
      window.clearTimeout(timer);
    }),
    [],
  );
  useEffect(
    () => () => {
      sandboxLaunchAbortRef.current?.abort();
      intelligentCreateAbortRef.current?.abort();
      sandboxMessageAbortRef.current?.abort();
    },
    [],
  );

  // When the app (or resolved user) changes, list existing sessions. On the
  // very first resolve, restore the previously-open session (if it still
  // exists and we weren't on a create view); otherwise start a fresh chat.
  useEffect(() => {
    if (myAgents || agentDetailTarget || sandboxSession || !appName || !userId) {
      return;
    }
    const preparedSelection = preparedAgentSelectionRef.current;
    if (
      preparedSelection?.agentId === appName &&
      preparedSelection.userId === userId
    ) {
      preparedAgentSelectionRef.current = null;
      return;
    }
    let cancelled = false;
    (async () => {
      const list = await refreshSessions(appName);
      if (cancelled) return;
      if (!restoredRef.current) {
        restoredRef.current = true;
        const savedId = localStorage.getItem(LS.session) || "";
        if (loadView() === null && savedId && list.some((s) => s.id === savedId)) {
          void pickSession(savedId);
          return;
        }
      }
      startNewChat();
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentDetailTarget, appName, myAgents, sandboxSession, userId]);

  // After switching agent from a search result, open the target session (runs
  // after the agent-switch effect above, so it wins over its startNewChat()).
  useEffect(() => {
    const p = pendingOpenRef.current;
    if (p && p.app === appName) {
      pendingOpenRef.current = null;
      void pickSession(p.sid);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appName]);

  // Open a session surfaced by search, switching agent first if needed.
  function openFromSearch(app: string, sid: string) {
    setSearchView(false);
    if (app === appName) {
      void pickSession(sid);
    } else {
      pendingOpenRef.current = { app, sid };
      setAppName(app);
    }
  }

  function commitHydratedSessions(app: string, hydrated: AdkSession[]) {
    setTokenUsageBySession((current) => {
      const next = { ...current };
      for (const session of hydrated) {
        next[sessionUsageKey(app, session.id)] = aggregateTokenUsage(
          session.events ?? [],
        );
      }
      return next;
    });
    setSessions(hydrated);
  }

  async function refreshSessions(app: string): Promise<AdkSession[]> {
    const request = sessionRefreshRequestRef.current + 1;
    sessionRefreshRequestRef.current = request;
    try {
      const hydrated = await loadHydratedSessions(app, userId);
      if (sessionRefreshRequestRef.current !== request) return hydrated;
      commitHydratedSessions(app, hydrated);
      return hydrated;
    } catch (e) {
      if (sessionRefreshRequestRef.current === request) setError(String(e));
      return [];
    }
  }

  function openSandboxLaunch(
    kind: "codex" | SandboxAgentKind = "codex",
    fromAgents = false,
  ) {
    if (sandboxSession) return;
    setError("");
    setSandboxLaunchError("");
    setSandboxLaunchState("confirm");
    setSandboxLaunchKind(kind);
    setSandboxLaunchFromAgents(fromAgents);
    setSandboxLaunchOpen(true);
  }

  function cancelSandboxLaunch() {
    sandboxLaunchAbortRef.current?.abort();
    sandboxLaunchAbortRef.current = null;
    setSandboxLaunchOpen(false);
    setSandboxLaunchState("confirm");
    setSandboxLaunchError("");
    if (
      !sandboxSession &&
      newChatMode !== "agent" &&
      !sandboxLaunchFromAgents
    ) {
      setNewChatMode("agent");
    }
  }

  async function launchSandboxSession(displayName: string, persistent: boolean) {
    sandboxLaunchAbortRef.current?.abort();
    const controller = new AbortController();
    sandboxLaunchAbortRef.current = controller;
    setSandboxLaunchState("loading");
    setSandboxLaunchError("");
    const operation = beginSandboxCreate({
      sandboxKind: sandboxLaunchKind,
      sandboxSource: sandboxLaunchFromAgents ? "my_agents" : "new_chat",
    });
    try {
      const createdSession = sandboxLaunchKind === "codex"
        ? await sandboxClient.startSession({
            displayName,
            persistent,
            signal: controller.signal,
          })
        : await sandboxClient.startAgentSession(sandboxLaunchKind, {
            displayName,
            persistent,
            signal: controller.signal,
          });
      if (sandboxLaunchAbortRef.current !== controller) {
        operation.fail({ errorKind: "abort" });
        return;
      }
      operation.succeed({ sandboxId: String(createdSession.id) });
      if (sandboxLaunchFromAgents) {
        setSandboxAgentRefreshKey((current) => current + 1);
        setSandboxLaunchOpen(false);
        setSandboxLaunchState("confirm");
        setMyAgents(true);
        return;
      }
      if (sandboxLaunchKind !== "codex") {
        const workspace = await sandboxClient.openAgentSession(
          sandboxLaunchKind,
          createdSession.id,
          { signal: controller.signal },
        );
        if (sandboxLaunchAbortRef.current !== controller) return;
        viewSidRef.current = "";
        setSessionId("");
        setPendingTurns([]);
        setInput("");
        setInvocation(emptyInvocation());
        setNewChatMode(
          sandboxLaunchKind === "deepseek-harness" ? "deepseek-harness" : "agent",
        );
        discardDraftAttachments(attachments);
        setAttachments([]);
        releaseAllSandboxPreviews();
        setSandboxTurns([]);
        setSandboxSession(null);
        setCreateView(null);
        setSkillCenter(false);
        setAddAgent(false);
        setAddMenu(false);
        setSearchView(false);
        setManageAgents(false);
        setAgentDetailTarget(null);
        setMyAgents(false);
        setSandboxAgentDetailTarget(null);
        setSandboxAgentWorkspace(workspace);
        setSandboxLaunchOpen(false);
        setSandboxLaunchState("confirm");
        return;
      }
      const nextSession = await sandboxClient.connectSession(createdSession.id, {
        signal: controller.signal,
      });
      if (sandboxLaunchAbortRef.current !== controller) return;
      viewSidRef.current = "";
      setSessionId("");
      setPendingTurns([]);
      setInput("");
      setInvocation(emptyInvocation());
      setNewChatMode("temporary");
      discardDraftAttachments(attachments);
      setAttachments([]);
      releaseAllSandboxPreviews();
      setSandboxTurns([]);
      setSandboxSession(nextSession);
      setCreateView(null);
      setSkillCenter(false);
      setAddAgent(false);
      setAddMenu(false);
      setSearchView(false);
      setManageAgents(false);
      setAgentDetailTarget(null);
      setMyAgents(false);
      setSandboxAgentDetailTarget(null);
      setSandboxAgentWorkspace(null);
      setSandboxLaunchOpen(false);
      setSandboxLaunchState("confirm");
    } catch (launchError) {
      operation.fail(classifyTelemetryError(launchError));
      if ((launchError as Error)?.name === "AbortError") return;
      if (sandboxLaunchAbortRef.current !== controller) return;
      setSandboxLaunchError(
        launchError instanceof Error
          ? launchError.message
          : String(launchError),
      );
      setSandboxLaunchState("error");
    } finally {
      if (sandboxLaunchAbortRef.current === controller) {
        sandboxLaunchAbortRef.current = null;
      }
    }
  }

  function activateIntelligentDevelopmentSession(
    connected: SandboxSessionInfo,
    restoredTurns: Turn[],
  ) {
    viewSidRef.current = "";
    setSessionId("");
    setPendingTurns([]);
    setInput("");
    setInvocation(emptyInvocation());
    discardDraftAttachments(attachments);
    setAttachments([]);
    releaseAllSandboxPreviews();
    setSandboxTurns(restoredTurns);
    sandboxSessionIdRef.current = connected.id;
    setSandboxSession(connected);
    setSandboxBusy(connected.busy);
    setCreateView(null);
    setSkillCenter(false);
    setAddAgent(false);
    setAddMenu(false);
    setSearchView(false);
    setManageAgents(false);
    setAgentDetailTarget(null);
    setMyAgents(false);
    setPageStack([]);
    setApplicationsView(null);
    setCronJobsView(false);
    setSandboxAgentDetailTarget(null);
    setSandboxAgentWorkspace(null);
  }

  async function openSandboxAgent(
    resource: SandboxAgentResource,
    source: AgentConnectSource = "my_agents",
  ) {
    setError("");
    const operation = beginAgentConnect({
      targetId: String(resource.id),
      agentKind: resource.toolName,
      connectSource: source,
    });
    try {
      const session = resource.resourceType === "snapshot"
        ? await sandboxClient.resumeSnapshot(resource.toolName, resource.snapshotId)
        : resource;
      if (resource.resourceType === "snapshot") {
        setSandboxAgentRefreshKey((current) => current + 1);
      }
      if (session.toolName === "codex") {
        const connected = await sandboxClient.connectSession(session.id);
        const snapshot = await loadSandboxThreadHistory(connected);
        operation.succeed({
          sandboxStatus: telemetrySandboxStatus(connected.status),
        });
        viewSidRef.current = "";
        setSessionId("");
        setPendingTurns([]);
        setInput("");
        setInvocation(emptyInvocation());
        releaseAllSandboxPreviews();
        if (snapshot) {
          setSandboxTurns(sandboxSnapshotTurnsForStatus(snapshot, connected.busy));
          setSandboxSession({
            ...connected,
            threadId: snapshot.threadId,
            cwd: snapshot.cwd ?? connected.cwd,
            workspaceLocked: snapshot.workspaceLocked,
            permissions: snapshot.permissions,
            ...(snapshot.model ? { model: snapshot.model } : {}),
          });
        } else {
          setSandboxTurns([]);
          setSandboxSession(connected);
        }
        setSandboxBusy(connected.busy);
        popStudioPage("sandbox-agent-detail");
        setSandboxAgentDetailTarget(null);
        setSandboxAgentWorkspace(null);
        setMyAgents(false);
        setManageAgents(false);
        return;
      }
      const workspace = await sandboxClient.openAgentSession(
        session.toolName,
        session.id,
      );
      operation.succeed({
        sandboxStatus: telemetrySandboxStatus(workspace.session.status),
      });
      popStudioPage("sandbox-agent-detail");
      setSandboxAgentWorkspace(workspace);
      setSandboxAgentDetailTarget(null);
      setMyAgents(false);
      setManageAgents(false);
    } catch (cause) {
      operation.fail(classifyTelemetryError(cause));
      setError(cause instanceof Error ? cause.message : String(cause));
      throw cause;
    }
  }

  async function openCodexHandoffSession(sessionId: string) {
    const resources = await sandboxClient.listSessions();
    const session = resources.find(
      (resource) =>
        resource.resourceType === "session" &&
        resource.toolName === "codex" &&
        resource.id === sessionId,
    );
    if (!session) {
      throw new Error("云端 Codex Session 暂未出现在列表中，请稍后重试。");
    }
    await openSandboxAgent(session, "my_agents");
    setSandboxProjectUploadOpen(false);
  }

  function openSandboxAgentDetails(session: SandboxAgentResource) {
    setMyAgentsActiveType(session.toolName);
    pushStudioPage({ page: "sandbox-agent-detail", returnTo: "agents" });
    setSandboxAgentDetailTarget(session);
    setSandboxAgentWorkspace(null);
    setMyAgents(true);
    setManageAgents(false);
    setError("");
  }

  async function deleteSandboxAgent(session: SandboxAgentResource) {
    if (session.resourceType === "snapshot") {
      await sandboxClient.deleteSnapshot(session.toolName, session.snapshotId);
    } else {
      if (sandboxSession?.id === session.id) exitSandboxSession();
      if (session.toolName === "codex") {
        await sandboxClient.deleteSession(session.id);
      } else {
        await sandboxClient.deleteAgentSession(session.toolName, session.id);
      }
    }
    setMyAgentsActiveType(session.toolName);
    popStudioPage("sandbox-agent-detail");
    setSandboxAgentDetailTarget(null);
    setSandboxAgentWorkspace(null);
    setSandboxAgentRefreshKey((current) => current + 1);
    setMyAgents(true);
  }

  async function confirmSandboxThreadDelete() {
    const target = sandboxThreadDeleteTarget;
    if (!target) return;
    const deleted = await sandboxCommands.deleteThread(target.id);
    if (deleted) setSandboxThreadDeleteTarget(null);
  }

  function exitSandboxSession(closeRemote = true) {
    sandboxMessageAbortRef.current?.abort();
    sandboxMessageAbortRef.current = null;
    sandboxSessionIdRef.current = "";
    sandboxActiveAssistantTurnIdRef.current = "";
    setSandboxBusy(false);
    releaseAllSandboxPreviews();
    setSandboxTurns([]);
    setAttachments([]);
    setInput("");
    setError("");
    setNewChatMode("agent");
    setSandboxSettingsBusy(false);
    setSandboxSettingsError("");
    setSandboxPermissionsOpen(false);
    setSandboxWorkspaceOpen(false);
    setSandboxToolKind(null);
    setSandboxToolLaunch(null);
    setSandboxToolLoading(false);
    setSandboxToolError("");
    setSandboxApproval(null);
    setSandboxApprovalBusy(false);
    setSandboxApprovalError("");
    resetSandboxEndpointCopyState();
    setSandboxThreadDeleteTarget(null);
    setSandboxUploadBusy(false);
    sandboxUploadRunRef.current += 1;
    const closingSession = sandboxSession;
    setSandboxSession(null);
    if (closingSession && closeRemote) {
      const closingClient = closingSession.intelligentDevelopment
        ? intelligentDevelopmentClient
        : sandboxClient;
      void closingClient
        .closeSession(closingSession.id)
        .catch((closeError) => setError(String(closeError)));
    }
  }

  async function openSandboxTool(kind: "terminal" | "browser") {
    const activeSession = sandboxSession;
    if (!activeSession) return;
    setSandboxToolKind(kind);
    setSandboxToolLaunch(null);
    setSandboxToolError("");
    setSandboxToolLoading(true);
    try {
      const launch = kind === "terminal"
        ? await sandboxClientForSession.launchTerminal(activeSession.id)
        : await sandboxClientForSession.launchBrowser(activeSession.id);
      setSandboxToolLaunch(launch);
    } catch (cause) {
      setSandboxToolError(
        cause instanceof Error ? cause.message : String(cause),
      );
    } finally {
      setSandboxToolLoading(false);
    }
  }

  async function copySandboxEndpoint() {
    const activeSession = sandboxSession;
    if (!activeSession || sandboxEndpointCopyState === "copying") return;
    setSandboxEndpointCopyState("copying");
    setError("");
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("当前浏览器不支持写入剪贴板。");
      }
      const exported = await sandboxClient.getEndpoint(activeSession.id);
      await navigator.clipboard.writeText(exported.endpoint);
      if (sandboxSessionIdRef.current !== activeSession.id) return;
      setSandboxEndpointCopyState("copied");
      if (sandboxEndpointCopyTimerRef.current !== undefined) {
        window.clearTimeout(sandboxEndpointCopyTimerRef.current);
      }
      sandboxEndpointCopyTimerRef.current = window.setTimeout(() => {
        setSandboxEndpointCopyState("idle");
        sandboxEndpointCopyTimerRef.current = undefined;
      }, 1600);
    } catch (cause) {
      if (sandboxSessionIdRef.current !== activeSession.id) return;
      setSandboxEndpointCopyState("idle");
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }

  async function saveSandboxPermissions(value: SandboxPermissions) {
    const activeSession = sandboxSession;
    if (!activeSession || sandboxSettingsBusy) return;
    setSandboxSettingsBusy(true);
    setSandboxSettingsError("");
    try {
      const permissions = await sandboxClientForSession.updatePermissions(
        activeSession.id,
        value,
      );
      setSandboxSession((current) =>
        current?.id === activeSession.id
          ? { ...current, permissions }
          : current,
      );
      appendSandboxActivity(
        activeSession.id,
        "已更新当前 Sandbox Session 的 Codex 权限",
        [
          {
            label: "沙箱模式",
            value: SANDBOX_MODE_LABELS[permissions.sandboxMode],
          },
          {
            label: "审批策略",
            value: SANDBOX_APPROVAL_POLICY_LABELS[permissions.approvalPolicy],
          },
          {
            label: "审批方式",
            value: SANDBOX_REVIEWER_LABELS[permissions.approvalsReviewer],
          },
          {
            label: "网络访问",
            value: permissions.networkAccess ? "允许" : "关闭",
          },
        ],
      );
      if (sandboxSessionIdRef.current === activeSession.id) {
        setSandboxPermissionsOpen(false);
      }
    } catch (cause) {
      setSandboxSettingsError(
        cause instanceof Error ? cause.message : String(cause),
      );
    } finally {
      setSandboxSettingsBusy(false);
    }
  }

  const browseSandboxDirectories = useCallback(
    async (path: string) => {
      const activeSessionId = sandboxSession?.id;
      if (!activeSessionId) throw new Error("当前没有已连接的 Sandbox。");
      return sandboxClientForSession.listDirectories(activeSessionId, path);
    },
    [sandboxSession?.id],
  );

  async function saveSandboxWorkspace(cwd: string) {
    const activeSession = sandboxSession;
    if (
      !activeSession ||
      activeSession.workspaceLocked ||
      sandboxSettingsBusy
    ) return;
    setSandboxSettingsBusy(true);
    setSandboxSettingsError("");
    try {
      const applied = await sandboxClientForSession.updateWorkspace(
        activeSession.id,
        cwd,
      );
      setSandboxSession((current) =>
        current?.id === activeSession.id
          ? { ...current, cwd: applied }
          : current,
      );
      sandboxCommands.invalidateSkills();
      appendSandboxActivity(
        activeSession.id,
        "已更新工作空间",
        [{ label: "工作目录", value: applied, code: true }],
      );
      if (sandboxSessionIdRef.current === activeSession.id) {
        setSandboxWorkspaceOpen(false);
      }
    } catch (cause) {
      setSandboxSettingsError(
        cause instanceof Error ? cause.message : String(cause),
      );
    } finally {
      setSandboxSettingsBusy(false);
    }
  }

  async function decideSandboxApproval(
    decision: SandboxApprovalDecision,
  ) {
    const activeSession = sandboxSession;
    const activeApproval = sandboxApproval;
    if (!activeSession || !activeApproval || sandboxApprovalBusy) return;
    setSandboxApprovalBusy(true);
    setSandboxApprovalError("");
    try {
      await sandboxClientForSession.resolveApproval(
        activeSession.id,
        activeApproval.id,
        decision,
      );
      appendSandboxActivity(
        activeSession.id,
        approvalActivityTitle(activeApproval, decision),
        approvalActivityDetails(activeApproval),
        sandboxActiveAssistantTurnIdRef.current,
      );
      setSandboxApproval((current) =>
        current?.id === activeApproval.id ? null : current,
      );
    } catch (cause) {
      setSandboxApprovalError(
        cause instanceof Error ? cause.message : String(cause),
      );
    } finally {
      setSandboxApprovalBusy(false);
    }
  }

  async function addSandboxFiles(files: FileList | File[]) {
    const activeSession = sandboxSession;
    if (!activeSession || sandboxUploadBusy) return;
    const uploadRun = ++sandboxUploadRunRef.current;
    setError("");
    setSandboxUploadBusy(true);
    const drafts = Array.from(files).map((file) => {
      const attachment: Attachment = {
        id: attachmentDraftId(),
        mimeType: browserMimeType(file),
        name: file.name,
        sizeBytes: file.size,
        status: "uploading",
        previewUrl: createSandboxPreviewUrl(file),
      };
      return { file, attachment };
    });
    setAttachments((current) => [
      ...current,
      ...drafts.map(({ attachment }) => attachment),
    ]);
    try {
      const uploadResults = await Promise.all(
        drafts.map(async ({ file, attachment }) => {
          try {
            const uploaded = await sandboxClientForSession.uploadFile(
              activeSession.id,
              file,
            );
            if (sandboxUploadRunRef.current !== uploadRun) return null;
            setAttachments((current) =>
              current.map((item) =>
                item.id === attachment.id
                  ? {
                      ...item,
                      id: uploaded.id,
                      uri: uploaded.path,
                      name: uploaded.name,
                      mimeType: uploaded.mimeType,
                      sizeBytes: uploaded.sizeBytes,
                      status: "ready",
                    }
                  : item,
              ),
            );
            return uploaded;
          } catch (cause) {
            if (sandboxUploadRunRef.current !== uploadRun) return null;
            const message =
              cause instanceof Error ? cause.message : String(cause);
            setAttachments((current) =>
              current.map((item) =>
                item.id === attachment.id
                  ? { ...item, status: "error", error: message }
                  : item,
              ),
            );
            setError(message);
            return null;
          }
        }),
      );
      const uploadedFiles = uploadResults.filter(
        (uploaded) => uploaded !== null,
      );
      if (
        sandboxUploadRunRef.current === uploadRun &&
        uploadedFiles.length > 0
      ) {
        appendSandboxActivity(
          activeSession.id,
          uploadedFiles.length === 1
            ? "已上传文件到 Sandbox"
            : `已上传 ${uploadedFiles.length} 个文件到 Sandbox`,
          uploadedFiles.map((uploaded, index) => ({
            label: uploadedFiles.length === 1 ? "文件" : `文件 ${index + 1}`,
            value: uploaded.path,
            code: true,
          })),
        );
      }
    } finally {
      if (sandboxUploadRunRef.current === uploadRun) {
        setSandboxUploadBusy(false);
      } else {
        for (const { attachment } of drafts) {
          releaseSandboxPreviewUrl(attachment.previewUrl);
        }
      }
    }
  }

  function removeSandboxAttachment(id: string) {
    const removed = attachments.find((item) => item.id === id);
    if (!removed) return;
    releaseSandboxPreviewUrl(removed.previewUrl);
    setAttachments((current) => current.filter((item) => item.id !== id));
  }

  function stopSandboxGeneration() {
    const controller = sandboxMessageAbortRef.current;
    const activeSession = sandboxSession;
    if (!controller) return;
    if (activeSession?.intelligentDevelopment) {
      if (sandboxStopWaitRef.current?.controller === controller) return;
      const promise = intelligentDevelopmentClient
        .interruptSession(activeSession.id)
        .then(() => {
          if (sandboxStopWaitRef.current?.controller === controller) {
            controller.abort();
          }
          return true;
        })
        .catch((cause) => {
          if (sandboxStopWaitRef.current?.controller === controller) {
            sandboxStopWaitRef.current = null;
          }
          if (
            sandboxSessionIdRef.current === activeSession.id &&
            sandboxMessageAbortRef.current === controller
          ) {
            setError(cause instanceof Error ? cause.message : String(cause));
          }
          return false;
        });
      sandboxStopWaitRef.current = { controller, promise };
      return;
    }
    controller.abort();
    if (activeSession) {
      void sandboxClient.interruptSession(activeSession.id).catch((cause) => {
        if (sandboxSessionIdRef.current === activeSession.id) {
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      });
    }
  }

  function requestIntelligentNavigation(action: () => void) {
    if (sandboxSession?.intelligentDevelopment && sandboxBusy) {
      pendingIntelligentNavigationRef.current = action;
      setIntelligentLeaveOpen(true);
      return;
    }
    action();
  }

  function confirmIntelligentNavigation() {
    const activeSession = sandboxSession;
    const action = pendingIntelligentNavigationRef.current;
    if (!activeSession?.intelligentDevelopment || !action) {
      setIntelligentLeaveOpen(false);
      pendingIntelligentNavigationRef.current = null;
      return;
    }
    setError("");
    const interrupt = intelligentDevelopmentClient.interruptSession(activeSession.id);
    sandboxMessageAbortRef.current?.abort();
    pendingIntelligentNavigationRef.current = null;
    setIntelligentLeaveOpen(false);
    action();
    void interrupt.catch(() => {
      if (!sandboxSessionIdRef.current) {
        setError(
          "已离开开发环境，但未能确认本轮构建已停止。任务可能仍在运行，请稍后从历史会话检查状态。",
        );
      }
    });
  }

  async function sendSandboxMessage(
    text: string,
    messageAttachments: Attachment[] = [],
    selectedSkills: SandboxSkill[] = [],
    activeSessionOverride?: SandboxSessionInfo,
  ) {
    const activeSession = activeSessionOverride ?? sandboxSession;
    const readyAttachments = messageAttachments.filter(
      (attachment) => attachment.status === "ready" && attachment.uri,
    );
    if (
      !activeSession ||
      sandboxBusy ||
      (!text.trim() && readyAttachments.length === 0)
    ) return;
    setError("");
    setSandboxApproval(null);
    setSandboxApprovalError("");
    const operation = beginAgentMessage({
      agentId: String(activeSession.id),
      agentKind: activeSession.toolName,
      messageSource: "composer",
      sessionState: "existing",
      sessionId: String(activeSession.id),
    });
    const controller = new AbortController();
    sandboxMessageAbortRef.current?.abort();
    sandboxMessageAbortRef.current = controller;
    const userBlocks: Turn["blocks"] = [];
    if (selectedSkills.length > 0) {
      userBlocks.push({
        kind: "invocation",
        value: {
          skills: selectedSkills.map(({ name, description }) => ({
            name,
            description,
          })),
        },
      });
    }
    if (readyAttachments.length > 0) {
      userBlocks.push({
        kind: "attachment",
        files: readyAttachments.map((attachment) => ({
          id: attachment.id,
          mimeType: attachment.mimeType,
          name: attachment.name,
          sizeBytes: attachment.sizeBytes,
          previewUrl: attachment.previewUrl,
        })),
      });
    }
    if (text.trim()) userBlocks.push({ kind: "text", text });
    const uploadedPaths = readyAttachments
      .map((attachment) => attachment.uri)
      .filter((path): path is string => Boolean(path));
    const skillPrefix = selectedSkills
      .map((skill) => `$${skill.name}`)
      .join(" ");
    const visiblePrompt = [skillPrefix, text.trim()].filter(Boolean).join(" ");
    const prompt = uploadedPaths.length > 0
      ? [
          visiblePrompt,
          "以下文件已上传到当前 Sandbox 工作空间，请在任务中使用：",
          ...uploadedPaths.map((path) => `- ${path}`),
        ].filter(Boolean).join("\n\n")
      : visiblePrompt;
    const userTurnId = crypto.randomUUID();
    const assistantTurnId = crypto.randomUUID();
    const optimisticTurns: Turn[] = [
      {
        role: "user",
        blocks: userBlocks,
        meta: { localId: userTurnId, ts: Date.now() / 1000 },
      },
      {
        role: "assistant",
        blocks: [],
        meta: { localId: assistantTurnId },
      },
    ];
    sandboxActiveAssistantTurnIdRef.current = assistantTurnId;
    setSandboxTurns((current) => [...current, ...optimisticTurns]);
    setSandboxBusy(true);
    setSandboxSession((current) =>
      current?.id === activeSession.id
        ? { ...current, busy: true, workspaceLocked: true }
        : current,
    );
    const activeClient = activeSession.intelligentDevelopment
      ? intelligentDevelopmentClient
      : sandboxClient;
    let remainingBusy = false;
    try {
      const reply = await activeClient.sendMessage(
        {
          sessionId: activeSession.id,
          text: prompt,
          skillIds: selectedSkills.map((skill) => skill.id),
        },
        {
          signal: controller.signal,
          onApproval: (approval) => {
            if (
              controller.signal.aborted ||
              sandboxMessageAbortRef.current !== controller
            ) return;
            setSandboxApprovalError("");
            setSandboxApproval(approval);
          },
          onApprovalResolved: (approvalId) => {
            if (
              controller.signal.aborted ||
              sandboxMessageAbortRef.current !== controller
            ) return;
            setSandboxApproval((current) =>
              current?.id === approvalId ? null : current,
            );
          },
          onBlocks: (blocks) => {
            if (
              controller.signal.aborted ||
              sandboxMessageAbortRef.current !== controller
            ) return;
            setSandboxTurns((current) => {
              const next = current.slice();
              const assistantIndex = next.findIndex(
                (turn) => turn.meta?.localId === assistantTurnId,
              );
              const assistantTurn = next[assistantIndex];
              if (assistantTurn?.role === "assistant") {
                next[assistantIndex] = { ...assistantTurn, blocks };
              }
              return next;
            });
          },
          onUsage: (update) => {
            if (
              controller.signal.aborted ||
              sandboxMessageAbortRef.current !== controller
            ) return;
            setSandboxTurns((current) => {
              const next = current.slice();
              const assistantIndex = next.findIndex(
                (turn) => turn.meta?.localId === assistantTurnId,
              );
              const assistantTurn = next[assistantIndex];
              if (assistantTurn?.role === "assistant") {
                next[assistantIndex] = {
                  ...assistantTurn,
                  meta: {
                    ...assistantTurn.meta,
                    sandboxUsage: update.usage,
                  },
                };
              }
              return next;
            });
          },
        },
      );
      if (
        controller.signal.aborted ||
        sandboxMessageAbortRef.current !== controller
      ) {
        operation.fail({
          sessionId: String(activeSession.id),
          failedPhase: "sandbox_send",
          errorKind: "abort",
        });
        return;
      }
      operation.succeed({ sessionId: String(activeSession.id) });
      setSandboxTurns((current) => {
        const next = current.slice();
        const assistantIndex = next.findIndex(
          (turn) => turn.meta?.localId === assistantTurnId,
        );
        const assistantTurn = next[assistantIndex];
        if (assistantTurn?.role === "assistant") {
          next[assistantIndex] = {
            ...assistantTurn,
            blocks: reply.blocks,
            meta: {
              ...assistantTurn.meta,
              ts: Date.now() / 1000,
              ...(reply.usage
                ? { sandboxUsage: reply.usage.usage }
                : {}),
            },
          };
        }
        return next;
      });
      if (!activeSession.intelligentDevelopment) {
        void sandboxCommands.refreshThreads();
      }
    } catch (messageError) {
      operation.fail({
        sessionId: String(activeSession.id),
        failedPhase: "sandbox_send",
        ...classifyTelemetryError(messageError),
      });
      if ((messageError as Error)?.name === "AbortError") {
        return;
      }
      if (sandboxMessageAbortRef.current !== controller) {
        return;
      }
      setSandboxTurns((current) =>
        current.filter(
          (turn) =>
            turn.meta?.localId !== userTurnId &&
            turn.meta?.localId !== assistantTurnId,
        ),
      );
      setInput(text);
      setAttachments(messageAttachments);
      sandboxCommands.setSelectedSkills(selectedSkills);
      const taskStillRunning =
        activeSession.intelligentDevelopment &&
        messageError instanceof SandboxServiceError &&
        messageError.code === "INTELLIGENT_DEVELOPMENT_TASK_IN_PROGRESS";
      remainingBusy = activeSession.intelligentDevelopment;
      try {
        const status = await activeClient.getStatus(activeSession.id);
        remainingBusy = status.busy;
        setSandboxSession((current) =>
          current?.id === activeSession.id
            ? { ...current, ...status }
            : current,
        );
      } catch {
        // Keep the optimistic lock when the connection itself is unavailable.
      }
      if (!taskStillRunning) {
        setError(
          activeSession.intelligentDevelopment
            ? intelligentDevelopmentErrorMessage(messageError)
            : `内置智能体发送失败：${
                messageError instanceof Error
                  ? messageError.message
                  : String(messageError)
              }`,
        );
      }
    } finally {
      if (sandboxMessageAbortRef.current === controller) {
        const stopWait = sandboxStopWaitRef.current;
        if (stopWait?.controller === controller) {
          const cleanupConfirmed = await stopWait.promise;
          if (sandboxStopWaitRef.current === stopWait) {
            sandboxStopWaitRef.current = null;
          }
          if (cleanupConfirmed) {
            setSandboxTurns((current) => current.filter(
              (turn) =>
                turn.meta?.localId !== assistantTurnId || turn.blocks.length > 0,
            ));
            appendSandboxActivity(activeSession.id, "已停止，可继续输入");
          }
        }
        sandboxMessageAbortRef.current = null;
        if (sandboxActiveAssistantTurnIdRef.current === assistantTurnId) {
          sandboxActiveAssistantTurnIdRef.current = "";
        }
        setSandboxApproval(null);
        if (activeSession.intelligentDevelopment) {
          setSandboxBusy(remainingBusy);
          setSandboxSession((current) =>
            current?.id === activeSession.id
              ? { ...current, busy: remainingBusy }
              : current,
          );
        } else {
          setSandboxBusy(false);
          setSandboxSession((current) =>
            current?.id === activeSession.id
              ? { ...current, busy: false }
              : current,
          );
        }
      }
    }
  }

  async function submitSandboxInput(value: string) {
    if (
      !sandboxSession?.intelligentDevelopment &&
      await sandboxCommands.executeSlash(value)
    ) return;
    if (!sandboxSession || sandboxBusy || sandboxCommands.commandBusy) return;
    const messageAttachments = attachments;
    const selectedSkills = sandboxCommands.selectedSkills;
    setInput("");
    setAttachments([]);
    sandboxCommands.setSelectedSkills([]);
    await sendSandboxMessage(value.trim(), messageAttachments, selectedSkills);
  }

  // Reset to a fresh, not-yet-created chat. The backend session is created
  // lazily on the first message (see send()). A background stream (if any)
  // keeps running and persisting — its writes are suppressed here by viewSidRef.
  function startNewChat() {
    exitSandboxSession();
    setError("");
    setGreeting(pickGreeting());
    setNewChatMode("agent");
    setNewChatTask(null);
    setNewChatSkillTarget(null);
    const abandonedSession = sessionId && persistentTurns.length === 0 && attachments.length > 0
      ? sessionId
      : "";
    viewSidRef.current = "";
    setSessionId("");
    setInitializingSession(false);
    setPendingTurns([]);
    setInvocation(emptyInvocation());
    setDraftStudioToolIds([]);
    discardDraftAttachments(attachments);
    setAttachments([]);
    if (abandonedSession) void abandonDraftSession(abandonedSession);
  }

  function returnToIntelligentCreate() {
    startNewChat();
    setIntelligentDeployment(null);
    setAddMenu(false);
    if (migrationProjectReturn) {
      setCreateView("migration");
      return;
    }
    setCreateView("intelligent");
  }

  function clearSelectedAgentAfterRemoval() {
    agentSelectionClearedRef.current = true;
    localStorage.removeItem(LS.app);
    if (sessionId) streamAbortsRef.current.get(sessionId)?.abort();
    creatingSessionRef.current = null;
    startNewChat();
    setAppName("");
    setNewChatCapabilities({});
    setAgentInfo(null);
  }

  function openNewChat() {
    cancelIntelligentPreparation();
    setIntelligentDeployment(null);
    setPlatformFeedbackOrigin(null);
    setCreateView(null);
    setSkillCenter(false);
    setSkillCenterLaunch(null);
    setAddAgent(false);
    setAddMenu(false);
    setSearchView(false);
    setManageAgents(false);
    setAgentDetailTarget(null);
    setSandboxAgentDetailTarget(null);
    setSandboxAgentWorkspace(null);
    setMyAgents(false);
    setWorkspaceView(false);
    setEnvironmentView(false);
    setPageStack([]);
    setApplicationsView(null);
    setCronJobsView(false);
    startNewChat();
  }

  function cancelIntelligentPreparation() {
    intelligentCreateAbortRef.current?.abort();
    intelligentCreateAbortRef.current = null;
    setIntelligentPreparationStage(null);
  }

  async function startIntelligentDevelopment(
    goal: string,
    modelId: string,
    baseVersion?: IntelligentCreateBaseVersion,
    returnTarget?: { projectId: string },
  ) {
    if (intelligentPreparationStage) return;
    intelligentCreateAbortRef.current?.abort();
    const controller = new AbortController();
    intelligentCreateAbortRef.current = controller;
    setIntelligentPreparationStage("preparing");
    setIntelligentCapabilitiesError("");
    try {
      const created = await intelligentDevelopmentClient.startSession({
        displayName: baseVersion?.projectName ?? goal.slice(0, 40),
        modelId,
        ...(baseVersion
          ? {
              projectId: baseVersion.projectId,
              baseVersionId: baseVersion.versionId,
            }
          : {}),
        signal: controller.signal,
      });
      if (
        controller.signal.aborted ||
        intelligentCreateAbortRef.current !== controller
      ) return;
      setIntelligentPreparationStage("starting");
      const connected = await intelligentDevelopmentClient.connectSession(
        created.id,
        { signal: controller.signal },
      );
      if (
        controller.signal.aborted ||
        intelligentCreateAbortRef.current !== controller
      ) return;
      if (returnTarget) setMigrationProjectReturn(returnTarget);
      activateIntelligentDevelopmentSession(connected, []);
      intelligentCreateAbortRef.current = null;
      setIntelligentPreparationStage(null);
      await sendSandboxMessage(goal, [], [], connected);
    } catch (cause) {
      if ((cause as Error)?.name !== "AbortError") {
        setIntelligentCapabilitiesError(
          cause instanceof Error ? cause.message : "智能开发会话创建失败",
        );
      }
    } finally {
      if (intelligentCreateAbortRef.current === controller) {
        intelligentCreateAbortRef.current = null;
        setIntelligentPreparationStage(null);
      }
    }
  }

  async function removeSession(id: string) {
    try {
      // Deleting a session with a running stream — abort just that one.
      streamAbortsRef.current.get(id)?.abort();
      setEvaluating(id, false);
      await deleteSessionMedia(appName, userId, id);
      await deleteSession(appName, userId, id);
      const presentationTimer = streamPresentationTimersRef.current.get(id);
      if (presentationTimer !== undefined) window.clearTimeout(presentationTimer);
      streamPresentationTimersRef.current.delete(id);
      setStreamPresentationSids((current) => {
        if (!current.has(id)) return current;
        const next = new Set(current);
        next.delete(id);
        return next;
      });
      setTurnsBySession((m) => {
        const { [id]: _drop, ...rest } = m;
        return rest;
      });
      setTokenUsageBySession((current) => {
        const key = sessionUsageKey(appName, id);
        if (!(key in current)) return current;
        const { [key]: _drop, ...rest } = current;
        return rest;
      });
      if (id === sessionId) startNewChat();
      await refreshSessions(appName);
    } catch (e) {
      setError(String(e));
    }
  }

  async function pickSession(id: string) {
    if (sandboxSession) exitSandboxSession();
    if (id === sessionId) return;
    viewSidRef.current = id;
    setError("");
    setInitializingSession(false);
    setPendingTurns([]);
    setNewChatMode("agent");
    setNewChatTask(null);
    setInvocation(emptyInvocation());
    setSessionId(id);
    // Already have this session's turns (it's cached, or streaming in the
    // background)? Show them instantly and let any live stream keep updating —
    // no re-fetch, no "loading" flash, streaming stays visible.
    if (turnsBySession[id] !== undefined) return;
    setLoadingSession(true);
    try {
      const s = await getSession(appName, userId, id);
      setTurnsFor(id, eventsToTurns(s.events ?? [], s.state));
      setTokenUsageBySession((current) => ({
        ...current,
        [sessionUsageKey(appName, id)]: aggregateTokenUsage(s.events ?? []),
      }));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoadingSession(false);
    }
  }

  async function openFeedbackCaseInStudio(item: AgentFeedbackCase) {
    if (!item.sessionId || !item.messageId) {
      setError("这条案例缺少会话定位信息，无法跳转。");
      return;
    }
    setSearchView(false);
    setCreateView(null);
    setAddAgent(false);
    setAddMenu(false);
    setSkillCenter(false);
    exitAgentDetailContext();
    setFeedbackCaseReturnAgentId(appName);
    setFeedbackCaseReturnKind(item.kind);
    setFeedbackTargetEventId(item.messageId);
    await pickSession(item.sessionId);
  }

  function returnToFeedbackCases() {
    const agentId = feedbackCaseReturnAgentId || appName;
    setSearchView(false);
    setCreateView(null);
    setAddAgent(false);
    setAddMenu(false);
    setSkillCenter(false);
    setFocusedDeploymentTaskId("");
    setFocusedWorkspaceAgentId(agentId);
    setFocusedWorkspaceAgentSection("evaluations");
    setFocusedWorkspaceCaseKind(feedbackCaseReturnKind);
    setManageAgents(true);
    setFeedbackCaseReturnAgentId("");
    setFeedbackTargetEventId("");
  }

  function clearDeletedFeedbackCases(items: AgentFeedbackCase[]) {
    const clearBySession = new Map<string, Set<string>>();
    const clearByCacheScope = new Map<string, {
      runtimeId: string;
      appName: string;
      userId: string;
      sessionId: string;
      eventIds: Set<string>;
    }>();
    for (const item of items) {
      if (!item.sessionId || !item.messageId) continue;
      const sessionEvents = clearBySession.get(item.sessionId) ?? new Set<string>();
      sessionEvents.add(item.messageId);
      clearBySession.set(item.sessionId, sessionEvents);
      if (item.runtimeId && item.userId) {
        const key = [
          item.runtimeId,
          appName,
          item.userId,
          item.sessionId,
        ].join(":");
        const scope = clearByCacheScope.get(key) ?? {
          runtimeId: item.runtimeId,
          appName,
          userId: item.userId,
          sessionId: item.sessionId,
          eventIds: new Set<string>(),
        };
        scope.eventIds.add(item.messageId);
        clearByCacheScope.set(key, scope);
      }
    }
    if (clearBySession.size === 0) return;
    setTurnsBySession((current) => {
      const next = { ...current };
      for (const [sid, eventIds] of clearBySession) {
        const existing = next[sid];
        if (!existing) continue;
        next[sid] = existing.map((turn) =>
          turn.meta?.eventId && eventIds.has(turn.meta.eventId)
            ? { ...turn, meta: { ...turn.meta, feedback: undefined } }
            : turn,
        );
      }
      return next;
    });
    setSessions((current) =>
      current.map((session) => {
        const eventIds = clearBySession.get(session.id);
        if (!eventIds || !session.state) return session;
        const state = { ...session.state };
        for (const eventId of eventIds) delete state[`veadk_feedback:${eventId}`];
        return { ...session, state };
      }),
    );
    setFeedbackPendingIds((current) => {
      const next = new Set(current);
      for (const eventIds of clearBySession.values()) {
        for (const eventId of eventIds) next.delete(eventId);
      }
      return next;
    });
    for (const scope of clearByCacheScope.values()) {
      clearMessageFeedbackCache({
        runtimeId: scope.runtimeId,
        appName: scope.appName,
        userId: scope.userId,
        sessionId: scope.sessionId,
        eventIds: [...scope.eventIds],
      });
    }
    setFeedbackCasePreview((current) => {
      if (!current) return current;
      return items.some((item) =>
        item.id === current.id || item.messageId === current.messageId
      )
        ? null
        : current;
    });
  }

  async function ensureSession(activate = true): Promise<string> {
    if (sessionId) return sessionId;
    if (!creatingSessionRef.current) {
      creatingSessionRef.current = createSession(appName, userId);
    }
    const pending = creatingSessionRef.current;
    try {
      const sid = await pending;
      if (activate) setSessionId(sid);
      const now = Date.now() / 1000;
      const optimistic: AdkSession = { id: sid, lastUpdateTime: now, events: [] };
      setSessions((prev) => [optimistic, ...prev.filter((s) => s.id !== sid)]);
      return sid;
    } finally {
      if (creatingSessionRef.current === pending) creatingSessionRef.current = null;
    }
  }

  async function addFiles(files: FileList | File[]) {
    setError("");
    let sid: string;
    try {
      sid = await ensureSession();
    } catch (e) {
      setError(String(e));
      return;
    }
    const drafts = Array.from(files).map((file) => ({
      file,
      attachment: {
        id: attachmentDraftId(),
        mimeType: browserMimeType(file),
        name: file.name,
        sizeBytes: file.size,
        status: "uploading" as const,
      },
    }));
    setAttachments((current) => [...current, ...drafts.map((draft) => draft.attachment)]);
    await Promise.all(
      drafts.map(async ({ file, attachment }) => {
        try {
          const uploaded = await uploadMedia(appName, userId, sid, file);
          if (removedAttachmentIdsRef.current.delete(attachment.id)) {
            if (uploaded.uri) await deleteMedia(appName, uploaded.uri);
            return;
          }
          setAttachments((current) => current.map((item) =>
            item.id === attachment.id
              ? uploaded
              : item,
          ));
        } catch (e) {
          if (removedAttachmentIdsRef.current.delete(attachment.id)) return;
          const message = e instanceof Error ? e.message : String(e);
          setAttachments((current) => current.map((item) =>
            item.id === attachment.id ? { ...item, status: "error", error: message } : item,
          ));
          setError(message);
        }
      }),
    );
  }

  async function send(
    text: string,
    atts: Attachment[] = [],
    selectedInvocation: FrontendInvocation = emptyInvocation(),
    messageSource: AgentMessageSource = "composer",
    selectedPlatformTools?: readonly string[],
  ) {
    // `busy` here = the CURRENT session is already streaming (can't double-send
    // to it). Other sessions can stream concurrently.
    if (
      (!text.trim() && atts.length === 0) ||
      conversationBusy ||
      !appName ||
      !userId
    ) return;
    setError("");
    const createsSession = !sessionId;
    let platformTools = [...(selectedPlatformTools ?? selectedStudioToolIds)];
    const environmentMounts = createsSession
      ? []
      : environmentMountsBySession[
          studioToolSelectionKey(appName, userId, sessionId)
        ] ?? [];
    if (environmentMounts.length > 0 && currentRuntime) {
      platformTools = [...new Set([...platformTools, ...ENVIRONMENT_STUDIO_TOOL_IDS])];
    }
    const sessionState = createsSession ? "new" : "existing";
    const trackRuntimeMessage = Boolean(currentRuntime);
    const messageOperation = currentRuntime
      ? beginAgentMessage({
          agentId: String(appName),
          agentKind: "runtime",
          messageSource,
          sessionState,
          ...(sessionId ? { sessionId: String(sessionId) } : {}),
        })
      : null;

    const userBlocks: Turn["blocks"] = [];
    if (selectedInvocation.skills.length > 0 || selectedInvocation.targetAgent) {
      userBlocks.push({ kind: "invocation", value: selectedInvocation });
    }
    if (atts.length)
      userBlocks.push({
        kind: "attachment",
        files: atts.map((a) => ({
          id: a.id,
          mimeType: a.mimeType,
          data: a.data,
          uri: a.uri,
          name: a.name,
          sizeBytes: a.sizeBytes,
        })),
      });
    if (text.trim()) userBlocks.push({ kind: "text", text });
    const optimisticTurns: Turn[] = [
      { role: "user", blocks: userBlocks, meta: { ts: Date.now() / 1000 } },
      { role: "assistant", blocks: [] },
    ];
    if (createsSession) {
      setPendingTurns(optimisticTurns);
      setInitializingSession(true);
    }

    const selectedTask = newChatTask;
    let sid: string;
    try {
      sid = await ensureSession(!createsSession);
    } catch (e) {
      if (createsSession) {
        setPendingTurns([]);
        setInitializingSession(false);
        setInput(text);
        setInvocation(selectedInvocation);
      }
      if (trackRuntimeMessage) {
        messageOperation?.fail({
          failedPhase: "create_session",
          ...classifyTelemetryError(e),
        });
      }
      setError(String(e));
      return;
    }

    if (selectedTask) {
      const requiredTools = NEW_CHAT_TASK_TOOLS[selectedTask];
      const agentTools = new Set(agentInfo?.tools ?? []);
      const availableTools = new Set([
        ...agentTools,
        ...(currentRuntime ? availableStudioToolIds : []),
      ]);
      const missingTools = requiredTools.filter((tool) => !availableTools.has(tool));
      if (missingTools.length > 0) {
        if (createsSession) {
          setPendingTurns([]);
          setInitializingSession(false);
          setInput(text);
          setInvocation(selectedInvocation);
        }
        if (trackRuntimeMessage) {
          messageOperation?.fail({
            sessionId: String(sid),
            failedPhase: "mount_task_capabilities",
            ...classifyTelemetryError(
              `missing Studio tools: ${missingTools.join(", ")}`,
            ),
          });
        }
        setError(`当前 Agent 缺少任务工具：${missingTools.join("、")}`);
        return;
      }
      if (currentRuntime) {
        const optionalTools = NEW_CHAT_TASK_OPTIONAL_TOOLS[selectedTask].filter(
          (toolName) => availableStudioToolIds.has(toolName) && !agentTools.has(toolName),
        );
        platformTools = [...new Set([
          ...platformTools,
          ...requiredTools.filter((toolName) => !agentTools.has(toolName)),
          ...optionalTools,
        ])];
      }
    }

    setTurnsFor(sid, (current) =>
      createsSession ? optimisticTurns : [...current, ...optimisticTurns],
    );
    if (createsSession) {
      if (currentRuntime) {
        const key = studioToolSelectionKey(appName, userId, sid);
        setStudioToolIdsBySession((current) => ({
          ...current,
          [key]: [...platformTools],
        }));
      }
      viewSidRef.current = sid;
      setSessionId(sid);
      setPendingTurns([]);
      setInitializingSession(false);
    }

    // Register this session's own stream (concurrent with other sessions').
    const ctrl = new AbortController();
    streamAbortsRef.current.set(sid, ctrl);
    setStreaming(sid, true);
    startStreamPresentation(sid);
    viewSidRef.current = sid;

    setActiveAgentBySession((m) => ({ ...m, [sid]: "" }));
    setSeenAgentsBySession((m) => ({ ...m, [sid]: new Set() }));
    setExecPathBySession((m) => ({ ...m, [sid]: [] }));

    let streamFailed = false;
    let streamError: unknown = null;
    try {
      let acc = emptyAcc();
      let currentStreamAuthor = "";
      let tokens = 0;
      let ts = Date.now() / 1000;
      let eventId = "";
      let invocationId = "";
      let hasCompletedReply = false;
      for await (const event of runSSE({
        appName,
        userId,
        sessionId: sid,
        text,
        attachments: atts,
        invocation: selectedInvocation,
        platformTools: currentRuntime ? platformTools : undefined,
        environmentMounts: currentRuntime && environmentMounts.length > 0
          ? environmentMounts
          : undefined,
        signal: ctrl.signal,
        onRuntimeContext: (context) => {
          setRuntimeLogTargetsBySession((current) => ({
            ...current,
            [`${appName}\n${sid}`]: context,
          }));
        },
      })) {
        if (ctrl.signal.aborted) break;
        const errMsg = event.error ?? event.errorMessage ?? event.error_message;
        if (typeof errMsg === "string" && errMsg) {
          streamFailed = true;
          streamError = errMsg;
          if (viewSidRef.current === sid) setError(errMsg);
          break;
        }
        // Live topology: author + transfer/end signals, keyed by session.
        applyStreamSignals(sid, event);
        const eventAuthor = event.author && event.author !== "user"
          ? event.author
          : "";
        if (eventAuthor && eventAuthor !== currentStreamAuthor) {
          currentStreamAuthor = eventAuthor;
          acc = emptyAcc();
        }
        acc = applyEvent(acc, event);
        const usage = event.usageMetadata ?? event.usage_metadata;
        addTokenUsageFor(appName, sid, event);
        if (usage?.totalTokenCount) tokens = usage.totalTokenCount;
        if (event.timestamp) ts = event.timestamp;
        if (event.id) eventId = event.id;
        const nextInvocationId = event.invocationId ?? event.invocation_id;
        if (nextInvocationId) invocationId = nextInvocationId;
        const blocks = acc.blocks;
        if (
          event.partial !== true &&
          turnHasVisibleContent({ role: "assistant", blocks })
        ) {
          hasCompletedReply = true;
        }
        const meta = {
          author: currentStreamAuthor || undefined,
          tokens: tokens || undefined,
          ts,
          eventId: eventId || undefined,
          invocationId: invocationId || undefined,
        };
        setTurnsFor(sid, (t) => {
          const next = t.slice();
          const last = next[next.length - 1];
          if (
            last?.role === "assistant" &&
            (!last.meta?.author || last.meta.author === currentStreamAuthor)
          ) {
            next[next.length - 1] = { ...last, blocks, meta };
          } else {
            next.push({ role: "assistant", blocks, meta });
          }
          return next;
        });
      }
      if (!ctrl.signal.aborted && !streamFailed && !hasCompletedReply) {
        streamFailed = true;
        streamError = RUN_SSE_INCOMPLETE_RESPONSE_ERROR;
        if (viewSidRef.current === sid) {
          setError(RUN_SSE_INCOMPLETE_RESPONSE_ERROR);
        }
      }
      void refreshSessions(appName);
      if (trackRuntimeMessage && ctrl.signal.aborted) {
        messageOperation?.fail({
          sessionId: String(sid),
          failedPhase: "run_sse",
          errorKind: "abort",
        });
      } else if (trackRuntimeMessage) {
        if (streamFailed) {
          messageOperation?.fail({
            sessionId: String(sid),
            failedPhase: "run_sse",
            ...classifyTelemetryError(streamError ?? "run_sse failed"),
          });
        } else {
          messageOperation?.succeed({ sessionId: String(sid) });
        }
      }
      if (!ctrl.signal.aborted && !streamFailed && eventId) {
        automaticEvaluationStatusRefreshRef.current();
      }
    } catch (e) {
      streamFailed = true;
      streamError = e;
      if (trackRuntimeMessage) {
        messageOperation?.fail({
          sessionId: String(sid),
          failedPhase: "run_sse",
          ...classifyTelemetryError(e),
        });
      }
      // An abort (unmount / session delete) is expected — surface only real
      // errors, and only while this session is on screen.
      if (
        (e as Error)?.name !== "AbortError" &&
        !ctrl.signal.aborted &&
        viewSidRef.current === sid
      ) {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      if (
        !ctrl.signal.aborted &&
        streamFailed &&
        viewSidRef.current === sid &&
        text.trim()
      ) {
        setInput((current) => current.trim() ? current : text);
      }
      if (streamAbortsRef.current.get(sid) === ctrl) streamAbortsRef.current.delete(sid);
      setStreaming(sid, false);
      finishStreamPresentation(sid);
      setActiveAgentBySession((m) => ({ ...m, [sid]: "" }));
      setExecPathBySession((m) => ({ ...m, [sid]: [] }));
    }
  }

  function stopCurrentGeneration() {
    if (!sessionId) return;
    streamAbortsRef.current.get(sessionId)?.abort();
  }

  function onAction(action: A2uiAction | undefined, node: A2uiComponent) {
    const name = action?.event?.name ?? node.id;
    const context = action?.event?.context ?? {};
    void send(
      `[ui-action] ${name}: ${JSON.stringify(context)}`,
      [],
      emptyInvocation(),
      "a2ui_action",
    );
  }

  /** Complete an MCP/tool OAuth request: open the authorize URL, capture the
   *  callback, then send the credential back as a function response — ADK
   *  exchanges the code for a token and resumes the paused tool call. The
   *  continuation streams into the same assistant turn. */
  async function onAuth(block: Extract<Block, { kind: "auth" }>) {
    if (!block.authUri) throw new Error("事件中没有授权地址。");
    if (!appName || !userId || !sessionId) throw new Error("会话尚未就绪。");
    const sid = sessionId;
    const callbackUrl = await runOAuthPopup(block.authUri);
    const response = withAuthResponseUri(block.authConfig, callbackUrl);

    // The moment we have the callback, mark the auth card resolved so it
    // collapses to a compact "已授权" row immediately — rather than sitting on
    // "等待授权…" until the whole reply finishes streaming.
    const resolveAuth = (bs: Block[]) =>
      bs.map((b) => (b.kind === "auth" && !b.done ? { ...b, done: true } : b));
    setTurnsFor(sid, (t) => {
      const next = t.slice();
      const last = next[next.length - 1];
      if (last?.role === "assistant") {
        next[next.length - 1] = { ...last, blocks: resolveAuth(last.blocks) };
      }
      return next;
    });

    // Base = the current assistant turn's blocks (keeps the thinking + resolved
    // auth card); the resumed run's events are appended after it.
    const lastTurn = turns[turns.length - 1];
    const base = resolveAuth(
      lastTurn && lastTurn.role === "assistant" ? lastTurn.blocks : [],
    );

    const ctrl = new AbortController();
    streamAbortsRef.current.set(sid, ctrl);
    setStreaming(sid, true);
    startStreamPresentation(sid);
    let streamFailed = false;
    const environmentMounts = environmentMountsBySession[
      studioToolSelectionKey(appName, userId, sid)
    ] ?? [];
    const resumedPlatformTools = environmentMounts.length > 0
      ? [...new Set([...selectedStudioToolIds, ...ENVIRONMENT_STUDIO_TOOL_IDS])]
      : selectedStudioToolIds;
    try {
      let acc = emptyAcc();
      let currentStreamAuthor = lastTurn?.meta?.author ?? "";
      let currentBase = base;
      let tokens = 0;
      let ts = Date.now() / 1000;
      let eventId = lastTurn?.meta?.eventId ?? "";
      let invocationId = lastTurn?.meta?.invocationId ?? "";
      let hasCompletedReply = false;
      for await (const event of runSSE({
        appName,
        userId,
        sessionId,
        text: "",
        functionResponses: [
          { id: block.callId, name: "adk_request_credential", response },
        ],
        platformTools: currentRuntime ? resumedPlatformTools : undefined,
        environmentMounts: currentRuntime && environmentMounts.length > 0
          ? environmentMounts
          : undefined,
        signal: ctrl.signal,
        onRuntimeContext: (context) => {
          setRuntimeLogTargetsBySession((current) => ({
            ...current,
            [`${appName}\n${sid}`]: context,
          }));
        },
      })) {
        if (ctrl.signal.aborted) break;
        const errMsg = event.error ?? event.errorMessage ?? event.error_message;
        if (typeof errMsg === "string" && errMsg) {
          streamFailed = true;
          if (viewSidRef.current === sid) setError(errMsg);
          break;
        }
        applyStreamSignals(sid, event);
        const eventAuthor = event.author && event.author !== "user"
          ? event.author
          : "";
        if (eventAuthor && eventAuthor !== currentStreamAuthor) {
          currentStreamAuthor = eventAuthor;
          currentBase = [];
          acc = emptyAcc();
        }
        acc = applyEvent(acc, event);
        const usage = event.usageMetadata ?? event.usage_metadata;
        addTokenUsageFor(appName, sid, event);
        if (usage?.totalTokenCount) tokens = usage.totalTokenCount;
        if (event.timestamp) ts = event.timestamp;
        if (event.id) eventId = event.id;
        const nextInvocationId = event.invocationId ?? event.invocation_id;
        if (nextInvocationId) invocationId = nextInvocationId;
        const blocks = [...currentBase, ...acc.blocks];
        if (
          event.partial !== true &&
          turnHasVisibleContent({ role: "assistant", blocks: acc.blocks })
        ) {
          hasCompletedReply = true;
        }
        setTurnsFor(sid, (t) => {
          const next = t.slice();
          const last = next[next.length - 1];
          const meta = {
            author: currentStreamAuthor || last?.meta?.author,
            tokens: tokens || last?.meta?.tokens,
            ts,
            eventId: eventId || last?.meta?.eventId,
            invocationId: invocationId || last?.meta?.invocationId,
          };
          if (
            last?.role === "assistant" &&
            (!last.meta?.author || last.meta.author === currentStreamAuthor)
          ) {
            next[next.length - 1] = {
              ...last,
              blocks,
              meta,
            };
          } else {
            next.push({ role: "assistant", blocks, meta });
          }
          return next;
        });
      }
      if (!ctrl.signal.aborted && !streamFailed && !hasCompletedReply) {
        streamFailed = true;
        if (viewSidRef.current === sid) {
          setError(RUN_SSE_INCOMPLETE_RESPONSE_ERROR);
        }
      }
      void refreshSessions(appName);
      if (!ctrl.signal.aborted && !streamFailed && eventId) {
        automaticEvaluationStatusRefreshRef.current();
      }
    } catch (e) {
      streamFailed = true;
      if (
        (e as Error)?.name !== "AbortError" &&
        !ctrl.signal.aborted &&
        viewSidRef.current === sid
      ) {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      if (streamAbortsRef.current.get(sid) === ctrl) streamAbortsRef.current.delete(sid);
      setStreaming(sid, false);
      finishStreamPresentation(sid);
      setActiveAgentBySession((m) => ({ ...m, [sid]: "" }));
      setExecPathBySession((m) => ({ ...m, [sid]: [] }));
    }
  }

  // Hooks must stay above the authentication returns below. Connection state
  // may survive an auth transition, so discovery also waits for resolved access.
  const currentConn = connections.find(
    (connection) =>
      connection.runtimeId &&
      connection.apps.some(
        (candidate) => remoteAppId(connection.id, candidate) === appName,
      ),
  );
  const currentRuntime =
    currentConn && currentConn.runtimeId && currentConn.region
      ? {
          runtimeId: currentConn.runtimeId,
          name: currentConn.name,
          region: currentConn.region,
        }
      : undefined;
  const selectedDraftStudioRuntime =
    draftStudioRuntime?.appName === appName ? draftStudioRuntime : undefined;
  const studioToolRuntime = currentRuntime ?? selectedDraftStudioRuntime;

  useEffect(() => {
    let cancelled = false;
    setStudioToolCapabilities(null);
    setStudioToolsError("");
    if (
      authStatus !== "authenticated" ||
      !access ||
      myAgents ||
      agentDetailTarget ||
      !studioToolRuntime
    ) {
      setStudioToolsLoading(false);
      return;
    }
    setStudioToolsLoading(true);
    getRuntimeStudioToolCapabilities(
      studioToolRuntime.runtimeId,
      studioToolRuntime.region,
    )
      .then((capabilities) => {
        if (!cancelled) setStudioToolCapabilities(capabilities);
      })
      .catch((cause) => {
        if (cancelled) return;
        setStudioToolsError(
          cause instanceof Error ? cause.message : "读取本地工具失败",
        );
      })
      .finally(() => {
        if (!cancelled) setStudioToolsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    access,
    agentDetailTarget,
    authStatus,
    myAgents,
    studioToolRuntime?.region,
    studioToolRuntime?.runtimeId,
  ]);

  useEffect(() => {
    const controller = new AbortController();
    setSessionEnvironments([]);
    setSessionWorkspaces([]);
    setSessionEnvironmentsError("");
    if (
      authStatus !== "authenticated" ||
      !access ||
      myAgents ||
      agentDetailTarget ||
      !studioToolRuntime
    ) {
      setSessionEnvironmentsLoading(false);
      return () => controller.abort();
    }
    setSessionEnvironmentsLoading(true);
    void Promise.all([
      listEnvironments(controller.signal),
      listWorkspaces(controller.signal),
    ])
      .then(([items, workspaces]) => {
        if (controller.signal.aborted) return;
        setSessionEnvironments(items.filter((environment) =>
          environment.baseEnvironment === "aio-sandbox" &&
          environment.latestVersion?.status === "available" &&
          environment.latestVersion.toolStatus === "ready" &&
          Boolean(environment.latestVersion.toolId)
        ));
        setSessionWorkspaces(workspaces);
      })
      .catch((cause) => {
        if (controller.signal.aborted) return;
        setSessionEnvironmentsError(
          cause instanceof Error ? cause.message : "读取环境失败",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setSessionEnvironmentsLoading(false);
      });
    return () => controller.abort();
  }, [
    access,
    agentDetailTarget,
    authStatus,
    environmentView,
    myAgents,
    studioToolRuntime?.region,
    studioToolRuntime?.runtimeId,
  ]);

  if (authError) {
    return (
      <div className="boot boot-error">
        <p>{authError}</p>
        <button type="button" onClick={resolveAuth}>
          重试
        </button>
      </div>
    );
  }
  if (authStatus === null) {
    return <div className="boot" />; // resolving identity
  }
  if (authStatus === "unauthenticated") {
    return (
      <LoginPage
        branding={siteBranding}
        cloudProvider={cloudProvider}
        onUsername={onUsername}
      />
    );
  }
  if (!access) {
    return <div className="boot" />;
  }

  const canCreateAgents = access.capabilities.createAgents;
  const canManageAgents = access.capabilities.manageAgents;
  const canViewAgentUsage = features.agentUsage && canManageAgents;
  const visibleCreateView = canCreateAgents ? createView : null;
  const showAddMenu = canCreateAgents && addMenu;
  const showAddAgent = canCreateAgents && addAgent;
  const showManageAgents = manageAgents && Boolean(
    agentDetailTarget || focusedDeploymentTaskId || focusedWorkspaceAgentId,
  );
  const agentEntries = buildAgentEntries(apps, connections);
  const workspaceAgentEntries: AgentEntry[] = agentEntries
    .filter(
      (entry) =>
        entry.runtimeId &&
        (libraryRuntimeIds === null || libraryRuntimeIds.has(entry.runtimeId)),
    )
    .map((entry) => ({
      ...entry,
      canDelete: entry.runtimeId
        ? libraryRuntimePermissions[entry.runtimeId]?.canDelete === true
        : false,
    }));
  const orderedWorkspaceAgentEntries: AgentEntry[] = (() => {
    if (workspaceAgentEntries.length === 0) return workspaceAgentEntries;
    const orderIndex = new Map(workspaceAgentOrder.map((id, index) => [id, index]));
    return [...workspaceAgentEntries].sort((left, right) => {
      const leftIndex = orderIndex.get(left.id);
      const rightIndex = orderIndex.get(right.id);
      if (leftIndex != null && rightIndex != null) return leftIndex - rightIndex;
      if (leftIndex != null) return -1;
      if (rightIndex != null) return 1;
      return workspaceAgentEntries.indexOf(left) - workspaceAgentEntries.indexOf(right);
    });
  })();
  const labelOf = (id: string) => agentEntries.find((e) => e.id === id)?.label ?? id;
  // The runtime backing the current selection (if it's a cloud runtime app) —
  // drives the picker's side detail panel.
  const activeStudioToolSelectionKey = sessionId
    ? studioToolSelectionKey(appName, userId, sessionId)
    : "";
  const storedStudioToolIds = sessionId
    ? (studioToolIdsBySession[activeStudioToolSelectionKey] ?? [])
    : draftStudioToolIds;
  const allStudioToolIds = new Set(
    studioToolCapabilities?.tools.map((tool) => tool.id) ?? [],
  );
  const availableStudioToolIds = new Set(
    [...allStudioToolIds].filter((toolId) => !agentInfo?.tools.includes(toolId)),
  );
  const selectedEnvironmentMounts = sessionId
    ? environmentMountsBySession[activeStudioToolSelectionKey] ?? []
    : [];
  const selectedEnvironmentWorkspaceIds = sessionId
    ? environmentWorkspaceIdsBySession[activeStudioToolSelectionKey] ?? []
    : [];
  const canMountSessionEnvironment = ENVIRONMENT_STUDIO_TOOL_IDS.every((toolId) =>
    allStudioToolIds.has(toolId)
  );
  const selectedStudioToolIds = [...new Set([
    ...storedStudioToolIds.filter((toolId) => availableStudioToolIds.has(toolId)),
    ...(selectedEnvironmentMounts.length > 0 && canMountSessionEnvironment
      ? [...ENVIRONMENT_STUDIO_TOOL_IDS]
      : []),
  ])];
  const visibleStudioTools = studioToolCapabilities?.tools.filter((tool) =>
    !ENVIRONMENT_STUDIO_TOOL_IDS.includes(
      tool.id as (typeof ENVIRONMENT_STUDIO_TOOL_IDS)[number],
    ) || selectedEnvironmentMounts.length > 0
  ) ?? [];
  const updateSelectedStudioToolIds = (selectedIds: string[]) => {
    const next = [...new Set([
      ...selectedIds,
      ...(selectedEnvironmentMounts.length > 0 ? [...ENVIRONMENT_STUDIO_TOOL_IDS] : []),
    ])].filter((toolId) =>
      availableStudioToolIds.has(toolId),
    );
    if (!sessionId) {
      setDraftStudioToolIds(next);
      return;
    }
    setStudioToolIdsBySession((current) => ({
      ...current,
      [activeStudioToolSelectionKey]: next,
    }));
  };
  const updateSelectedEnvironments = (
    selections: SessionEnvironmentMountSelection[],
    workspaceIds: string[] = [],
  ) => {
    if (!sessionId) return;
    const valid = selections.every((selection) => sessionEnvironments.some((environment) =>
      environment.id === selection.environment_id &&
      environment.latestVersion?.versionId === selection.environment_version_id
    ));
    if (!valid) return;
    setEnvironmentMountsBySession((current) => ({
      ...current,
      [activeStudioToolSelectionKey]: selections,
    }));
    setEnvironmentWorkspaceIdsBySession((current) => ({
      ...current,
      [activeStudioToolSelectionKey]: workspaceIds,
    }));
    setStudioToolIdsBySession((current) => {
      const selectedIds = current[activeStudioToolSelectionKey] ?? [];
      return {
        ...current,
        [activeStudioToolSelectionKey]: selections.length > 0
          ? [...new Set([...selectedIds, ...ENVIRONMENT_STUDIO_TOOL_IDS])]
          : selectedIds.filter((toolId) => !ENVIRONMENT_STUDIO_TOOL_IDS.includes(
              toolId as (typeof ENVIRONMENT_STUDIO_TOOL_IDS)[number],
            )),
      };
    });
  };

  const studioToolsUnavailableReason = studioToolsError
    ? studioToolsError
    : studioToolCapabilities && !studioToolCapabilities.enabled
      ? "本地 Studio BFF 没有配置工具。"
      : studioToolCapabilities && !studioToolCapabilities.supported
        ? "当前 Runtime Agent 未开启 BFF 工具能力。"
        : "";
  const sessionEnvironmentsUnavailableReason = sessionEnvironmentsError
    || (!studioToolsLoading && studioToolCapabilities && !canMountSessionEnvironment
      ? "当前 Studio BFF 未提供 Sandbox 执行工具。"
      : "");
  const connectedRuntimeId = currentRuntime?.runtimeId ?? "";
  const currentRuntimeAppName = currentConn
    ? currentConn.apps.find((app) =>
        remoteAppId(currentConn.id, app) === appName
      ) ?? agentInfo?.appName ?? currentConn.apps[0] ?? currentConn.name
    : "";

  const submitIssueFeedbackForTurn = async (feedback: {
    issues: IssueFeedbackIssue[];
    description: string;
  }): Promise<void> => {
    const target = issueFeedbackTarget;
    const sid = sessionId;
    if (!target || !sid) throw new Error("当前会话不可用，请关闭后重试。");
    const invocationId = target.turn.meta?.invocationId ?? "";
    const sessionTrace = connectedRuntimeId
      ? []
      : await getSessionTrace(appName, sid).catch(() => []);
    await submitIssueFeedback({
      source: "agent_exec",
      module: "conversation",
      issues: feedback.issues,
      problem: "",
      description: feedback.description,
      page: "conversation",
      appName: currentRuntimeAppName || appName,
      runtimeId: connectedRuntimeId,
      region: currentRuntime?.region ?? "cn-beijing",
      sessionId: sid,
      eventId: target.turn.meta?.eventId ?? target.turn.meta?.localId ?? "",
      invocationId,
      input: target.input,
      output: turnText(target.turn),
      toolCalls: issueFeedbackToolCalls(target.turn),
      trace: traceForInvocation(sessionTrace, invocationId),
    });
  };

  const submitPlatformIssueFeedback = async (feedback: {
    module: IssueFeedbackModule;
    issues: IssueFeedbackIssue[];
    description: string;
  }): Promise<void> => {
    const sid = sandboxSession ? "" : sessionId;
    const contextTurns = sandboxSession || sid ? turns : [];
    const sessionTrace = sid && appName && !connectedRuntimeId
      ? await getSessionTrace(appName, sid).catch(() => [])
      : [];
    await submitIssueFeedback({
      source: "platform",
      module: feedback.module,
      issues: feedback.issues,
      problem: "",
      description: feedback.description,
      page: platformFeedbackOrigin ?? "unknown",
      appName: currentRuntimeAppName || appName,
      runtimeId: connectedRuntimeId,
      region: currentRuntime?.region ?? "cn-beijing",
      sessionId: sid,
      eventId: "",
      invocationId: "",
      input: contextTurns
        .filter((turn) => turn.role === "user")
        .map(turnText)
        .filter(Boolean)
        .join("\n\n"),
      output: contextTurns
        .filter((turn) => turn.role === "assistant")
        .map(turnText)
        .filter(Boolean)
        .join("\n\n"),
      toolCalls: contextTurns.flatMap(issueFeedbackToolCalls),
      trace: sessionTrace,
    });
  };

  const rateAssistantTurn = async (
    turn: Turn,
    rating: MessageFeedbackRating | null,
    input = "",
    comment = "",
    reportGlobalError = true,
  ): Promise<string | null> => {
    const eventId = turn.meta?.eventId;
    const sid = sessionId;
    if (!eventId || !sid || !currentRuntime) {
      return "当前回复暂不支持加入评测集";
    }
    if (cloudProvider === "byteplus") {
      return "BytePlus 暂不支持 AgentKit 评测集";
    }
    const output = turnText(turn);
    const previousFeedback = turn.meta?.feedback;
    const optimisticFeedback = {
      ...previousFeedback,
      rating,
      comment,
      syncStatus: "syncing" as const,
      updatedAt: Date.now() / 1000,
    };
    setTurnsFor(sid, (current) =>
      current.map((item) =>
        item.meta?.eventId === eventId
          ? { ...item, meta: { ...item.meta, feedback: optimisticFeedback } }
          : item,
      ),
    );
    setFeedbackPendingIds((current) => new Set(current).add(eventId));
    if (currentConn?.runtimeId && currentRuntimeAppName) {
      upsertCachedAgentFeedbackCase({
        runtimeId: currentConn.runtimeId,
        region: currentConn.region ?? defaultCloudRegion(cloudProvider),
        appName: currentRuntimeAppName,
        userId,
        sessionId: sid,
        messageId: eventId,
        invocationId: turn.meta?.invocationId,
        rating,
        input,
        output,
        comment,
        createdAt: turn.meta?.ts
          ? new Date(turn.meta.ts * 1000).toISOString()
          : undefined,
      });
    }
    try {
      const feedback = await submitMessageFeedback({
        appName,
        userId,
        sessionId: sid,
        eventId,
        rating,
        comment,
      });
      setTurnsFor(sid, (current) =>
        current.map((item) =>
          item.meta?.eventId === eventId
            ? { ...item, meta: { ...item.meta, feedback } }
            : item,
        ),
      );
      setSessions((current) =>
        current.map((item) =>
          item.id === sid
            ? {
                ...item,
                state: {
                  ...(item.state ?? {}),
                  [`veadk_feedback:${eventId}`]: feedback,
                },
              }
            : item,
        ),
      );
      if (currentConn?.runtimeId && currentRuntimeAppName) {
        upsertCachedAgentFeedbackCase({
          runtimeId: currentConn.runtimeId,
          region: currentConn.region ?? defaultCloudRegion(cloudProvider),
          appName: currentRuntimeAppName,
          userId,
          sessionId: sid,
          messageId: eventId,
          invocationId: turn.meta?.invocationId,
          rating: feedback.rating,
          input,
          output,
          comment,
          createdAt: turn.meta?.ts
            ? new Date(turn.meta.ts * 1000).toISOString()
            : undefined,
        });
        refreshAgentFeedbackCases({
          runtimeId: currentConn.runtimeId,
          region: currentConn.region ?? defaultCloudRegion(cloudProvider),
          appName: currentRuntimeAppName,
          pageSize: 100,
        });
      }
    } catch (feedbackError) {
      const feedbackErrorMessage = feedbackError instanceof Error
        ? feedbackError.message
        : String(feedbackError);
      setTurnsFor(sid, (current) =>
        current.map((item) =>
          item.meta?.eventId === eventId
            ? { ...item, meta: { ...item.meta, feedback: previousFeedback } }
            : item,
        ),
      );
      if (currentConn?.runtimeId && currentRuntimeAppName) {
        upsertCachedAgentFeedbackCase({
          runtimeId: currentConn.runtimeId,
          region: currentConn.region ?? defaultCloudRegion(cloudProvider),
          appName: currentRuntimeAppName,
          userId,
          sessionId: sid,
          messageId: eventId,
          invocationId: turn.meta?.invocationId,
          rating: previousFeedback?.rating ?? null,
          input,
          output,
          comment: previousFeedback?.comment ?? "",
          createdAt: turn.meta?.ts
            ? new Date(turn.meta.ts * 1000).toISOString()
            : undefined,
        });
      }
      if (reportGlobalError && viewSidRef.current === sid) {
        setError(feedbackErrorMessage);
      }
      return feedbackErrorMessage;
    } finally {
      setFeedbackPendingIds((current) => {
        const next = new Set(current);
        next.delete(eventId);
        return next;
      });
    }
    return null;
  };

  const submitResponseAnnotation = async (note: string) => {
    const target = responseAnnotationTarget;
    if (!target) return;
    const errorMessage = await rateAssistantTurn(
      target.turn,
      "bad",
      target.input,
      formatResponseAnnotationComment(target.selectedText, note),
      false,
    );
    if (errorMessage) throw new Error(errorMessage);
  };

  // Prepare every piece of first-paint Agent data before changing the visible
  // selection. Background streams keep persisting to their original sessions.
  const refreshCurrentAgentAndStartNewChat = async (id: string) => {
    const request = agentSelectionPreparationRequestRef.current + 1;
    agentSelectionPreparationRequestRef.current = request;
    const nextConnections = loadConnections();
    const cachedCapabilities = newChatCapabilitiesCacheRef.current.get(id);
    const evaluationTarget = automaticEvaluationTargetForSelection(
      nextConnections,
      id,
    );
    const [capabilities, hydratedSessions, nextAgentInfo, evaluationStatuses] =
      await Promise.all([
        cachedCapabilities
          ? Promise.resolve(cachedCapabilities)
          : probeNewChatCapabilities(id),
        loadHydratedSessions(id, userId),
        getAgentInfo(id).catch(() => null),
        evaluationTarget
          ? getAutomaticEvaluationStatuses({
              runtimeId: evaluationTarget.runtimeId,
              region: evaluationTarget.region,
              appName: evaluationTarget.appName,
              userId,
            }).catch(() => undefined)
          : Promise.resolve(undefined),
      ]);
    if (agentSelectionPreparationRequestRef.current !== request) return;

    const selectionEffectsWillRerun =
      id !== appName ||
      myAgents ||
      agentDetailTarget !== null ||
      sandboxSession !== null;
    preparedAgentSelectionRef.current = selectionEffectsWillRerun
      ? {
          agentId: id,
          userId,
          automaticEvaluationStatuses: evaluationStatuses,
        }
      : null;
    sessionRefreshRequestRef.current += 1;
    newChatCapabilitiesCacheRef.current.set(id, capabilities);
    setConnections(nextConnections);
    setNewChatCapabilities(capabilities);
    commitHydratedSessions(id, hydratedSessions);
    setAgentInfo(nextAgentInfo);
    setCapabilitiesLoading(false);
    setEvaluatingSids(new Set(
      evaluationStatuses?.items
        .filter((status) => status.state === "running")
        .map((status) => status.sessionId) ?? [],
    ));
    setAppName(id);
    exitAgentDetailContext();
    setFocusedDeploymentTaskId("");
    setFocusedWorkspaceAgentId("");
    setCreateView(null);
    setSkillCenter(false);
    setAddAgent(false);
    setAddMenu(false);
    setSearchView(false);
    setIntelligentDeployment(null);
    setWorkspaceView(false);
    setEnvironmentView(false);
    startNewChat();
  };

  const openIntelligentDeploymentChat = async (agentId: string) => {
    await refreshCurrentAgentAndStartNewChat(agentId);
  };

  const selectAgent = async (id: string) => {
    await refreshCurrentAgentAndStartNewChat(id);
  };

  const openAgentCreateFromMyAgents = (region: string) => {
    if (!canCreateAgents) {
      setError("当前账号没有添加 Agent 的权限。");
      return;
    }
    setMyAgents(false);
    setManageAgents(false);
    setNewRuntimeRegion(region);
    setImportedDraft(null);
    setCreateView(null);
    setAddMenuSurface("entry");
    setAddMenu(true);
    setError("");
  };

  const connectRuntimeForUser = async (
    agent: MyAgentCardData,
    source: AgentConnectSource,
  ): Promise<string> => {
    if (!agent.runtime) throw new Error("缺少 Runtime 信息，无法连接智能体。");
    const operation = beginAgentConnect({
      targetId: String(agent.runtime.runtimeId),
      agentKind: "runtime",
      connectSource: source,
    });
    try {
      const agentId = await connectRuntime(
        agent.runtime.runtimeId,
        agent.name,
        agent.runtime.region,
        agent.runtime.currentVersion,
      );
      operation.succeed({
        runtimeRegion: agent.runtime.region,
        runtimeIsMine: agent.isMine ? 1 : 0,
      });
      return agentId;
    } catch (error) {
      operation.fail(classifyTelemetryError(error));
      throw error;
    }
  };

  const connectMyAgent = async (
    agent: MyAgentCardData,
    options: {
      rethrow?: boolean;
      source?: AgentConnectSource;
      onConnected?: (agentId: string) => void;
    } = {},
  ) => {
    if (!agent.runtime) return;
    try {
      const agentId = await connectRuntimeForUser(
        agent,
        options.source ?? "my_agents",
      );
      await refreshCurrentAgentAndStartNewChat(agentId);
      options.onConnected?.(agentId);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      setError(message);
      if (options.rethrow) throw new Error(message);
    }
  };

  const openMyAgentDetails = (agent: MyAgentCardData) => {
    if (!agent.runtime) return;
    pushStudioPage({ page: "agent-detail", returnTo: "agents" });
    setAgentDetailTarget(agent);
    setFocusedDeploymentTaskId("");
    setFocusedWorkspaceAgentId("");
    setMyAgents(true);
    setManageAgents(true);
    setError("");
  };

  const closeAgentDetailPage = () => {
    exitAgentDetailContext();
    setFocusedDeploymentTaskId("");
    setFocusedWorkspaceAgentId("");
    setMyAgents(true);
    setError("");
  };

  const closeSandboxAgentDetailPage = () => {
    popStudioPage("sandbox-agent-detail");
    setSandboxAgentDetailTarget(null);
    setSandboxAgentWorkspace(null);
    setMyAgents(true);
    setError("");
  };

  const closeSystemInfoPage = () => {
    popStudioPage("system-info");
    setError("");
  };

  const openSandboxAgentCreate = (
    kind: "codex" | SandboxAgentKind,
  ) => {
    if (!canCreateAgents) {
      setError("当前账号没有创建智能体的权限。");
      return;
    }
    openSandboxLaunch(kind, true);
  };

  const openMyAgentsPage = () => {
    setPlatformFeedbackOrigin(null);
    if (sandboxSession) exitSandboxSession();
    viewSidRef.current = "";
    setSessionId("");
    setCreateView(null);
    setSkillCenter(false);
    setAddAgent(false);
    setAddMenu(false);
    setSearchView(false);
    setManageAgents(false);
    setAgentDetailTarget(null);
    setSandboxAgentDetailTarget(null);
    setSandboxAgentWorkspace(null);
    setFocusedDeploymentTaskId("");
    setFocusedWorkspaceAgentId("");
    setMyAgents(true);
    setWorkspaceView(false);
    setEnvironmentView(false);
    setPageStack([]);
    setApplicationsView(null);
    setCronJobsView(false);
    setError("");
  };

  const openWorkspacePage = () => {
    setPlatformFeedbackOrigin(null);
    if (sandboxSession) exitSandboxSession();
    viewSidRef.current = "";
    setSessionId("");
    setCreateView(null);
    setSkillCenter(false);
    setAddAgent(false);
    setAddMenu(false);
    setSearchView(false);
    setManageAgents(false);
    setAgentDetailTarget(null);
    setSandboxAgentDetailTarget(null);
    setSandboxAgentWorkspace(null);
    setFocusedDeploymentTaskId("");
    setFocusedWorkspaceAgentId("");
    setMyAgents(false);
    setEnvironmentView(false);
    setWorkspaceView(true);
    setPageStack([]);
    setApplicationsView(null);
    setCronJobsView(false);
    setError("");
  };

  const openApplicationsPage = () => {
    setPlatformFeedbackOrigin(null);
    if (sandboxSession) exitSandboxSession();
    viewSidRef.current = "";
    setSessionId("");
    setCreateView(null);
    setSkillCenter(false);
    setAddAgent(false);
    setAddMenu(false);
    setSearchView(false);
    setManageAgents(false);
    setAgentDetailTarget(null);
    setSandboxAgentDetailTarget(null);
    setSandboxAgentWorkspace(null);
    setMyAgents(false);
    setWorkspaceView(false);
    setEnvironmentView(false);
    setPageStack([]);
    setCronJobsView(false);
    setApplicationsView("catalog");
    setError("");
  };

  const openCronJobsPage = () => {
    setPlatformFeedbackOrigin(null);
    if (sandboxSession) exitSandboxSession();
    viewSidRef.current = "";
    setSessionId("");
    setCreateView(null);
    setSkillCenter(false);
    setAddAgent(false);
    setAddMenu(false);
    setSearchView(false);
    setManageAgents(false);
    setAgentDetailTarget(null);
    setSandboxAgentDetailTarget(null);
    setSandboxAgentWorkspace(null);
    setMyAgents(false);
    setWorkspaceView(false);
    setEnvironmentView(false);
    setPageStack([]);
    setApplicationsView(null);
    setCronJobsView(true);
    setError("");
  };

  const talkToWorkspaceAgent = async (agent: AgentEntry) => {
    setFeedbackCaseReturnAgentId("");
    setFeedbackTargetEventId("");
    if (agent.runtimeId && agent.id.startsWith("detail:")) {
      const operation = beginAgentConnect({
        targetId: String(agent.runtimeId),
        agentKind: "runtime",
        connectSource: "agent_workspace",
      });
      try {
        const agentId = await connectRuntime(
          agent.runtimeId,
          agent.label,
          agent.region ?? defaultCloudRegion(cloudProvider),
          agent.currentVersion,
        );
        operation.succeed({
          runtimeRegion: agent.region,
        });
        await refreshCurrentAgentAndStartNewChat(agentId);
      } catch (cause) {
        operation.fail(classifyTelemetryError(cause));
        setError(cause instanceof Error ? cause.message : String(cause));
      }
      return;
    }
    await refreshCurrentAgentAndStartNewChat(agent.id);
  };

  const detailConnection = agentDetailTarget?.runtime
    ? connections.find(
        (connection) =>
          connection.runtimeId === agentDetailTarget.runtime?.runtimeId,
      )
    : undefined;
  const detailAgentEntry: AgentEntry | null = agentDetailTarget?.runtime
    ? {
        id: `detail:${agentDetailTarget.runtime.runtimeId}`,
        label: agentDetailTarget.name,
        app: agentDetailTarget.appName ?? agentDetailTarget.name,
        remote: true,
        runtimeApp: detailConnection?.apps[0],
        runtimeId: agentDetailTarget.runtime.runtimeId,
        region: agentDetailTarget.runtime.region,
        currentVersion: agentDetailTarget.runtime.currentVersion,
        canDelete: agentDetailTarget.runtime.canDelete,
      }
    : null;

  const currentStudioPage: StudioPageId = activeStackPage === "system-info"
    ? activeStackEntry?.returnTo ?? "new-chat"
    : activeStackPage === "agent-detail" || activeStackPage === "sandbox-agent-detail"
      ? activeStackPage
      : platformFeedbackOrigin !== null
        ? "feedback"
        : environmentView
          ? "environments"
        : workspaceView
          ? "workspaces"
        : skillCenter
          ? "library"
          : cronJobsView
            ? "cronjobs"
            : applicationsView
              ? "applications"
              : searchView
                ? "search"
                : sandboxAgentWorkspace
                  ? "sandbox-agent-workspace"
                  : myAgents || manageAgents
                    ? "agents"
                    : sandboxSession
                      ? "sandbox"
                      : sessionId
                        ? "conversation"
                        : createView || addAgent || addMenu
                          ? "create"
                          : "new-chat";

  const sidebarActivePage: SidebarPage = systemInfo
    ? null
    : platformFeedbackOrigin !== null
      ? "feedback"
      : environmentView
        ? "environments"
      : workspaceView
        ? "workspaces"
      : skillCenter
        ? "library"
        : cronJobsView
          ? "cronjobs"
          : applicationsView
            ? "applications"
            : searchView
              ? "search"
              : myAgents || manageAgents || sandboxAgentDetailTarget || sandboxAgentWorkspace
                ? "agents"
                : sessionId || sandboxSession || createView || skillCenter || addAgent || addMenu
                  ? null
                  : "new-chat";

  return (
    <div className="layout">
      <Sidebar
        branding={siteBranding}
        cloudProvider={cloudProvider}
        access={access}
        features={features}
        sessions={sessions}
        currentSessionId={sessionId}
        activePage={sidebarActivePage}
        streamingSids={streamingSids}
        evaluatingSids={evaluatingSids}
        sandboxHistory={sandboxSession && !sandboxSession.intelligentDevelopment
          ? {
              threads: sandboxCommands.threads,
              currentThreadId: sandboxSession.threadId,
              loading: sandboxCommands.threadsLoading,
              error: sandboxCommands.threadsError,
              hasMore: sandboxCommands.threadsHasMore,
              busyThreadId: sandboxCommands.threadActionId,
              newDisabled: sandboxBusy || sandboxCommands.commandBusy,
              onNew: () => void sandboxCommands.newThread(),
              onSelect: (threadId) => void sandboxCommands.resumeThread(threadId),
              onLoadMore: () => void sandboxCommands.loadMoreThreads(),
              onDelete: setSandboxThreadDeleteTarget,
          }
          : undefined}
        onNewChat={() => requestIntelligentNavigation(openNewChat)}
        onSearch={() => requestIntelligentNavigation(() => {
          setPlatformFeedbackOrigin(null);
          if (sandboxSession) exitSandboxSession();
          setCreateView(null);
          setSkillCenter(false);
          setAddAgent(false);
          setAddMenu(false);
          setManageAgents(false);
          setAgentDetailTarget(null);
          setSandboxAgentDetailTarget(null);
          setSandboxAgentWorkspace(null);
          setMyAgents(false);
          setWorkspaceView(false);
          setEnvironmentView(false);
          setPageStack([]);
          setApplicationsView(null);
          setCronJobsView(false);
          setSearchView(true);
          setError("");
        })}
        onQuickCreate={() => requestIntelligentNavigation(() => {
          if (!canCreateAgents) {
            setError("当前账号没有添加 Agent 的权限。");
            return;
          }
          if (sandboxSession) exitSandboxSession();
          // "添加 Agent" — open the two-card chooser. Drop any selected session.
          viewSidRef.current = "";
          setSessionId("");
          setSkillCenter(false);
          setAddAgent(false);
          setSearchView(false);
          setManageAgents(false);
          setAgentDetailTarget(null);
          setSandboxAgentDetailTarget(null);
          setSandboxAgentWorkspace(null);
          setMyAgents(false);
          setWorkspaceView(false);
          setEnvironmentView(false);
          setPageStack([]);
          setApplicationsView(null);
          setCronJobsView(false);
          setCreateView(null);
          setImportedDraft(null);
          setNewRuntimeRegion(defaultCloudRegion(cloudProvider));
          setAddMenuSurface("entry");
          setAddMenu(true);
          setError("");
        })}
        onLibrary={() => requestIntelligentNavigation(() => {
          if (sandboxSession) exitSandboxSession();
          setCreateView(null);
          setAddAgent(false);
          setAddMenu(false);
          setSearchView(false);
          setManageAgents(false);
          setAgentDetailTarget(null);
          setSandboxAgentDetailTarget(null);
          setSandboxAgentWorkspace(null);
          setMyAgents(false);
          setWorkspaceView(false);
          setEnvironmentView(false);
          setPageStack([]);
          setApplicationsView(null);
          setCronJobsView(false);
          setSkillCenterLaunch(null);
          setLibraryTab("skills");
          setLibraryPageTitle("技能库");
          setSkillCenter(true);
          setError("");
        })}
        onAddAgent={() => requestIntelligentNavigation(() => {
          if (!canCreateAgents) {
            setError("当前账号没有添加 Agent 的权限。");
            return;
          }
          if (sandboxSession) exitSandboxSession();
          viewSidRef.current = "";
          setCreateView(null);
          setSkillCenter(false);
          setSearchView(false);
          setManageAgents(false);
          setAgentDetailTarget(null);
          setSandboxAgentDetailTarget(null);
          setSandboxAgentWorkspace(null);
          setMyAgents(false);
          setWorkspaceView(false);
          setEnvironmentView(false);
          setPageStack([]);
          setApplicationsView(null);
          setCronJobsView(false);
          setSessionId("");
          setAddMenu(false);
          setAddAgent(true);
          setError("");
        })}
        onMyAgents={() => requestIntelligentNavigation(openMyAgentsPage)}
        onWorkspace={() => requestIntelligentNavigation(openWorkspacePage)}
        onApplications={() => requestIntelligentNavigation(openApplicationsPage)}
        onCronJobs={() => requestIntelligentNavigation(openCronJobsPage)}
        onAgentKitCli={() => setAgentKitCliOpen(true)}
        onSystemInfo={() => requestIntelligentNavigation(() => {
          pushStudioPage({
            page: "system-info",
            returnTo: currentStudioPage,
          });
          setError("");
        })}
        onIssueFeedback={() => {
          if (platformFeedbackOrigin !== null) return;
          setPageStack([]);
          setPlatformFeedbackOrigin(
            sidebarActivePage ??
              (sandboxSession
                ? "sandbox"
                : sessionId
                  ? "conversation"
                  : "workspace"),
          );
          setError("");
        }}
        onPickSession={(id) => requestIntelligentNavigation(() => {
          setPlatformFeedbackOrigin(null);
          setCreateView(null);
          setSkillCenter(false);
          setAddAgent(false);
          setAddMenu(false);
          setSearchView(false);
          setManageAgents(false);
          setAgentDetailTarget(null);
          setSandboxAgentDetailTarget(null);
          setSandboxAgentWorkspace(null);
          setMyAgents(false);
          setWorkspaceView(false);
          setEnvironmentView(false);
          setPageStack([]);
          setApplicationsView(null);
          setCronJobsView(false);
          setError("");
          pickSession(id);
        })}
        onDeleteSession={removeSession}
        userInfo={userInfo}
        onLogout={onLogout}
      />

      {(() => {
        const composer = (
          <div
            className={`composer-slot${sandboxSession ? " sandbox-composer-wrap" : ""}`}
          >
            {sandboxSession && (
              <SandboxSessionWarning
                agentName={
                  sandboxSession.intelligentDevelopment
                    ? "智能开发"
                    : sandboxSession.toolName === "codex"
                      ? "Codex"
                      : sandboxSession.toolName === "deepseek-harness"
                        ? "DeepSeek Harness"
                        : sandboxSession.toolName === "openclaw"
                          ? "OpenClaw"
                          : "Hermes"
                }
                expireAt={
                  sandboxSession.intelligentDevelopment
                    ? sandboxSession.expireAt
                    : undefined
                }
                exitLabel={
                  sandboxSession.intelligentDevelopment
                    ? "退出开发环境"
                    : undefined
                }
                onExit={() => requestIntelligentNavigation(
                  sandboxSession.intelligentDevelopment
                    ? returnToIntelligentCreate
                    : startNewChat
                )}
              />
            )}
            {sandboxSession ? (
              <SandboxComposer
                appName={appName}
                value={input}
                onChange={setInput}
                onSubmit={(value) => void submitSandboxInput(value)}
                onStop={sandboxBusy ? stopSandboxGeneration : undefined}
                disabled={false}
                busy={sandboxBusy || sandboxCommands.commandBusy}
                attachments={attachments}
                onAddFiles={addSandboxFiles}
                onRemoveAttachment={removeSandboxAttachment}
                actions={{
                  onOpenTerminal: () => void openSandboxTool("terminal"),
                  onOpenBrowser: () => void openSandboxTool("browser"),
                  onOpenPermissions: () => {
                    setSandboxSettingsError("");
                    setSandboxPermissionsOpen(true);
                  },
                  onOpenWorkspace: () => {
                    setSandboxSettingsError("");
                    setSandboxWorkspaceOpen(true);
                  },
                  onCopyEndpoint: copySandboxEndpoint,
                  endpointCopyEnabled:
                    newChatCapabilities.sandboxEndpointExportEnabled === true,
                  endpointCopyState: sandboxEndpointCopyState,
                  workspaceLocked: sandboxSession.workspaceLocked,
                  settingsBusy: sandboxSettingsBusy,
                  uploadBusy: sandboxUploadBusy || sandboxBusy,
                }}
                models={sandboxCommands.models}
                modelsLoading={sandboxCommands.modelsLoading}
                modelsLoaded={sandboxCommands.modelsLoaded}
                currentModel={sandboxSession.model}
                onRequestModels={() => void sandboxCommands.loadModels()}
                skills={sandboxCommands.skills}
                skillsLoading={sandboxCommands.skillsLoading}
                skillsLoaded={sandboxCommands.skillsLoaded}
                selectedSkills={sandboxCommands.selectedSkills}
                onRequestSkills={() => void sandboxCommands.loadSkills()}
                onSelectedSkillsChange={sandboxCommands.setSelectedSkills}
                textOnly={sandboxSession.intelligentDevelopment}
              />
            ) : (
              <Composer
                cloudProvider={cloudProvider}
                sessionId={sessionId}
                sessionInitializing={initializingSession}
                appName={appName}
                agentName={appName ? labelOf(appName) : "Agent"}
                value={input}
                onChange={setInput}
                videoTask={videoTask}
                onOpenVideoTask={() => {
                  if (videoTaskRef.current) setVideoTaskDialogOpen(true);
                }}
                onVideoSubmit={startVideoTask}
                onSubmit={() => {
                const text = input;
                if (
                  !sandboxSession &&
                  turns.length === 0 &&
                  newChatWorkspaceMode === "skill"
                ) {
                  if (!text.trim()) return;
                  let launch: SkillCenterWorkspaceLaunch;
                  if (newChatSkillAction === "create") {
                    launch = {
                      operation: "create",
                      initialIntent: text.trim(),
                      selectPublishSpace: true,
                    };
                  } else {
                    const target = newChatSkillTarget;
                    if (!target) {
                      setError("请先选择需要优化的 Skill。");
                      return;
                    }
                    launch = {
                      operation: "optimize",
                      initialIntent: text.trim(),
                      space: target.space,
                      source: {
                        kind: "skill-center",
                        skillId: target.skill.skillId,
                        version: target.skill.version,
                        region: target.space.region || defaultCloudRegion(cloudProvider),
                        projectName: target.space.projectName,
                        skillSpaceId: target.space.id,
                        skillSpaceName: target.space.name,
                        name: target.skill.skillName || target.skill.skillId,
                        description: target.skill.skillDescription,
                      },
                    };
                  }
                  setInput("");
                  setError("");
                  setSkillCenterLaunch(launch);
                  setLibraryTab("skills");
                  setLibraryPageTitle(
                    launch.operation === "create"
                      ? "创建技能"
                      : `优化 ${launch.source?.name || "技能"}`,
                  );
                  setSkillCenter(true);
                  return;
                }
                setInput("");
                if (sandboxSession) {
                  void sendSandboxMessage(text);
                  return;
                }
                const atts = attachments;
                const selectedInvocation = invocation;
                setAttachments([]);
                setInvocation(emptyInvocation());
                send(
                  text,
                  atts,
                  selectedInvocation,
                  "composer",
                  selectedStudioToolIds,
                );
                releaseAttachmentPreviews(atts);
              }}
              onStop={busy ? stopCurrentGeneration : undefined}
              disabled={
                sandboxSession
                  ? false
                  : !userId ||
                    newChatMode === "temporary" ||
                    newChatMode === "deepseek-harness" ||
                    (newChatWorkspaceMode === "agent" &&
                      newChatMode === "agent" &&
                      !appName) ||
                    (newChatWorkspaceMode === "skill" &&
                      newChatSkillAction === "optimize" &&
                      !newChatSkillTarget)
              }
              busy={
                sandboxSession
                  ? sandboxBusy
                  : conversationBusy
              }
              showMeta={turns.length > 0 && !sandboxSession}
              attachments={sandboxSession ? [] : attachments}
              skills={sandboxSession ? [] : availableSkills}
              agents={sandboxSession ? [] : availableAgents}
              invocation={sandboxSession ? emptyInvocation() : invocation}
              capabilitiesLoading={!sandboxSession && capabilitiesLoading}
              modelName={
                modelNameFromRuntime(agentInfo?.model) || activeTokenUsage.modelName
              }
              tokenUsage={activeTokenUsage}
              systemTokenEstimate={systemTokenEstimate}
              allowAttachments={!sandboxSession}
              onInvocationChange={setInvocation}
              onAddFiles={addFiles}
              onRemoveAttachment={removeDraftAttachment}
              newChatMode={sandboxSession ? "agent" : newChatMode}
              newChatWorkspaceMode={sandboxSession ? "agent" : newChatWorkspaceMode}
              newChatSkillAction={newChatSkillAction}
              newChatSkillTarget={newChatSkillTarget}
              skillCustomizationEnabled={
                newChatCapabilitiesReady &&
                newChatCapabilities.skillCustomizationEnabled === true
              }
              newChatTask={sandboxSession ? null : newChatTask}
              newChatLayout={!sandboxSession && turns.length === 0}
              showWorkspaceTabs={!sandboxSession && turns.length === 0}
              showAgentPicker={
                !sandboxSession &&
                turns.length === 0 &&
                newChatWorkspaceMode === "agent" &&
                newChatMode === "agent"
              }
              agentPickerDisabled={!userId || conversationBusy}
              selectedRuntimeId={studioToolRuntime?.runtimeId}
              agentsSource={agentsSource}
              localApps={apps}
              runtimeScope={access.capabilities.runtimeScope}
              onSelectLocalApp={refreshCurrentAgentAndStartNewChat}
              onSelectRuntime={async (runtime) => {
                try {
                  await connectMyAgent(
                    {
                      id: runtime.runtimeId,
                      name: runtime.name,
                      description: runtime.description?.trim() || "暂无描述",
                      createdAt: runtime.createdAt ?? "",
                      specificationLabel: "地域",
                      specification: formatCloudRegion(
                        runtime.region,
                        cloudProvider,
                      ),
                      isMine: runtime.isMine,
                      runtime: {
                        runtimeId: runtime.runtimeId,
                        region: runtime.region,
                        currentVersion: runtime.currentVersion,
                        canDelete: runtime.canDelete,
                      },
                    },
                    {
                      rethrow: true,
                      source: "new_chat_picker",
                      onConnected: (agentId) => {
                        setDraftStudioRuntime({
                          appName: agentId,
                          runtimeId: runtime.runtimeId,
                          name: runtime.name,
                          region: runtime.region,
                        });
                      },
                    },
                  );
                } catch (cause) {
                  setDraftStudioRuntime((current) =>
                    current?.runtimeId === runtime.runtimeId ? null : current,
                  );
                  throw cause;
                }
              }}
              onSelectSandboxSession={(session) =>
                openSandboxAgent(session, "new_chat_picker")
              }
              runtimeLogTarget={currentRuntime
                ? runtimeLogTargetsBySession[`${appName}\n${sessionId}`] ?? currentRuntime
                : undefined}
              showModeSelector={false}
              onWorkspaceModeChange={(mode) => {
                setNewChatWorkspaceMode(mode);
                if (mode !== "agent") setNewChatTask(null);
                setError("");
              }}
              onSkillActionChange={setNewChatSkillAction}
              onSkillTargetChange={setNewChatSkillTarget}
              temporaryEnabled={newChatCapabilitiesReady && newChatCapabilities.temporaryEnabled}
              deepseekHarnessEnabled={
                newChatCapabilitiesReady &&
                newChatCapabilities.deepseekHarnessEnabled
              }
              harnessEnabled={
                studioToolCapabilities?.enabled === true &&
                studioToolCapabilities.supported === true
              }
              builtinTools={
                studioToolCapabilities?.tools.map((tool) => tool.id) ?? []
              }
              onModeChange={(mode) => {
                if (mode === "temporary" && !newChatCapabilities.temporaryEnabled) return;
                if (mode === "temporary") {
                  setNewChatTask(null);
                  setNewChatMode(mode);
                  openSandboxLaunch();
                  return;
                }
                if (
                  mode === "deepseek-harness" &&
                  !newChatCapabilities.deepseekHarnessEnabled
                ) return;
                if (mode === "deepseek-harness") {
                  setNewChatTask(null);
                  setNewChatMode(mode);
                  openSandboxLaunch("deepseek-harness");
                  return;
                }
                setNewChatMode(mode);
                if (mode !== "agent") setNewChatTask(null);
                setError("");
              }}
              onTaskChange={setNewChatTask}
              />
            )}
          </div>
        );
        return (
          <section className="main-shell">
            <main
              className={`main${sandboxSession ? " is-sandbox-session" : ""}${
                sandboxSession?.intelligentDevelopment
                  ? " is-intelligent-development"
                  : ""
              }`}
            >
            {error && <div className="error" role="alert">{error}</div>}
            {draftStorageError && (
              <div className="error" role="alert">
                {draftStorageError}
              </div>
            )}
            {loadingSession && (
              <div className="session-loading">
                <Loader2 className="icon spin" /> 加载会话…
              </div>
            )}
            {feedbackCaseReturnAgentId &&
              !showManageAgents &&
              !showAddMenu &&
              !showAddAgent &&
              !searchView &&
              !skillCenter &&
              visibleCreateView === null && (
                <div className="case-return-bar">
                  <button type="button" onClick={returnToFeedbackCases}>
                    <ArrowLeft aria-hidden />
                    <span>返回评测案例</span>
                  </button>
                </div>
              )}

            {systemInfo ? (
              <SystemInfo
                version={version}
                localMode={agentsSource === "local"}
                role={access?.role ?? "user"}
                provider={cloudProvider}
                region={studioRegion || defaultCloudRegion(cloudProvider)}
                onBack={closeSystemInfoPage}
              />
            ) : platformFeedbackOrigin !== null ? (
              <PlatformFeedback
                initialModule={issueFeedbackModuleForPage(platformFeedbackOrigin)}
                onSubmit={submitPlatformIssueFeedback}
              />
            ) : environmentView ? (
              <EnvironmentCenter cloudProvider={cloudProvider} />
            ) : workspaceView ? (
              <WorkspaceCenter cloudProvider={cloudProvider} />
            ) : cronJobsView ? (
              <CronJobs cloudProvider={cloudProvider} />
            ) : applicationsView === "coding-agents" ? (
              <CodingAgentsIntegration
                onBack={() => setApplicationsView("catalog")}
              />
            ) : applicationsView === "feishu" ? (
              <FeishuBotIntegration
                onBack={() => setApplicationsView("catalog")}
              />
            ) : applicationsView === "website-integration" ? (
              <WebsiteIntegration
                onBack={() => setApplicationsView("catalog")}
              />
            ) : applicationsView && applicationsView !== "catalog" ? (
              <GitHubIntegration
                automation={applicationsView}
                cloudProvider={cloudProvider}
                onBack={() => setApplicationsView("catalog")}
              />
            ) : applicationsView === "catalog" ? (
              <Applications onOpen={setApplicationsView} />
            ) : sandboxAgentWorkspace ? (
              <SandboxAgentWorkspace
                workspace={sandboxAgentWorkspace}
                onBack={openMyAgentsPage}
              />
            ) : sandboxAgentDetailTarget ? (
              <SandboxAgentDetails
                session={sandboxAgentDetailTarget}
                onBack={closeSandboxAgentDetailPage}
                onOpen={() =>
                  openSandboxAgent(sandboxAgentDetailTarget, "sandbox_detail")
                }
                onDelete={() => deleteSandboxAgent(sandboxAgentDetailTarget)}
              />
            ) : myAgents && !showManageAgents ? (
              <MyAgents
                cloudProvider={cloudProvider}
                studioRegion={agentsSource === "local" ? "cn-beijing" : studioRegion}
                canCreate={canCreateAgents}
                canUpdate={canCreateAgents || canManageAgents}
                runtimeScope={access.capabilities.runtimeScope}
                onCreateAgent={openAgentCreateFromMyAgents}
                onOpenCodexProjectUpload={() => setSandboxProjectUploadOpen(true)}
                onUseAgent={(agent) =>
                  connectMyAgent(agent, { source: "my_agents" })
                }
                onViewAgentDetails={openMyAgentDetails}
                onCreateSandboxAgent={openSandboxAgentCreate}
                onUseSandboxAgent={(session) =>
                  openSandboxAgent(session, "my_agents")
                }
                onViewSandboxAgentDetails={openSandboxAgentDetails}
                activeType={myAgentsActiveType}
                onActiveTypeChange={setMyAgentsActiveType}
                sandboxRefreshKey={sandboxAgentRefreshKey}
                connectedRuntimeId={connectedRuntimeId}
                hiddenRuntimeIds={hiddenRuntimeIds}
                drafts={savedAgentDrafts}
                deploymentTasks={deploymentTasks}
                draftDeploymentTaskIds={draftDeploymentTaskIds}
                onViewDeploymentTask={openDeploymentDetail}
                onEditDraft={(item) => {
                  setMyAgents(false);
                  setImportedDraft(item.draft);
                  setCustomCreateMode("custom");
                  setCustomCreationSurface(
                    workspaceAgentCreationMode(item) === "quick"
                      ? "vulcan"
                      : "traditional",
                  );
                  setEditingDraftId(item.id);
                  editingDraftBaselineRef.current = item;
                  setRuntimeUpdateTarget(item.deploymentTarget ?? null);
                  setFocusedDeploymentTaskId("");
                  setFocusedWorkspaceAgentId("");
                  setCreateView("custom");
                  setError("");
                }}
                onDeleteDraft={(item) => deleteWorkspaceDrafts([item])}
              />
            ) : showManageAgents ? (
              <AgentWorkspace
                key={detailAgentEntry?.id ?? "workspace"}
                agents={detailAgentEntry ? [detailAgentEntry] : orderedWorkspaceAgentEntries}
                drafts={savedAgentDrafts}
                agentOrder={workspaceAgentOrder}
                selectedAgentId={appName}
                agentInfo={agentInfo}
                agentInfoAgentId={appName}
                loadingAgentInfo={capabilitiesLoading}
                canCreate={canCreateAgents}
                canUpdate={canCreateAgents || canManageAgents}
                canViewUsage={canViewAgentUsage}
                loadingAgents={agentLibraryLoading}
                agentsError={agentLibraryError}
                deploymentTasks={deploymentTasks}
                focusedDeploymentTaskId={focusedDeploymentTaskId}
                focusedAgentId={detailAgentEntry?.id ?? focusedWorkspaceAgentId}
                focusedAgentSection={focusedWorkspaceAgentSection}
                focusedCaseKind={focusedWorkspaceCaseKind}
                feedbackCasePreview={feedbackCasePreview}
                detailOnly
                onBack={closeAgentDetailPage}
                onRetryAgents={() => void refreshAgentLibrary()}
                onAgentOrderChange={saveWorkspaceAgentOrder}
                onDeleteAgents={deleteWorkspaceAgents}
                onDeleteDrafts={deleteWorkspaceDrafts}
                onSelectAgent={selectAgent}
                onTalkAgent={talkToWorkspaceAgent}
                onOpenFeedbackCase={(item) => void openFeedbackCaseInStudio(item)}
                onFeedbackCasesDeleted={clearDeletedFeedbackCases}
                onCreateAgent={() => {
                  if (!canCreateAgents) {
                    setError("当前账号没有添加 Agent 的权限。");
                    return;
                  }
                  exitAgentDetailContext();
                  setAddMenuSurface("entry");
                  setAddMenu(true);
                  setCreateView(null);
                  setImportedDraft(null);
                  setRuntimeUpdateTarget(null);
                  setNewRuntimeRegion(defaultCloudRegion(cloudProvider));
                  setEditingDraftId("");
                  editingDraftBaselineRef.current = null;
                  setFocusedDeploymentTaskId("");
                  setFocusedWorkspaceAgentId("");
                  setError("");
                }}
                onUpdateAgent={async (capability) => {
                  if (!canManageAgents && !canCreateAgents) {
                    setError("当前账号没有管理 Agent 的权限。");
                    return;
                  }
                  if (!capability.canUpdate) {
                    setError(capability.reason || "当前 Runtime 不支持原地更新。");
                    return;
                  }
                  if (
                    capability.recoveryStatus !== "complete" &&
                    capability.recoveryStatus !== "draft-only"
                  ) {
                    setError(
                      capability.reason ||
                        "该 Runtime 的原发布配置不可恢复，无法安全更新。",
                    );
                    return;
                  }
                  if (!capability.runtime.runtimeId) {
                    setError("仅支持更新已部署的云端智能体。");
                    return;
                  }
                  if (!capability.runtime.region) {
                    setError("Runtime 缺少地域信息，无法更新。");
                    return;
                  }
                  if (!capability.agent?.appName) {
                    setError("Runtime 缺少智能体名称，无法更新。");
                    return;
                  }
                  const runtimeAgent = capability.agent;
                  const runtimeEnvValues = Object.fromEntries(
                    capability.runtime.envs
                      .filter(({ key }) => !isRuntimeModelSelectionEnv(key))
                      .map(({ key, value }) => [key, value]),
                  );
                  const runtimeEnv = new Map(
                    capability.runtime.envs.map(({ key, value }) => [
                      key,
                      value.trim(),
                    ]),
                  );
                  const runtimeDraft = runtimeAgentDraftFromCloud(
                    runtimeAgent,
                    cloudProvider,
                    capability.runtime.configuredEnvKeys,
                  );
                  const runtimeModel = modelConfigurationFromRuntime(
                    runtimeAgent.model,
                  );
                  const hydratedDraft = hydrateA2aRegistryFromRuntime(
                    hydrateRuntimeModelSelection(
                      {
                        ...runtimeDraft,
                        modelProvider:
                          runtimeModel.modelProvider ||
                          runtimeEnv.get("MODEL_AGENT_PROVIDER") ||
                          runtimeDraft.modelProvider,
                        modelApiBase:
                          runtimeEnv.get("MODEL_AGENT_API_BASE") ||
                          runtimeDraft.modelApiBase,
                        deployment: {
                          ...(runtimeDraft.deployment ?? {
                            feishuEnabled: false,
                          }),
                          network: capability.runtime.network,
                          envValues: runtimeEnvValues,
                        },
                        cloudEnvironment: capability.runtime.environment ?? {
                          environmentId: "",
                          environmentVersionId: "",
                        },
                      },
                      capability.runtime.envs,
                    ),
                    capability.runtime.envs,
                  );
                  const apiKeyId =
                    hydratedDraft.deployment?.modelApiKeyId?.trim();
                  let arkModelIds = new Set<string>();
                  try {
                    const response = await listModelOptions({ apiKeyId });
                    arkModelIds = new Set(
                      response.models.map((model) => model.id.trim()),
                    );
                  } catch {
                    // If the ModelArk catalog is unavailable, no Runtime model
                    // can be verified as ModelArk; custom is the safe fallback.
                  }
                  const classifiedDraft = classifyRuntimeModelSources(
                    hydratedDraft,
                    arkModelIds,
                  );
                  exitAgentDetailContext();
                  setImportedDraft(classifiedDraft);
                  setCustomCreateMode("custom");
                  setCustomCreationSurface(
                    classifiedDraft.dynamicAgentDelegation === true
                      ? "vulcan"
                      : "traditional",
                  );
                  const nextDraftId = `runtime-${capability.runtime.runtimeId}`;
                  setEditingDraftId(nextDraftId);
                  editingDraftBaselineRef.current = null;
                  setFocusedDeploymentTaskId("");
                  setFocusedWorkspaceAgentId("");
                  setRuntimeUpdateTarget({
                    runtimeId: capability.runtime.runtimeId,
                    name:
                      capability.runtime.name ||
                      runtimeAgent.name ||
                      runtimeDraft.name,
                    region: capability.runtime.region,
                    appName: capability.agent.appName,
                    currentVersion: capability.runtime.currentVersion,
                    etag: capability.etag,
                    editMode:
                      capability.editMode === "source-preserving"
                        ? "source-preserving"
                        : "regenerate",
                    configuredMcpEnvKeys: configuredMcpEnvKeys(classifiedDraft),
                  });
                  setCreateView("custom");
                  setError("");
                }}
                onEditDraft={(item) => {
                  exitAgentDetailContext();
                  setImportedDraft(item.draft);
                  setCustomCreateMode("custom");
                  setCustomCreationSurface(
                    workspaceAgentCreationMode(item) === "quick"
                      ? "vulcan"
                      : "traditional",
                  );
                  setEditingDraftId(item.id);
                  editingDraftBaselineRef.current = item;
                  setRuntimeUpdateTarget(item.deploymentTarget ?? null);
                  setFocusedDeploymentTaskId("");
                  setFocusedWorkspaceAgentId("");
                  setCreateView("custom");
                  setError("");
                }}
              />
            ) : showAddMenu && addMenuSurface === "entry" ? (
              <AgentCreationModePicker
                onSelectVulcan={() => {
                  setAddMenu(false);
                  setImportedDraft(null);
                  setCustomCreateMode("custom");
                  setCustomCreationSurface("vulcan");
                  setRuntimeUpdateTarget(null);
                  setFocusedDeploymentTaskId("");
                  setFocusedWorkspaceAgentId("");
                  setEditingDraftId(`draft-${Date.now().toString(36)}`);
                  editingDraftBaselineRef.current = null;
                  setCreateView("custom");
                }}
                onSelectTraditional={() => {
                  setAddMenuSurface("traditional");
                }}
              />
            ) : showAddMenu ? (
              <StackCards
                title="您想以哪种方式添加 Agent 来运行？"
                sub="选择最适合你的方式，下一步即可开始"
                cards={[
                  {
                    key: "scratch",
                    icon: ScratchIcon,
                    title: "从 0 快速创建",
                    desc: "用智能 / 自定义 / 模板 / 工作流的方式从零创建一个 Agent。",
                    onClick: () => {
                      setAddMenu(false);
                      setImportedDraft(null);
                      setCustomCreateMode("custom");
                      setCustomCreationSurface("traditional");
                      setRuntimeUpdateTarget(null);
                      setFocusedDeploymentTaskId("");
                      setFocusedWorkspaceAgentId("");
                      setEditingDraftId(`draft-${Date.now().toString(36)}`);
                      editingDraftBaselineRef.current = null;
                      setCreateView("custom");
                    },
                  },
                  {
                    key: "intelligent",
                    icon: ScratchIcon,
                    title: "智能模式",
                    desc: "描述目标，按你的意图构建、调试并验证 Agent。",
                    onClick: () => {
                      setAddMenu(false);
                      setImportedDraft(null);
                      setRuntimeUpdateTarget(null);
                      setFocusedDeploymentTaskId("");
                      setFocusedWorkspaceAgentId("");
                      setEditingDraftId("");
                      editingDraftBaselineRef.current = null;
                      setMigrationProjectReturn(undefined);
                      setCreateView("intelligent");
                    },
                  },
                  {
                    key: "package",
                    icon: PackageIcon,
                    title: "从代码包添加和部署",
                    desc: "上传 Agent 项目压缩包，查看代码并直接部署到 AgentKit Runtime。",
                    onClick: () => {
                      setAddMenu(false);
                      setImportedDraft(null);
                      setCreateView("package");
                    },
                  },
                  {
                    key: "migration",
                    icon: MigrationIcon,
                    title: "从存量迁移",
                    desc: "从您的 LangChain / Dify 等存量项目迁移至 AgentKit Runtime",
                    onClick: () => {
                      setAddMenu(false);
                      setImportedDraft(null);
                      setMigrationProjectReturn(undefined);
                      setCreateView("migration");
                    },
                  },
                ]}
              />
            ) : searchView ? (
              <SearchView
                userId={userId}
                appId={appName}
                agentInfo={agentInfo}
                capabilitiesLoading={capabilitiesLoading}
                agentLabel={labelOf}
                onOpenSession={openFromSearch}
              />
            ) : showAddAgent ? (
              <AddAgentKitView
                onAdded={(id) => {
                  setConnections(loadConnections());
                  setAddAgent(false);
                  setAppName(id);
                }}
                onCancel={() => setAddAgent(false)}
              />
            ) : skillCenter ? (
              <LibraryView
                cloudProvider={cloudProvider}
                studioRegion={studioRegion || defaultCloudRegion(cloudProvider)}
                activeTab={libraryTab}
                onTabChange={setLibraryTab}
                onPageTitleChange={setLibraryPageTitle}
                skillInitialWorkspace={skillCenterLaunch}
                onSkillInitialWorkspaceConsumed={() => setSkillCenterLaunch(null)}
                artifactSources={appName
                  ? [{
                      appName,
                      agentId: currentConn?.runtimeId ?? appName,
                      agentName: labelOf(appName),
                      runtimeId: currentConn?.runtimeId,
                      region: currentConn?.region,
                      sessions,
                    }]
                  : []}
                artifactUserId={userId}
                onArtifactActivate={() => {
                  if (appName && userId) void refreshSessions(appName);
                }}
                onArtifactSourceOpen={openFromSearch}
              />
            ) : visibleCreateView !== null && !["menu", "intelligent"].includes(visibleCreateView) && !hasCreds ? (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 12,
                  height: "100%",
                  padding: 24,
                  textAlign: "center",
                  color: "var(--text-secondary, #6b7280)",
                }}
              >
                <div style={{ fontSize: 18, fontWeight: 600 }}>
                  需要配置{cloudProvider === "byteplus" ? "BytePlus" : "火山引擎"} AK/SK
                </div>
                <div style={{ maxWidth: 420, lineHeight: 1.6 }}>
                  智能体工作台需要
                  {cloudProvider === "byteplus" ? " BytePlus " : " Volcengine "}
                  凭据才能使用。请在运行环境中设置{" "}
                  <code>
                    {cloudProvider === "byteplus"
                      ? "BYTEPLUS_ACCESS_KEY"
                      : "VOLCENGINE_ACCESS_KEY"}
                  </code>{" "}
                  与{" "}
                  <code>
                    {cloudProvider === "byteplus"
                      ? "BYTEPLUS_SECRET_KEY"
                      : "VOLCENGINE_SECRET_KEY"}
                  </code>{" "}
                  后重试。
                </div>
              </div>
            ) : intelligentDeployment ? (
              <IntelligentDeployment
                delivery={intelligentDeployment}
                cloudProvider={cloudProvider}
                initialDeployRegion={newRuntimeRegion}
                onBack={() => setIntelligentDeployment(null)}
                onAgentAdded={openIntelligentDeploymentChat}
                onDeploymentTaskChange={updateDeploymentTask}
                onDeploymentStarted={startDeployment}
                onDeploymentComplete={finishDeployment}
              />
            ) : visibleCreateView === "intelligent" ? (
              <IntelligentCreate
                capabilities={intelligentCapabilities}
                loading={intelligentCapabilitiesLoading}
                preparationStage={intelligentPreparationStage}
                error={intelligentCapabilitiesError}
                onCancel={cancelIntelligentPreparation}
                onDownload={downloadIntelligentDelivery}
                onDeploy={setIntelligentDeployment}
                onBack={() => {
                  cancelIntelligentPreparation();
                  setCreateView(null);
                  setAddMenuSurface("traditional");
                  setAddMenu(true);
                }}
                onCreate={startIntelligentDevelopment}
              />
            ) : visibleCreateView === "custom" ? (
              <CustomCreate
                key={editingDraftId || "custom"}
                cloudProvider={cloudProvider}
                initialDraft={importedDraft ?? undefined}
                onBack={() => {
                  setCreateView(null);
                  setAddMenuSurface(
                    !importedDraft && !runtimeUpdateTarget &&
                      customCreationSurface === "vulcan"
                      ? "entry"
                      : "traditional",
                  );
                  setAddMenu(true);
                }}
                onCreate={onCreate}
                onAgentAdded={onAgentAdded}
                features={features}
                onDeploymentTaskChange={updateDeploymentTask}
                createMode={customCreateMode}
                freshCreationSurface={customCreationSurface}
                workspaceDraftId={editingDraftId || undefined}
                deploymentTarget={runtimeUpdateTarget ?? undefined}
                initialDeployRegion={newRuntimeRegion}
                onDraftChange={(draft, dirty) => {
                  if (!editingDraftId) return;
                  if (dirty) {
                    saveWorkspaceDraft(
                      editingDraftId,
                      draft,
                      runtimeUpdateTarget ?? undefined,
                      customCreationSurface === "vulcan" ? "quick" : "traditional",
                    );
                  } else {
                    restoreWorkspaceDraftBaseline(editingDraftId);
                  }
                }}
                onDiscard={editingDraftId ? () => {
                  restoreWorkspaceDraftBaseline(editingDraftId);
                  setEditingDraftId("");
                  editingDraftBaselineRef.current = null;
                  setImportedDraft(null);
                  setRuntimeUpdateTarget(null);
                  setFocusedDeploymentTaskId("");
                  setFocusedWorkspaceAgentId(appName);
                  setCreateView(null);
                  setAddMenu(false);
                  setManageAgents(true);
                  setError("");
                } : undefined}
                onDeploymentStarted={startDeployment}
                onDeploymentComplete={finishDeployment}
              />
            ) : visibleCreateView === "package" ? (
              <CodePackageCreate
                cloudProvider={cloudProvider}
                onBack={() => {
                  setCreateView(null);
                  setAddMenuSurface("traditional");
                  setAddMenu(true);
                }}
                onAgentAdded={onAgentAdded}
                onDeploymentTaskChange={updateDeploymentTask}
                onDeploymentStarted={startDeployment}
                onDeploymentComplete={finishDeployment}
                initialDeployRegion={newRuntimeRegion}
              />
            ) : visibleCreateView === "migration" ? (
              <MigrationWorkspace
                cloudProvider={cloudProvider}
                onBack={() => {
                  setMigrationProjectReturn(undefined);
                  setCreateView(null);
                  setAddMenuSurface("traditional");
                  setAddMenu(true);
                }}
                onAgentAdded={onAgentAdded}
                onDeploymentTaskChange={updateDeploymentTask}
                onDeploymentStarted={startDeployment}
                onDeploymentComplete={finishDeployment}
                initialDeployRegion={newRuntimeRegion}
                projectCapabilities={intelligentCapabilities}
                projectCapabilitiesLoading={intelligentCapabilitiesLoading}
                optimizationPreparationStage={intelligentPreparationStage}
                optimizationError={intelligentCapabilitiesError}
                initialPage={migrationProjectReturn ? "projects" : "new"}
                initialProjectId={migrationProjectReturn?.projectId}
                onOptimizeVersion={(goal, modelId, base) =>
                  startIntelligentDevelopment(
                    goal,
                    modelId,
                    base,
                    { projectId: base.projectId },
                  )}
                onCancelOptimization={cancelIntelligentPreparation}
                onDownloadSavedVersion={downloadIntelligentDelivery}
                onDeploySavedVersion={(delivery) => {
                  setMigrationProjectReturn({
                    projectId: delivery.projectId ?? "",
                  });
                  setIntelligentDeployment(delivery);
                }}
              />
            ) : turns.length === 0 && !newChatCapabilitiesReady ? (
              <div className="session-loading">
                <Loader2 className="icon spin" /> 正在检查 Agent 能力…
              </div>
            ) : turns.length === 0 ? (
              <div
                className="welcome"
                key={`welcome-${newChatCapabilities.agentId ?? appName}`}
              >
                <div className="welcome-primary">
                  <div className="welcome-heading">
                    <NewChatFeatureNotice canUpdate={access.role === "admin"} />
                    <h1 className="welcome-title">
                      {sandboxSession
                        ? "让灵感自由生长"
                        : greeting}
                    </h1>
                  </div>
                  {composer}
                </div>
              </div>
            ) : (
              <>
                <div
                  className={`transcript${activeConversationPresenting ? " is-streaming" : ""}`}
                  ref={scrollRef}
                  onScroll={onConversationScroll}
                  onWheel={onConversationWheel}
                  onTouchMove={onConversationTouchMove}
                >
                  {turns.map((turn, i) => {
            const isLast = i === turns.length - 1;
            if (turn.role === "system") {
              return turn.activity ? (
                <div
                  key={turn.activity.id}
                  className="turn turn--system"
                >
                  <SandboxActivityRecord
                    activity={turn.activity}
                    time={fmtTime(turn.meta?.ts)}
                  />
                </div>
              ) : null;
            }
            if (turn.role === "user") {
              const text = turn.blocks.map((b) => (b.kind === "text" ? b.text : "")).join("");
              const atts = turn.blocks.flatMap((b) =>
                b.kind === "attachment" ? b.files : [],
              );
              const turnInvocation = turn.blocks.find((b) => b.kind === "invocation");
              return (
                <motion.div
                  key={i}
                  className="turn turn--user"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.2, ease: "easeOut" }}
                >
                  {turnInvocation?.kind === "invocation" && (
                    <InvocationChips value={turnInvocation.value} />
                  )}
                  {atts.length > 0 && (
                    <MediaGroup appName={appName} items={atts} />
                  )}
                  {text && (
                    <div className="bubble">
                      <Markdown text={text} />
                    </div>
                  )}
                  <div
                    className="turn-actions turn-actions--right"
                    data-share-image-exclude="true"
                  >
                    {turn.meta?.ts && <span className="meta-text">{fmtTime(turn.meta.ts)}</span>}
                    <CopyButton text={text} />
                  </div>
                </motion.div>
              );
            }
            const agentAuthor = turn.meta?.author ?? "";
            const agentNode = agentAuthor && rootCapabilityNode
              ? findAgentNode(rootCapabilityNode, agentAuthor)
              : undefined;
            const isSubAgent = Boolean(
              agentAuthor &&
              rootAgentNames.length > 0 &&
              !rootAgentNames.includes(agentAuthor),
            );
            const agentDisplayName = displayAgentName(agentNode?.name || agentAuthor);
            const agentDescription = agentNode?.description ||
              (isSubAgent ? "正在执行主 Agent 移交的任务。" : "");
            if (
              turn.blocks.length > 0 &&
              turn.blocks.every((block) => block.kind === "agent-transfer")
            ) return null;
            const pending = turn.blocks.length === 0;
            const feedbackRating = turn.meta?.feedback?.rating ?? null;
            const feedbackEventId = turn.meta?.eventId ?? "";
            const feedbackPending = feedbackPendingIds.has(feedbackEventId);
            const canRate = Boolean(
              currentRuntime && feedbackEventId && turnText(turn),
            );
            const feedbackInput = canRate ? previousUserTurnText(turns, i) : "";
            const turnIsStreaming = isLast && (
              activeConversationBusy || presentingStream
            );
            const canAnnotate = Boolean(
              canRate &&
              cloudProvider !== "byteplus" &&
              !turnIsStreaming &&
              !turnAwaitingAuth(turn),
            );
            return (
              <motion.div
                key={i}
                data-share-message-source="true"
                data-response-annotation-index={i}
                ref={(node) => {
                  if (!feedbackEventId) return;
                  if (node) {
                    turnNodeRefs.current.set(feedbackEventId, node);
                  } else {
                    turnNodeRefs.current.delete(feedbackEventId);
                  }
                }}
                className={[
                  "turn turn--assistant",
                  isSubAgent ? "turn--subagent" : "",
                  feedbackTargetEventId &&
                  feedbackTargetEventId === feedbackEventId ? "is-feedback-target" : "",
                ].filter(Boolean).join(" ")}
                tabIndex={canAnnotate ? 0 : undefined}
                aria-label={canAnnotate
                  ? "模型回复；选中文字后可添加批注"
                  : undefined}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
              >
                {isSubAgent && (
                  <>
                    <div className="subagent-run-label">
                      <span className="subagent-run-handoff">
                        <CornerDownRight />
                        <span>智能体移交</span>
                      </span>
                      <span className="subagent-run-title">{agentDisplayName}</span>
                    </div>
                    <p className="subagent-run-description" title={agentDescription}>
                      {agentDescription}
                    </p>
                  </>
                )}
                {pending ? (
                  isLast && activeConversationBusy ? <ThinkingPlaceholder /> : null
                ) : (
                  <>
                    <Blocks
                      appName={appName}
                      blocks={turn.blocks}
                      streaming={isLast && (activeConversationBusy || presentingStream)}
                      onStreamFrame={isLast ? followConversationStreamFrame : undefined}
                      onStreamComplete={
                        isLast && !activeConversationBusy && presentingStream
                          ? () => completeStreamPresentation(sessionId)
                          : undefined
                      }
                      onAction={onAction}
                      onAuth={onAuth}
                      onArtifactDownload={(filename, version) =>
                        downloadArtifact(appName, userId, sessionId, filename, version)
                      }
                      onArtifactPreview={(filename, version) =>
                        previewArtifact(appName, userId, sessionId, filename, version)
                      }
                      onResolveDelivery={resolveIntelligentDelivery}
                      onResolveDeliveryComparison={resolveIntelligentDeliveryComparison}
                      onDownloadDelivery={downloadIntelligentDelivery}
                      onDeployDelivery={setIntelligentDeployment}
                    />
                    {/* Finalized turn that produced no visible answer (e.g. only
                        thinking + an empty A2UI surface) — show a fallback note. */}
                    {!(isLast && activeConversationBusy) && !turnHasVisibleContent(turn) && (
                      <div className="turn-empty">本次没有返回可显示的内容。</div>
                    )}
                    {/* Hide the actions/timestamp row while this turn is still
                        thinking/streaming or waiting on an OAuth card; reveal it
                        only once the reply is done. */}
                    {!(isLast && activeConversationBusy) && !turnAwaitingAuth(turn) && (
                      <div className="turn-meta" data-share-image-exclude="true">
                        {sandboxSession && turn.meta?.sandboxUsage ? (
                          <SandboxTokenUsageRow usage={turn.meta.sandboxUsage} />
                        ) : null}
                        <div className="turn-actions">
                          {canRate && (
                            <>
                              <button
                                type="button"
                                className={`icon-btn feedback-btn${
                                  feedbackRating === "good"
                                    ? " feedback-btn--good"
                                    : ""
                                }`}
                                aria-label="赞"
                                aria-pressed={feedbackRating === "good"}
                                aria-busy={feedbackPending}
                                title={feedbackRating === "good" ? "取消点赞" : "赞"}
                                disabled={feedbackPending}
                                onClick={() => void rateAssistantTurn(
                                  turn,
                                  feedbackRating === "good" ? null : "good",
                                  feedbackInput,
                                )}
                              >
                                <FeedbackUpIcon
                                  className="icon"
                                  filled={feedbackRating === "good"}
                                />
                              </button>
                              <button
                                type="button"
                                className={`icon-btn feedback-btn${
                                  feedbackRating === "bad"
                                    ? " feedback-btn--bad"
                                    : ""
                                }`}
                                aria-label="踩"
                                aria-pressed={feedbackRating === "bad"}
                                aria-busy={feedbackPending}
                                title={feedbackRating === "bad" ? "取消点踩" : "踩"}
                                disabled={feedbackPending}
                                onClick={() => void rateAssistantTurn(
                                  turn,
                                  feedbackRating === "bad" ? null : "bad",
                                  feedbackInput,
                                )}
                              >
                                <FeedbackDownIcon
                                  className="icon"
                                  filled={feedbackRating === "bad"}
                                />
                              </button>
                            </>
                          )}
                          {!sandboxSession && (
                            <>
                              <button
                                type="button"
                                className="icon-btn"
                                aria-label="问题反馈"
                                title="问题反馈"
                                onClick={() => setIssueFeedbackTarget({
                                  turn,
                                  input: previousUserTurnText(turns, i),
                                })}
                              >
                                <IssueFeedbackIcon className="icon" />
                              </button>
                              <button
                                type="button"
                                className="icon-btn"
                                title="Tracing 火焰图"
                                onClick={() => {
                                  setTraceEndTimeMs(
                                    turn.meta?.ts ? turn.meta.ts * 1000 : Date.now(),
                                  );
                                  setTraceOpen(true);
                                }}
                              >
                                <TraceIcon />
                              </button>
                            </>
                          )}
                          <CopyButton text={turnText(turn)} />
                          <ShareMessageButton
                            onClick={(event) => {
                              const targetTurn = event.currentTarget.closest<HTMLElement>(
                                "[data-share-message-source]",
                              );
                              if (targetTurn) setShareMessageTarget({ targetTurn });
                            }}
                          />
                        </div>
                        {turn.meta && <span className="meta-text">{fmtMeta(turn.meta)}</span>}
                      </div>
                    )}
                  </>
                )}
              </motion.div>
            );
          })}
                </div>
                {!sandboxSession && (
                  <AgentInfoPanel
                    appName={appName}
                    info={agentInfo}
                    loading={capabilitiesLoading}
                    activeAgent={activeAgent}
                    seenAgents={seenAgents}
                    execPath={execPath}
                    studioTools={visibleStudioTools}
                    selectedStudioToolIds={selectedStudioToolIds}
                    managedStudioToolIds={selectedEnvironmentMounts.length > 0
                      ? ENVIRONMENT_STUDIO_TOOL_IDS
                      : []}
                    studioToolsLoading={studioToolsLoading}
                    studioToolsDisabled={conversationBusy}
                    studioToolsUnavailableReason={studioToolsUnavailableReason}
                    onStudioToolsChange={
                      studioToolRuntime ? updateSelectedStudioToolIds : undefined
                    }
                    environments={sessionEnvironments}
                    workspaces={sessionWorkspaces}
                    selectedEnvironments={selectedEnvironmentMounts}
                    selectedEnvironmentWorkspaceIds={selectedEnvironmentWorkspaceIds}
                    environmentsLoading={sessionEnvironmentsLoading || studioToolsLoading}
                    environmentsDisabled={conversationBusy || !canMountSessionEnvironment}
                    environmentsError={sessionEnvironmentsUnavailableReason}
                    onEnvironmentsChange={
                      studioToolRuntime && sessionId
                        ? updateSelectedEnvironments
                        : undefined
                    }
                  />
                )}
                <div className="conversation-composer-slot">
                  {composer}
                </div>
              </>
            )}
            </main>
          </section>
        );
      })()}

      {issueFeedbackTarget && sessionId && (
        <IssueFeedbackDialog
          onClose={() => setIssueFeedbackTarget(null)}
          onSubmit={submitIssueFeedbackForTurn}
        />
      )}

      {shareMessageTarget && (
        <ShareMessageDialog
          targetTurn={shareMessageTarget.targetTurn}
          onClose={() => setShareMessageTarget(null)}
        />
      )}

      {responseAnnotationTarget && sessionId && (
        <ResponseAnnotationPopover
          key={responseAnnotationTarget.selectionId}
          anchor={responseAnnotationTarget.anchor}
          selectedText={responseAnnotationTarget.selectedText}
          onClose={() => setResponseAnnotationTarget((current) =>
            current?.selectionId === responseAnnotationTarget.selectionId
              ? null
              : current
          )}
          onSubmit={submitResponseAnnotation}
        />
      )}

      {traceOpen && sessionId && (
        <TraceDrawer
          appName={appName}
          sessionId={sessionId}
          endTimeMs={traceEndTimeMs}
          onClose={() => setTraceOpen(false)}
        />
      )}

      <SandboxLaunchDialog
        open={sandboxLaunchOpen}
        state={sandboxLaunchState}
        agentKind={sandboxLaunchKind}
        error={sandboxLaunchError}
        onCancel={cancelSandboxLaunch}
        onConfirm={(displayName, persistent) =>
          void launchSandboxSession(displayName, persistent)
        }
      />

      <SandboxProjectUploadDialog
        open={sandboxProjectUploadOpen}
        onClose={() => setSandboxProjectUploadOpen(false)}
        onRefreshAgents={() => setSandboxAgentRefreshKey((current) => current + 1)}
        onOpenSession={openCodexHandoffSession}
      />

      {intelligentLeaveOpen ? (
        <StudioConfirmDialog
          title="当前构建仍在进行"
          description="离开将停止本轮构建；当前会话仍会保留，可稍后从历史会话重新进入。"
          confirmLabel="停止并离开"
          variant="warning"
          onCancel={() => {
            pendingIntelligentNavigationRef.current = null;
            setIntelligentLeaveOpen(false);
          }}
          onConfirm={confirmIntelligentNavigation}
        />
      ) : null}

      {sandboxThreadDeleteTarget ? (
        <StudioConfirmDialog
          title="删除 Codex 历史会话"
          description={`将删除“${
            sandboxThreadDeleteTarget.name ||
            sandboxThreadDeleteTarget.preview ||
            `Thread ${sandboxThreadDeleteTarget.id.slice(0, 8)}`
          }”，并从历史会话中移除。`}
          confirmLabel="确认删除"
          variant="danger"
          busy={sandboxCommands.threadActionId === sandboxThreadDeleteTarget.id}
          onCancel={() => {
            if (sandboxCommands.threadActionId) return;
            setSandboxThreadDeleteTarget(null);
          }}
          onConfirm={() => void confirmSandboxThreadDelete()}
        />
      ) : null}

      {sandboxSession ? (
        <>
          <SandboxToolDialog
            open={!sandboxSession.intelligentDevelopment && sandboxToolKind !== null}
            kind={sandboxToolKind ?? "terminal"}
            launch={sandboxToolLaunch}
            loading={sandboxToolLoading}
            error={sandboxToolError}
            onReload={() => {
              if (sandboxToolKind) void openSandboxTool(sandboxToolKind);
            }}
            onClose={() => {
              setSandboxToolKind(null);
              setSandboxToolLaunch(null);
              setSandboxToolLoading(false);
              setSandboxToolError("");
            }}
          />
          <SandboxPermissionsDialog
            open={!sandboxSession.intelligentDevelopment && sandboxPermissionsOpen}
            value={sandboxSession.permissions}
            busy={sandboxSettingsBusy || sandboxBusy}
            error={sandboxSettingsError}
            onSave={(value) => void saveSandboxPermissions(value)}
            onClose={() => {
              if (sandboxSettingsBusy) return;
              setSandboxPermissionsOpen(false);
              setSandboxSettingsError("");
            }}
          />
          <SandboxWorkspaceDialog
            open={!sandboxSession.intelligentDevelopment && sandboxWorkspaceOpen}
            cwd={sandboxSession.cwd}
            locked={sandboxSession.workspaceLocked}
            busy={sandboxSettingsBusy}
            error={sandboxSettingsError}
            browse={browseSandboxDirectories}
            onSave={(cwd) => void saveSandboxWorkspace(cwd)}
            onClose={() => {
              if (sandboxSettingsBusy) return;
              setSandboxWorkspaceOpen(false);
              setSandboxSettingsError("");
            }}
          />
          <SandboxThreadsDialog
            open={!sandboxSession.intelligentDevelopment && sandboxCommands.threadsOpen}
            threads={sandboxCommands.threads}
            currentThreadId={sandboxSession.threadId}
            loading={sandboxCommands.threadsLoading}
            error={sandboxCommands.threadsError}
            onSelect={(threadId) => void sandboxCommands.resumeThread(threadId)}
            onClose={sandboxCommands.closeThreads}
          />
          <SandboxApprovalDialog
            approval={sandboxApproval}
            busy={sandboxApprovalBusy}
            error={sandboxApprovalError}
            onDecision={(decision) => void decideSandboxApproval(decision)}
          />
        </>
      ) : null}

      <AuthExpiredDialog
        open={authExpired}
        checking={authRecoveryChecking}
        error={authRecoveryError}
        onLogin={() => void recoverAuthentication()}
      />

      <AgentKitCliDialog
        open={agentKitCliOpen}
        onClose={() => setAgentKitCliOpen(false)}
      />

      <NewChatVideoTaskDialog
        open={videoTaskDialogOpen}
        task={videoTask}
        onClose={() => setVideoTaskDialogOpen(false)}
        onRetry={retryVideoTask}
        onDownload={() => void downloadCurrentVideoTask()}
      />

      {confirmLeave && (
        <div className="confirm-scrim" onClick={() => setConfirmLeave(false)}>
          <div className="confirm-box" onClick={(e) => e.stopPropagation()}>
            <div className="confirm-title">返回创建首页？</div>
            <div className="confirm-text">返回后当前填写的内容将会丢失，确定要返回吗？</div>
            <div className="confirm-actions">
              <button className="confirm-btn" onClick={() => setConfirmLeave(false)}>
                取消
              </button>
              <button
                className="confirm-btn confirm-btn--danger"
                onClick={() => {
                  setImportedDraft(null);
                  setCreateView(null);
                  setAddMenuSurface("traditional");
                  setAddMenu(true);
                  setConfirmLeave(false);
                }}
              >
                确定返回
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
