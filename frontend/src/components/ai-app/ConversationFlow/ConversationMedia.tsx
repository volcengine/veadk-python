import { useRef, useState } from "react";
import { ModalButton } from "../../composites/ModalButton";
import { Button } from "../../primitives/Button";
import { ErrorState } from "../../primitives/ErrorState";
import type { ConversationMediaBlock } from "./ConversationFlow.types";
import { ConversationDownloadIcon, ConversationPreviewIcon } from "./ConversationFlowIcons";
import "./ConversationMedia.css";

export type ConversationMediaProps = Omit<ConversationMediaBlock, "id" | "type">;

const mediaMimeTypes = {
  image: new Set(["image/png", "image/jpeg", "image/webp", "image/gif", "image/avif", "image/bmp"]),
  video: new Set(["video/mp4", "video/webm", "video/ogg", "video/quicktime"]),
  audio: new Set(["audio/mpeg", "audio/mp3", "audio/mp4", "audio/ogg", "audio/wav", "audio/x-wav", "audio/webm", "audio/aac", "audio/flac"]),
};

/** Keep source validation identical for direct blocks and Studio attachments */
export function safeConversationMediaSource(source: string | undefined, kind: ConversationMediaBlock["kind"]): string | undefined {
  const value = source?.trim();
  if (!value || /[\u0000-\u001f\u007f\\]/.test(value) || value.startsWith("//")) return undefined;
  if (/^data:/i.test(value)) {
    const comma = value.indexOf(",");
    if (comma < 0) return undefined;
    const [mime, ...parameters] = value.slice(5, comma).toLowerCase().split(";");
    return mediaMimeTypes[kind].has(mime) && parameters.every(parameter => parameter === "base64" || /^charset=[a-z0-9._-]+$/.test(parameter)) ? value : undefined;
  }
  if (!/^[a-z][a-z0-9+.-]*:/i.test(value)) return value;
  try {
    const url = new URL(value);
    if (/^https?:\/\//i.test(value) && (url.protocol === "http:" || url.protocol === "https:")) return value;
    return url.protocol === "blob:" && url.pathname ? value : undefined;
  } catch {
    return undefined;
  }
}

const mediaLabels = { image: "图片", video: "视频", audio: "音频" };

function MediaContent({ kind, src, alt, name, poster, caption, onPreview, onDownload }: ConversationMediaProps) {
  const [failed, setFailed] = useState(false);
  const [theme, setTheme] = useState<string | undefined>();
  const figureRef = useRef<HTMLElement>(null);
  const label = name ?? alt ?? mediaLabels[kind];
  const fail = () => setFailed(true);
  const showPreviewAction = onPreview && (kind !== "image" || failed || !src);
  const showDownload = onDownload || (name && src);

  return <figure ref={figureRef} className="studio-conversation-media-block" data-kind={kind}>
    {failed || !src ? <ErrorState className="studio-conversation-media-block__error" title={`${mediaLabels[kind]}无法加载`} description={name ?? caption} role="alert" />
      : kind === "image" ? <ModalButton
        label={<img className="studio-conversation-media-block__image" src={src} alt={alt ?? name ?? "图片附件"} loading="lazy" decoding="async" onError={fail} />}
        title={name ?? "图片预览"}
        closeLabel="关闭图片"
        topGlow={false}
        data-theme={theme}
        className="studio-conversation-media-block__modal"
        buttonProps={{ variant: "ghost", className: "studio-conversation-media-block__image-button", "aria-label": `放大 ${label}` }}
        onOpenChange={open => {
          if (!open) return;
          setTheme(figureRef.current?.closest("[data-theme]")?.getAttribute("data-theme") ?? undefined);
          onPreview?.();
        }}
      >
        <img className="studio-conversation-media-block__expanded-image" src={src} alt={alt ?? name ?? "图片附件"} onError={fail} />
      </ModalButton>
      : kind === "video" ? <video className="studio-conversation-media-block__video" src={src} poster={safeConversationMediaSource(poster, "image")} aria-label={label} controls playsInline preload="metadata" onError={fail} />
      : <audio className="studio-conversation-media-block__audio" src={src} aria-label={label} controls preload="metadata" onError={fail} />}
    {(name || caption || showDownload || showPreviewAction) && <figcaption className="studio-conversation-media-block__caption">
      <span className="studio-conversation-media-block__text">{caption ?? name}</span>
      {(showDownload || showPreviewAction) && <span className="studio-conversation-media-block__actions">
        {showPreviewAction && <Button variant="ghost" iconOnly startIcon={<ConversationPreviewIcon />} aria-label={`预览 ${label}`} onClick={onPreview} />}
        {onDownload ? <Button variant="ghost" iconOnly startIcon={<ConversationDownloadIcon />} aria-label={`下载 ${label}`} onClick={onDownload} />
          : name && src && <a className="studio-conversation-media-block__download" href={src} download={name} aria-label={`下载 ${label}`}><ConversationDownloadIcon /></a>}
      </span>}
    </figcaption>}
  </figure>;
}

/** Inline multimodal content; media controls never start playback automatically */
export function ConversationMedia(props: ConversationMediaProps) {
  const source = safeConversationMediaSource(props.src, props.kind) ?? "";
  return <MediaContent key={`${props.kind}:${source}`} {...props} src={source} />;
}
