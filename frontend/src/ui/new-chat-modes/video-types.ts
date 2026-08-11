import type { CloudProvider } from "../../adk/cloudProvider";
import type { NewChatCompactSelectOption } from "./NewChatCompactSelect";

export type VideoTaskMode =
  | "auto"
  | "text_to_video"
  | "reference_to_video"
  | "video_editing"
  | "video_extension"
  | "first_last_frame";

export type VideoAspectRatio = "21:9" | "16:9" | "4:3" | "1:1" | "3:4" | "9:16";
export type VideoResolution = "480p" | "720p";

export interface NewChatVideoConfig {
  taskMode: VideoTaskMode;
  aspectRatio: VideoAspectRatio;
  resolution: VideoResolution;
  durationSeconds: number;
  referenceImage: File | null;
  referenceVideo: File | null;
  firstFrame: File | null;
  lastFrame: File | null;
}

export interface VideoProviderModels {
  generation: string;
  enhancer: string;
}

export const VIDEO_MODELS_BY_PROVIDER: Record<CloudProvider, VideoProviderModels> = {
  volcengine: {
    generation: "doubao-seedance-2-5-260628",
    enhancer: "doubao-seed-2-1-pro-260628",
  },
  byteplus: {
    generation: "dreamina-seedance-2-5-260628",
    enhancer: "dola-seed-2-1-turbo-260628",
  },
};

export function videoModelsForProvider(provider: CloudProvider): VideoProviderModels {
  return VIDEO_MODELS_BY_PROVIDER[provider];
}

export const VIDEO_TASK_MODE_OPTIONS: NewChatCompactSelectOption[] = [
  { value: "auto", label: "自动识别" },
  { value: "text_to_video", label: "文生视频" },
  { value: "reference_to_video", label: "参考素材生视频" },
  { value: "video_editing", label: "视频编辑" },
  { value: "video_extension", label: "视频续写" },
  { value: "first_last_frame", label: "首尾帧生成" },
];

export const VIDEO_ASPECT_RATIO_OPTIONS: NewChatCompactSelectOption[] = [
  { value: "21:9", label: "21:9" },
  { value: "16:9", label: "16:9" },
  { value: "4:3", label: "4:3" },
  { value: "1:1", label: "1:1" },
  { value: "3:4", label: "3:4" },
  { value: "9:16", label: "9:16" },
];

export const VIDEO_RESOLUTION_OPTIONS: NewChatCompactSelectOption[] = [
  { value: "480p", label: "480p" },
  { value: "720p", label: "720p" },
];

export const DEFAULT_NEW_CHAT_VIDEO_CONFIG: NewChatVideoConfig = {
  taskMode: "auto",
  aspectRatio: "16:9",
  resolution: "720p",
  durationSeconds: 8,
  referenceImage: null,
  referenceVideo: null,
  firstFrame: null,
  lastFrame: null,
};
