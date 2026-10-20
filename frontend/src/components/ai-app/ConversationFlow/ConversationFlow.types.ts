import type { ComponentPropsWithoutRef, CSSProperties, ReactNode } from "react";
import type { ScrollAreaProps } from "../../primitives/ScrollArea";

export type ConversationStatus = "pending" | "running" | "complete" | "error" | "cancelled";
export type ConversationFeedback = "like" | "dislike" | null;

export interface ConversationStepBase {
  /** 同一条消息内稳定且唯一的步骤标识 */
  id: string;
  title: string;
  /** 默认 complete，由调用方提供执行状态 */
  status?: ConversationStatus;
  /** 执行耗时，单位毫秒；负数及非有限数不显示 */
  durationMs?: number;
  /** 执行开始时间，Unix 毫秒时间戳；running 时据此实时计时 */
  startedAt?: number;
  /** 执行结束时间，Unix 毫秒时间戳 */
  endedAt?: number;
  /** 整个步骤是否默认展开，默认 false */
  defaultOpen?: boolean;
}

export interface ConversationReasoningStep extends ConversationStepBase {
  type: "reasoning";
  /** 思考细节，支持流式更新后的 React 内容 */
  content?: ReactNode;
}

export interface ConversationToolStep extends ConversationStepBase {
  type: "tool";
  /** 工具输入原文；未提供时隐藏 Input 区域 */
  input?: string;
  /** 工具输出原文；未提供时隐藏 Output 区域 */
  output?: string;
  /** 默认 json */
  inputLanguage?: string;
  /** 默认 json */
  outputLanguage?: string;
  /** 工具错误说明 */
  error?: ReactNode;
  /** 已有组件渲染的工具结果，例如图表、媒体或表格 */
  result?: ReactNode;
}

export type ConversationStep = ConversationReasoningStep | ConversationToolStep;

export interface ConversationMarkdownBlock {
  type: "markdown";
  id: string;
  text: string;
}

export interface ConversationVisualizationBlock {
  type: "visualization";
  id: string;
  kind: "echarts" | "mermaid";
  source: string;
  title?: string;
}

export interface ConversationMediaBlock {
  type: "media";
  id: string;
  kind: "image" | "video" | "audio";
  /** 相对路径、HTTP(S)、Blob URL 或对应媒体类型的安全 data URL */
  src: string;
  alt?: string;
  name?: string;
  /** 视频封面图片 */
  poster?: string;
  caption?: string;
  /** 图片放大或点击媒体预览操作时通知业务 */
  onPreview?: () => void;
  onDownload?: () => void;
}

export interface ConversationHandoffBlock extends ConversationStepBase {
  type: "handoff";
  fromAgent?: string;
  toAgent: string;
  status: ConversationStatus;
  content?: ReactNode;
  steps?: readonly ConversationStep[];
}

export interface ConversationPlanItem {
  id: string;
  title: string;
  status: ConversationStatus;
}

export interface ConversationPlanBlock {
  type: "plan";
  id: string;
  title: string;
  items: readonly ConversationPlanItem[];
}

export interface ConversationFile {
  id: string;
  name: string;
  description?: string;
  href?: string;
  preview?: ReactNode;
  onPreview?: () => void;
  onDownload?: () => void;
}

export interface ConversationFilesBlock {
  type: "files";
  id: string;
  title?: string;
  files: readonly ConversationFile[];
}

export interface ConversationAuthorizationBlock {
  type: "authorization";
  id: string;
  title: string;
  description?: ReactNode;
  status: ConversationStatus;
  onAuthorize?: () => void;
  onCancel?: () => void;
}

export interface ConversationCustomBlock {
  type: "custom";
  id: string;
  title?: string;
  content: ReactNode;
}

export type ConversationBlock = ConversationMarkdownBlock | ConversationVisualizationBlock | ConversationMediaBlock | ConversationStep | ConversationHandoffBlock | ConversationPlanBlock | ConversationFilesBlock | ConversationAuthorizationBlock | ConversationCustomBlock;

export interface ConversationMessageBase {
  /** 对话中稳定且唯一的消息标识 */
  id: string;
  /** 消息无障碍名称，不在对话中展示 */
  name?: string;
  /** 复制原文；未提供时仅字符串 content 可复制 */
  copyText?: string;
  /** 有序内容块；提供后优先于旧的 content 和 steps */
  blocks?: readonly ConversationBlock[];
}

export interface ConversationUserMessage extends ConversationMessageBase {
  role: "user";
  content?: ReactNode;
}

export interface ConversationSystemMessage extends ConversationMessageBase {
  role: "system";
  content?: ReactNode;
}

export interface ConversationAssistantMessage extends ConversationMessageBase {
  role: "assistant";
  /** 回答正文；执行中可暂不提供 */
  content?: ReactNode;
  /** 默认 complete，由调用方更新 */
  status?: ConversationStatus;
  steps?: readonly ConversationStep[];
  /** 整条回复执行耗时，单位毫秒，允许 0 */
  durationMs?: number;
  /** 整条回复开始时间，Unix 毫秒时间戳；running 时据此实时计时 */
  startedAt?: number;
  /** 整条回复结束时间，Unix 毫秒时间戳 */
  endedAt?: number;
  /** 首个 token 耗时，单位毫秒，允许 0 */
  ttftMs?: number;
  /** 总 token 数，允许 0；负数及非有限数不显示 */
  tokens?: number;
  model?: string;
  /** 回复错误说明 */
  error?: ReactNode;
  /** 受控反馈状态；未提供时组件只发出 onFeedback 回调 */
  feedback?: ConversationFeedback;
  /** 自定义回复操作区；提供后替换内置复制、重试和反馈按钮，null 隐藏操作区 */
  actions?: ReactNode;
}

export type ConversationMessage = ConversationUserMessage | ConversationSystemMessage | ConversationAssistantMessage;

export type ConversationFlowProps = Omit<ComponentPropsWithoutRef<"div">, "children"> & {
  messages: readonly ConversationMessage[];
  /** 对话流固定高度，默认 600px，内部通过 ScrollArea 纵向滚动 */
  height?: CSSProperties["height"];
  /** 内部 ScrollArea 属性，滚动方向固定为纵向 */
  scrollAreaProps?: Omit<ScrollAreaProps, "children" | "orientation" | "ref">;
  /** 提供后显示重新生成按钮，执行动作由调用方处理 */
  onRetry?: (messageId: string) => void;
  /** 提供后显示反馈按钮；再次点击已选项会传 null */
  onFeedback?: (messageId: string, feedback: ConversationFeedback) => void;
  /** 提供后为执行中的回复显示停止按钮 */
  onStop?: (messageId: string) => void;
};
