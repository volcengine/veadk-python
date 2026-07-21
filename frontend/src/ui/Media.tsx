import { useEffect, useMemo, useState } from "react";
import {
  Download,
  FileText,
  FileType2,
  FileVideo2,
  ImageIcon,
  Loader2,
  Maximize2,
  X,
  Play,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { PhotoView } from "react-photo-view";
import { mediaContentUrl } from "../adk/client";
import { Markdown } from "./Markdown";

export interface MediaItem {
  id: string;
  mimeType?: string;
  data?: string;
  uri?: string;
  name?: string;
  sizeBytes?: number;
  previewUrl?: string;
  status?: "uploading" | "ready" | "error";
  error?: string;
}

interface MediaGroupProps {
  appName: string;
  items: MediaItem[];
  compact?: boolean;
  onRemove?: (id: string) => void;
}

function mediaKind(mimeType = "") {
  if (mimeType.startsWith("image/")) return "image";
  if (mimeType.startsWith("video/")) return "video";
  if (mimeType === "application/pdf") return "pdf";
  if (mimeType === "text/markdown") return "markdown";
  return "text";
}

function labelFor(item: MediaItem) {
  const kind = mediaKind(item.mimeType);
  if (kind === "pdf") return "PDF";
  if (kind === "markdown") return "MD";
  if (kind === "video") return item.mimeType?.split("/")[1]?.toUpperCase() ?? "VIDEO";
  if (kind === "image") return item.mimeType?.split("/")[1]?.toUpperCase() ?? "IMAGE";
  return "TXT";
}

function formatBytes(bytes?: number) {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function sourceFor(item: MediaItem, appName: string) {
  if (item.previewUrl) return item.previewUrl;
  if (item.data) return `data:${item.mimeType ?? "application/octet-stream"};base64,${item.data}`;
  if (item.uri) return mediaContentUrl(appName, item.uri);
  return "";
}

function KindIcon({ kind }: { kind: ReturnType<typeof mediaKind> }) {
  if (kind === "image") return <ImageIcon />;
  if (kind === "video") return <FileVideo2 />;
  if (kind === "pdf") return <FileType2 />;
  return <FileText />;
}

export function MediaGroup({ appName, items, compact = false, onRemove }: MediaGroupProps) {
  const [open, setOpen] = useState<MediaItem | null>(null);
  return (
    <>
      <div className={`media-grid${compact ? " media-grid--compact" : ""}`}>
        {items.map((item) => {
          const kind = mediaKind(item.mimeType);
          const source = sourceFor(item, appName);
          const disabled = item.status === "uploading" || item.status === "error" || !source;

          const previewButton = (
            <button
              type="button"
              className="media-card-main"
              disabled={disabled}
              onClick={() => setOpen(item)}
              aria-label={`预览 ${item.name ?? "附件"}`}
            >
              {kind === "image" && source ? (
                <img className="media-card-image" src={source} alt={item.name ?? "图片"} loading="lazy" />
              ) : kind === "video" && source ? (
                <div className="media-card-video-container">
                  <video
                    className="media-card-video"
                    src={source}
                    muted
                    playsInline
                    preload="metadata"
                    aria-hidden="true"
                  />
                  <span className="media-card-video-play">
                    <Play />
                  </span>
                </div>
              ) : (
                <span className="media-card-icon"><KindIcon kind={kind} /></span>
              )}
              <span className="media-card-copy">
                <span className="media-card-name">{item.name ?? "附件"}</span>
                <span className="media-card-meta">
                  <span className="media-card-type">{labelFor(item)}</span>
                  {item.status === "uploading" ? (
                    <><Loader2 className="media-card-spinner" /> 上传中</>
                  ) : item.status === "error" ? (
                    item.error ?? "上传失败"
                  ) : (
                    formatBytes(item.sizeBytes)
                  )}
                </span>
              </span>
              {!compact && item.status !== "uploading" && item.status !== "error" ? (
                <Maximize2 className="media-card-open" />
              ) : null}
            </button>
          );
          return (
            <motion.div
              className={`media-card media-card--${kind}${item.status === "error" ? " media-card--error" : ""}`}
              key={item.id}
              layout
              initial={{ opacity: 0, scale: 0.985, y: 4 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
            >
              {kind === "image" && !disabled ? (
                <PhotoView src={source}>{previewButton}</PhotoView>
              ) : (
                previewButton
              )}
              {onRemove ? (
                <button
                  type="button"
                  className="media-card-remove"
                  aria-label={`移除 ${item.name ?? "附件"}`}
                  onClick={() => onRemove(item.id)}
                >
                  <X />
                </button>
              ) : null}
            </motion.div>
          );
        })}
      </div>
      <AnimatePresence>
        {open ? (
          <MediaViewer appName={appName} item={open} onClose={() => setOpen(null)} />
        ) : null}
      </AnimatePresence>
    </>
  );
}

function MediaViewer({ appName, item, onClose }: { appName: string; item: MediaItem; onClose: () => void }) {
  const source = useMemo(() => sourceFor(item, appName), [appName, item]);
  const kind = mediaKind(item.mimeType);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(kind === "text" || kind === "markdown");
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (kind !== "text" && kind !== "markdown") return;
    const controller = new AbortController();
    setLoading(true);
    setLoadError("");
    fetch(source, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.text();
      })
      .then(setText)
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setLoadError(error instanceof Error ? error.message : String(error));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [kind, source]);

  return (
    <motion.div
      className="media-viewer-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label={item.name ?? "附件预览"}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <motion.div
        className="media-viewer"
        initial={{ opacity: 0, y: 18, scale: 0.985 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 10, scale: 0.99 }}
        transition={{ type: "spring", stiffness: 420, damping: 30 }}
      >
        <header className="media-viewer-header">
          <div>
            <strong>{item.name ?? "附件"}</strong>
            <span>{labelFor(item)}{item.sizeBytes ? ` · ${formatBytes(item.sizeBytes)}` : ""}</span>
          </div>
          <nav>
            <a href={source} download={item.name} aria-label="下载"><Download /></a>
            <button type="button" onClick={onClose} aria-label="关闭"><X /></button>
          </nav>
        </header>
        <div className={`media-viewer-body media-viewer-body--${kind}`}>
          {kind === "image" ? <img src={source} alt={item.name ?? "图片"} /> : null}
          {kind === "video" ? (
            <div className="media-viewer-video-wrapper">
              <video
                src={source}
                controls
                autoPlay
                playsInline
                preload="auto"
                className="media-viewer-video"
              />
            </div>
          ) : null}
          {kind === "pdf" ? <iframe src={source} title={item.name ?? "PDF"} /> : null}
          {loading ? <div className="media-viewer-loading"><Loader2 /> 正在读取文档…</div> : null}
          {!loading && loadError ? <div className="media-viewer-loading">文档加载失败：{loadError}</div> : null}
          {!loading && kind === "markdown" ? <div className="media-document"><Markdown text={text} /></div> : null}
          {!loading && kind === "text" ? <pre className="media-document media-document--plain">{text}</pre> : null}
        </div>
      </motion.div>
    </motion.div>
  );
}
