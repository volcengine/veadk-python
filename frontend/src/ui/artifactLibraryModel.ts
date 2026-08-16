import type { AdkEvent, AdkSession } from "../adk/client";
import { sessionTitle } from "../blocks";

export type ArtifactType = "document" | "image" | "video";
export type ArtifactPreviewMode = "image" | "video" | "frame" | "unavailable";

export interface ArtifactOrigin {
  runtimeId?: string;
  region?: string;
  eventId?: string;
  invocationId?: string;
  toolName?: string;
  taskId?: string;
}

export interface ArtifactSessionSource {
  appName: string;
  agentId?: string;
  agentName?: string;
  runtimeId?: string;
  region?: string;
  sessions: readonly AdkSession[];
}

export interface ArtifactIngestCandidate {
  sourceUrl: string;
  name: string;
  mimeType?: string;
  appName: string;
  agentId?: string;
  agentName: string;
  sessionId: string;
  sessionTitle: string;
  sessionUpdatedAt: string;
  createdAt: string;
  origin: ArtifactOrigin;
}

export interface ArtifactLibraryItem {
  id: string;
  appName: string;
  agentId?: string;
  sessionId: string;
  sessionTitle: string;
  agentName: string;
  sessionUpdatedAt: number;
  name: string;
  version: number;
  type: ArtifactType;
  createdAt: number;
  updatedAt?: number;
  description?: string;
  tags?: readonly string[];
  mimeType?: string;
  sizeBytes?: number;
  canManage?: boolean;
  thumbnailUrl?: string;
  contentUrl?: string;
  origin?: ArtifactOrigin;
  preview: {
    filename: string;
    version: number;
    mode: ArtifactPreviewMode;
  };
}

interface SessionArtifactRecord {
  filename: string;
  version: number;
  createdAt: number;
}

const IMAGE_EXTENSIONS = new Set([
  "avif", "bmp", "gif", "heic", "jpeg", "jpg", "png", "svg", "tif", "tiff", "webp",
]);
const VIDEO_EXTENSIONS = new Set([
  "avi", "m4v", "mkv", "mov", "mp4", "mpeg", "mpg", "webm",
]);
const FRAME_EXTENSIONS = new Set([
  "csv", "htm", "html", "json", "md", "pdf", "svg", "txt", "xml", "yaml", "yml",
]);

function fileExtension(filename: string): string {
  const index = filename.lastIndexOf(".");
  return index < 0 ? "" : filename.slice(index + 1).toLocaleLowerCase();
}

function timestampMillis(value: number | undefined, fallback: number): number {
  if (!Number.isFinite(value)) return fallback;
  const timestamp = value as number;
  return timestamp > 10_000_000_000 ? timestamp : timestamp * 1_000;
}

function eventArtifactDelta(event: AdkEvent): Record<string, number> | undefined {
  return event.actions?.artifactDelta ?? event.actions?.artifact_delta;
}

function previewFilename(filename: string): string {
  return `${filename.replace(/\.pptx$/i, "")}.preview.webp`;
}

function functionResponse(event: AdkEvent) {
  return (event.content?.parts ?? [])
    .map((part) => part.functionResponse ?? part.function_response)
    .filter((value) => Boolean(value));
}

function responsePayload(value: Record<string, unknown> | undefined): Record<string, unknown> {
  if (!value) return {};
  const result = value.result;
  return result && typeof result === "object" && !Array.isArray(result)
    ? result as Record<string, unknown>
    : value;
}

function outputName(name: string, url: string, type: ArtifactType): string {
  if (/\.[A-Za-z0-9]{2,8}$/.test(name)) return name;
  try {
    const segments = new URL(url).pathname.split("/").filter(Boolean);
    const filename = segments[segments.length - 1] ?? "";
    const extension = filename.match(/\.[A-Za-z0-9]{2,8}$/)?.[0] ?? "";
    if (extension) return `${name}${extension}`;
  } catch {
    // The server performs the authoritative URL validation.
  }
  return `${name}.${type === "image" ? "png" : "mp4"}`;
}

function generatedOutputs(
  toolName: string,
  response: Record<string, unknown> | undefined,
): Array<{ name: string; url: string; type: ArtifactType; taskId?: string }> {
  const payload = responsePayload(response);
  const isImage = toolName === "image_generate" || toolName.endsWith("_image_generate");
  const isVideo = ["video_generate", "video_task_query"].some(
    (name) => toolName === name || toolName.endsWith(`_${name}`),
  );
  if (!isImage && !isVideo) return [];
  const type: ArtifactType = isImage ? "image" : "video";
  const outputs: Array<{ name: string; url: string; type: ArtifactType; taskId?: string }> = [];
  const successList = payload.success_list;
  if (Array.isArray(successList)) {
    for (const item of successList) {
      if (!item || typeof item !== "object" || Array.isArray(item)) continue;
      for (const [name, url] of Object.entries(item)) {
        if (typeof url === "string" && url.startsWith("https://")) {
          outputs.push({ name: outputName(name, url, type), url, type });
        }
      }
    }
  }
  const directUrl = payload.video_url;
  if (isVideo && typeof directUrl === "string" && directUrl.startsWith("https://")) {
    const taskId = typeof payload.task_id === "string" ? payload.task_id : undefined;
    outputs.push({
      name: outputName(taskId || "generated-video", directUrl, type),
      url: directUrl,
      type,
      taskId,
    });
  }
  return outputs;
}

