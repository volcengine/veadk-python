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
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import {
  formatCloudRegion,
  type CloudRegion,
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
  previewWebKnowledgeDocument,
  uploadKnowledgeDocument,
  updateKnowledgeBase,
  updateKnowledgeDocument,
  type CloudProvider,
  type CreateKnowledgeBaseInput,
  type CreateKnowledgeDocumentInput,
  type KnowledgeBaseItem,
  type KnowledgeDocumentItem,
  type KnowledgeDocumentPreviewChunk,
  type KnowledgeWebPreview,
} from "../adk/knowledge";
import { StudioConfirmDialog } from "./StudioConfirmDialog";
import { LibraryResourceCard } from "./LibraryResourceCard";
import { Markdown } from "./Markdown";
import {
  ResourceCreateCard,
  ResourceDataTable,
  ResourceDetailLayout,
  ResourceDetailSummary,
  ResourceGrid,
  ResourceLoadingState,
  ResourceResults,
  ResourceSearch,
  ResourceToolbar,
} from "./ResourceCollection";
import { formatResourceSource } from "./resourceMetadata";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import "./KnowledgeLibrary.css";

type KnowledgeDetailSection = "overview" | "data";

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

interface KnowledgeDialogProps {
  title: string;
  children: ReactNode;
  onClose: () => void;
  busy?: boolean;
  className?: string;
}

function KnowledgeDialog({ title, children, onClose, busy = false, className = "" }: KnowledgeDialogProps) {
  const { t } = useTranslation("ui");
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
          <button ref={closeRef} type="button" onClick={onClose} disabled={busy} aria-label={t("common.close")}>
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

function formatDate(value: string, locale: string): string {
  if (!value) return "";
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return value;
  return new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(timestamp);
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

function validateKnowledgeFile(file: File, kind: Exclude<KnowledgeSourceKind, "web">, t: TFunction<"ui">): string {
  if (file.size > MAX_KNOWLEDGE_FILE_BYTES) return t("knowledge.errors.fileTooLarge");
  if (kind === "image") {
    return IMAGE_EXTENSIONS.has(fileExtension(file.name))
      ? ""
      : t("knowledge.errors.invalidImageType");
  }
  return DOCUMENT_EXTENSIONS.has(fileExtension(file.name))
    ? ""
    : t("knowledge.errors.invalidDocumentType");
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
  region,
  onClose,
  onCreated,
}: {
  region: CloudRegion;
  onClose: () => void;
  onCreated: (item: KnowledgeBaseItem) => void;
}) {
  const { t } = useTranslation("ui");
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
      region,
    };
    try {
      onCreated(await createKnowledgeBase(input));
    } catch (reason) {
      setError(formatKnowledgeError(reason, t("knowledge.errors.createBase")));
    } finally {
      setBusy(false);
    }
  };
  return (
    <KnowledgeDialog title={t("knowledge.createBase")} onClose={onClose} busy={busy}>
      <form onSubmit={(event) => void submit(event)}>
        <div className="knowledge-dialog__body">
          <label><span>{t("common.name")}</span><input autoFocus value={name} maxLength={48} aria-invalid={nameTouched && nameInvalid || undefined} aria-describedby="knowledge-name-help" onBlur={() => setNameTouched(true)} onChange={(event) => setName(event.target.value)} /></label>
          <p id="knowledge-name-help" className={`knowledge-dialog__note${nameTouched && nameInvalid ? " is-error" : ""}`} role={nameTouched && nameInvalid ? "alert" : undefined}>{nameTouched && nameInvalid ? t("knowledge.invalidName") : t("knowledge.nameHelp")}</p>
          <label><span>{t("knowledge.optionalDescription")}</span><textarea value={description} maxLength={80} onChange={(event) => setDescription(event.target.value)} /></label>
          <FormError message={error} />
        </div>
        <footer className="knowledge-dialog__actions">
          <button type="button" onClick={onClose} disabled={busy}>{t("common.cancel")}</button>
          <button type="submit" className="is-primary" disabled={busy || !normalizedName || nameInvalid}>{busy ? t("common.creating") : t("common.create")}</button>
        </footer>
      </form>
    </KnowledgeDialog>
  );
}

