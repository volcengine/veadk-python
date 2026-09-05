import { getFontEmbedCSS, toBlob } from "html-to-image";
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

interface ShareImagePage {
  blob: Blob;
  width: number;
  height: number;
}

interface ExportPageRange {
  top: number;
  height: number;
}

interface ExportChunkRange extends ExportPageRange {
  pages: ExportPageRange[];
}

interface ExportElementMetrics {
  top: number;
  bottom: number;
  height: number;
  position: string;
}

interface ExportBreakMetrics {
  top: number;
  bottom: number;
  height: number;
}

type ExportMeasurements = WeakMap<HTMLElement, ExportElementMetrics>;

const EXPORT_WIDTH = 816;
const EXPORT_PAGE_HEIGHT = 1_154;
const EXPORT_CHUNK_HEIGHT = 12_000;
const EXPORT_MIN_PAGE_FILL = 0.72;
const EXPORT_MAX_LAST_PAGE_HEIGHT = EXPORT_PAGE_HEIGHT * 1.12;
const PDF_MARGIN_MM = 10;
const EXPORT_BREAK_SELECTOR = [
  ".turn--user",
  ".turn--assistant",
  ".codex-sandbox-run__event",
  ".block-tool",
  ".block-thinking",
  ".block-progress",
  ".block-plan",
  ".tool-result",
  ".share-message-export-note",
  "p",
  "pre",
  "li",
].join(", ");

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

function expandConversationExportContent(root: HTMLElement): void {
  root
    .querySelectorAll<HTMLElement>(
      ".block-tool, .block-thinking, .block-progress, .block-plan",
    )
    .forEach((node) => {
      node.style.opacity = "1";
      node.style.transform = "none";
      node.style.animation = "none";
    });

  root.querySelectorAll<HTMLElement>(".think-collapse").forEach((node) => {
    node.classList.add("open");
    node.style.gridTemplateRows = "1fr";
    node.style.transition = "none";
  });

  root
    .querySelectorAll<HTMLElement>(
      ".codex-sandbox-run__stream, .think-body, .tool-result",
    )
    .forEach((node) => {
      node.style.height = "auto";
      node.style.maxHeight = "none";
      node.style.overflow = "visible";
      node.scrollTop = 0;
      node.scrollLeft = 0;
    });

  root.querySelectorAll<HTMLElement>(".tool-args").forEach((node) => {
    node.style.maxWidth = "100%";
    node.style.overflowWrap = "anywhere";
    node.style.whiteSpace = "pre-wrap";
  });

  root
    .querySelectorAll<HTMLElement>(".think-collapse-inner")
    .forEach((node) => {
      node.style.height = "auto";
      node.style.overflow = "visible";
    });
}

function removeDuplicateCodexExportPayloads(root: HTMLElement): void {
  root
    .querySelectorAll<HTMLElement>(".codex-sandbox-run")
    .forEach((codexActivity) => {
      codexActivity.parentElement
        ?.querySelector(":scope > .tool-detail")
        ?.remove();
    });
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
    expandConversationExportContent(clone);
    removeDuplicateCodexExportPayloads(clone);
    exportRoot.append(clone);
  }

  const exportNote = document.createElement("p");
  exportNote.className = "share-message-export-note";
  exportNote.textContent = "上述会话由 AgentKit Studio 导出，仅供参考";
  exportRoot.append(exportNote);

  document.body.append(exportRoot);
  return exportRoot;
}

