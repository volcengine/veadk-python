import { toBlob } from "html-to-image";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type SVGProps,
} from "react";
import { createPortal } from "react-dom";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import "./ShareMessageDialog.css";

interface ShareMessageDialogProps {
  targetTurn: HTMLElement;
  onClose: () => void;
}

type GenerationState = "generating" | "ready" | "error";
type CopyState = "idle" | "copying" | "copied";

const MAX_CANVAS_DIMENSION = 16_384;
const MAX_CANVAS_PIXELS = 32_000_000;

function CloseIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      aria-hidden="true"
      {...props}
    >
      <path d="m7 7 10 10" />
      <path d="m17 7-10 10" />
    </svg>
  );
}

function exportBackgroundColor(): string {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue("--background")
    .trim();
  return value ? `hsl(${value})` : "white";
}

function exportPixelRatio(width: number, height: number): number {
  const preferred = Math.min(Math.max(window.devicePixelRatio || 1, 1), 2);
  const dimensionLimit = MAX_CANVAS_DIMENSION / Math.max(width, height);
  const areaLimit = Math.sqrt(MAX_CANVAS_PIXELS / Math.max(width * height, 1));
  return Math.min(preferred, dimensionLimit, areaLimit);
}

function conversationTurnsThrough(targetTurn: HTMLElement): HTMLElement[] {
  const transcript = targetTurn.closest(".transcript");
  if (!transcript) return [targetTurn];
  const turns = Array.from(transcript.children).filter(
    (node): node is HTMLElement =>
      node instanceof HTMLElement &&
      node.matches(".turn--user, .turn--assistant"),
  );
  const targetIndex = turns.indexOf(targetTurn);
  return targetIndex >= 0 ? turns.slice(0, targetIndex + 1) : [targetTurn];
}

function createConversationExport(targetTurn: HTMLElement): HTMLElement {
  const exportRoot = document.createElement("section");
  exportRoot.className = "share-message-export";
  exportRoot.setAttribute("aria-hidden", "true");

  for (const turn of conversationTurnsThrough(targetTurn)) {
    const clone = turn.cloneNode(true) as HTMLElement;
    clone.removeAttribute("data-share-message-source");
    clone.classList.remove("is-feedback-target");
    clone.style.opacity = "1";
    clone.style.transform = "none";
    clone.style.animation = "none";
    clone
      .querySelectorAll("[data-share-image-exclude]")
      .forEach((node) => node.remove());
    exportRoot.append(clone);
  }

  const exportNote = document.createElement("p");
  exportNote.className = "share-message-export-note";
  exportNote.textContent = "上述会话由 AgentKit Studio 导出，仅供参考";
  exportRoot.append(exportNote);

  document.body.append(exportRoot);
  return exportRoot;
}

async function generateShareImage(targetTurn: HTMLElement): Promise<Blob> {
  if (document.fonts?.ready) await document.fonts.ready;
  const exportRoot = createConversationExport(targetTurn);
  try {
    const width = Math.ceil(exportRoot.scrollWidth);
    const height = Math.ceil(exportRoot.scrollHeight);
    const pixelRatio = exportPixelRatio(width, height);
    if (pixelRatio < 0.2) {
      throw new Error("当前会话过长，暂时无法生成单张图片。");
    }

    const blob = await toBlob(exportRoot, {
      width,
      height,
      pixelRatio,
      backgroundColor: exportBackgroundColor(),
      cacheBust: true,
      style: {
        position: "static",
        top: "auto",
        left: "auto",
        width: `${width}px`,
        height: `${height}px`,
        margin: "0",
        overflow: "visible",
        animation: "none",
      },
    });
    if (!blob) throw new Error("图片生成失败，请重试。");
    return blob;
  } finally {
    exportRoot.remove();
  }
}

function shareImageFileName(): string {
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  return `agentkit-conversation-${timestamp}.png`;
}

