// Shared types for the agent-creation modes (intelligent / custom / workflow).
// Each mode assembles an AgentDraft and calls onCreate(draft).

export interface MemoryConfig {
  shortTerm: boolean;
  longTerm: boolean;
}

/** A custom function tool the user wants — the backend generator emits a stub for it. */
export interface CustomTool {
  name: string;
  description: string;
}

/** An MCP tool server the agent should connect to (becomes an MCPToolset). */
export interface McpTool {
  /** Friendly label (also used to derive the python variable name). */
  name: string;
  transport: "http" | "stdio";
  /** http transport: the MCP server URL (StreamableHTTP). */
  url?: string;
  /** http transport: optional bearer token -> Authorization header. */
  authToken?: string;
  /** Environment variable used by generated code for the bearer token. */
  authTokenEnv?: string;
  /** stdio transport: the command to launch (e.g. "npx"). */
  command?: string;
  /** stdio transport: command args (e.g. ["-y", "@playwright/mcp@latest"]). */
  args?: string[];
}

// Import and re-export the multi-source SelectedSkill (and related types) from
// the skills module. Importing locally brings the names into scope so the
// AgentDraft interface below can reference SelectedSkill, while `export type`
// makes them available to external importers of "./types" unchanged.
import type { SelectedSkill, SkillHit, SkillSource } from "./skills/types";
import { DEFAULT_KB_BACKEND } from "./veadkCatalog";
import {
  defaultModelName,
  VOLCENGINE_DEFAULT_MODEL_NAME,
  type CloudProvider,
} from "../adk/cloudProvider";
export type { SelectedSkill, SkillHit, SkillSource };


export interface NetworkConfig {
  /** "public" (default, public endpoint), "private" (VPC only), or "both". */
  mode: "public" | "private" | "both";
  /** Required when mode is private/both. */
  vpcId?: string;
  /** Comma-separated subnet IDs for private/both mode. */
  subnetIds?: string;
  /** Whether the private network has shared internet access. */
  enableSharedInternetAccess?: boolean;
}

export interface A2aRegistryConfig {
  enabled: boolean;
  /** REGISTRY_SPACE_ID. */
  registrySpaceId: string;
  /** REGISTRY_TOP_K. Empty means the UI supplies the explicit default. */
  registryTopK?: string;
  /** REGISTRY_REGION. Empty means the UI supplies the explicit default. */
  registryRegion?: string;
  /** REGISTRY_ENDPOINT. Empty means the UI supplies the explicit default. */
  registryEndpoint?: string;
}

export interface DeploymentConfig {
  feishuEnabled: boolean;
  /** Explicit AgentKit Runtime resource name. */
  runtimeName?: string;
  /** Whether the user explicitly edited runtimeName instead of using the Root Agent default. */
  runtimeNameCustomized?: boolean;
  network?: NetworkConfig;
  /** Safe Ark API Key metadata used to restore the selection when editing. */
  modelApiKeyId?: string;
  modelApiKeyName?: string;
  /** Values entered for feature-specific runtime configuration.
   *  Draft and YAML persistence intentionally preserve these values. */
  envValues?: Record<string, string>;
}

export type CloudCliToolId = "lark-cli" | "github-cli" | "pandoc";
export const MAX_CLOUD_DOCKERFILE_LENGTH = 65_536;

export interface CloudEnvironmentConfig {
  /** Official command-line tools baked into the deployment image. */
  cliTools: CloudCliToolId[];
  /** User-edited Dockerfile. Omitted while Studio should generate it. */
  dockerfile?: string;
}

export type HarnessSidecarOptionId =
  | "context_engine"
  | "compressor"
  | "verifier"
  | "long_run_control"
  | "mcp_resilience";

export type HarnessSidecarProfileId = "default" | "ops";

export interface HarnessSidecarIntent {
  enabled: boolean;
  profile: HarnessSidecarProfileId;
  componentOverrides: Record<HarnessSidecarOptionId, boolean>;
  catalogVersion?: string;
  planHash?: string;
}

/** A draft VeADK agent configuration produced by a creation flow. */
export interface AgentDraft {
  name: string;
  description: string;
  /** System prompt. */
  instruction: string;
  /**
   * Agent kind for the custom flow. "llm" is a VeADK `Agent` (LlmAgent);
   * "sequential"/"parallel"/"loop" are orchestrators from `google.adk.agents`
   * that only schedule their sub_agents (no model/instruction/tools/memory of
   * their own); "a2a" is a leaf remote Agent configured through an AgentKit
   * A2A center. Defaults to "llm" when absent.
   */
  agentType?: "llm" | "sequential" | "parallel" | "loop" | "a2a";
  /** Cloud provider selected by the Studio shell. */
  cloudProvider?: CloudProvider;
  /** Max iterations for a "loop" orchestrator (LoopAgent.max_iterations). */
  maxIterations?: number;
  /** Remote agent URL for an "a2a" agent (RemoteVeAgent.url). */
  a2aUrl?: string;
  model?: string;
  /** Model configuration (optional). Empty values fall back to veadk config/env. */
  modelSource?: "ark" | "custom";
  modelName?: string;
  modelProvider?: string;
  modelApiBase?: string;
  /** Free-text tool names retained for legacy and intelligent creation flows. */
  tools: string[];
  skills: string[];
  memory: MemoryConfig;
  knowledgebase: boolean;
  /** Observability / tracing. */
  tracing: boolean;
  /** Nested sub-agents (the custom flow supports recursive creation). */
  subAgents: AgentDraft[];