function createConversationExportPageRanges(
  exportRoot: HTMLElement,
): ExportPageRange[] {
  const totalHeight = Math.max(1, Math.ceil(exportRoot.scrollHeight));
  const rootTop = exportRoot.getBoundingClientRect().top;
  const breakBlocks = Array.from(
    exportRoot.querySelectorAll<HTMLElement>(EXPORT_BREAK_SELECTOR),
  )
    .map<ExportBreakMetrics>((node) => {
      const rect = node.getBoundingClientRect();
      return {
        top: Math.floor(rect.top - rootTop),
        bottom: Math.ceil(rect.bottom - rootTop),
        height: Math.ceil(rect.height),
      };
    })
    .filter(
      ({ bottom, height }) => bottom > 0 && bottom < totalHeight && height > 0,
    )
    .sort((left, right) => left.bottom - right.bottom);
  const ranges: ExportPageRange[] = [];
  let pageTop = 0;

  while (pageTop < totalHeight) {
    const remainingHeight = totalHeight - pageTop;
    if (remainingHeight <= EXPORT_MAX_LAST_PAGE_HEIGHT) {
      ranges.push({ top: pageTop, height: remainingHeight });
      break;
    }

    const idealBottom = Math.min(totalHeight, pageTop + EXPORT_PAGE_HEIGHT);
    const minimumBottom = pageTop + EXPORT_PAGE_HEIGHT * EXPORT_MIN_PAGE_FILL;
    const containingBlockTop = breakBlocks.reduce<number | undefined>(
      (best, block) => {
        const canKeepWhole =
          block.top >= minimumBottom &&
          block.top > pageTop &&
          block.top < idealBottom &&
          block.bottom > idealBottom &&
          block.height <= EXPORT_PAGE_HEIGHT;
        if (!canKeepWhole) return best;
        return best === undefined ? block.top : Math.min(best, block.top);
      },
      undefined,
    );
    const pageBottom =
      containingBlockTop ??
      breakBlocks.reduce(
        (best, candidate) =>
          candidate.bottom >= minimumBottom && candidate.bottom <= idealBottom
            ? candidate.bottom
            : best,
        idealBottom,
      );
    ranges.push({ top: pageTop, height: Math.max(1, pageBottom - pageTop) });
    pageTop = pageBottom;
  }

  return ranges;
}

function createConversationExportChunks(
  pageRanges: ExportPageRange[],
): ExportChunkRange[] {
  const chunks: ExportChunkRange[] = [];
  for (const page of pageRanges) {
    const current = chunks[chunks.length - 1];
    const pageBottom = page.top + page.height;
    if (current && pageBottom - current.top <= EXPORT_CHUNK_HEIGHT) {
      current.pages.push(page);
      current.height = pageBottom - current.top;
    } else {
      chunks.push({ top: page.top, height: page.height, pages: [page] });
    }
  }
  return chunks;
}

function measureConversationExport(
  exportRoot: HTMLElement,
): ExportMeasurements {
  const rootTop = exportRoot.getBoundingClientRect().top;
  const measurements: ExportMeasurements = new WeakMap();
  exportRoot.querySelectorAll<HTMLElement>("*").forEach((node) => {
    const rect = node.getBoundingClientRect();
    measurements.set(node, {
      top: rect.top - rootTop,
      bottom: rect.bottom - rootTop,
      height: rect.height,
      position: getComputedStyle(node).position,
    });
  });
  return measurements;
}

function pruneConversationExportClone(
  source: HTMLElement,
  clone: HTMLElement,
  range: ExportPageRange,
  measurements: ExportMeasurements,
): void {
  if (source.matches(EXPORT_BREAK_SELECTOR)) return;

  const sourceChildren = Array.from(source.children).filter(
    (node): node is HTMLElement => node instanceof HTMLElement,
  );
  const cloneChildren = Array.from(clone.children).filter(
    (node): node is HTMLElement => node instanceof HTMLElement,
  );
  const rangeBottom = range.top + range.height;

  for (let index = sourceChildren.length - 1; index >= 0; index -= 1) {
    const sourceChild = sourceChildren[index];
    const cloneChild = cloneChildren[index];
    const metrics = measurements.get(sourceChild);
    if (!cloneChild || !metrics) continue;
    const intersects = metrics.bottom > range.top && metrics.top < rangeBottom;
    if (intersects) {
      pruneConversationExportClone(
        sourceChild,
        cloneChild,
        range,
        measurements,
      );
      continue;
    }

    if (
      metrics.height <= 0 ||
      metrics.position === "absolute" ||
      metrics.position === "fixed"
    ) {
      cloneChild.remove();
      continue;
    }

    cloneChild.replaceChildren();
    cloneChild.removeAttribute("id");
    cloneChild.setAttribute("aria-hidden", "true");
    cloneChild.style.boxSizing = "border-box";
    cloneChild.style.height = `${metrics.height}px`;
    cloneChild.style.minHeight = `${metrics.height}px`;
    cloneChild.style.maxHeight = `${metrics.height}px`;
    cloneChild.style.overflow = "hidden";
    cloneChild.style.visibility = "hidden";
    cloneChild.style.animation = "none";
    cloneChild.style.transition = "none";
  }
}

