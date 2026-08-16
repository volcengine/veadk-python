import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
  type SVGProps,
} from "react";
import { createPortal } from "react-dom";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { Delete, Edit, Eye } from "@openai/apps-sdk-ui/components/Icon";
import { Tooltip } from "@openai/apps-sdk-ui/components/Tooltip";
import {
  cloudRegionOptions,
  formatCloudRegion,
} from "../adk/cloudProvider";
import {
  createKnowledgeBase,
  createKnowledgeDocument,
  deleteKnowledgeBase,
  deleteKnowledgeDocument,
  formatKnowledgeError,
  listKnowledgeBasesAcrossRegions,
  listKnowledgeDocuments,
  KNOWLEDGE_PROVIDER_ASSOCIATION_INVALID,
  KnowledgeRequestError,
  previewKnowledgeDocument,
  uploadKnowledgeDocument,
  updateKnowledgeBase,
  updateKnowledgeDocument,
  type CloudProvider,
  type CreateKnowledgeBaseInput,
  type CreateKnowledgeDocumentInput,
  type KnowledgeBaseItem,
  type KnowledgeDocumentItem,
  type KnowledgeDocumentPreviewChunk,
} from "../adk/knowledge";
import { StudioConfirmDialog } from "./StudioConfirmDialog";
import { LibraryResourceCard } from "./LibraryResourceCard";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import "./MyAgents.css";
import "./KnowledgeLibrary.css";

function KnowledgeIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H19v16H7.5A2.5 2.5 0 0 0 5 21.5v-16Z" />
      <path d="M5 18.5A2.5 2.5 0 0 1 7.5 16H19" />
      <path d="M9 7h6M9 10h4" />
    </svg>
  );
}

function DocumentIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M6 3h8l4 4v14H6V3Z" />
      <path d="M14 3v5h5M9 12h6M9 16h6" />
    </svg>
  );
}

function SearchIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" aria-hidden="true" {...props}>
      <circle cx="10.8" cy="10.8" r="6.3" />
      <path d="m15.5 15.5 4 4" />
    </svg>
  );
}

function CloseIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" aria-hidden="true" {...props}>
      <path d="m7 7 10 10M17 7 7 17" />
    </svg>
  );
}

function PlusIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" aria-hidden="true" {...props}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function BackIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="m15 18-6-6 6-6" />
    </svg>
  );
}

interface KnowledgeDialogProps {
  title: string;
  children: ReactNode;
  onClose: () => void;
  busy?: boolean;
  className?: string;
}

function KnowledgeDialog({ title, children, onClose, busy = false, className = "" }: KnowledgeDialogProps) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const busyRef = useRef(busy);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    busyRef.current = busy;
    onCloseRef.current = onClose;
  }, [busy, onClose]);
  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busyRef.current) {
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href], audio[controls], video[controls], iframe, [tabindex]:not([tabindex="-1"])',
      )).filter((element) => element.getClientRects().length > 0);
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);
  return createPortal(
    <div
      className="knowledge-dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <section ref={dialogRef} className={`knowledge-dialog${className ? ` ${className}` : ""}`} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-busy={busy || undefined}>
        <header className="knowledge-dialog__header">
          <h2 id={titleId}>{title}</h2>
          <button ref={closeRef} type="button" onClick={onClose} disabled={busy} aria-label="关闭">
            <CloseIcon />
          </button>
        </header>
        {children}
      </section>
    </div>,
    document.body,
  );
}

function FormError({ message }: { message: string }) {
  return message ? <div className="knowledge-form-error" role="alert">{message}</div> : null;
}

function isAbortError(reason: unknown): boolean {
  return reason instanceof DOMException && reason.name === "AbortError";
}

function formatDate(value: string): string {
  if (!value) return "";
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(timestamp);
}

function statusLabel(status: string): string {
  const normalized = status.trim().toLowerCase();
  if (["ready", "active", "available", "success"].includes(normalized)) return "可用";
  if (["creating", "pending", "processing", "indexing"].includes(normalized)) return "处理中";
  if (["failed", "error", "unavailable"].includes(normalized)) return "异常";
  return status || "未知";
}

type KnowledgeSourceKind = "image" | "document" | "web";

const IMAGE_ACCEPT = [".jpg", ".jpeg", ".png"].join(",");
const IMAGE_EXTENSIONS = new Set(IMAGE_ACCEPT.split(","));
const DOCUMENT_ACCEPT = [
  ".pdf", ".pptx", ".docx", ".xlsx", ".txt",
].join(",");
const DOCUMENT_EXTENSIONS = new Set(DOCUMENT_ACCEPT.split(","));
const MAX_KNOWLEDGE_FILE_BYTES = 200 * 1024 * 1024;

function fileExtension(name: string): string {
  const index = name.lastIndexOf(".");
  return index < 0 ? "" : name.slice(index).toLocaleLowerCase();
}

function validateKnowledgeFile(file: File, kind: Exclude<KnowledgeSourceKind, "web">): string {
  if (file.size > MAX_KNOWLEDGE_FILE_BYTES) return "单个文件不能超过 200 MB";
  if (kind === "image") {
    return IMAGE_EXTENSIONS.has(fileExtension(file.name))
      ? ""
      : "请选择 PNG、JPG 或 JPEG 图片";
  }
  return DOCUMENT_EXTENSIONS.has(fileExtension(file.name))
    ? ""
    : "请选择 PDF、PPTX、DOCX、XLSX 或 TXT 文件";
}