function EditKnowledgeBaseDialog({ item, onClose, onUpdated }: { item: KnowledgeBaseItem; onClose: () => void; onUpdated: (item: KnowledgeBaseItem) => void }) {
  const { t } = useTranslation("ui");
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
      setError(formatKnowledgeError(reason, t("knowledge.errors.updateBase")));
    } finally {
      setBusy(false);
    }
  };
  return (
    <KnowledgeDialog title={t("knowledge.editBase")} onClose={onClose} busy={busy}>
      <form onSubmit={(event) => void submit(event)}>
        <div className="knowledge-dialog__body">
          <label><span>{t("common.name")}</span><input value={item.name} disabled /></label>
          <label><span>{t("common.description")}</span><textarea autoFocus value={description} maxLength={80} onChange={(event) => setDescription(event.target.value)} /></label>
          <p className="knowledge-dialog__note">{t("knowledge.descriptionOnly")}</p>
          <FormError message={error} />
        </div>
        <footer className="knowledge-dialog__actions">
          <button type="button" onClick={onClose} disabled={busy}>{t("common.cancel")}</button>
          <button type="submit" className="is-primary" disabled={busy}>{busy ? t("common.saving") : t("common.save")}</button>
        </footer>
      </form>
    </KnowledgeDialog>
  );
}

function parseMetadata(value: string, invalidMessage: string): Record<string, unknown> {
  if (!value.trim()) return {};
  const parsed: unknown = JSON.parse(value);
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(invalidMessage);
  }
  return parsed as Record<string, unknown>;
}

