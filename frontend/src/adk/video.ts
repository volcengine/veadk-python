import { withAuth } from "./auth";
import { withLocalUser } from "./identity";
import { DEFAULT_REQUEST_TIMEOUT_MS, requestSignal, TRANSFER_REQUEST_TIMEOUT_MS } from "./timeout";
import type {
  VideoAspectRatio,
  VideoResolution,
  VideoTaskMode,
} from "../ui/new-chat-modes/video-types";
import { adkT, withLocaleHeaders } from "./i18n";

const VIDEO_API_ROOT = "/web/video";
const VIDEO_ENHANCEMENT_TIMEOUT_MS = 180_000;

export interface VideoCapabilities {
  provider: string;
  generationModel: string;
  enhancerModel: string;
  assetStorageAvailable: boolean;
  assetStorageUnavailableReason: string;
  maxAssetBytes: number;
  supportedModes: VideoTaskMode[];
}

export type VideoAssetKind =
  | "reference_image"
  | "reference_video"
  | "first_frame"
  | "last_frame";

export interface UploadedVideoAsset {
  assetId: string;
  previewUrl: string;
  fileName: string;
  mimeType: string;
}

export interface EnhanceVideoPromptRequest {
  prompt: string;
  taskMode: VideoTaskMode;
  assetIds: string[];
  ratio: VideoAspectRatio;
  resolution: VideoResolution;
  durationSeconds: number;
}

export interface EnhanceVideoPromptResponse {
  resolvedTaskMode: VideoTaskMode;
  enhancedPrompt: string;
  enhancerModel: string;
  ratio: VideoAspectRatio;
  resolution: VideoResolution;
  durationSeconds: number;
}

export interface CreateVideoTaskRequest {
  enhancedPrompt: string;
  resolvedTaskMode: VideoTaskMode;
  assetIds: string[];
  ratio: VideoAspectRatio;
  resolution: VideoResolution;
  durationSeconds: number;
}

export interface CreateVideoTaskResponse {
  taskId: string;
  status: "queued" | "running";
  generationModel: string;
}

export interface VideoTaskResponse {
  taskId: string;
  status: "queued" | "running" | "succeeded" | "failed";
  taskMode: VideoTaskMode;
  generationModel: string;
  enhancedPrompt: string;
  outputFormat: "mp4" | "mov";
  videoUrl?: string;
  error?: string;
}

async function request(
  path: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
): Promise<Response> {
  return fetch(withAuth(`${VIDEO_API_ROOT}${path}`), {
    ...init,
    headers: withLocaleHeaders(withLocalUser(init.headers)),
    signal: requestSignal(init.signal, timeoutMs),
  });
}

async function responseError(response: Response, fallback: string): Promise<Error> {
  const raw = await response.text().catch(() => "");
  let detail = "";
  try {
    const body = JSON.parse(raw) as { detail?: unknown; error?: unknown };
    const value = body.detail ?? body.error;
    detail = typeof value === "string" ? value : "";
  } catch {
    detail = raw.trim().slice(0, 500);
  }
  return new Error(detail || adkT("common.fallbackWithHttpStatus", { fallback, status: response.status }));
}

async function json<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) throw await responseError(response, fallback);
  const raw = await response.text().catch(() => "");
  try {
    return JSON.parse(raw) as T;
  } catch {
    const contentType = response.headers.get("content-type") || adkT("common.contentTypeMissing");
    throw new Error(adkT("common.nonJsonResponse", { fallback, contentType }));
  }
}

export async function getVideoCapabilities(signal?: AbortSignal): Promise<VideoCapabilities> {
  return json(
    await request("/capabilities", { signal, headers: { Accept: "application/json" } }),
    adkT("video.loadCapabilitiesFailed"),
  );
}

export async function uploadVideoAsset(
  file: File,
  kind: VideoAssetKind,
  signal?: AbortSignal,
): Promise<UploadedVideoAsset> {
  const form = new FormData();
  form.set("file", file);
  form.set("role", kind);
  return json(
    await request("/assets", { method: "POST", body: form, signal }, TRANSFER_REQUEST_TIMEOUT_MS),
    adkT("video.uploadAssetFailed", { fileName: file.name }),
  );
}

export async function enhanceVideoPrompt(
  payload: EnhanceVideoPromptRequest,
  signal?: AbortSignal,
): Promise<EnhanceVideoPromptResponse> {
  return json(
    await request("/prompts/enhance", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    }, VIDEO_ENHANCEMENT_TIMEOUT_MS),
    adkT("video.enhancePromptFailed"),
  );
}

export async function createVideoTask(
  payload: CreateVideoTaskRequest,
  signal?: AbortSignal,
): Promise<CreateVideoTaskResponse> {
  return json(
    await request("/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    }, TRANSFER_REQUEST_TIMEOUT_MS),
    adkT("video.createTaskFailed"),
  );
}

export async function getVideoTask(
  taskId: string,
  signal?: AbortSignal,
): Promise<VideoTaskResponse> {
  return json(
    await request(`/tasks/${encodeURIComponent(taskId)}`, {
      signal,
      headers: { Accept: "application/json" },
    }),
    adkT("video.getTaskFailed"),
  );
}

export async function downloadVideoTask(
  taskId: string,
  signal?: AbortSignal,
): Promise<Blob> {
  const response = await request(
    `/tasks/${encodeURIComponent(taskId)}/download`,
    { signal, headers: { Accept: "video/*" } },
    TRANSFER_REQUEST_TIMEOUT_MS,
  );
  if (!response.ok) throw await responseError(response, adkT("video.downloadFailed"));
  return response.blob();
}

export function videoResultPreviewUrl(url: string): string {
  return url.startsWith("/") ? withAuth(url) : url;
}
