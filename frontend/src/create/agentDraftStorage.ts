import type { AgentDraft } from "./types";
import { createT } from "./i18n";
import { prepareMcpAuth, referencedMcpEnvKeys } from "./mcpAuth";

const WORKSPACE_DRAFT_STORAGE_VERSION = 1;
const SERVER_MANAGED_MODEL_API_KEY = "MODEL_AGENT_API_KEY";
const WORKSPACE_DRAFT_ERROR_NAME = "WorkspaceDraftError";

function workspaceDraftError(key: string): Error {
  const error = new Error(createT(key));
  error.name = WORKSPACE_DRAFT_ERROR_NAME;
  return error;
}

export type WorkspaceAgentCreationMode = "quick" | "traditional";

export interface WorkspaceAgentDraft {
  id: string;
  draft: AgentDraft;
  updatedAt: number;
  creationMode?: WorkspaceAgentCreationMode;
  deploymentTarget?: {
    runtimeId: string;
    name: string;
    region: string;
    appName?: string;
    currentVersion?: number | null;
    etag?: string;
    editMode?: "source-preserving" | "regenerate";
    configuredMcpEnvKeys?: string[];
    configuredRuntimeEnvKeys?: string[];
  };
}

interface WorkspaceDraftStoragePayload {
  version: typeof WORKSPACE_DRAFT_STORAGE_VERSION;
  drafts: WorkspaceAgentDraft[];
}

interface LocalStorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isWorkspaceAgentDraft(value: unknown): value is WorkspaceAgentDraft {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.updatedAt === "number" &&
    (value.creationMode === undefined ||
      value.creationMode === "quick" ||
      value.creationMode === "traditional") &&
    isRecord(value.draft)
  );
}

export function workspaceAgentCreationMode(
  item: WorkspaceAgentDraft,
): WorkspaceAgentCreationMode {
  if (item.creationMode) return item.creationMode;
  return item.draft.dynamicAgentDelegation === true ? "quick" : "traditional";
}

export function workspaceDraftsKey(userId: string): string {
  return `veadk.agentDrafts.${encodeURIComponent(userId)}`;
}

/** Remove values that must remain ephemeral from every nested deployment. */
function stripBrowserStorageSecrets(
  draft: AgentDraft,
  protectedMcpKeys: ReadonlySet<string>,
  transientMcpKeys: ReadonlySet<string>,
): AgentDraft {
  const deployment = draft.deployment;
  const envValues = deployment?.envValues;
  const safeDeployment = deployment
    ? {
        ...deployment,
        ...(envValues
          ? {
              envValues: Object.fromEntries(
                Object.entries(envValues).filter(
                  ([key]) =>
                    key !== SERVER_MANAGED_MODEL_API_KEY &&
                    !protectedMcpKeys.has(key),
                ),
              ),
            }
          : {}),
      }
    : undefined;
  return {
    ...draft,
    ...(draft.mcpTools
      ? {
          mcpTools: draft.mcpTools.map((tool) => {
            if (
              !tool.authTokenEnv ||
              !transientMcpKeys.has(tool.authTokenEnv)
            ) {
              return tool;
            }
            const safeTool = { ...tool };
            delete safeTool.authTokenEnv;
            return safeTool;
          }),
        }
      : {}),
    ...(safeDeployment ? { deployment: safeDeployment } : {}),
    subAgents: draft.subAgents.map((child) =>
      stripBrowserStorageSecrets(child, protectedMcpKeys, transientMcpKeys),
    ),
    ...(draft.workflow
      ? {
          workflow: {
            ...draft.workflow,
            nodes: draft.workflow.nodes.map((node) => ({
              ...node,
              agent: stripBrowserStorageSecrets(
                node.agent,
                protectedMcpKeys,
                transientMcpKeys,
              ),
            })),
          },
        }
      : {}),
  };
}

/** Restore only the configured marker after stripping transient token values. */
function preserveConfiguredMcpState(
  prepared: AgentDraft,
  source: AgentDraft,
): AgentDraft {
  return {
    ...prepared,
    ...(prepared.mcpTools
      ? {
          mcpTools: prepared.mcpTools.map((tool, index) => ({
            ...tool,
            ...(source.mcpTools?.[index]?.credentialConfigured === true
              ? { credentialConfigured: true }
              : {}),
          })),
        }
      : {}),
    subAgents: prepared.subAgents.map((child, index) =>
      preserveConfiguredMcpState(child, source.subAgents[index] ?? child),
    ),
    ...(prepared.workflow
      ? {
          workflow: {
            ...prepared.workflow,
            nodes: prepared.workflow.nodes.map((node, index) => ({
              ...node,
              agent: preserveConfiguredMcpState(
                node.agent,
                source.workflow?.nodes[index]?.agent ?? node.agent,
              ),
            })),
          },
        }
      : {}),
  };
}

export function sanitizeAgentDraftForStorage(draft: AgentDraft): AgentDraft {
  const prepared = prepareMcpAuth(draft);
  const storageDraft = preserveConfiguredMcpState(prepared.draft, draft);
  return stripBrowserStorageSecrets(
    storageDraft,
    new Set(referencedMcpEnvKeys(prepared.draft)),
    new Set(Object.keys(prepared.envValues)),
  );
}

function sanitizeWorkspaceDraft(item: WorkspaceAgentDraft): WorkspaceAgentDraft {
  return {
    ...item,
    draft: sanitizeAgentDraftForStorage(item.draft),
  };
}

function parseWorkspaceDrafts(value: unknown): WorkspaceAgentDraft[] {
  const drafts = Array.isArray(value)
    ? value
    : isRecord(value) && value.version === WORKSPACE_DRAFT_STORAGE_VERSION
      ? value.drafts
      : undefined;
  if (!Array.isArray(drafts) || !drafts.every(isWorkspaceAgentDraft)) {
    if (isRecord(value) && typeof value.version === "number") {
      throw workspaceDraftError("helpers.drafts.unsupportedVersion");
    }
    throw workspaceDraftError("helpers.drafts.invalidFormat");
  }
  return drafts.map(sanitizeWorkspaceDraft);
}

export function loadWorkspaceDrafts(
  storage: LocalStorageLike,
  userId: string,
): WorkspaceAgentDraft[] {
  if (!userId) return [];
  const raw = storage.getItem(workspaceDraftsKey(userId));
  if (!raw) return [];
  try {
    return parseWorkspaceDrafts(JSON.parse(raw));
  } catch (cause) {
    if (cause instanceof Error && cause.name === WORKSPACE_DRAFT_ERROR_NAME) {
      throw cause;
    }
    throw workspaceDraftError("helpers.drafts.readFailed");
  }
}

export function writeWorkspaceDrafts(
  storage: LocalStorageLike,
  userId: string,
  drafts: WorkspaceAgentDraft[],
): void {
  if (!userId) return;
  const payload: WorkspaceDraftStoragePayload = {
    version: WORKSPACE_DRAFT_STORAGE_VERSION,
    drafts: drafts.map(sanitizeWorkspaceDraft),
  };
  try {
    storage.setItem(workspaceDraftsKey(userId), JSON.stringify(payload));
  } catch (cause) {
    if (
      cause instanceof DOMException &&
      (cause.name === "QuotaExceededError" || cause.name === "NS_ERROR_DOM_QUOTA_REACHED")
    ) {
      throw new Error(
        createT("helpers.drafts.quotaExceeded"),
      );
    }
    throw new Error(createT("helpers.drafts.writeRejected"));
  }
}