export function ShareMessageDialog({
  targetTurn,
  onClose,
}: ShareMessageDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  const copyResetTimerRef = useRef<number | undefined>(undefined);
  const [generationState, setGenerationState] =
    useState<GenerationState>("generating");
  const [generationAttempt, setGenerationAttempt] = useState(0);
  const [imageBlob, setImageBlob] = useState<Blob | null>(null);
  const [imageUrl, setImageUrl] = useState("");
  const [error, setError] = useState("");
  const [copyState, setCopyState] = useState<CopyState>("idle");

  onCloseRef.current = onClose;

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const previousFocus =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>(
          "button:not(:disabled)",
        ) ?? [],
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
      if (copyResetTimerRef.current !== undefined) {
        window.clearTimeout(copyResetTimerRef.current);
      }
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  useEffect(() => {
    let disposed = false;
    let objectUrl = "";
    setGenerationState("generating");
    setImageBlob(null);
    setImageUrl("");
    setError("");
    setCopyState("idle");

    void generateShareImage(targetTurn)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        if (disposed) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        setImageBlob(blob);
        setImageUrl(objectUrl);
        setGenerationState("ready");
      })
      .catch((cause) => {
        if (disposed) return;
        setGenerationState("error");
        setError(cause instanceof Error ? cause.message : String(cause));
      });

    return () => {
      disposed = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [generationAttempt, targetTurn]);

  const copyImage = async () => {
    if (!imageBlob || copyState === "copying") return;
    setCopyState("copying");
    setError("");
    try {
      if (!navigator.clipboard?.write || typeof ClipboardItem === "undefined") {
        throw new Error("当前浏览器不支持复制图片，请下载后使用。");
      }
      await navigator.clipboard.write([
        new ClipboardItem({ "image/png": imageBlob }),
      ]);
      setCopyState("copied");
      copyResetTimerRef.current = window.setTimeout(
        () => setCopyState("idle"),
        1_500,
      );
    } catch (cause) {
      setCopyState("idle");
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  const downloadImage = () => {
    if (!imageBlob) return;
    const downloadUrl = URL.createObjectURL(imageBlob);
    const anchor = document.createElement("a");
    anchor.href = downloadUrl;
    anchor.download = shareImageFileName();
    anchor.style.display = "none";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1_000);
  };

  return createPortal(
    <div
      className="share-message-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className="share-message-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        aria-busy={generationState === "generating"}
      >
        <header className="share-message-head">
          <div>
            <h2 id={titleId}>分享为图片</h2>
            <p id={descriptionId}>包含截至当前回复的全部输入与输出。</p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className="share-message-close"
            aria-label="关闭"
            title="关闭"
            onClick={onClose}
          >
            <CloseIcon />
          </button>
        </header>

        <div className="share-message-body">
          {generationState === "generating" ? (
            <div className="share-message-generating" role="status">
              <TextShimmer>正在生成图片…</TextShimmer>
            </div>
          ) : generationState === "error" ? (
            <div className="share-message-failure">
              <p role="alert">{error || "图片生成失败，请重试。"}</p>
              <button
                type="button"
                onClick={() => setGenerationAttempt((attempt) => attempt + 1)}
              >
                重试生成
              </button>
            </div>
          ) : (
            <div className="share-message-preview">
              <img src={imageUrl} alt="会话记录分享图片预览" />
            </div>
          )}
          {generationState !== "error" && error && (
            <p className="share-message-error" role="alert">{error}</p>
          )}
        </div>

        <footer className="share-message-actions">
          <button type="button" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            onClick={downloadImage}
            disabled={!imageBlob || generationState !== "ready"}
          >
            下载 PNG
          </button>
          <button
            type="button"
            className="is-primary"
            onClick={() => void copyImage()}
            disabled={!imageBlob || generationState !== "ready" || copyState === "copying"}
          >
            {copyState === "copying"
              ? "正在复制…"
              : copyState === "copied"
                ? "已复制"
                : "复制图片"}
          </button>
        </footer>
      </section>
    </div>,
    document.body,
  );
}
