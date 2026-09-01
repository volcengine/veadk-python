import { toBlob } from "html-to-image";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
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
type DownloadState = "idle" | "downloading";
type ExportFormat = "png" | "pdf";

const MAX_CANVAS_DIMENSION = 16_384;
const MAX_CANVAS_PIXELS = 32_000_000;
const PDF_MARGIN_MM = 10;

function waitForDialogPaint(): Promise<void> {
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => resolve());
    });
  });
}

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

function shareFileName(format: ExportFormat): string {
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  const extension = format === "pdf" ? ".pdf" : ".png";
  return `agentkit-conversation-${timestamp}${extension}`;
}

function loadBlobImage(blob: Blob): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(blob);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(objectUrl);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error("无法读取会话图片，请重试。"));
    };
    image.src = objectUrl;
  });
}

function findPageBreak(
  image: HTMLImageElement,
  pageTop: number,
  idealBottom: number,
): number {
  const searchHeight = Math.min(
    idealBottom - pageTop,
    Math.max(96, Math.round((idealBottom - pageTop) * 0.16)),
  );
  const searchTop = Math.max(pageTop + 1, idealBottom - searchHeight);
  const canvas = document.createElement("canvas");
  canvas.width = image.naturalWidth;
  canvas.height = idealBottom - searchTop;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context || canvas.height < 4) return idealBottom;
  context.drawImage(
    image,
    0,
    searchTop,
    image.naturalWidth,
    canvas.height,
    0,
    0,
    image.naturalWidth,
    canvas.height,
  );
  const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
  const rowIsBlank = (row: number) => {
    const rowStart = row * canvas.width * 4;
    const red = pixels[rowStart];
    const green = pixels[rowStart + 1];
    const blue = pixels[rowStart + 2];
    let differentPixels = 0;
    for (let x = 0; x < canvas.width; x += 3) {
      const index = rowStart + x * 4;
      const difference =
        Math.abs(pixels[index] - red) +
        Math.abs(pixels[index + 1] - green) +
        Math.abs(pixels[index + 2] - blue);
      if (difference > 42) differentPixels += 1;
    }
    return differentPixels <= Math.max(2, Math.floor(canvas.width / 300));
  };

  for (let row = canvas.height - 1; row >= 3; row -= 1) {
    if (
      rowIsBlank(row) &&
      rowIsBlank(row - 1) &&
      rowIsBlank(row - 2) &&
      rowIsBlank(row - 3)
    ) {
      return searchTop + row - 1;
    }
  }
  return idealBottom;
}

async function generateSharePdf(imageBlob: Blob): Promise<Blob> {
  const [{ jsPDF }, image] = await Promise.all([
    import("jspdf"),
    loadBlobImage(imageBlob),
  ]);
  const pdf = new jsPDF({
    orientation: "portrait",
    unit: "mm",
    format: "a4",
    compress: true,
  });
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const contentWidth = pageWidth - PDF_MARGIN_MM * 2;
  const contentHeight = pageHeight - PDF_MARGIN_MM * 2;
  const pagePixelHeight = Math.max(
    1,
    Math.floor((image.naturalWidth * contentHeight) / contentWidth),
  );
  let pageTop = 0;
  let pageIndex = 0;

  while (pageTop < image.naturalHeight) {
    const idealBottom = Math.min(image.naturalHeight, pageTop + pagePixelHeight);
    const pageBottom = idealBottom < image.naturalHeight
      ? findPageBreak(image, pageTop, idealBottom)
      : idealBottom;
    const sliceHeight = Math.max(1, pageBottom - pageTop);
    const slice = document.createElement("canvas");
    slice.width = image.naturalWidth;
    slice.height = sliceHeight;
    const context = slice.getContext("2d");
    if (!context) throw new Error("浏览器无法生成 PDF，请重试。");
    context.drawImage(
      image,
      0,
      pageTop,
      image.naturalWidth,
      sliceHeight,
      0,
      0,
      image.naturalWidth,
      sliceHeight,
    );
    const sliceDataUrl = slice.toDataURL("image/png");
    const renderedHeight = (sliceHeight * contentWidth) / image.naturalWidth;
    if (pageIndex > 0) pdf.addPage();
    pdf.addImage(
      sliceDataUrl,
      "PNG",
      PDF_MARGIN_MM,
      PDF_MARGIN_MM,
      contentWidth,
      renderedHeight,
      `conversation-export-${pageIndex}`,
      "FAST",
    );
    slice.width = 0;
    slice.height = 0;
    pageTop = pageBottom;
    pageIndex += 1;
  }

  return new Blob([pdf.output("arraybuffer")], { type: "application/pdf" });
}

function downloadBlob(blob: Blob, fileName: string): void {
  const downloadUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = downloadUrl;
  anchor.download = fileName;
  anchor.style.display = "none";
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1_000);
}

