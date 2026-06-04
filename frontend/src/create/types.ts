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

/** A skill selected from the Skill Hub (findskill.com); its files get bundled
 *  into the generated project under skills/<name>/. */
export interface SelectedSkill {
  slug: string;
  name: string;
  namespace: string;
}

/** A draft VeADK agent configuration produced by a creation flow. */
export interface AgentDraft {
  name: string;
  description: string;
  /** System prompt. */
  instruction: string;
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
}

export function emptyDraft(): AgentDraft {
  return {
    name: "",
    description: "",
    instruction: "",
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
  };
}

export interface CreateModeProps {
  /** Return to the quick-create card menu. */
  onBack: () => void;
  /** Called when the user finishes assembling an agent. */
  onCreate: (draft: AgentDraft) => void;
}