function CreateKnowledgeDocumentDialog({ base, onClose, onCreated, onAssociationInvalid }: { base: KnowledgeBaseItem; onClose: () => void; onCreated: () => void; onAssociationInvalid: (error: KnowledgeRequestError) => void }) {
  const { t } = useTranslation("ui");
  const [sourceKind, setSourceKind] = useState<KnowledgeSourceKind>("document");
  const [name, setName] = useState("");
  const [documentType, setDocumentType] = useState("");
  const [source, setSource] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [metadata, setMetadata] = useState("{}");
  const [busyAction, setBusyAction] = useState<"" | "preview" | "save" | "upload">("");
  const [error, setError] = useState("");
  const [webPreview, setWebPreview] = useState<{ preview: KnowledgeWebPreview; metadata: Record<string, unknown> } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const webUrlRef = useRef<HTMLInputElement>(null);
  const webConfirmRef = useRef<HTMLButtonElement>(null);
  const dragDepth = useRef(0);
  const busy = Boolean(busyAction);

  useEffect(() => {
    if (webPreview && !busy) webConfirmRef.current?.focus();
  }, [busy, webPreview]);

  const chooseSourceKind = (kind: KnowledgeSourceKind) => {
    if (busy || kind === sourceKind) return;
    setSourceKind(kind);
    setFile(null);
    setSource("");
    setName("");
    setDocumentType("");
    setError("");
    setWebPreview(null);
    setDragging(false);
    dragDepth.current = 0;
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const chooseFile = (candidate: File | null) => {
    if (!candidate || sourceKind === "web") return;
    const validationError = validateKnowledgeFile(candidate, sourceKind, t);
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
      parsedMetadata = parseMetadata(metadata, t("knowledge.errors.metadataObject"));
    } catch (reason) {
      setError(formatKnowledgeError(reason, t("knowledge.errors.metadataFormat")));
      return;
    }
    setBusyAction(sourceKind === "web" ? (webPreview ? "save" : "preview") : "upload");
    setError("");
    try {
      if (sourceKind === "web") {
        if (!webPreview) {
          const preview = await previewWebKnowledgeDocument(base.id, base.region, {
            url: source.trim(),
          });
          if (!preview.sourceMarkdown.trim()) {
            throw new Error(t("knowledge.errors.noWebPreview"));
          }
          setWebPreview({ preview, metadata: parsedMetadata });
        } else {
          const input: CreateKnowledgeDocumentInput = {
            sourceType: "url",
            metadata: webPreview.metadata,
            url: webPreview.preview.url,
            sourceTitle: webPreview.preview.name,
            sourceMarkdown: webPreview.preview.sourceMarkdown,
          };
          await createKnowledgeDocument(base.id, base.region, input);
          onCreated();
        }
      } else if (file) {
        await uploadKnowledgeDocument(base.id, base.region, {
          file,
          name: name.trim() || undefined,
          documentType: documentType.trim() || undefined,
          metadata: parsedMetadata,
        });
        onCreated();
      }
    } catch (reason) {
      if (
        reason instanceof KnowledgeRequestError
        && reason.errorCode === KNOWLEDGE_PROVIDER_ASSOCIATION_INVALID
      ) {
        onAssociationInvalid(reason);
      } else {
        setError(formatKnowledgeError(
          reason,
          sourceKind === "web"
            ? webPreview ? t("knowledge.errors.addWeb") : t("knowledge.errors.previewWeb")
            : t("knowledge.errors.uploadFile"),
        ));
      }
    } finally {
      setBusyAction("");
    }
  };

  const returnToWebForm = () => {
    if (busy) return;
    setWebPreview(null);
    setError("");
    requestAnimationFrame(() => webUrlRef.current?.focus());
  };

  return (
    <KnowledgeDialog
      title={webPreview ? t("knowledge.previewWeb") : t("knowledge.addData")}
      onClose={onClose}
      busy={busy}
      className={webPreview ? "knowledge-dialog--preview knowledge-dialog--web-confirm" : ""}
    >
      <form onSubmit={(event) => void submit(event)}>
        {webPreview ? (
          <>
            <div className="knowledge-preview knowledge-web-preview">
              <div className="knowledge-preview__meta">
                <strong title={webPreview.preview.name}>{webPreview.preview.name}</strong>
                <a href={webPreview.preview.url} target="_blank" rel="noopener noreferrer">{t("knowledge.openOriginalWeb")}</a>
              </div>
              <div className="knowledge-preview__body" aria-live="polite">
                <div className="knowledge-preview__markdown-shell">
                  <Markdown text={webPreview.preview.sourceMarkdown} allowRawHtml={false} className="knowledge-preview__markdown" />
                </div>
              </div>
              {error ? <div className="knowledge-web-preview__error"><FormError message={error} /></div> : null}
            </div>
            <footer className="knowledge-dialog__actions">
              <button type="button" className="is-back" onClick={returnToWebForm} disabled={busy}>{t("knowledge.backToEdit")}</button>
              <button type="button" onClick={onClose} disabled={busy}>{t("common.cancel")}</button>
              <button ref={webConfirmRef} type="submit" className="is-primary" disabled={busy}>{busyAction === "save" ? t("common.adding") : t("knowledge.confirmAdd")}</button>
            </footer>
          </>
        ) : (
          <>
            <div className="knowledge-dialog__body">
              <div className="knowledge-source-tabs" role="tablist" aria-label={t("knowledge.source")}>
                {([
                  ["image", t("knowledge.image")],
                  ["document", t("knowledge.documentFile")],
                  ["web", t("knowledge.webPage")],
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
                  <>
                    <label><span>{t("knowledge.webUrl")}</span><input ref={webUrlRef} autoFocus type="url" value={source} disabled={busy} onChange={(event) => { setSource(event.target.value); setError(""); }} placeholder="https://example.com/article" /></label>
                    <div className="knowledge-upload-status" role="status" aria-live="polite">
                      {busyAction === "preview" ? <TextShimmer>{t("knowledge.generatingWebPreview")}</TextShimmer> : null}
                    </div>
                  </>
                ) : (
                  <>
                    <input
                      ref={fileInputRef}
                      className="knowledge-upload-input"
                      type="file"
                      aria-label={t("knowledge.selectFile")}
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
                      <strong>{file ? file.name : t("knowledge.selectOrDropFile")}</strong>
                      <span>{file
                        ? t("knowledge.selectedFile", { size: formatFileSize(file.size) })
                        : sourceKind === "image"
                          ? t("knowledge.imageFileHelp")
                          : t("knowledge.documentFileHelp")}</span>
                    </button>
                    <div className="knowledge-upload-status" role="status" aria-live="polite">
                      {busy ? <TextShimmer>{t("knowledge.uploadingFile")}</TextShimmer> : null}
                    </div>
                  </>
                )}
              </div>
              {sourceKind !== "web" ? (
                <div className="knowledge-dialog__fields">
                  <label><span>{t("knowledge.optionalName")}</span><input value={name} disabled={busy} maxLength={256} onChange={(event) => setName(event.target.value)} /></label>
                  <label><span>{t("knowledge.optionalType")}</span><input value={documentType} disabled={busy} maxLength={64} onChange={(event) => setDocumentType(event.target.value)} placeholder="pdf, docx, png" /></label>
                </div>
              ) : null}
              <label><span>{t("knowledge.metadataJson")}</span><textarea className="is-code" value={metadata} disabled={busy} onChange={(event) => setMetadata(event.target.value)} spellCheck={false} /></label>
              <FormError message={error} />
            </div>
            <footer className="knowledge-dialog__actions">
              <button type="button" onClick={onClose} disabled={busy}>{t("common.cancel")}</button>
              <button type="submit" className="is-primary" disabled={busy || (sourceKind === "web" ? !source.trim() : !file)}>{busy ? (sourceKind === "web" ? t("common.generating") : t("common.uploading")) : (sourceKind === "web" ? t("knowledge.generatePreview") : t("knowledge.uploadFile"))}</button>
            </footer>
          </>
        )}
      </form>
    </KnowledgeDialog>
  );
}

function EditKnowledgeDocumentDialog({ base, item, onClose, onUpdated }: { base: KnowledgeBaseItem; item: KnowledgeDocumentItem; onClose: () => void; onUpdated: (item: KnowledgeDocumentItem) => void }) {
  const { t } = useTranslation("ui");
  const [metadata, setMetadata] = useState(() => JSON.stringify(item.metadata ?? {}, null, 2));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    let parsed: Record<string, unknown>;
    try {
      parsed = parseMetadata(metadata, t("knowledge.errors.metadataObject"));
    } catch (reason) {
      setError(formatKnowledgeError(reason, t("knowledge.errors.metadataFormat")));
      return;
    }
    setBusy(true);
    setError("");
    try {
      onUpdated(await updateKnowledgeDocument(base.id, item.id, base.region, { metadata: parsed }));
    } catch (reason) {
      setError(formatKnowledgeError(reason, t("knowledge.errors.updateDocument")));
    } finally {
      setBusy(false);
    }
  };
  return (
    <KnowledgeDialog title={t("knowledge.editMetadata")} onClose={onClose} busy={busy}>
      <form onSubmit={(event) => void submit(event)}>
        <div className="knowledge-dialog__body">
          <label><span>{t("knowledge.knowledge")}</span><input value={item.name || item.id} disabled /></label>
          <label><span>{t("knowledge.metadataJson")}</span><textarea autoFocus className="is-code knowledge-metadata-editor" value={metadata} onChange={(event) => setMetadata(event.target.value)} spellCheck={false} /></label>
          <FormError message={error} />
        </div>
        <footer className="knowledge-dialog__actions">
          <button type="button" onClick={onClose} disabled={busy}>{t("common.cancel")}</button>
          <button type="submit" className="is-primary" disabled={busy}>{busy ? t("common.saving") : t("common.save")}</button>
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

function knowledgePreviewTable(value: unknown, t: TFunction<"ui">): KnowledgePreviewTable | null {
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
    return { columns: [t("knowledge.value")], rows: value.map((item) => [previewValue(item)]) };
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
    columns: [t("knowledge.field"), t("knowledge.value")],
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

function knowledgePreviewEmptyCopy(document: KnowledgeDocumentItem, t: TFunction<"ui">): { title: string; detail: string } {
  const status = document.status.trim().toLocaleLowerCase();
  if (PROCESSING_DOCUMENT_STATUSES.has(status)) {
    return {
      title: t("knowledge.preview.processingTitle"),
      detail: t("knowledge.preview.processingDetail"),
    };
  }
  if (FAILED_DOCUMENT_STATUSES.has(status)) {
    return {
      title: t("knowledge.preview.failedTitle"),
      detail: t("knowledge.preview.failedDetail"),
    };
  }
  const format = knowledgeDocumentFormat(document).toLocaleLowerCase();
  if (format === "pdf" || DOCUMENT_PREVIEW_EXTENSIONS.has(format)) {
    return {
      title: t("knowledge.preview.noParsedTitle"),
      detail: t("knowledge.preview.noParsedDetail"),
    };
  }
  if (
    IMAGE_PREVIEW_EXTENSIONS.has(format)
    || AUDIO_PREVIEW_EXTENSIONS.has(format)
    || VIDEO_PREVIEW_EXTENSIONS.has(format)
  ) {
    return {
      title: t("knowledge.preview.noMediaTitle"),
      detail: t("knowledge.preview.noMediaDetail"),
    };
  }
  return {
    title: t("knowledge.preview.noDataTitle"),
    detail: t("knowledge.preview.noDataDetail"),
  };
}

function KnowledgeChunkAttachment({ chunk }: { chunk: KnowledgeDocumentPreviewChunk }) {
  const { t } = useTranslation("ui");
  const [failed, setFailed] = useState(false);
  const source = safeKnowledgePreviewUrl(chunk.attachmentUrl);
  const kind = knowledgeAttachmentKind(chunk);
  if (!source || kind === "none") return null;
  if (failed) {
    return <div className="knowledge-preview__attachment-error">{t("knowledge.preview.attachmentError")}</div>;
  }
  if (kind === "image") {
    return <img className="knowledge-preview__image" src={source} alt={chunk.title || t("knowledge.preview.imageAlt")} loading="lazy" onError={() => setFailed(true)} />;
  }
  if (kind === "audio") {
    return (
      <audio className="knowledge-preview__audio" src={source} controls preload="metadata" onError={() => setFailed(true)}>
        {t("knowledge.preview.audioUnsupported")}
      </audio>
    );
  }
  if (kind === "video") return (
    <video className="knowledge-preview__video" src={source} controls playsInline preload="metadata" onError={() => setFailed(true)}>
      {t("knowledge.preview.videoUnsupported")}
    </video>
  );
  if (kind === "pdf") {
    return (
      <div className="knowledge-preview__pdf">
        <iframe
          src={source}
          title={chunk.title ? t("knowledge.preview.namedPdf", { name: chunk.title }) : t("knowledge.preview.pdf")}
          sandbox=""
          referrerPolicy="no-referrer"
          onError={() => setFailed(true)}
        />
        <a href={source} target="_blank" rel="noopener noreferrer">{t("knowledge.preview.openPdf")}</a>
      </div>
    );
  }
  return (
    <div className="knowledge-preview__file-fallback">
      <p>{t("knowledge.preview.fileUnsupported")}</p>
      <a href={source} target="_blank" rel="noopener noreferrer">{t("knowledge.preview.openOriginalFile")}</a>
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
  const { t } = useTranslation("ui");
  const [chunks, setChunks] = useState<KnowledgeDocumentPreviewChunk[]>([]);
  const [document, setDocument] = useState(item);
  const [resolvedSourceMarkdown, setResolvedSourceMarkdown] = useState("");
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
      setResolvedSourceMarkdown(page.sourceMarkdown || page.document.sourceMarkdown);
      setChunks((current) => offset > 0 ? [...current, ...page.chunks] : page.chunks);
      setHasMore(page.hasMore);
    } catch (reason) {
      if (!isAbortError(reason) && requestRef.current === request) {
        setError(formatKnowledgeError(reason, t("knowledge.errors.loadPreview")));
      }
    } finally {
      if (requestRef.current === request) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, [base.id, base.region, item, t]);

  useEffect(() => {
    void loadPreview();
    return () => {
      abortRef.current?.abort();
      requestRef.current += 1;
    };
  }, [loadPreview]);

  const sourceUrl = safeKnowledgeSourceUrl(document.url || item.url);
  const emptyCopy = knowledgePreviewEmptyCopy(document, t);
  const contentIsMarkdown = document.metadata._veadk_content_format === "markdown";

  return (
    <KnowledgeDialog title={document.name || item.name || item.id} onClose={onClose} className="knowledge-dialog--preview">
      <div className="knowledge-preview">
        {document.sizeBytes > 0 || sourceUrl ? (
          <div className="knowledge-preview__meta">
            {document.sizeBytes > 0 ? <span>{formatFileSize(document.sizeBytes)}</span> : null}
            {sourceUrl ? <a href={sourceUrl} target="_blank" rel="noopener noreferrer">{t("knowledge.openOriginalWeb")}</a> : null}
          </div>
        ) : null}
        <div className="knowledge-preview__body" aria-live="polite">
          {resolvedSourceMarkdown ? (
            <div className="knowledge-preview__markdown-shell">
              <Markdown text={resolvedSourceMarkdown} allowRawHtml={false} className="knowledge-preview__markdown" />
            </div>
          ) : loading ? (
            <div className="knowledge-preview__state" role="status">
              <TextShimmer as="span" duration={2.4}>{t("knowledge.preview.loading")}</TextShimmer>
            </div>
          ) : error && chunks.length === 0 ? (
            <div className="knowledge-preview__state is-error" role="alert">
              <p>{error}</p>
              <button type="button" onClick={() => void loadPreview()}>{t("common.retry")}</button>
            </div>
          ) : chunks.length === 0 ? (
            <div className="knowledge-preview__state">
              <p>{emptyCopy.title}</p>
              <span>{sourceUrl ? t("knowledge.preview.openOriginalHint") : emptyCopy.detail}</span>
              <button type="button" onClick={() => void loadPreview()}>{t("common.reload")}</button>
            </div>
          ) : (
            <div className="knowledge-preview__chunks">
              {chunks.map((chunk, index) => {
                const table = knowledgePreviewTable(chunk.tableFields, t);
                const key = chunk.id || `${index}:${chunk.title}`;
                return (
                  <article className="knowledge-preview__chunk" key={key}>
                    <header>
                      <h3>{chunk.title || t("knowledge.preview.chunk", { index: index + 1 })}</h3>
                    </header>
                    {chunk.content ? (
                      contentIsMarkdown
                        ? <Markdown text={chunk.content} allowRawHtml={false} className="knowledge-preview__markdown" />
                        : <p className="knowledge-preview__content">{chunk.content}</p>
                    ) : null}
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
                  {loadingMore ? <TextShimmer as="span" duration={2.4}>{t("knowledge.preview.loadingMore")}</TextShimmer> : t("knowledge.preview.loadMore")}
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
  region,
  active = true,
  activationRevision = 0,
  onDetailChange,
  toolbarLeading,
  toolbarFilters,
}: {
  cloudProvider: CloudProvider;
  region: CloudRegion;
  active?: boolean;
  activationRevision?: number;
  onDetailChange?: (active: boolean) => void;
  toolbarLeading?: ReactNode;
  toolbarFilters?: ReactNode;
}) {
  const { t, i18n } = useTranslation("ui");
  const [items, setItems] = useState<KnowledgeBaseItem[]>([]);
  const [nextTokens, setNextTokens] = useState<Record<string, string>>({});
  const [regionWarnings, setRegionWarnings] = useState<string[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [detailSection, setDetailSection] = useState<KnowledgeDetailSection>("overview");
  const [query, setQuery] = useState("");
  const [documentQuery, setDocumentQuery] = useState("");
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
    () => [region],
    [region],
  );
  const baseKey = useCallback(
    (item: KnowledgeBaseItem) => `${item.region}\u0000${item.id}`,
    [],
  );
  const selected = items.find((item) => baseKey(item) === selectedKey) ?? null;
  const providerAssociationInvalid = Boolean(
    selected && invalidProviderKey === baseKey(selected),
  );

  useEffect(() => {
    onDetailChange?.(Boolean(selected));
  }, [onDetailChange, selected]);

  useEffect(() => {
    setDetailSection("overview");
    setDocumentQuery("");
  }, [selectedKey]);

  const filteredItems = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return items;
    return items.filter((item) => [item.name, item.description, item.ownerLabel, item.providerKnowledgeId].some((value) => value.toLocaleLowerCase().includes(normalized)));
  }, [items, query]);

  const filteredDocuments = useMemo(() => {
    const normalized = documentQuery.trim().toLocaleLowerCase();
    if (!normalized) return documents;
    return documents.filter((item) => [
      item.name,
      item.id,
      knowledgeDocumentFormat(item),
    ].some((value) => value.toLocaleLowerCase().includes(normalized)));
  }, [documentQuery, documents]);

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
        `${formatCloudRegion(region, cloudProvider)}: ${formatKnowledgeError(reason, t("common.loadFailed"))}`
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
            ...new Set([...current, formatKnowledgeError(reason, t("knowledge.errors.loadMoreBases"))]),
          ]);
        } else {
          setError(formatKnowledgeError(reason, t("knowledge.errors.loadBases")));
        }
      }
    } finally {
      if (basesRequest.current === request) {
        basesLoadingRef.current = false;
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, [baseKey, cloudProvider, regions, t]);

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
          setDocumentsMoreError(formatKnowledgeError(reason, t("knowledge.errors.loadMoreData")));
        } else {
          setDocumentsError(formatKnowledgeError(reason, t("knowledge.errors.loadData")));
        }
      }
    } finally {
      if (documentsRequest.current === request) {
        documentsLoadingRef.current = false;
        setDocumentsLoading(false);
      }
    }
  }, [baseKey, t]);

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
      setError(formatKnowledgeError(reason, t("knowledge.errors.deleteBase")));
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
      setDocumentsError(formatKnowledgeError(reason, t("knowledge.errors.deleteDocument")));
      setDeleteDocumentTarget(null);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <section className={`knowledge-library${selected ? " is-detail" : " resource-collection"}`} aria-label={t("knowledge.library")}>
      {selected ? (
        <ResourceDetailLayout
          className="knowledge-library__detail"
          title={selected.name}
          description={selected.description || t("common.noDescription")}
          identitySeed={selected.name}
          backLabel={t("knowledge.backToList")}
          onBack={() => setSelectedKey("")}
          sections={[
            {
              key: "overview",
              label: t("skillCenter.overview"),
              content: (
                <section className="knowledge-overview">
                  <ResourceDetailSummary className="knowledge-overview__summary">
                    <div><dt>{t("knowledge.provider")}</dt><dd>{selected.providerType || "-"}</dd></div>
                    <div><dt>{t("knowledge.knowledgeId")}</dt><dd className="knowledge-keyboard-reveal" tabIndex={0} title={selected.providerKnowledgeId}>{selected.providerKnowledgeId || "-"}</dd></div>
                    <div><dt>{t("knowledge.project")}</dt><dd>{selected.projectName || "default"}</dd></div>
                    <div><dt>{t("knowledge.creator")}</dt><dd>{formatResourceSource(selected.ownerLabel)}</dd></div>
                    <div><dt>{t("skillCenter.updatedAt")}</dt><dd>{formatDate(selected.updatedAt, i18n.resolvedLanguage ?? i18n.language) || "-"}</dd></div>
                  </ResourceDetailSummary>
                </section>
              ),
            },
            {
              key: "data",
              label: t("knowledge.data"),
              content: (
                <section className="knowledge-documents">
                  <div className={`knowledge-documents__body${documents.length > 0 ? " is-table" : ""}`} aria-live="polite">
                    {documentsLoading && documents.length === 0 ? (
                      <ResourceLoadingState />
                    ) : documentsError && documents.length === 0 ? (
                      <div className="knowledge-library__state is-error" role="alert">
                        <p>{documentsError}</p>
                        {providerAssociationInvalid && selected.canManage
                          ? <button type="button" onClick={() => setDeleteBaseTarget(selected)}>{t("knowledge.deleteInvalidAssociation")}</button>
                          : <button type="button" onClick={() => void loadDocuments(selected)}>{t("common.retry")}</button>}
                      </div>
                    ) : documents.length === 0 ? (
                      <div className="knowledge-library__state"><DocumentIcon /><p>{t("knowledge.noData")}</p>{selected.canManage && <button type="button" onClick={() => setCreateDocumentBase(selected)}>{t("knowledge.addFirstData")}</button>}</div>
                    ) : (
                      <ResourceDataTable
                        rows={filteredDocuments}
                        rowKey={(item) => item.id}
                        rowLabel={(item) => item.name || item.id}
                        columns={[
                          {
                            key: "name",
                            header: t("common.name"),
                            className: "is-primary-column",
                            render: (item) => <span title={item.name || item.id}>{item.name || item.id}</span>,
                          },
                          {
                            key: "format",
                            header: t("knowledge.format"),
                            className: "is-compact-column",
                            render: (item) => knowledgeDocumentFormat(item),
                          },
                          {
                            key: "size",
                            header: t("knowledge.size"),
                            className: "is-compact-column",
                            render: (item) => formatFileSize(item.sizeBytes),
                          },
                        ]}
                        searchValue={documentQuery}
                        onSearchChange={setDocumentQuery}
                        searchPlaceholder={t("knowledge.searchData")}
                        searchLabel={t("knowledge.searchLibraryData")}
                        primaryAction={selected.canManage ? {
                          label: providerAssociationInvalid ? t("knowledge.associationInvalid") : t("knowledge.addData"),
                          disabled: providerAssociationInvalid,
                          title: providerAssociationInvalid ? t("knowledge.providerMissing") : undefined,
                          onClick: () => setCreateDocumentBase(selected),
                        } : undefined}
                        rowActions={(item) => [
                          {
                            label: t("common.preview"),
                            onSelect: () => setPreviewDocument(item),
                          },
                          ...(selected.canManage ? [
                            {
                              label: t("common.edit"),
                              onSelect: () => setEditDocument(item),
                            },
                            {
                              label: t("common.delete"),
                              onSelect: () => setDeleteDocumentTarget(item),
                              danger: true,
                            },
                          ] : []),
                        ]}
                        scrollRef={documentsScrollRef}
                        onScroll={handleDocumentsScroll}
                        busy={documentsLoading}
                        emptyLabel={t("knowledge.noMatchingData")}
                        footer={documentsLoading ? (
                          <div className="knowledge-document-pagination" role="status" aria-live="polite">
                            <span className="my-agent-loading-mark" aria-hidden="true" />
                            <span>{t("knowledge.loadingMoreData")}</span>
                          </div>
                        ) : documentsMoreError ? (
                          <div className="knowledge-document-pagination is-error" role="alert">
                            <span>{documentsMoreError}</span>
                            <button type="button" onClick={() => void loadDocuments(selected, true)}>{t("knowledge.retryLoading")}</button>
                          </div>
                        ) : documentsHasMore ? (
                          <div
                            ref={documentsLoadMoreRef}
                            className="knowledge-document-pagination"
                            role="status"
                            aria-live="polite"
                          >
                            {t("skillCenter.scrollForMore")}
                          </div>
                        ) : null}
                      />
                    )}
                  </div>
                </section>
              ),
            },
          ]}
          activeSectionKey={detailSection}
          navigationLabel={t("knowledge.details")}
          onSectionChange={setDetailSection}
          actions={selected.canManage ? (
            <>
                <Button type="button" color="danger" variant="soft" size="lg" pill={false} onClick={() => setDeleteBaseTarget(selected)}>{t("common.delete")}</Button>
                <Button type="button" color="primary" size="lg" pill={false} onClick={() => setEditBaseOpen(true)}>{t("common.edit")}</Button>
            </>
          ) : undefined}
        />
      ) : (
        <>
          <ResourceToolbar className="knowledge-library__toolbar library-resource-toolbar">
            {toolbarLeading}
            <div className="resource-toolbar__actions">
              {toolbarFilters}
              <ResourceSearch
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={t("knowledge.searchBases")}
                aria-label={t("knowledge.searchBases")}
              />
            </div>
          </ResourceToolbar>
          <ResourceResults
            ref={resultsRef}
            aria-live="polite"
            onScroll={handleResultsScroll}
          >
            {regionWarnings.length > 0 && !loading && (
              <div className="knowledge-region-warning" role="status">
                <span>{t("knowledge.someBasesFailed")}</span>
                <button type="button" onClick={() => void loadBases()}>{t("common.retry")}</button>
              </div>
            )}
            {loading && items.length === 0 ? (
              <ResourceLoadingState />
            ) : error ? (
              <div className="knowledge-library__state is-error" role="alert"><p>{error}</p><button type="button" onClick={() => void loadBases()}>{t("common.retry")}</button></div>
            ) : filteredItems.length === 0 && query.trim() ? (
              <div className="knowledge-library__state"><KnowledgeIcon /><p>{t("knowledge.noMatchingBases")}</p></div>
            ) : (
              <ResourceGrid>
                {!query.trim() ? (
                  <ResourceCreateCard
                    aria-label={t("knowledge.createBase")}
                    icon={<PlusIcon />}
                    onClick={() => setCreateBaseOpen(true)}
                  >
                    {t("knowledge.createBase")}
                  </ResourceCreateCard>
                ) : null}
                {filteredItems.map((item) => (
                  <LibraryResourceCard
                    key={baseKey(item)}
                    className="knowledge-card"
                    title={item.name}
                    description={item.description || t("common.noDescription")}
                    metadata={[
                      {
                        label: t("knowledge.creator"),
                        value: formatResourceSource(item.ownerLabel),
                        title: formatResourceSource(item.ownerLabel),
                      },
                      { label: t("knowledge.project"), value: item.projectName || "default", title: item.projectName || "default" },
                    ]}
                    action={{
                      label: invalidProviderKey === baseKey(item) ? t("knowledge.associationInvalid") : t("knowledge.addData"),
                      icon: "plus",
                      disabled: !item.canManage || invalidProviderKey === baseKey(item),
                      title: !item.canManage ? t("knowledge.noManagePermission") : invalidProviderKey === baseKey(item) ? t("knowledge.providerMissing") : undefined,
                      onClick: () => setCreateDocumentBase(item),
                    }}
                    detailAction={{ label: t("common.viewDetails"), onClick: () => setSelectedKey(baseKey(item)) }}
                  />
                ))}
              </ResourceGrid>
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
                    <span>{t("knowledge.loadingMoreBases")}</span>
                  </>
                ) : canLoadMoreBases ? <span>{t("skillCenter.scrollForMore")}</span> : null}
              </div>
            ) : null}
          </ResourceResults>
        </>
      )}

      {createBaseOpen && <CreateKnowledgeBaseDialog region={region} onClose={() => setCreateBaseOpen(false)} onCreated={(item) => { setItems((current) => [item, ...current]); setSelectedKey(baseKey(item)); setCreateBaseOpen(false); }} />}
      {selected && editBaseOpen && <EditKnowledgeBaseDialog item={selected} onClose={() => setEditBaseOpen(false)} onUpdated={(item) => { replaceBase(item); setEditBaseOpen(false); }} />}
      {selected && previewDocument && <KnowledgeDocumentPreviewDialog base={selected} item={previewDocument} onClose={() => setPreviewDocument(null)} />}
      {createDocumentBase && <CreateKnowledgeDocumentDialog base={createDocumentBase} onClose={() => setCreateDocumentBase(null)} onAssociationInvalid={(reason) => {
        setInvalidProviderKey(baseKey(createDocumentBase));
        if (selected && baseKey(selected) === baseKey(createDocumentBase)) {
          setDocumentsError(formatKnowledgeError(reason, t("knowledge.associationInvalid")));
        }
        setCreateDocumentBase(null);
      }} onCreated={() => {
        if (selected && baseKey(selected) === baseKey(createDocumentBase)) void loadDocuments(selected);
        setCreateDocumentBase(null);
      }} />}
      {selected && editDocument && <EditKnowledgeDocumentDialog base={selected} item={editDocument} onClose={() => setEditDocument(null)} onUpdated={(item) => { const next = documentsRef.current.map((candidate) => candidate.id === item.id ? item : candidate); documentsRef.current = next; setDocuments(next); setEditDocument(null); }} />}
      {deleteBaseTarget && <StudioConfirmDialog title={t("knowledge.deleteBaseTitle")} description={t("knowledge.deleteBaseDescription", { name: deleteBaseTarget.name })} confirmLabel={deleting ? t("common.deleting") : t("common.delete")} variant="danger" busy={deleting} onCancel={() => setDeleteBaseTarget(null)} onConfirm={() => void confirmDeleteBase()} />}
      {deleteDocumentTarget && <StudioConfirmDialog title={t("knowledge.deleteDocumentTitle")} description={t("knowledge.deleteDocumentDescription", { name: deleteDocumentTarget.name || deleteDocumentTarget.id })} confirmLabel={deleting ? t("common.deleting") : t("common.delete")} variant="danger" busy={deleting} onCancel={() => setDeleteDocumentTarget(null)} onConfirm={() => void confirmDeleteDocument()} />}
    </section>
  );
}
