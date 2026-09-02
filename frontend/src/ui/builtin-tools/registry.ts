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
    runningLabel: "正在进行网络搜索",
    doneLabel: "已完成网络搜索",
    tone: "search",
    icon: WebSearchIcon,
  },
  run_code: {
    name: "run_code",
    runningLabel: "正在 AgentKit 沙箱中执行代码",
    doneLabel: "已在 AgentKit 沙箱中完成代码执行",
    tone: "sandbox",
    icon: RunCodeIcon,
  },
  list_envs: {
    name: "list_envs",
    runningLabel: "正在查看可用环境",
    doneLabel: "已读取可用环境",
    tone: "resources",
    icon: ListEnvironmentsIcon,
  },
  get_env_manifest: {
    name: "get_env_manifest",
    runningLabel: "正在读取环境 Manifest",
    doneLabel: "已读取环境 Manifest",
    tone: "knowledge",
    icon: EnvironmentManifestIcon,
  },
  execute_in_sandbox: {
    name: "execute_in_sandbox",
    runningLabel: "正在环境中执行命令",
    doneLabel: "已在环境中完成命令执行",
    tone: "sandbox",
    icon: ExecuteInSandboxIcon,
  },
  image_generate: {
    name: "image_generate",
    runningLabel: "正在生成图片",
    doneLabel: "已完成图片生成",
    tone: "image",
    icon: ImageGenerateIcon,
  },
  video_generate: {
    name: "video_generate",
    runningLabel: "正在生成视频",
    doneLabel: "已完成视频生成",
    tone: "video",
    icon: VideoGenerateIcon,
  },
  ppt_generate: {
    name: "ppt_generate",
    runningLabel: "正在生成 PPT",
    doneLabel: "已完成 PPT 生成",
    tone: "presentation",
    icon: PresentationGenerateIcon,
  },
  load_memory: {
    name: "load_memory",
    runningLabel: "正在检索长期记忆",
    doneLabel: "已完成记忆检索",
    tone: "memory",
    icon: LoadMemoryIcon,
  },
  load_knowledgebase: {
    name: "load_knowledgebase",
    runningLabel: "正在检索知识库",
    doneLabel: "已完成知识库检索",
    tone: "knowledge",
    icon: LoadKnowledgebaseIcon,
  },
  load_skill: {
    name: "load_skill",
    runningLabel: "正在加载技能",
    doneLabel: "已加载技能",
    tone: "skill",
    icon: LoadSkillIcon,
  },
  collect_resources: {
    name: "collect_resources",
    runningLabel: "正在收集可用资源",
    doneLabel: "已完成资源收集",
    failedLabel: "资源收集失败",
    tone: "resources",
    icon: CollectResourcesIcon,
    detailRenderer: CollectResourcesCard,
  },
  create_agents: {
    name: "create_agents",
    runningLabel: "正在创建并运行 Agent",
    doneLabel: "已完成 Agent 创建",
    failedLabel: "Agent 创建失败",
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