function formatFileSize(size: number): string {
  if (size <= 0) return "-";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function knowledgeDocumentFormat(item: KnowledgeDocumentItem): string {
  const explicit = item.type.trim().replace(/^\./, "");
  if (explicit) return explicit.toUpperCase();
  const name = item.name.trim();
  const extension = name.includes(".") ? name.split(".").pop()?.trim() : "";
  return extension ? extension.toUpperCase() : "-";
}

function CreateKnowledgeBaseDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (item: KnowledgeBaseItem) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [nameTouched, setNameTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const normalizedName = name.trim();
  const nameInvalid = Boolean(
    normalizedName && !/^[A-Za-z][A-Za-z0-9_]{0,47}$/.test(normalizedName),
  );
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setNameTouched(true);
    if (!normalizedName || nameInvalid) return;
    setBusy(true);
    setError("");
    const input: CreateKnowledgeBaseInput = {
      name: normalizedName,
      description: description.trim() || undefined,
    };
    try {
      onCreated(await createKnowledgeBase(input));
    } catch (reason) {
      setError(formatKnowledgeError(reason, "创建知识库失败"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <KnowledgeDialog title="新建知识库" onClose={onClose} busy={busy}>
      <form onSubmit={(event) => void submit(event)}>
        <div className="knowledge-dialog__body">
          <label><span>名称</span><input autoFocus value={name} maxLength={48} aria-invalid={nameTouched && nameInvalid || undefined} aria-describedby="knowledge-name-help" onBlur={() => setNameTouched(true)} onChange={(event) => setName(event.target.value)} /></label>
          <p id="knowledge-name-help" className={`knowledge-dialog__note${nameTouched && nameInvalid ? " is-error" : ""}`} role={nameTouched && nameInvalid ? "alert" : undefined}>{nameTouched && nameInvalid ? "名称必须以字母开头，且只能包含字母、数字和下划线。" : "以字母开头，仅支持字母、数字和下划线，最多 48 个字符。"}</p>
          <label><span>描述（可选）</span><textarea value={description} maxLength={80} onChange={(event) => setDescription(event.target.value)} /></label>
          <FormError message={error} />
        </div>
        <footer className="knowledge-dialog__actions">
          <button type="button" onClick={onClose} disabled={busy}>取消</button>
          <button type="submit" className="is-primary" disabled={busy || !normalizedName || nameInvalid}>{busy ? "创建中" : "创建"}</button>
        </footer>
      </form>
    </KnowledgeDialog>
  );
}

function EditKnowledgeBaseDialog({ item, onClose, onUpdated }: { item: KnowledgeBaseItem; onClose: () => void; onUpdated: (item: KnowledgeBaseItem) => void }) {
  const [description, setDescription] = useState(item.description);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      onUpdated(await updateKnowledgeBase(item.id, item.region, { description: description.trim() }));
    } catch (reason) {
      setError(formatKnowledgeError(reason, "更新知识库失败"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <KnowledgeDialog title="编辑知识库" onClose={onClose} busy={busy}>
      <form onSubmit={(event) => void submit(event)}>
        <div className="knowledge-dialog__body">
          <label><span>名称</span><input value={item.name} disabled /></label>
          <label><span>描述</span><textarea autoFocus value={description} maxLength={80} onChange={(event) => setDescription(event.target.value)} /></label>
          <p className="knowledge-dialog__note">AgentKit 当前仅支持更新知识库描述。</p>
          <FormError message={error} />
        </div>
        <footer className="knowledge-dialog__actions">
          <button type="button" onClick={onClose} disabled={busy}>取消</button>
          <button type="submit" className="is-primary" disabled={busy}>{busy ? "保存中" : "保存"}</button>
        </footer>
      </form>
    </KnowledgeDialog>
  );
}

function parseMetadata(value: string): Record<string, unknown> {
  if (!value.trim()) return {};
  const parsed: unknown = JSON.parse(value);
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error("Metadata 必须是 JSON 对象");
  }
  return parsed as Record<string, unknown>;
}

function CreateKnowledgeDocumentDialog({ base, onClose, onCreated, onAssociationInvalid }: { base: KnowledgeBaseItem; onClose: () => void; onCreated: () => void; onAssociationInvalid: (error: KnowledgeRequestError) => void }) {
  const [sourceKind, setSourceKind] = useState<KnowledgeSourceKind>("document");
  const [name, setName] = useState("");
  const [documentType, setDocumentType] = useState("");
  const [source, setSource] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [metadata, setMetadata] = useState("{}");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragDepth = useRef(0);

  const chooseSourceKind = (kind: KnowledgeSourceKind) => {
    if (busy || kind === sourceKind) return;
    setSourceKind(kind);
    setFile(null);
    setSource("");
    setName("");
    setDocumentType("");
    setError("");
    setDragging(false);
    dragDepth.current = 0;
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const chooseFile = (candidate: File | null) => {
    if (!candidate || sourceKind === "web") return;
    const validationError = validateKnowledgeFile(candidate, sourceKind);
    if (validationError) {
      setFile(null);
      setName("");
      setDocumentType("");
      setError(validationError);
      return;
    }
    setFile(candidate);
    setError("");
    setName(candidate.name.replace(/\.[^.]+$/, ""));
    setDocumentType(fileExtension(candidate.name).slice(1));
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (sourceKind === "web" ? !source.trim() : !file) return;
    let parsedMetadata: Record<string, unknown>;
    try {
      parsedMetadata = parseMetadata(metadata);
    } catch (reason) {
      setError(formatKnowledgeError(reason, "Metadata 格式错误"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (sourceKind === "web") {
        const input: CreateKnowledgeDocumentInput = {
          sourceType: "url",
          name: name.trim() || undefined,
          documentType: documentType.trim() || undefined,
          metadata: parsedMetadata,
          url: source.trim(),
        };
        await createKnowledgeDocument(base.id, base.region, input);
      } else if (file) {
        await uploadKnowledgeDocument(base.id, base.region, {
          file,
          name: name.trim() || undefined,
          documentType: documentType.trim() || undefined,
          metadata: parsedMetadata,
        });
      }
      onCreated();
    } catch (reason) {
      if (
        reason instanceof KnowledgeRequestError
        && reason.errorCode === KNOWLEDGE_PROVIDER_ASSOCIATION_INVALID
      ) {
        onAssociationInvalid(reason);
      } else {
        setError(formatKnowledgeError(reason, sourceKind === "web" ? "添加网页失败" : "上传文件失败"));
      }
    } finally {
      setBusy(false);
    }
  };
  return (
    <KnowledgeDialog title="添加数据" onClose={onClose} busy={busy}>
      <form onSubmit={(event) => void submit(event)}>
        <div className="knowledge-dialog__body">
          <div className="knowledge-source-tabs" role="tablist" aria-label="知识来源">
            {([
              ["image", "图片"],
              ["document", "文档文件"],
              ["web", "在线网页"],
            ] as const).map(([kind, label]) => (
              <button
                key={kind}
                type="button"
                role="tab"
                id={`knowledge-source-${kind}-tab`}
                aria-controls={`knowledge-source-${kind}-panel`}
                aria-selected={sourceKind === kind}
                tabIndex={sourceKind === kind ? 0 : -1}
                className={sourceKind === kind ? "is-active" : ""}
                disabled={busy}
                onClick={() => chooseSourceKind(kind)}
                onKeyDown={(event) => {
                  const kinds: KnowledgeSourceKind[] = ["image", "document", "web"];
                  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                  event.preventDefault();
                  const current = kinds.indexOf(kind);
                  const next = event.key === "Home"
                    ? kinds[0]
                    : event.key === "End"
                      ? kinds[kinds.length - 1]
                      : kinds[(current + (event.key === "ArrowRight" ? 1 : -1) + kinds.length) % kinds.length];
                  chooseSourceKind(next);
                  requestAnimationFrame(() => document.getElementById(`knowledge-source-${next}-tab`)?.focus());
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <div
            id={`knowledge-source-${sourceKind}-panel`}
            className="knowledge-source-panel"
            role="tabpanel"
            aria-labelledby={`knowledge-source-${sourceKind}-tab`}
          >
            {sourceKind === "web" ? (
              <label><span>网页 URL</span><input autoFocus type="url" value={source} disabled={busy} onChange={(event) => setSource(event.target.value)} placeholder="https://example.com/article" /></label>
            ) : (
              <>
                <input
                  ref={fileInputRef}
                  className="knowledge-upload-input"
                  type="file"
                  aria-label="选择知识文件"
                  accept={sourceKind === "image" ? IMAGE_ACCEPT : DOCUMENT_ACCEPT}
                  disabled={busy}
                  onChange={(event) => {
                    chooseFile(event.currentTarget.files?.[0] ?? null);
                    event.currentTarget.value = "";
                  }}
                />
                <button
                  type="button"
                  className={`knowledge-upload-dropzone${dragging ? " is-dragging" : ""}${file ? " is-ready" : ""}`}
                  disabled={busy}
                  onClick={() => fileInputRef.current?.click()}
                  onDragEnter={(event) => {
                    event.preventDefault();
                    if (busy) return;
                    dragDepth.current += 1;
                    setDragging(true);
                  }}
                  onDragOver={(event) => {
                    event.preventDefault();
                    if (!busy) event.dataTransfer.dropEffect = "copy";
                  }}
                  onDragLeave={(event) => {
                    event.preventDefault();
                    dragDepth.current = Math.max(0, dragDepth.current - 1);
                    if (dragDepth.current === 0) setDragging(false);
                  }}
                  onDrop={(event) => {
                    event.preventDefault();
                    dragDepth.current = 0;
                    setDragging(false);
                    if (!busy) chooseFile(event.dataTransfer.files?.[0] ?? null);
                  }}
                >
                  <strong>{file ? file.name : "选择文件或拖拽到这里"}</strong>
                  <span>{file
                    ? `${formatFileSize(file.size)} · 点击可重新选择`
                    : sourceKind === "image"
                      ? "支持 PNG、JPG 和 JPEG，单个文件不超过 200 MB"
                      : "支持 PDF、PPTX、DOCX、XLSX 和 TXT，单个文件不超过 200 MB"}</span>
                </button>
                <div className="knowledge-upload-status" role="status" aria-live="polite">
                  {busy ? <TextShimmer>正在上传文件并添加到知识库</TextShimmer> : null}
                </div>
              </>
            )}
          </div>
          <div className="knowledge-dialog__fields">
            <label><span>名称（可选）</span><input value={name} disabled={busy} maxLength={256} onChange={(event) => setName(event.target.value)} /></label>
            <label><span>类型（可选）</span><input value={documentType} disabled={busy} maxLength={64} onChange={(event) => setDocumentType(event.target.value)} placeholder={sourceKind === "web" ? "html" : "pdf、docx、png"} /></label>
          </div>
          <label><span>Metadata（JSON）</span><textarea className="is-code" value={metadata} disabled={busy} onChange={(event) => setMetadata(event.target.value)} spellCheck={false} /></label>
          <FormError message={error} />
        </div>
        <footer className="knowledge-dialog__actions">
          <button type="button" onClick={onClose} disabled={busy}>取消</button>
          <button type="submit" className="is-primary" disabled={busy || (sourceKind === "web" ? !source.trim() : !file)}>{busy ? (sourceKind === "web" ? "添加中" : "上传中") : (sourceKind === "web" ? "添加网页" : "上传文件")}</button>
        </footer>
      </form>
    </KnowledgeDialog>
  );
}

function EditKnowledgeDocumentDialog({ base, item, onClose, onUpdated }: { base: KnowledgeBaseItem; item: KnowledgeDocumentItem; onClose: () => void; onUpdated: (item: KnowledgeDocumentItem) => void }) {
  const [metadata, setMetadata] = useState(() => JSON.stringify(item.metadata ?? {}, null, 2));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    let parsed: Record<string, unknown>;
    try {
      parsed = parseMetadata(metadata);
    } catch (reason) {
      setError(formatKnowledgeError(reason, "Metadata 格式错误"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      onUpdated(await updateKnowledgeDocument(base.id, item.id, base.region, { metadata: parsed }));
    } catch (reason) {
      setError(formatKnowledgeError(reason, "更新知识失败"));
    } finally {
      setBusy(false);
    }
  };
  return (
    <KnowledgeDialog title="编辑知识 Metadata" onClose={onClose} busy={busy}>
      <form onSubmit={(event) => void submit(event)}>
        <div className="knowledge-dialog__body">
          <label><span>知识</span><input value={item.name || item.id} disabled /></label>
          <label><span>Metadata（JSON）</span><textarea autoFocus className="is-code knowledge-metadata-editor" value={metadata} onChange={(event) => setMetadata(event.target.value)} spellCheck={false} /></label>
          <FormError message={error} />
        </div>
        <footer className="knowledge-dialog__actions">
          <button type="button" onClick={onClose} disabled={busy}>取消</button>
          <button type="submit" className="is-primary" disabled={busy}>{busy ? "保存中" : "保存"}</button>
        </footer>
      </form>
    </KnowledgeDialog>
  );
}

type KnowledgeAttachmentKind = "image" | "audio" | "video" | "pdf" | "file" | "none";

interface KnowledgePreviewTable {
  columns: string[];
  rows: string[][];
}

const IMAGE_PREVIEW_EXTENSIONS = new Set(["avif", "bmp", "gif", "jpeg", "jpg", "png", "svg", "webp"]);
const AUDIO_PREVIEW_EXTENSIONS = new Set(["aac", "flac", "m4a", "mp3", "ogg", "wav", "webm"]);
const VIDEO_PREVIEW_EXTENSIONS = new Set(["m4v", "mov", "mp4", "mpeg", "mpg", "ogg", "webm"]);
const PDF_PREVIEW_EXTENSIONS = new Set(["pdf"]);
const DOCUMENT_PREVIEW_EXTENSIONS = new Set(["doc", "docx", "ppt", "pptx", "xls", "xlsx"]);
const PROCESSING_DOCUMENT_STATUSES = new Set(["creating", "indexing", "pending", "processing", "queued", "submitted"]);
const FAILED_DOCUMENT_STATUSES = new Set(["error", "failed", "unavailable"]);

function previewRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function previewValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (["string", "number", "boolean"].includes(typeof value)) return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function knowledgePreviewTable(value: unknown): KnowledgePreviewTable | null {
  if (Array.isArray(value)) {
    if (value.length === 0) return null;
    const records = value.map(previewRecord);
    if (records.some((record) => Object.keys(record).length > 0)) {
      const columns = [...new Set(records.flatMap((record) => Object.keys(record)))];
      return {
        columns,
        rows: records.map((record) => columns.map((column) => previewValue(record[column]))),
      };
    }
    return { columns: ["值"], rows: value.map((item) => [previewValue(item)]) };
  }
  const record = previewRecord(value);
  const entries = Object.entries(record);
  if (entries.length === 0) return null;
  if (entries.every(([, item]) => Array.isArray(item))) {
    const columns = entries.map(([key]) => key);
    const rowCount = Math.max(...entries.map(([, item]) => (item as unknown[]).length));
    return {
      columns,
      rows: Array.from({ length: rowCount }, (_, index) => (
        entries.map(([, item]) => previewValue((item as unknown[])[index]))
      )),
    };
  }
  return {
    columns: ["字段", "值"],
    rows: entries.map(([key, item]) => [key, previewValue(item)]),
  };
}

function safeKnowledgePreviewUrl(value: string): string {
  const candidate = value.trim();
  if (!candidate || candidate.startsWith("//")) return "";
  if (candidate.startsWith("/")) return candidate;
  try {
    const url = new URL(candidate);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function safeKnowledgeSourceUrl(value: string): string {
  const candidate = safeKnowledgePreviewUrl(value);
  return candidate.startsWith("http://") || candidate.startsWith("https://")
    ? candidate
    : "";
}

function knowledgeAttachmentKind(chunk: KnowledgeDocumentPreviewChunk): KnowledgeAttachmentKind {
  const type = chunk.attachmentType.trim().toLocaleLowerCase();
  if (type === "image" || type === "doc-image" || type.startsWith("image/")) return "image";
  if (type === "audio" || type.startsWith("audio/")) return "audio";
  if (type === "video" || type.startsWith("video/")) return "video";
  if (type === "pdf" || type === "application/pdf") return "pdf";
  const cleanUrl = chunk.attachmentUrl.split(/[?#]/, 1)[0];
  const extension = cleanUrl.includes(".") ? cleanUrl.split(".").pop()?.toLocaleLowerCase() ?? "" : "";
  if (IMAGE_PREVIEW_EXTENSIONS.has(extension)) return "image";
  if (AUDIO_PREVIEW_EXTENSIONS.has(extension)) return "audio";
  if (VIDEO_PREVIEW_EXTENSIONS.has(extension)) return "video";
  if (PDF_PREVIEW_EXTENSIONS.has(extension)) return "pdf";
  if (type || extension) return "file";
  return "none";
}

function knowledgePreviewEmptyCopy(document: KnowledgeDocumentItem): { title: string; detail: string } {
  const status = document.status.trim().toLocaleLowerCase();
  if (PROCESSING_DOCUMENT_STATUSES.has(status)) {
    return {
      title: "数据正在处理中",
      detail: "知识库完成解析后即可预览，请稍后重新加载。",
    };
  }
  if (FAILED_DOCUMENT_STATUSES.has(status)) {
    return {
      title: "数据解析失败",
      detail: "请检查源文件或网页地址后重新添加，也可以重新加载最新状态。",
    };
  }
  const format = knowledgeDocumentFormat(document).toLocaleLowerCase();
  if (format === "pdf" || DOCUMENT_PREVIEW_EXTENSIONS.has(format)) {
    return {
      title: "暂时没有可预览的解析内容",
      detail: "此类文件会在知识库完成解析后显示文本、表格或页面图片。",
    };
  }
  if (
    IMAGE_PREVIEW_EXTENSIONS.has(format)
    || AUDIO_PREVIEW_EXTENSIONS.has(format)
    || VIDEO_PREVIEW_EXTENSIONS.has(format)
  ) {
    return {
      title: "暂时没有可预览的媒体内容",
      detail: "知识库尚未返回可访问的媒体预览，请稍后重新加载。",
    };
  }
  return {
    title: "暂无可预览的数据内容",
    detail: "知识库尚未返回解析结果，请稍后重新加载。",
  };
}

function KnowledgeChunkAttachment({ chunk }: { chunk: KnowledgeDocumentPreviewChunk }) {
  const [failed, setFailed] = useState(false);
  const source = safeKnowledgePreviewUrl(chunk.attachmentUrl);
  const kind = knowledgeAttachmentKind(chunk);
  if (!source || kind === "none") return null;
  if (failed) {
    return <div className="knowledge-preview__attachment-error">附件无法预览，请稍后重试。</div>;
  }
  if (kind === "image") {
    return <img className="knowledge-preview__image" src={source} alt={chunk.title || "知识数据图片"} loading="lazy" onError={() => setFailed(true)} />;
  }
  if (kind === "audio") {
    return (
      <audio className="knowledge-preview__audio" src={source} controls preload="metadata" onError={() => setFailed(true)}>
        当前浏览器不支持音频预览。
      </audio>
    );
  }
  if (kind === "video") return (
    <video className="knowledge-preview__video" src={source} controls playsInline preload="metadata" onError={() => setFailed(true)}>
      当前浏览器不支持视频预览。
    </video>
  );
  if (kind === "pdf") {
    return (
      <div className="knowledge-preview__pdf">
        <iframe
          src={source}
          title={chunk.title ? `${chunk.title} PDF 预览` : "PDF 预览"}
          sandbox=""
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
        />
        <a href={source} target="_blank" rel="noopener noreferrer">无法显示时，在新窗口打开 PDF</a>
      </div>
    );
  }
  return (
    <div className="knowledge-preview__file-fallback">
      <p>当前格式暂不支持直接在线预览，已优先显示解析后的内容。</p>
      <a href={source} target="_blank" rel="noopener noreferrer">打开原文件</a>
    </div>
  );
}

function KnowledgeDocumentPreviewDialog({
  base,
  item,
  onClose,
}: {
  base: KnowledgeBaseItem;
  item: KnowledgeDocumentItem;
  onClose: () => void;
}) {
  const [chunks, setChunks] = useState<KnowledgeDocumentPreviewChunk[]>([]);
  const [document, setDocument] = useState(item);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState("");
  const requestRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const loadPreview = useCallback(async (offset = 0) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const request = requestRef.current + 1;
    requestRef.current = request;
    offset > 0 ? setLoadingMore(true) : setLoading(true);
    setError("");
    if (offset === 0) {
      setChunks([]);
      setHasMore(false);
    }
    try {
      const page = await previewKnowledgeDocument(base.id, item.id, {
        region: base.region,
        offset,
        signal: controller.signal,
      });
      if (requestRef.current !== request) return;
      setDocument(page.document.id ? page.document : item);
      setChunks((current) => offset > 0 ? [...current, ...page.chunks] : page.chunks);
      setHasMore(page.hasMore);
    } catch (reason) {
      if (!isAbortError(reason) && requestRef.current === request) {
        setError(formatKnowledgeError(reason, "加载数据预览失败"));
      }
    } finally {
      if (requestRef.current === request) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, [base.id, base.region, item]);

  useEffect(() => {
    void loadPreview();
    return () => {
      abortRef.current?.abort();
      requestRef.current += 1;
    };
  }, [loadPreview]);

  const sourceUrl = safeKnowledgeSourceUrl(document.url || item.url);
  const emptyCopy = knowledgePreviewEmptyCopy(document);

  return (
    <KnowledgeDialog title={item.name || item.id} onClose={onClose} className="knowledge-dialog--preview">
      <div className="knowledge-preview">
        {document.sizeBytes > 0 || sourceUrl ? (
          <div className="knowledge-preview__meta">
            {document.sizeBytes > 0 ? <span>{formatFileSize(document.sizeBytes)}</span> : null}
            {sourceUrl ? <a href={sourceUrl} target="_blank" rel="noopener noreferrer">打开原网页</a> : null}
          </div>
        ) : null}
        <div className="knowledge-preview__body" aria-live="polite">
          {loading ? (
            <div className="knowledge-preview__state" role="status">
              <TextShimmer as="span" duration={2.4}>正在加载数据预览</TextShimmer>
            </div>
          ) : error && chunks.length === 0 ? (
            <div className="knowledge-preview__state is-error" role="alert">
              <p>{error}</p>
              <button type="button" onClick={() => void loadPreview()}>重试</button>
            </div>
          ) : chunks.length === 0 ? (
            <div className="knowledge-preview__state">
              <p>{emptyCopy.title}</p>
              <span>{sourceUrl ? "您可以打开原网页查看来源内容。" : emptyCopy.detail}</span>
              <button type="button" onClick={() => void loadPreview()}>重新加载</button>
            </div>
          ) : (
            <div className="knowledge-preview__chunks">
              {chunks.map((chunk, index) => {
                const table = knowledgePreviewTable(chunk.tableFields);
                const key = chunk.id || `${index}:${chunk.title}`;
                return (
                  <article className="knowledge-preview__chunk" key={key}>
                    <header>
                      <h3>{chunk.title || `片段 ${index + 1}`}</h3>
                    </header>
                    {chunk.content ? <p className="knowledge-preview__content">{chunk.content}</p> : null}
                    {table ? (
                      <div className="knowledge-preview__table-wrap">
                        <table>
                          <thead><tr>{table.columns.map((column, columnIndex) => <th scope="col" key={`${column}:${columnIndex}`}>{column}</th>)}</tr></thead>
                          <tbody>
                            {table.rows.map((row, rowIndex) => (
                              <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : null}
                    <KnowledgeChunkAttachment chunk={chunk} />
                  </article>
                );
              })}
              {error ? <div className="knowledge-preview__more-error" role="alert">{error}</div> : null}
              {hasMore ? (
                <button type="button" className="knowledge-preview__load-more" disabled={loadingMore} onClick={() => void loadPreview(chunks.length)}>
                  {loadingMore ? <TextShimmer as="span" duration={2.4}>正在加载更多</TextShimmer> : "加载更多"}
                </button>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </KnowledgeDialog>
  );
}

export function KnowledgeLibrary({
  cloudProvider,
  active = true,
  activationRevision = 0,
}: {
  cloudProvider: CloudProvider;
  active?: boolean;
  activationRevision?: number;
}) {
  const [items, setItems] = useState<KnowledgeBaseItem[]>([]);
  const [nextTokens, setNextTokens] = useState<Record<string, string>>({});
  const [regionWarnings, setRegionWarnings] = useState<string[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [documents, setDocuments] = useState<KnowledgeDocumentItem[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [documentsError, setDocumentsError] = useState("");
  const [documentsMoreError, setDocumentsMoreError] = useState("");
  const [invalidProviderKey, setInvalidProviderKey] = useState("");
  const [documentsHasMore, setDocumentsHasMore] = useState(false);
  const [createBaseOpen, setCreateBaseOpen] = useState(false);
  const [editBaseOpen, setEditBaseOpen] = useState(false);
  const [createDocumentBase, setCreateDocumentBase] = useState<KnowledgeBaseItem | null>(null);
  const [previewDocument, setPreviewDocument] = useState<KnowledgeDocumentItem | null>(null);
  const [editDocument, setEditDocument] = useState<KnowledgeDocumentItem | null>(null);
  const [deleteBaseTarget, setDeleteBaseTarget] = useState<KnowledgeBaseItem | null>(null);
  const [deleteDocumentTarget, setDeleteDocumentTarget] = useState<KnowledgeDocumentItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const basesRequest = useRef(0);
  const documentsRequest = useRef(0);
  const documentsRef = useRef<KnowledgeDocumentItem[]>([]);
  const documentsLoadingRef = useRef(false);
  const documentsHasMoreRef = useRef(false);
  const basesAbort = useRef<AbortController | null>(null);
  const documentsAbort = useRef<AbortController | null>(null);
  const nextTokensRef = useRef<Record<string, string>>({});
  const basesLoadingRef = useRef(false);
  const resultsRef = useRef<HTMLDivElement>(null);
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const documentsScrollRef = useRef<HTMLDivElement>(null);
  const documentsLoadMoreRef = useRef<HTMLDivElement>(null);

  const regions = useMemo(
    () => cloudRegionOptions(cloudProvider).map((option) => option.value),
    [cloudProvider],
  );
  const baseKey = useCallback(
    (item: KnowledgeBaseItem) => `${item.region}\u0000${item.id}`,
    [],
  );
  const selected = items.find((item) => baseKey(item) === selectedKey) ?? null;
  const providerAssociationInvalid = Boolean(
    selected && invalidProviderKey === baseKey(selected),
  );
  const filteredItems = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return items;
    return items.filter((item) => [item.name, item.description, item.ownerLabel, item.providerKnowledgeId].some((value) => value.toLocaleLowerCase().includes(normalized)));
  }, [items, query]);

  useEffect(() => {
    setPreviewDocument(null);
  }, [selected?.id, selected?.region]);

  const loadBases = useCallback(async (append = false) => {
    if (append && (
      basesLoadingRef.current
      || Object.keys(nextTokensRef.current).length === 0
    )) return;
    basesAbort.current?.abort();
    const controller = new AbortController();
    basesAbort.current = controller;
    const request = basesRequest.current + 1;
    basesRequest.current = request;
    basesLoadingRef.current = true;
    append ? setLoadingMore(true) : setLoading(true);
    setError("");
    if (!append) setRegionWarnings([]);
    try {
      const page = await listKnowledgeBasesAcrossRegions({
        regions,
        nextTokens: append ? nextTokensRef.current : undefined,
        signal: controller.signal,
      });
      if (basesRequest.current !== request) return;
      setItems((current) => append
        ? [...current, ...page.items.filter((item) => !current.some((existing) => baseKey(existing) === baseKey(item)))]
        : page.items);
      nextTokensRef.current = page.nextTokens;
      setNextTokens(page.nextTokens);
      const warnings = page.failures.map(({ region, error: reason }) => (
        `${formatCloudRegion(region, cloudProvider)}：${formatKnowledgeError(reason, "加载失败")}`
      ));
      setRegionWarnings((current) => append
        ? [...new Set([...current, ...warnings])]
        : warnings);
      if (!append) {
        setSelectedKey((current) => page.items.some((item) => baseKey(item) === current) ? current : "");
      }
    } catch (reason) {
      if (isAbortError(reason)) return;
      if (basesRequest.current === request) {
        if (append) {
          setRegionWarnings((current) => [
            ...new Set([...current, formatKnowledgeError(reason, "加载更多知识库失败")]),
          ]);
        } else {
          setError(formatKnowledgeError(reason, "加载知识库失败"));
        }
      }
    } finally {
      if (basesRequest.current === request) {
        basesLoadingRef.current = false;
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, [baseKey, cloudProvider, regions]);

  const loadDocuments = useCallback(async (base: KnowledgeBaseItem, append = false) => {
    if (append && documentsLoadingRef.current) return;
    documentsAbort.current?.abort();
    const controller = new AbortController();
    documentsAbort.current = controller;
    const request = documentsRequest.current + 1;
    documentsRequest.current = request;
    if (!append) {
      documentsRef.current = [];
      documentsHasMoreRef.current = false;
      setDocuments([]);
      setDocumentsHasMore(false);
      setDocumentsMoreError("");
    }
    documentsLoadingRef.current = true;
    setDocumentsLoading(true);
    append ? setDocumentsMoreError("") : setDocumentsError("");
    try {
      const page = await listKnowledgeDocuments(base.id, {
        region: base.region,
        offset: append ? documentsRef.current.length : 0,
        signal: controller.signal,
      });
      if (documentsRequest.current !== request) return;
      setInvalidProviderKey((current) => current === baseKey(base) ? "" : current);
      const current = documentsRef.current;
      const next = append
        ? [...current, ...page.items.filter((item) => (
          !item.id || !current.some((existing) => existing.id === item.id)
        ))]
        : page.items;
      const hasMore = page.hasMore && (!append || next.length > current.length);
      documentsRef.current = next;
      documentsHasMoreRef.current = hasMore;
      setDocuments(next);
      setDocumentsHasMore(hasMore);
    } catch (reason) {
      if (isAbortError(reason)) return;
      if (documentsRequest.current === request) {
        const associationInvalid = reason instanceof KnowledgeRequestError
          && reason.errorCode === KNOWLEDGE_PROVIDER_ASSOCIATION_INVALID;
        if (associationInvalid) {
          setInvalidProviderKey(baseKey(base));
          setCreateDocumentBase((current) => (
            current && baseKey(current) === baseKey(base) ? null : current
          ));
        }
        if (append) {
          setDocumentsMoreError(formatKnowledgeError(reason, "加载更多数据失败"));
        } else {
          setDocumentsError(formatKnowledgeError(reason, "加载数据失败"));
        }
      }
    } finally {
      if (documentsRequest.current === request) {
        documentsLoadingRef.current = false;
        setDocumentsLoading(false);
      }
    }
  }, [baseKey]);

  useEffect(() => {
    basesAbort.current?.abort();
    basesRequest.current += 1;
    basesLoadingRef.current = false;
    nextTokensRef.current = {};
    setItems([]);
    setNextTokens({});
    setRegionWarnings([]);
    setSelectedKey("");
    setInvalidProviderKey("");
    setError("");
    setLoading(true);
  }, [cloudProvider]);

  useEffect(() => {
    if (!active) return;
    void loadBases();
    return () => {
      basesAbort.current?.abort();
      basesRequest.current += 1;
      basesLoadingRef.current = false;
    };
  }, [active, activationRevision, loadBases]);

  useEffect(() => {
    if (!active) {
      documentsAbort.current?.abort();
      documentsRequest.current += 1;
      documentsLoadingRef.current = false;
      return;
    }
    if (!selected) {
      documentsAbort.current?.abort();
      documentsRequest.current += 1;
      documentsRef.current = [];
      documentsLoadingRef.current = false;
      documentsHasMoreRef.current = false;
      setDocuments([]);
      setDocumentsHasMore(false);
      setDocumentsMoreError("");
      return;
    }
    void loadDocuments(selected);
    return () => {
      documentsAbort.current?.abort();
      documentsRequest.current += 1;
      documentsLoadingRef.current = false;
    };
  }, [active, activationRevision, selected?.id, selected?.region]);

  const canLoadMoreBases = active
    && !selected
    && !query.trim()
    && !loading
    && !loadingMore
    && !error
    && Object.keys(nextTokens).length > 0;

  useEffect(() => {
    const target = loadMoreRef.current;
    const root = resultsRef.current;
    if (!target || !root || !canLoadMoreBases) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) void loadBases(true);
      },
      { root, rootMargin: "240px 0px", threshold: 0.01 },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [canLoadMoreBases, loadBases]);

  const handleResultsScroll = () => {
    const results = resultsRef.current;
    if (!results || !canLoadMoreBases) return;
    if (results.scrollHeight - results.scrollTop - results.clientHeight <= 240) {
      void loadBases(true);
    }
  };

  const canLoadMoreDocuments = Boolean(
    selected
    && documents.length > 0
    && documentsHasMore
    && !documentsLoading
    && !documentsMoreError,
  );

  useEffect(() => {
    const target = documentsLoadMoreRef.current;
    const root = documentsScrollRef.current;
    if (!selected || !target || !root || !canLoadMoreDocuments) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) void loadDocuments(selected, true);
      },
      { root: documentsScrollRef.current, rootMargin: "240px 0px", threshold: 0.01 },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [canLoadMoreDocuments, loadDocuments, selected?.id, selected?.region]);

  const handleDocumentsScroll = () => {
    const scroller = documentsScrollRef.current;
    if (
      !selected
      || !scroller
      || !documentsHasMoreRef.current
      || documentsLoadingRef.current
      || documentsMoreError
    ) return;
    const { scrollHeight, scrollTop, clientHeight } = scroller;
    if (scrollHeight - scrollTop - clientHeight <= 240) {
      void loadDocuments(selected, true);
    }
  };

  const replaceBase = (updated: KnowledgeBaseItem) => {
    setItems((current) => current.map((item) => baseKey(item) === baseKey(updated) ? updated : item));
  };

  const confirmDeleteBase = async () => {
    if (!deleteBaseTarget) return;
    setDeleting(true);
    try {
      await deleteKnowledgeBase(deleteBaseTarget.id, deleteBaseTarget.region);
      setItems((current) => current.filter((item) => baseKey(item) !== baseKey(deleteBaseTarget)));
      setInvalidProviderKey((current) => current === baseKey(deleteBaseTarget) ? "" : current);
      if (selectedKey === baseKey(deleteBaseTarget)) {
        setSelectedKey("");
      }
      setDeleteBaseTarget(null);
    } catch (reason) {
      setError(formatKnowledgeError(reason, "删除知识库失败"));
      setDeleteBaseTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  const confirmDeleteDocument = async () => {
    if (!selected || !deleteDocumentTarget) return;
    setDeleting(true);
    try {
      await deleteKnowledgeDocument(selected.id, deleteDocumentTarget.id, selected.region);
      const next = documentsRef.current.filter((item) => item.id !== deleteDocumentTarget.id);
      documentsRef.current = next;
      setDocuments(next);
      setDeleteDocumentTarget(null);
    } catch (reason) {
      setDocumentsError(formatKnowledgeError(reason, "删除知识失败"));
      setDeleteDocumentTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <section className={`knowledge-library${selected ? " is-detail" : " my-agents-page"}`} aria-label="知识库">
      {selected ? (
        <div className="knowledge-library__detail">
          <header className="knowledge-detail-head">
            <div className="knowledge-detail-head__title">
              <button type="button" className="knowledge-back-button" onClick={() => setSelectedKey("")} aria-label="返回知识库列表">
                <BackIcon />
              </button>
              <div><h2 title={selected.name}>{selected.name}</h2><p>{selected.description || "暂无描述"}</p></div>
            </div>
            {selected.canManage && (
              <div className="knowledge-detail-head__actions">
                <button type="button" onClick={() => setEditBaseOpen(true)}>编辑</button>
                <button type="button" className="is-danger" onClick={() => setDeleteBaseTarget(selected)}>删除</button>
              </div>
            )}
          </header>
          <dl className="knowledge-detail-meta">
            <div><dt>Provider</dt><dd>{selected.providerType || "-"}</dd></div>
            <div><dt>Knowledge ID</dt><dd className="knowledge-keyboard-reveal" tabIndex={0} title={selected.providerKnowledgeId}>{selected.providerKnowledgeId || "-"}</dd></div>
            <div><dt>项目</dt><dd>{selected.projectName || "default"}</dd></div>
            {selected.ownerLabel && <div><dt>创建者</dt><dd>{selected.ownerLabel}</dd></div>}
            <div><dt>更新时间</dt><dd>{formatDate(selected.updatedAt) || "-"}</dd></div>
          </dl>
          <section className="knowledge-documents">
            <header className="knowledge-documents__head">
              <h3>数据</h3>
              {selected.canManage && <button type="button" className="knowledge-primary-button" disabled={providerAssociationInvalid} title={providerAssociationInvalid ? "底层 Provider 知识库已不存在" : undefined} onClick={() => setCreateDocumentBase(selected)}><PlusIcon /><span>{providerAssociationInvalid ? "关联已失效" : "添加数据"}</span></button>}
            </header>
            <div className={`knowledge-documents__body${documents.length > 0 ? " is-table" : ""}`} aria-live="polite">
              {documentsLoading && documents.length === 0 ? (
                <div className="my-agent-initial-loading" role="status" aria-live="polite">
                  <span className="my-agent-loading-mark" aria-hidden="true" />
                  <span>正在加载数据</span>
                </div>
              ) : documentsError && documents.length === 0 ? (
                <div className="knowledge-library__state is-error" role="alert">
                  <p>{documentsError}</p>
                  {providerAssociationInvalid && selected.canManage
                    ? <button type="button" onClick={() => setDeleteBaseTarget(selected)}>删除失效关联</button>
                    : <button type="button" onClick={() => void loadDocuments(selected)}>重试</button>}
                </div>
              ) : documents.length === 0 ? (
                <div className="knowledge-library__state"><DocumentIcon /><p>这个知识库还没有数据</p>{selected.canManage && <button type="button" onClick={() => setCreateDocumentBase(selected)}>添加第一项数据</button>}</div>
              ) : (
                <div
                  ref={documentsScrollRef}
                  className="knowledge-document-table-wrap"
                  aria-busy={documentsLoading || undefined}
                  onScroll={handleDocumentsScroll}
                >
                  <table className="knowledge-document-table">
                    <thead>
                      <tr>
                        <th scope="col">名称</th>
                        <th scope="col">格式</th>
                        <th scope="col">大小</th>
                        <th scope="col" className="knowledge-document-table__actions-heading">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {documents.map((item) => (
                        <tr key={item.id}>
                          <td className="knowledge-document-table__name" title={item.name || item.id}>{item.name || item.id}</td>
                          <td>{knowledgeDocumentFormat(item)}</td>
                          <td>{formatFileSize(item.sizeBytes)}</td>
                          <td>
                            <div className="knowledge-document-table__actions">
                              <Tooltip content="预览" compact>
                                <Button
                                  type="button"
                                  className="knowledge-document-action-button"
                                  color="secondary"
                                  variant="ghost"
                                  size="sm"
                                  iconSize="sm"
                                  uniform
                                  aria-label={`预览 ${item.name || item.id}`}
                                  onClick={() => setPreviewDocument(item)}
                                >
                                  <Eye aria-hidden="true" />
                                </Button>
                              </Tooltip>
                              {selected.canManage ? (
                                <>
                                  <Tooltip content="编辑" compact>
                                    <Button
                                      type="button"
                                      className="knowledge-document-action-button"
                                      color="secondary"
                                      variant="ghost"
                                      size="sm"
                                      iconSize="sm"
                                      uniform
                                      aria-label={`编辑 ${item.name || item.id}`}
                                      onClick={() => setEditDocument(item)}
                                    >
                                      <Edit aria-hidden="true" />
                                    </Button>
                                  </Tooltip>
                                  <Tooltip content="删除" compact>
                                    <Button
                                      type="button"
                                      className="knowledge-document-action-button"
                                      color="danger"
                                      variant="ghost"
                                      size="sm"
                                      iconSize="sm"
                                      uniform
                                      aria-label={`删除 ${item.name || item.id}`}
                                      onClick={() => setDeleteDocumentTarget(item)}
                                    >
                                      <Delete aria-hidden="true" />
                                    </Button>
                                  </Tooltip>
                                </>
                              ) : null}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {documentsLoading ? (
                    <div className="knowledge-document-pagination" role="status" aria-live="polite">
                      <span className="my-agent-loading-mark" aria-hidden="true" />
                      <span>正在加载更多数据</span>
                    </div>
                  ) : documentsMoreError ? (
                    <div className="knowledge-document-pagination is-error" role="alert">
                      <span>{documentsMoreError}</span>
                      <button type="button" onClick={() => void loadDocuments(selected, true)}>重试加载</button>
                    </div>
                  ) : documentsHasMore ? (
                    <div
                      ref={documentsLoadMoreRef}
                      className="knowledge-document-pagination"
                      role="status"
                      aria-live="polite"
                    >
                      继续下滑加载更多
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          </section>
        </div>
      ) : (
        <>
          <div className="knowledge-library__toolbar my-agent-type-bar library-resource-toolbar">
            <div className="knowledge-library__toolbar-actions library-resource-toolbar__controls">
              <button type="button" className="my-agent-create-primary" onClick={() => setCreateBaseOpen(true)}>
                <PlusIcon /><span>新建知识库</span>
              </button>
            </div>
            <label className="knowledge-library__search my-agent-search">
              <SearchIcon />
              <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索知识库" aria-label="搜索知识库" />
            </label>
          </div>
          <div
            ref={resultsRef}
            className="knowledge-library__results my-agent-results"
            aria-live="polite"
            onScroll={handleResultsScroll}
          >
            {regionWarnings.length > 0 && !loading && (
              <div className="knowledge-region-warning" role="status">
                <span>部分知识库暂时无法加载，已展示其余可用内容。</span>
                <button type="button" onClick={() => void loadBases()}>重试</button>
              </div>
            )}
            {loading && items.length === 0 ? (
              <div className="my-agent-initial-loading" role="status" aria-live="polite">
                <span className="my-agent-loading-mark" aria-hidden="true" />
                <span>正在加载知识库</span>
              </div>
            ) : error ? (
              <div className="knowledge-library__state is-error" role="alert"><p>{error}</p><button type="button" onClick={() => void loadBases()}>重试</button></div>
            ) : filteredItems.length === 0 ? (
              <div className="knowledge-library__state"><KnowledgeIcon /><p>{query.trim() ? "没有匹配的知识库" : "您还没有任何知识库"}</p></div>
            ) : (
              <div className="knowledge-library__grid my-agent-grid">
                {filteredItems.map((item) => (
                  <LibraryResourceCard
                    key={baseKey(item)}
                    className="knowledge-card"
                    title={item.name}
                    status={<span className={`knowledge-status is-${item.status.toLowerCase()}`}>{statusLabel(item.status)}</span>}
                    description={item.description || "暂无描述"}
                    metadata={[
                      { label: "创建者", value: item.ownerLabel || "—", title: item.ownerLabel || "—" },
                      { label: "项目", value: item.projectName || "default", title: item.projectName || "default" },
                    ]}
                    secondaryAction={{
                      label: invalidProviderKey === baseKey(item) ? "关联已失效" : "添加数据",
                      disabled: !item.canManage || invalidProviderKey === baseKey(item),
                      title: !item.canManage ? "您没有管理此知识库的权限" : invalidProviderKey === baseKey(item) ? "底层 Provider 知识库已不存在" : undefined,
                      onClick: () => setCreateDocumentBase(item),
                    }}
                    primaryAction={{ label: "查看详情", onClick: () => setSelectedKey(baseKey(item)) }}
                    menuLabel={`更多知识库操作：${item.name}`}
                    menuAriaLabel={`${item.name}知识库操作`}
                    menuActions={[
                      {
                        label: "编辑知识库",
                        disabled: !item.canManage,
                        title: !item.canManage ? "您没有管理此知识库的权限" : undefined,
                        onClick: () => {
                          setSelectedKey(baseKey(item));
                          setEditBaseOpen(true);
                        },
                      },
                      {
                        label: "删除知识库",
                        danger: true,
                        disabled: !item.canManage || deleting,
                        title: !item.canManage ? "您没有管理此知识库的权限" : undefined,
                        onClick: () => setDeleteBaseTarget(item),
                      },
                    ]}
                  />
                ))}
              </div>
            )}
            {canLoadMoreBases || loadingMore ? (
              <div
                ref={loadMoreRef}
                className="my-agent-load-more"
                role="status"
                aria-live="polite"
              >
                {loadingMore ? (
                  <>
                    <span className="my-agent-loading-mark" aria-hidden="true" />
                    <span>正在加载更多知识库</span>
                  </>
                ) : canLoadMoreBases ? <span>继续下滑加载更多</span> : null}
              </div>
            ) : null}
          </div>
        </>
      )}

      {createBaseOpen && <CreateKnowledgeBaseDialog onClose={() => setCreateBaseOpen(false)} onCreated={(item) => { setItems((current) => [item, ...current]); setSelectedKey(baseKey(item)); setCreateBaseOpen(false); }} />}
      {selected && editBaseOpen && <EditKnowledgeBaseDialog item={selected} onClose={() => setEditBaseOpen(false)} onUpdated={(item) => { replaceBase(item); setEditBaseOpen(false); }} />}
      {selected && previewDocument && <KnowledgeDocumentPreviewDialog base={selected} item={previewDocument} onClose={() => setPreviewDocument(null)} />}
      {createDocumentBase && <CreateKnowledgeDocumentDialog base={createDocumentBase} onClose={() => setCreateDocumentBase(null)} onAssociationInvalid={(reason) => {
        setInvalidProviderKey(baseKey(createDocumentBase));
        if (selected && baseKey(selected) === baseKey(createDocumentBase)) {
          setDocumentsError(formatKnowledgeError(reason, "知识库关联已失效"));
        }
        setCreateDocumentBase(null);
      }} onCreated={() => {
        if (selected && baseKey(selected) === baseKey(createDocumentBase)) void loadDocuments(selected);
        setCreateDocumentBase(null);
      }} />}
      {selected && editDocument && <EditKnowledgeDocumentDialog base={selected} item={editDocument} onClose={() => setEditDocument(null)} onUpdated={(item) => { const next = documentsRef.current.map((candidate) => candidate.id === item.id ? item : candidate); documentsRef.current = next; setDocuments(next); setEditDocument(null); }} />}
      {deleteBaseTarget && <StudioConfirmDialog title="删除知识库？" description={`将删除 ${deleteBaseTarget.name} 的 AgentKit 关联；如果它由 Studio 创建，也会同时删除 Provider 资源。此操作无法撤销。`} confirmLabel={deleting ? "删除中" : "删除"} variant="danger" busy={deleting} onCancel={() => setDeleteBaseTarget(null)} onConfirm={() => void confirmDeleteBase()} />}
      {deleteDocumentTarget && <StudioConfirmDialog title="删除知识？" description={`将从 Provider 知识库中删除 ${deleteDocumentTarget.name || deleteDocumentTarget.id}，此操作无法撤销。`} confirmLabel={deleting ? "删除中" : "删除"} variant="danger" busy={deleting} onCancel={() => setDeleteDocumentTarget(null)} onConfirm={() => void confirmDeleteDocument()} />}
    </section>
  );
}
