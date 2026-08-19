import type { ComponentType, SVGProps } from "react";
import { AgentFaceSquareIcon } from "../icons/CreateAgentIcons";
import {
  ImageGenerateIcon,
  LoadKnowledgebaseIcon,
  LoadMemoryIcon,
  LoadSkillIcon,
  PresentationGenerateIcon,
  RunCodeIcon,
  VideoGenerateIcon,
  WebSearchIcon,
} from "./icons";

export type BuiltinToolTone =
  | "search"
  | "image"
  | "video"
  | "presentation"
  | "memory"
  | "knowledge"
  | "skill"
  | "agent"
  | "sandbox";

export interface BuiltinToolDefinition {
  name: string;
  runningLabel: string;
  doneLabel: string;
  tone: BuiltinToolTone;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
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
  generate_agent: {
    name: "generate_agent",
    runningLabel: "正在定制智能体",
    doneLabel: "智能体定制完毕",
    tone: "agent",
    icon: AgentFaceSquareIcon,
  },
};

export function getBuiltinToolDefinition(name: string): BuiltinToolDefinition | undefined {
  return BUILTIN_TOOLS[name];
}
