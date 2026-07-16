// Shared types for the agent-creation modes (intelligent / custom / template /
// workflow). Each mode assembles an AgentDraft and calls onCreate(draft).

export interface MemoryConfig {
  shortTerm: boolean;
  longTerm: boolean;
}

/** A custom function tool the user wants — codegen emits a stub for it. */
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


export interface DeploymentConfig {
  feishuEnabled: boolean;
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
  enableA2ui: boolean;
  /** Nested sub-agents (the custom flow supports recursive creation). */
  subAgents: AgentDraft[];

  /* ---- custom-mode codegen selections (all optional / additive) ---- */
  /** Ids of selected built-in tools (see veadkCatalog BUILTIN_TOOLS). */
  builtinTools?: string[];
  /** User-defined function tools — codegen emits runnable stubs. */
  customTools?: CustomTool[];
  /** MCP tool servers — codegen emits an MCPToolset per entry. */
  mcpTools?: McpTool[];
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

export function emptyDraft(): AgentDraft {
  return {
    name: "",
    description: "",
    instruction: "",
    agentType: "llm",
    maxIterations: 3,
    a2aUrl: "",
    tools: [],
    skills: [],
    memory: { shortTerm: false, longTerm: false },
    knowledgebase: false,
    tracing: false,
    enableA2ui: false,
    subAgents: [],
    builtinTools: [],
    customTools: [],
    mcpTools: [],
    modelName: "",
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