function createConversationExportPage(
  exportRoot: HTMLElement,
  range: ExportPageRange,
  pageNumber: number,
  pageCount: number,
  measurements: ExportMeasurements,
): HTMLElement {
  const exportPage = document.createElement("section");
  exportPage.className = "share-message-export-page";
  exportPage.setAttribute("aria-hidden", "true");
  exportPage.dataset.exportPage = String(pageNumber);
  exportPage.dataset.exportPageCount = String(pageCount);
  exportPage.style.height = `${range.height}px`;

  const pageContent = exportRoot.cloneNode(true) as HTMLElement;
  pruneConversationExportClone(exportRoot, pageContent, range, measurements);
  pageContent.classList.add("share-message-export-page-content");
  pageContent.style.position = "absolute";
  pageContent.style.top = `${-range.top}px`;
  pageContent.style.left = "0";
  pageContent.style.margin = "0";
  exportPage.append(pageContent);
  document.body.append(exportPage);
  return exportPage;
}

function canvasBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("图片生成失败，请重试。"));
    }, "image/png");
  });
}

async function splitExportChunk(
  chunkBlob: Blob,
  width: number,
  chunk: ExportChunkRange,
): Promise<ShareImagePage[]> {
  const bitmap = await createImageBitmap(chunkBlob);
  const scaleX = bitmap.width / width;
  const scaleY = bitmap.height / chunk.height;
  const pages: ShareImagePage[] = [];
  try {
    for (const page of chunk.pages) {
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = page.height;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("浏览器无法生成会话图片，请重试。");
      context.drawImage(
        bitmap,
        0,
        (page.top - chunk.top) * scaleY,
        width * scaleX,
        page.height * scaleY,
        0,
        0,
        width,
        page.height,
      );
      pages.push({
        blob: await canvasBlob(canvas),
        width,
        height: page.height,
      });
      canvas.width = 0;
      canvas.height = 0;
    }
  } finally {
    bitmap.close();
  }
  return pages;
}

async function generateShareImages(
  targetTurn: HTMLElement,
): Promise<ShareImagePage[]> {
  if (document.fonts?.ready) await document.fonts.ready;
  const exportRoot = createConversationExport(targetTurn);
  try {
    const width = Math.max(EXPORT_WIDTH, Math.ceil(exportRoot.scrollWidth));
    const pageRanges = createConversationExportPageRanges(exportRoot);
    const exportChunks = createConversationExportChunks(pageRanges);
    const measurements = measureConversationExport(exportRoot);
    const fontEmbedCSS = await getFontEmbedCSS(exportRoot);
    const pages: ShareImagePage[] = [];

    for (const [chunkIndex, chunk] of exportChunks.entries()) {
      const exportChunk = createConversationExportPage(
        exportRoot,
        chunk,
        chunkIndex + 1,
        exportChunks.length,
        measurements,
      );
      try {
        const blob = await toBlob(exportChunk, {
          width,
          height: chunk.height,
          pixelRatio: 1,
          backgroundColor: exportBackgroundColor(),
          fontEmbedCSS,
          style: {
            position: "static",
            top: "auto",
            left: "auto",
            width: `${width}px`,
            height: `${chunk.height}px`,
            margin: "0",
            overflow: "hidden",
            animation: "none",
          },
        });
        if (!blob) throw new Error("图片生成失败，请重试。");
        pages.push(...(await splitExportChunk(blob, width, chunk)));
      } finally {
        exportChunk.remove();
      }
    }

    return pages;
  } finally {
    exportRoot.remove();
  }
}

