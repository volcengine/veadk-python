import type { ComponentType, SVGProps } from "react";
import { BranchCompareCard } from "./BranchCompareCard";
import {
  CollectResourcesCard,
  CreateAgentsCard,
} from "./CreateAgentToolCards";
import {
  CollectResourcesIcon,
  CreateAgentsIcon,
  EnvironmentManifestIcon,
  ExecuteInSandboxIcon,
  ImageGenerateIcon,
  LoadKnowledgebaseIcon,
  LoadMemoryIcon,
  LoadSkillIcon,
  PresentationGenerateIcon,
  RunCodeIcon,
  ListEnvironmentsIcon,
  VideoGenerateIcon,
  WebSearchIcon,
} from "./icons";
import type { BranchCompareBranch } from "./branchCompareData";

export type BuiltinToolTone =
  | "search"
  | "image"
  | "video"
  | "presentation"
  | "memory"
  | "knowledge"
  | "skill"
  | "sandbox"
  | "resources"
  | "agent";

export interface BuiltinToolDetailProps {
  args?: unknown;
  response?: unknown;
  status: "running" | "completed" | "failed";
  onBranchSelect?: (branch: BranchCompareBranch) => void;
}

export interface BuiltinToolDefinition {
  name: string;
  runningLabel: string;
  doneLabel: string;
  failedLabel?: string;
  tone: BuiltinToolTone;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  detailRenderer?: ComponentType<BuiltinToolDetailProps>;
  hideHeader?: boolean;
}

const BUILTIN_TOOLS: Readonly<Record<string, BuiltinToolDefinition>> = {
  web_search: {
    name: "web_search",
    runningLabel: "Searching the web",
    doneLabel: "Web search complete",
    tone: "search",
    icon: WebSearchIcon,
  },
  link_reader: {
    name: "link_reader",
    runningLabel: "Reading webpage",
    doneLabel: "Webpage read complete",
    tone: "search",
    icon: WebSearchIcon,
  },
  run_code: {
    name: "run_code",
    runningLabel: "Running code in the AgentKit sandbox",
    doneLabel: "Code execution completed in the AgentKit sandbox",
    tone: "sandbox",
    icon: RunCodeIcon,
  },
  list_envs: {
    name: "list_envs",
    runningLabel: "Checking available environments",
    doneLabel: "Available environments loaded",
    tone: "resources",
    icon: ListEnvironmentsIcon,
  },
  get_env_manifest: {
    name: "get_env_manifest",
    runningLabel: "Loading the environment manifest",
    doneLabel: "Environment manifest loaded",
    tone: "knowledge",
    icon: EnvironmentManifestIcon,
  },
  execute_in_sandbox: {
    name: "execute_in_sandbox",
    runningLabel: "Running a command in the environment",
    doneLabel: "Command completed in the environment",
    tone: "sandbox",
    icon: ExecuteInSandboxIcon,
  },
  delegate_to_codex_sandbox: {
    name: "delegate_to_codex_sandbox",
    runningLabel: "Codex Sandbox is running",
    doneLabel: "Codex Sandbox completed",
    failedLabel: "Codex Sandbox failed",
    tone: "sandbox",
    icon: ExecuteInSandboxIcon,
  },
  image_generate: {
    name: "image_generate",
    runningLabel: "Generating image",
    doneLabel: "Image generated",
    tone: "image",
    icon: ImageGenerateIcon,
  },
  video_generate: {
    name: "video_generate",
    runningLabel: "Generating video",
    doneLabel: "Video generated",
    tone: "video",
    icon: VideoGenerateIcon,
  },
  ppt_generate: {
    name: "ppt_generate",
    runningLabel: "Generating presentation",
    doneLabel: "Presentation generated",
    tone: "presentation",
    icon: PresentationGenerateIcon,
  },
  load_memory: {
    name: "load_memory",
    runningLabel: "Searching long-term memory",
    doneLabel: "Memory search complete",
    tone: "memory",
    icon: LoadMemoryIcon,
  },
  load_knowledgebase: {
    name: "load_knowledgebase",
    runningLabel: "Searching the knowledge base",
    doneLabel: "Knowledge base search complete",
    tone: "knowledge",
    icon: LoadKnowledgebaseIcon,
  },
  load_skill: {
    name: "load_skill",
    runningLabel: "Loading skill",
    doneLabel: "Skill loaded",
    tone: "skill",
    icon: LoadSkillIcon,
  },
  collect_resources: {
    name: "collect_resources",
    runningLabel: "Collecting available resources",
    doneLabel: "Resource collection complete",
    failedLabel: "Resource collection failed",
    tone: "resources",
    icon: CollectResourcesIcon,
    detailRenderer: CollectResourcesCard,
  },
  create_agents: {
    name: "create_agents",
    runningLabel: "Creating and running agents",
    doneLabel: "Agent creation complete",
    failedLabel: "Agent creation failed",
    tone: "agent",
    icon: CreateAgentsIcon,
    detailRenderer: CreateAgentsCard,
  },
  branch_compare: {
    name: "branch_compare",
    runningLabel: "",
    doneLabel: "",
    failedLabel: "",
    tone: "search",
    icon: CreateAgentsIcon,
    detailRenderer: BranchCompareCard,
    hideHeader: true,
  },
};

export function getBuiltinToolDefinition(name: string): BuiltinToolDefinition | undefined {
  return BUILTIN_TOOLS[name];
}
