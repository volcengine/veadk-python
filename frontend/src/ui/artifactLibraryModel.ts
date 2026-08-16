import type { AdkEvent, AdkSession } from "../adk/client";
import { sessionTitle } from "../blocks";

export type ArtifactType = "document" | "image" | "video";
export type ArtifactPreviewMode = "image" | "video" | "frame" | "unavailable";

export interface ArtifactSessionSource {
  appName: string;
  agentName?: string;
  sessions: readonly AdkSession[];
}

export interface ArtifactLibraryItem {
  id: string;
  appName: string;
  sessionId: string;
  sessionTitle: string;
  agentName: string;
  sessionUpdatedAt: number;
  name: string;
  version: number;
  type: ArtifactType;
  createdAt: number;
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