function shareFileName(timestamp: string): string {
  return `agentkit-conversation-${timestamp}.pdf`;
}

function sharePageFileName(
  pageNumber: number,
  pageCount: number,
  timestamp: string,
): string {
  const digits = Math.max(2, String(pageCount).length);
  return `agentkit-conversation-${timestamp}-page-${String(pageNumber).padStart(digits, "0")}.png`;
}

function shareArchiveFileName(timestamp: string): string {
  return `agentkit-conversation-${timestamp}-png-pages.zip`;
}

const CRC32_TABLE = Array.from({ length: 256 }, (_, value) => {
  let checksum = value;
  for (let bit = 0; bit < 8; bit += 1) {
    checksum = checksum & 1 ? 0xedb88320 ^ (checksum >>> 1) : checksum >>> 1;
  }
  return checksum >>> 0;
});

function crc32(bytes: Uint8Array): number {
  let checksum = 0xffffffff;
  for (const byte of bytes) {
    checksum = CRC32_TABLE[(checksum ^ byte) & 0xff] ^ (checksum >>> 8);
  }
  return (checksum ^ 0xffffffff) >>> 0;
}

async function createPngArchive(
  imagePages: ShareImagePage[],
  timestamp: string,
): Promise<Blob> {
  const encoder = new TextEncoder();
  const archiveParts: BlobPart[] = [];
  const centralDirectoryParts: BlobPart[] = [];
  let localOffset = 0;
  let centralDirectorySize = 0;

  for (const [pageIndex, page] of imagePages.entries()) {
    const fileName = sharePageFileName(
      pageIndex + 1,
      imagePages.length,
      timestamp,
    );
    const fileNameBytes = encoder.encode(fileName);
    const fileBytes = new Uint8Array(await page.blob.arrayBuffer());
    const checksum = crc32(fileBytes);
    const localHeader = new ArrayBuffer(30);
    const localView = new DataView(localHeader);
    localView.setUint32(0, 0x04034b50, true);
    localView.setUint16(4, 20, true);
    localView.setUint16(6, 0x0800, true);
    localView.setUint16(8, 0, true);
    localView.setUint32(14, checksum, true);
    localView.setUint32(18, fileBytes.byteLength, true);
    localView.setUint32(22, fileBytes.byteLength, true);
    localView.setUint16(26, fileNameBytes.byteLength, true);
    archiveParts.push(localHeader, fileNameBytes, fileBytes);

    const centralHeader = new ArrayBuffer(46);
    const centralView = new DataView(centralHeader);
    centralView.setUint32(0, 0x02014b50, true);
    centralView.setUint16(4, 20, true);
    centralView.setUint16(6, 20, true);
    centralView.setUint16(8, 0x0800, true);
    centralView.setUint16(10, 0, true);
    centralView.setUint32(16, checksum, true);
    centralView.setUint32(20, fileBytes.byteLength, true);
    centralView.setUint32(24, fileBytes.byteLength, true);
    centralView.setUint16(28, fileNameBytes.byteLength, true);
    centralView.setUint32(42, localOffset, true);
    centralDirectoryParts.push(centralHeader, fileNameBytes);

    localOffset += 30 + fileNameBytes.byteLength + fileBytes.byteLength;
    centralDirectorySize += 46 + fileNameBytes.byteLength;
  }

  const endRecord = new ArrayBuffer(22);
  const endView = new DataView(endRecord);
  endView.setUint32(0, 0x06054b50, true);
  endView.setUint16(8, imagePages.length, true);
  endView.setUint16(10, imagePages.length, true);
  endView.setUint32(12, centralDirectorySize, true);
  endView.setUint32(16, localOffset, true);
  return new Blob([...archiveParts, ...centralDirectoryParts, endRecord], {
    type: "application/zip",
  });
}