export function ShareMessageDialog({
  targetTurn,
  onClose,
}: ShareMessageDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const formatLabelId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  const copyResetTimerRef = useRef<number | undefined>(undefined);
  const mountedRef = useRef(true);
  const [generationState, setGenerationState] =
    useState<GenerationState>("generating");
  const [generationAttempt, setGenerationAttempt] = useState(0);
  const [imageBlob, setImageBlob] = useState<Blob | null>(null);
  const [imageUrl, setImageUrl] = useState("");
  const [error, setError] = useState("");
  const [copyState, setCopyState] = useState<CopyState>("idle");
  const [downloadState, setDownloadState] = useState<DownloadState>("idle");
  const [exportFormat, setExportFormat] = useState<ExportFormat>("png");

  onCloseRef.current = onClose;

  useEffect(() => {
    mountedRef.current = true;
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
      mountedRef.current = false;
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

    const generate = async () => {
      try {
        await waitForDialogPaint();
        if (disposed) return;
        const blob = await generateShareImage(targetTurn);
        objectUrl = URL.createObjectURL(blob);
        if (disposed) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        setImageBlob(blob);
        setImageUrl(objectUrl);
        setGenerationState("ready");
      } catch (cause) {
        if (disposed) return;
        setGenerationState("error");
        setError(cause instanceof Error ? cause.message : String(cause));
      }
    };

    void generate();

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

  const selectExportFormat = (format: ExportFormat) => {
    setExportFormat(format);
    setCopyState("idle");
    setError("");
  };

  const handleFormatKeyDown = (
    event: ReactKeyboardEvent<HTMLButtonElement>,
    format: ExportFormat,
  ) => {
    const formats: ExportFormat[] = ["png", "pdf"];
    const currentIndex = formats.indexOf(format);
    let nextIndex = currentIndex;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      nextIndex = (currentIndex + 1) % formats.length;
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      nextIndex = (currentIndex - 1 + formats.length) % formats.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = formats.length - 1;
    } else {
      return;
    }
    event.preventDefault();
    const nextFormat = formats[nextIndex];
    selectExportFormat(nextFormat);
    dialogRef.current
      ?.querySelector<HTMLButtonElement>(`[data-export-format="${nextFormat}"]`)
      ?.focus();
  };

  const downloadExport = async () => {
    if (!imageBlob || downloadState === "downloading") return;
    setDownloadState("downloading");
    setError("");
    try {
      const blob = exportFormat === "pdf"
        ? await generateSharePdf(imageBlob)
        : imageBlob;
      downloadBlob(blob, shareFileName(exportFormat));
    } catch (cause) {
      if (mountedRef.current) {
        setError(cause instanceof Error ? cause.message : "导出失败，请重试。");
      }
    } finally {
      if (mountedRef.current) setDownloadState("idle");
    }
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
        aria-busy={generationState === "generating" || downloadState === "downloading"}
      >
        <header className="share-message-head">
          <div>
            <h2 id={titleId}>导出会话</h2>
            <p id={descriptionId}>选择格式并下载截至当前回复的全部输入与输出。</p>
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
              <TextShimmer>正在生成导出内容…</TextShimmer>
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
              <img src={imageUrl} alt="会话导出内容预览" />
            </div>
          )}
          {generationState !== "error" && error && (
            <p className="share-message-error" role="alert">{error}</p>
          )}
        </div>

        <div className="share-message-options">
          <span id={formatLabelId} className="share-message-format-label">
            导出格式
          </span>
          <div
            className="share-message-format"
            role="radiogroup"
            aria-labelledby={formatLabelId}
          >
            {(["png", "pdf"] as const).map((format) => (
              <button
                key={format}
                type="button"
                role="radio"
                data-export-format={format}
                className={exportFormat === format ? "is-active" : ""}
                aria-checked={exportFormat === format}
                tabIndex={exportFormat === format ? 0 : -1}
                disabled={downloadState === "downloading"}
                onClick={() => selectExportFormat(format)}
                onKeyDown={(event) => handleFormatKeyDown(event, format)}
              >
                {format.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <footer className="share-message-actions">
          <span className="share-message-download-status" aria-live="polite">
            {downloadState === "downloading" ? `正在生成 ${exportFormat.toUpperCase()}…` : ""}
          </span>
          {exportFormat === "png" && (
            <button
              type="button"
              onClick={() => void copyImage()}
              disabled={!imageBlob || generationState !== "ready" || copyState === "copying"}
            >
              {copyState === "copying"
                ? "正在复制…"
                : copyState === "copied"
                  ? "已复制"
                  : "复制图片"}
            </button>
          )}
          <button
            type="button"
            className="is-primary"
            onClick={() => void downloadExport()}
            disabled={
              !imageBlob ||
              generationState !== "ready" ||
              downloadState === "downloading"
            }
          >
            {downloadState === "downloading"
              ? "正在生成…"
              : `下载 ${exportFormat.toUpperCase()}`}
          </button>
        </footer>
      </section>
    </div>,
    document.body,
  );
}