  /* ---- custom-mode generation selections (all optional / additive) ---- */
  /** Ids of selected built-in tools (see veadkCatalog BUILTIN_TOOLS). */
  builtinTools?: string[];
  /** User-defined function tools — the backend generator emits runnable stubs. */
  customTools?: CustomTool[];
  /** MCP tool servers — the backend generator emits an MCPToolset per entry. */
  mcpTools?: McpTool[];
  /** AgentKit A2A center configuration for a remote Agent. */
  a2aRegistry?: A2aRegistryConfig;
  /** Chosen backends when memory is enabled. */
  shortTermBackend?: string;
  longTermBackend?: string;
  /** Existing long-term memory collection/index selected for managed backends. */
  longTermMemoryIndex?: string;
  /** Persist finished sessions into long-term memory. */
  autoSaveSession?: boolean;
  /** Chosen knowledgebase backend when knowledgebase is enabled. */
  knowledgebaseBackend?: string;
  /** Existing knowledgebase collection/index selected for managed backends. */
  knowledgebaseIndex?: string;
  /** Selected tracing exporter ids (apmplus | cozeloop | tls). */
  tracingExporters?: string[];
  /** Skills picked from the Skill Hub — downloaded into the project at build. */
  selectedSkills?: SelectedSkill[];
  /** Optional workflow graph (set by the workflow builder). */
  workflow?: {
    type: "sequential" | "parallel" | "loop" | "custom";
    nodes: { id: string; agent: AgentDraft }[];
    edges: { from: string; to: string }[];
  };
  /** Deployment-time options that do not change generated agent code. */
  deployment?: DeploymentConfig;
  /** Optional command-line tools installed into the cloud runtime image. */
  cloudEnvironment?: CloudEnvironmentConfig;
  /** Root Runtime-level Harness Sidecar selection. Never set on sub-Agents. */
  harnessSidecar?: HarnessSidecarIntent;
}

// Pre-filled defaults so description / system prompt / model are never empty
// when the custom wizard opens. `DEFAULT_MODEL_NAME` mirrors veadk's
// DEFAULT_MODEL_AGENT_NAME (veadk/consts.py).
export const DEFAULT_MODEL_NAME = VOLCENGINE_DEFAULT_MODEL_NAME;
const DEFAULT_DESCRIPTION =
  "一个基于 VeADK 构建的智能助手，理解用户意图并调用合适的工具完成任务。";
const DEFAULT_INSTRUCTION =
  "你是一个专业、可靠的智能助手。\n\n" +
  "你的目标是准确理解用户的需求，并给出条理清晰、简洁有用的回答。\n\n" +
  "约束：\n" +
  "- 信息不足时主动提问澄清，不要臆造事实。\n" +
  "- 需要时合理调用可用的工具，并说明关键结论。\n" +
  "- 保持礼貌、专业的语气。";

export function emptyDraft(cloudProvider: CloudProvider = "volcengine"): AgentDraft {
  return {
    name: "",
    description: DEFAULT_DESCRIPTION,
    instruction: DEFAULT_INSTRUCTION,
    agentType: "llm",
    cloudProvider,
    maxIterations: 3,
    a2aUrl: "",
    tools: [],
    skills: [],
    memory: { shortTerm: false, longTerm: false },
    knowledgebase: false,
    tracing: false,
    subAgents: [],
    builtinTools: [],
    customTools: [],
    mcpTools: [],
    a2aRegistry: {
      enabled: false,
      registrySpaceId: "",
      registryTopK: "",
      registryRegion: "",
      registryEndpoint: "",
    },
    modelName: defaultModelName(cloudProvider),
    modelSource: "ark",
    modelProvider: "",
    modelApiBase: "",
    shortTermBackend: "local",
    longTermBackend: "local",
    longTermMemoryIndex: "",
    autoSaveSession: false,
    knowledgebaseBackend: DEFAULT_KB_BACKEND,
    knowledgebaseIndex: "",
    tracingExporters: [],
    selectedSkills: [],
    cloudEnvironment: { cliTools: [] },
    deployment: {
      feishuEnabled: false,
      modelApiKeyId: "",
      modelApiKeyName: "",
    },
  };
}

export interface CreateModeProps {
  /** Cloud provider selected by the Studio shell. */
  cloudProvider?: CloudProvider;
  /** Return to the quick-create card menu. */
  onBack: () => void;
  /** Called when the user finishes assembling an agent. */
  onCreate: (draft: AgentDraft) => void;
  /** Called after successfully adding an agent to navigate to it. */
  onAgentAdded?: (agentId: string, agentName: string) => void;
}
