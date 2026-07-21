// Shared types for the agent-creation modes (intelligent / custom / template /
// workflow). Each mode assembles an AgentDraft and calls onCreate(draft).

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
  network?: NetworkConfig;
  /** Values entered for feature-specific runtime configuration.
   *  These are deployment-only and must not be exported to source/YAML. */
  envValues?: Record<string, string>;
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
   * their own); "a2a" is a leaf `RemoteVeAgent` referenced by URL over the A2A
   * protocol. Defaults to "llm" when absent.
   */
  agentType?: "llm" | "sequential" | "parallel" | "loop" | "a2a";
  /** Max iterations for a "loop" orchestrator (LoopAgent.max_iterations). */
  maxIterations?: number;
  /** Remote agent URL for an "a2a" agent (RemoteVeAgent.url). */
  a2aUrl?: string;
  model?: string;
  /** Model configuration (optional). Empty values fall back to veadk config/env. */
  modelName?: string;
  modelProvider?: string;
  modelApiBase?: string;
  /** Free-text tool names (legacy; intelligent/template modes still use these). */
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
  /** AgentKit A2A registry center tools. */
  a2aRegistry?: A2aRegistryConfig;
  /** Chosen backends when memory is enabled. */
  shortTermBackend?: string;
  longTermBackend?: string;
  /** Persist finished sessions into long-term memory. */
  autoSaveSession?: boolean;
  /** Chosen knowledgebase backend when knowledgebase is enabled. */
  knowledgebaseBackend?: string;
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
}

// Pre-filled defaults so description / system prompt / model are never empty
// when the custom wizard opens. `DEFAULT_MODEL_NAME` mirrors veadk's
// DEFAULT_MODEL_AGENT_NAME (veadk/consts.py).
export const DEFAULT_MODEL_NAME = "doubao-seed-2-1-pro-260628";
const DEFAULT_DESCRIPTION =
  "一个基于 VeADK 构建的智能助手，理解用户意图并调用合适的工具完成任务。";
const DEFAULT_INSTRUCTION =
  "你是一个专业、可靠的智能助手。\n\n" +
  "你的目标是准确理解用户的需求，并给出条理清晰、简洁有用的回答。\n\n" +
  "约束：\n" +
  "- 信息不足时主动提问澄清，不要臆造事实。\n" +
  "- 需要时合理调用可用的工具，并说明关键结论。\n" +
  "- 保持礼貌、专业的语气。";

export function emptyDraft(): AgentDraft {
  return {
    name: "",
    description: DEFAULT_DESCRIPTION,
    instruction: DEFAULT_INSTRUCTION,
    agentType: "llm",
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
    modelName: DEFAULT_MODEL_NAME,
    modelProvider: "",
    modelApiBase: "",
    shortTermBackend: "local",
    longTermBackend: "local",
    autoSaveSession: false,
    knowledgebaseBackend: "local",
    tracingExporters: [],
    selectedSkills: [],
    deployment: { feishuEnabled: false },
  };
}

export interface CreateModeProps {
  /** Return to the quick-create card menu. */
  onBack: () => void;
  /** Called when the user finishes assembling an agent. */
  onCreate: (draft: AgentDraft) => void;
  /** Called after successfully adding an agent to navigate to it. */
  onAgentAdded?: (agentId: string, agentName: string) => void;
}