async function generateSharePdf(imagePages: ShareImagePage[]): Promise<Blob> {
  const { jsPDF } = await import("jspdf");
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
  for (const [pageIndex, page] of imagePages.entries()) {
    const imageBytes = new Uint8Array(await page.blob.arrayBuffer());
    const scale = Math.min(
      contentWidth / page.width,
      contentHeight / page.height,
    );
    const renderedWidth = page.width * scale;
    const renderedHeight = page.height * scale;
    if (pageIndex > 0) pdf.addPage();
    pdf.addImage(
      imageBytes,
      "PNG",
      PDF_MARGIN_MM + (contentWidth - renderedWidth) / 2,
      PDF_MARGIN_MM,
      renderedWidth,
      renderedHeight,
      `conversation-export-${pageIndex}`,
      "FAST",
    );
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
  const [imagePages, setImagePages] = useState<ShareImagePage[]>([]);
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
    setImagePages([]);
    setImageUrl("");
    setError("");
    setCopyState("idle");

    const generate = async () => {
      try {
        await waitForDialogPaint();
        if (disposed) return;
        const pages = await generateShareImages(targetTurn);
        if (pages.length === 0) throw new Error("图片生成失败，请重试。");
        objectUrl = URL.createObjectURL(pages[0].blob);
        if (disposed) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        setImagePages(pages);
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
    const firstPage = imagePages[0];
    if (!firstPage || copyState === "copying") return;
    setCopyState("copying");
    setError("");
    try {
      if (!navigator.clipboard?.write || typeof ClipboardItem === "undefined") {
        throw new Error("当前浏览器不支持复制图片，请下载后使用。");
      }
      await navigator.clipboard.write([
        new ClipboardItem({ "image/png": firstPage.blob }),
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
    if (imagePages.length === 0 || downloadState === "downloading") return;
    setDownloadState("downloading");
    setError("");
    try {
      const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
      if (exportFormat === "pdf") {
        const blob = await generateSharePdf(imagePages);
        downloadBlob(blob, shareFileName(timestamp));
      } else if (imagePages.length === 1) {
        downloadBlob(imagePages[0].blob, sharePageFileName(1, 1, timestamp));
      } else {
        const archive = await createPngArchive(imagePages, timestamp);
        downloadBlob(archive, shareArchiveFileName(timestamp));
      }
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
        aria-busy={
          generationState === "generating" || downloadState === "downloading"
        }
      >
        <header className="share-message-head">
          <div>
            <h2 id={titleId}>导出会话</h2>
            <p id={descriptionId}>
              选择格式并下载截至当前回复的全部输入与输出。
            </p>
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
            <figure className="share-message-preview">
              <figcaption className="share-message-preview-meta">
                预览第 1 页，共 {imagePages.length} 页
              </figcaption>
              <img
                src={imageUrl}
                alt={`会话导出内容第 1 页，共 ${imagePages.length} 页`}
              />
            </figure>
          )}
          {generationState !== "error" && error && (
            <p className="share-message-error" role="alert">
              {error}
            </p>
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
            {downloadState === "downloading"
              ? `正在生成 ${exportFormat.toUpperCase()}…`
              : ""}
          </span>
          {exportFormat === "png" && (
            <button
              type="button"
              onClick={() => void copyImage()}
              disabled={
                imagePages.length === 0 ||
                generationState !== "ready" ||
                copyState === "copying"
              }
            >
              {copyState === "copying"
                ? "正在复制…"
                : copyState === "copied"
                  ? imagePages.length > 1
                    ? "已复制第一页"
                    : "已复制"
                  : imagePages.length > 1
                    ? "复制第一页"
                    : "复制图片"}
            </button>
          )}
          <button
            type="button"
            className="is-primary"
            onClick={() => void downloadExport()}
            disabled={
              imagePages.length === 0 ||
              generationState !== "ready" ||
              downloadState === "downloading"
            }
          >
            {downloadState === "downloading"
              ? "正在生成…"
              : exportFormat === "png" && imagePages.length > 1
                ? `下载 PNG 压缩包（${imagePages.length} 页）`
                : `下载 ${exportFormat.toUpperCase()}`}
          </button>
        </footer>
      </section>
    </div>,
    document.body,
  );
}