function isoTimestamp(value: number | undefined, fallback: number): string {
  return new Date(timestampMillis(value, fallback) || Date.now()).toISOString();
}

export function collectArtifactIngestCandidates(
  sources: readonly ArtifactSessionSource[],
): ArtifactIngestCandidate[] {
  const candidates: ArtifactIngestCandidate[] = [];
  const seen = new Set<string>();
  for (const source of sources) {
    for (const session of source.sessions) {
      const updatedAt = timestampMillis(session.lastUpdateTime, Date.now());
      const title = sessionTitle(session.events);
      for (const event of session.events ?? []) {
        for (const response of functionResponse(event)) {
          const toolName = response?.name ?? "";
          for (const output of generatedOutputs(toolName, response?.response)) {
            const key = `${session.id}:${event.id ?? ""}:${toolName}:${output.url}`;
            if (seen.has(key)) continue;
            seen.add(key);
            candidates.push({
              sourceUrl: output.url,
              name: output.name,
              mimeType: output.type === "image" ? "image/png" : "video/mp4",
              appName: source.appName,
              agentId: source.agentId,
              agentName: source.agentName?.trim() || source.appName,
              sessionId: session.id,
              sessionTitle: title,
              sessionUpdatedAt: isoTimestamp(session.lastUpdateTime, updatedAt),
              createdAt: isoTimestamp(event.timestamp, updatedAt),
              origin: {
                runtimeId: source.runtimeId,
                region: source.region,
                eventId: event.id,
                invocationId: event.invocationId ?? event.invocation_id,
                toolName,
                taskId: output.taskId,
              },
            });
          }
        }
      }
    }
  }
  return candidates;
}

export function artifactTypeFor(filename: string): ArtifactType {
  const extension = fileExtension(filename);
  if (IMAGE_EXTENSIONS.has(extension)) return "image";
  if (VIDEO_EXTENSIONS.has(extension)) return "video";
  return "document";
}

export function artifactPreviewModeFor(filename: string): ArtifactPreviewMode {
  const type = artifactTypeFor(filename);
  if (type === "image") return "image";
  if (type === "video") return "video";
  if (FRAME_EXTENSIONS.has(fileExtension(filename))) return "frame";
  return "unavailable";
}

export function collectArtifactLibraryItems(
  sources: readonly ArtifactSessionSource[],
): ArtifactLibraryItem[] {
  const items: ArtifactLibraryItem[] = [];

  for (const source of sources) {
    for (const session of source.sessions) {
      const sessionUpdatedAt = timestampMillis(session.lastUpdateTime, 0);
      const records = new Map<string, SessionArtifactRecord>();
      for (const event of session.events ?? []) {
        const delta = eventArtifactDelta(event);
        if (!delta) continue;
        const createdAt = timestampMillis(event.timestamp, sessionUpdatedAt);
        for (const [filename, version] of Object.entries(delta)) {
          if (!filename || !Number.isFinite(version)) continue;
          const current = records.get(filename);
          if (!current || version >= current.version) {
            records.set(filename, { filename, version, createdAt });
          }
        }
      }

      for (const record of records.values()) {
        if (/\.preview\.webp$/i.test(record.filename)) continue;
        const companion = records.get(previewFilename(record.filename));
        const previewRecord = companion ?? record;
        const previewMode = companion
          ? "image"
          : artifactPreviewModeFor(record.filename);
        items.push({
          id: `${source.appName}:${session.id}:${record.filename}:${record.version}`,
          appName: source.appName,
          agentId: source.agentId,
          sessionId: session.id,
          sessionTitle: sessionTitle(session.events),
          agentName: source.agentName?.trim() || source.appName,
          sessionUpdatedAt,
          name: record.filename,
          version: record.version,
          type: artifactTypeFor(record.filename),
          createdAt: record.createdAt || sessionUpdatedAt,
          preview: {
            filename: previewRecord.filename,
            version: previewRecord.version,
            mode: previewMode,
          },
        });
      }
    }
  }

  return items.sort((left, right) =>
    right.createdAt - left.createdAt || left.name.localeCompare(right.name, "zh-CN"),
  );
}

export function formatArtifactTime(value: number): string {
  if (!value) return "时间未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  const now = new Date();
  const sameDay = date.getFullYear() === now.getFullYear()
    && date.getMonth() === now.getMonth()
    && date.getDate() === now.getDate();
  if (sameDay) {
    return new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export function formatArtifactSize(value: number | undefined): string {
  if (!value || value <= 0) return "";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  if (value < 1024 * 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(value < 10 * 1024 * 1024 ? 1 : 0)} MB`;
  }
  return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}
