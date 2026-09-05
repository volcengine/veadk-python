import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import {
  downloadArtifact as downloadAdkArtifact,
  previewArtifact as previewAdkArtifact,
} from "../adk/client";
import {
  CloseLibraryIcon,
  DownloadArtifactIcon,
  EditArtifactIcon,
  SourceArtifactIcon,
  VideoArtifactIcon,
} from "./icons/LibraryIcons";
import {
  ArtifactEditDialog,
  type ArtifactMetadataUpdate,
} from "./ArtifactEditDialog";
import { StudioActionMenu } from "./StudioActionMenu";
import { StudioConfirmDialog } from "./StudioConfirmDialog";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import {
  ResourceFilterSelect,
  ResourceLoadingState,
  ResourceResults,
  ResourceSearch,
  ResourceToolbar,
  type ResourceFilterOption,
} from "./ResourceCollection";
import type { CloudRegion } from "../adk/cloudProvider";
import {
  collectArtifactLibraryItems,
  formatArtifactSize,
  formatArtifactTime,
  type ArtifactLibraryItem,
  type ArtifactSessionSource,
  type ArtifactType,
} from "./artifactLibraryModel";
import "./ArtifactLibrary.css";

export interface ArtifactLibraryProps {
  sources?: readonly ArtifactSessionSource[];
  items?: readonly ArtifactLibraryItem[];
  userId?: string;
  active?: boolean;
  activationRevision?: number;
  loading?: boolean;
  error?: string;
  onRetry?: () => void;
  onEdit?: (
    artifact: ArtifactLibraryItem,
    update: ArtifactMetadataUpdate,
  ) => Promise<ArtifactLibraryItem | void>;
  onDelete?: (artifact: ArtifactLibraryItem) => Promise<void>;
  onDownload?: (artifact: ArtifactLibraryItem) => Promise<void>;
  onOpenSource?: (artifact: ArtifactLibraryItem) => void;
  region: CloudRegion;
  toolbarLeading?: ReactNode;
  toolbarFilters?: ReactNode;
}

const ARTIFACT_BATCH_SIZE = 40;

type ArtifactTypeFilter = "all" | ArtifactType;

function artifactTypeOptions(
  t: TFunction,
): Array<ResourceFilterOption<ArtifactTypeFilter>> {
  return [
    { value: "all", label: t("artifactLibrary.types.all") },
    { value: "document", label: t("artifactLibrary.types.document") },
    { value: "image", label: t("artifactLibrary.types.image") },
    { value: "video", label: t("artifactLibrary.types.video") },
  ];
}

function artifactTypeLabel(t: TFunction, type: ArtifactType): string {
  return t(`artifactLibrary.types.${type}`);
}

function messageFrom(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}

function ArtifactVisual({
  artifact,
  large = false,
}: {
  artifact: ArtifactLibraryItem;
  large?: boolean;
}) {
  return (
    <div
      className={`library-artifact-preview library-artifact-preview--${artifact.type}${large ? " is-large" : ""}`}
    >
      {artifact.thumbnailUrl ? (
        <>
          <img
            className="library-artifact-preview-media"
            src={artifact.thumbnailUrl}
            alt=""
            loading="lazy"
          />
          {artifact.type === "video" ? (
            <span className="artifact-video-play is-overlay" aria-hidden="true">
              <VideoArtifactIcon />
            </span>
          ) : null}
        </>
      ) : artifact.type === "document" ? (
        <div className="artifact-document-sheet" aria-hidden="true">
          <span className="is-title" />
          <span />
          <span />
          <span className="is-short" />
        </div>
      ) : artifact.type === "image" ? (
        <div className="artifact-image-scene" aria-hidden="true">
          <span className="artifact-image-sun" />
          <span className="artifact-image-plane artifact-image-plane--back" />
          <span className="artifact-image-plane artifact-image-plane--front" />
        </div>
      ) : (
        <div className="artifact-video-frame" aria-hidden="true">
          <span className="artifact-video-orbit" />
          <span className="artifact-video-node artifact-video-node--one" />
          <span className="artifact-video-node artifact-video-node--two" />
          <span className="artifact-video-play">
            <VideoArtifactIcon />
          </span>
        </div>
      )}
    </div>
  );
}

function ArtifactRow({
  artifact,
  pendingAction,
  disabled,
  onPreview,
  onDownload,
  onEdit,
  onDelete,
  onOpenSource,
  t,
  locale,
}: {
  artifact: ArtifactLibraryItem;
  pendingAction: string;
  disabled: boolean;
  onPreview: (artifact: ArtifactLibraryItem) => void;
  onDownload: (artifact: ArtifactLibraryItem) => void;
  onEdit?: (artifact: ArtifactLibraryItem) => void;
  onDelete?: (artifact: ArtifactLibraryItem) => void;
  onOpenSource?: (artifact: ArtifactLibraryItem) => void;
  t: TFunction;
  locale: string;
}) {
  const downloadPending = pendingAction === `download:${artifact.id}`;
  return (
    <tr className="library-artifact-row">
      <td className="library-artifact-file">
        <button
          type="button"
          className="library-artifact-preview-trigger"
          aria-label={t("artifactLibrary.previewArtifact", { name: artifact.name })}
          disabled={disabled || Boolean(pendingAction)}
          onClick={() => onPreview(artifact)}
        >
          <div className="library-artifact-thumbnail">
            <ArtifactVisual artifact={artifact} />
          </div>
          <div className="library-artifact-row-title">
            <span className="library-artifact-row-name" title={artifact.name}>
              {artifact.name}
            </span>
            <span className="library-artifact-row-size">
              {formatArtifactSize(artifact.sizeBytes) || "—"}
            </span>
          </div>
        </button>
      </td>
      <td className="library-artifact-source-cell">
        {onOpenSource ? (
          <button
            type="button"
            className="library-artifact-source-link"
            title={`${artifact.agentName} / ${artifact.sessionTitle}`}
            onClick={() => onOpenSource(artifact)}
          >
            <span>{artifact.agentName}</span>
            <span aria-hidden="true">/</span>
            <span>{artifact.sessionTitle}</span>
          </button>
        ) : (
          <span title={`${artifact.agentName} / ${artifact.sessionTitle}`}>
            {artifact.agentName} / {artifact.sessionTitle}
          </span>
        )}
      </td>
      <td className="library-artifact-time">
        {formatArtifactTime(
          artifact.updatedAt ?? artifact.createdAt,
          locale,
          t("artifactLibrary.unknownTime"),
        )}
      </td>
      <td className="library-artifact-actions-cell">
        <div className="library-artifact-actions">
          <StudioActionMenu
            label={t("artifactLibrary.moreActions", { name: artifact.name })}
            menuLabel={t("artifactLibrary.actionMenu", { name: artifact.name })}
            placement="bottom-end"
            items={[
              {
                label: downloadPending
                  ? t("artifactLibrary.downloading")
                  : t("artifactLibrary.download"),
                onSelect: () => onDownload(artifact),
                disabled: disabled || Boolean(pendingAction),
              },
              ...(onEdit ? [{
                label: t("artifactLibrary.edit"),
                onSelect: () => onEdit(artifact),
                disabled: disabled || Boolean(pendingAction) || artifact.canManage === false,
              }] : []),
              ...(onDelete ? [{
                label: t("artifactLibrary.delete"),
                onSelect: () => onDelete(artifact),
                disabled: disabled || Boolean(pendingAction) || artifact.canManage === false,
                danger: true,
              }] : []),
            ]}
          />
        </div>
      </td>
    </tr>
  );
}

export function ArtifactLibrary({
  sources = [],
  items,
  userId = "",
  active = true,
  activationRevision = 0,
  loading = false,
  error = "",
  onRetry,
  onEdit,
  onDelete,
  onDownload,
  onOpenSource,
  region,
  toolbarLeading,
  toolbarFilters,
}: ArtifactLibraryProps) {
  const { t, i18n } = useTranslation("workspaceTools");
  const locale = i18n.resolvedLanguage || i18n.language;
  const [activeType, setActiveType] = useState<ArtifactTypeFilter>("all");
  const [query, setQuery] = useState("");
  const [previewArtifact, setPreviewArtifact] = useState<ArtifactLibraryItem | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [pendingAction, setPendingAction] = useState("");
  const [actionError, setActionError] = useState("");
  const [status, setStatus] = useState("");
  const [itemOverrides, setItemOverrides] = useState<Record<string, ArtifactLibraryItem>>({});
  const [removedIds, setRemovedIds] = useState<ReadonlySet<string>>(() => new Set());
  const [editArtifact, setEditArtifact] = useState<ArtifactLibraryItem | null>(null);
  const [editBusy, setEditBusy] = useState(false);
  const [editError, setEditError] = useState("");
  const [deleteArtifact, setDeleteArtifact] = useState<ArtifactLibraryItem | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [visibleCount, setVisibleCount] = useState(ARTIFACT_BATCH_SIZE);
  const closePreviewButtonRef = useRef<HTMLButtonElement>(null);
  const previewPanelRef = useRef<HTMLDivElement>(null);
  const requestGenerationRef = useRef(0);
  const resultsRef = useRef<HTMLElement>(null);
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const batchAdvancingRef = useRef(false);

  const closePreview = useCallback(() => {
    requestGenerationRef.current += 1;
    setPreviewArtifact(null);
    setPreviewUrl("");
    setPendingAction("");
  }, []);

  const collectedArtifacts = useMemo(
    () => items
      ? [...items]
      : collectArtifactLibraryItems(sources, t("library.untitledSession"), locale),
    [items, locale, sources, t],
  );
  const artifacts = useMemo(
    () => collectedArtifacts
      .filter((artifact) => !removedIds.has(artifact.id))
      .map((artifact) => itemOverrides[artifact.id] ?? artifact),
    [collectedArtifacts, itemOverrides, removedIds],
  );

  useEffect(() => () => {
    requestGenerationRef.current += 1;
  }, []);

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  useEffect(() => {
    if (!previewArtifact) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closePreviewButtonRef.current?.focus();
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closePreview();
        return;
      }
      if (event.key !== "Tab") return;
      const panel = previewPanelRef.current;
      if (!panel) return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(
        'button:not([disabled]), video[controls], iframe, [tabindex]:not([tabindex="-1"])',
      )).filter((element) => element.getClientRects().length > 0);
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
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
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      document.body.style.overflow = previousOverflow;
      if (previouslyFocused?.isConnected) previouslyFocused.focus();
    };
  }, [closePreview, previewArtifact]);

  const openPreview = async (artifact: ArtifactLibraryItem) => {
    const generation = requestGenerationRef.current + 1;
    requestGenerationRef.current = generation;
    setActionError("");
    setPreviewUrl("");
    setPreviewArtifact(artifact);
    if (artifact.preview.mode === "unavailable") return;
    if (artifact.contentUrl) {
      setPreviewUrl(artifact.contentUrl);
      return;
    }
    setPendingAction(`preview:${artifact.id}`);
    try {
      const url = await previewAdkArtifact(
        artifact.appName,
        userId,
        artifact.sessionId,
        artifact.preview.filename,
        artifact.preview.version,
      );
      if (requestGenerationRef.current !== generation) {
        URL.revokeObjectURL(url);
        return;
      }
      setPreviewUrl(url);
    } catch (reason) {
      if (requestGenerationRef.current === generation) {
        setActionError(t("artifactLibrary.previewFailed", {
          name: artifact.name,
          message: messageFrom(reason),
        }));
      }
    } finally {
      if (requestGenerationRef.current === generation) setPendingAction("");
    }
  };

  const download = async (artifact: ArtifactLibraryItem) => {
    setActionError("");
    setPendingAction(`download:${artifact.id}`);
    try {
      if (onDownload) {
        await onDownload(artifact);
      } else {
        await downloadAdkArtifact(
          artifact.appName,
          userId,
          artifact.sessionId,
          artifact.name,
          artifact.version,
        );
      }
      setStatus(t("artifactLibrary.downloadStarted", { name: artifact.name }));
    } catch (reason) {
      setActionError(t("artifactLibrary.downloadFailed", {
        name: artifact.name,
        message: messageFrom(reason),
      }));
    } finally {
      setPendingAction("");
    }
  };

  const saveEdit = async (update: ArtifactMetadataUpdate) => {
    if (!editArtifact || !onEdit) return;
    setEditBusy(true);
    setEditError("");
    try {
      const saved = await onEdit(editArtifact, update);
      const next = saved ?? { ...editArtifact, ...update, updatedAt: Date.now() };
      setItemOverrides((current) => ({ ...current, [editArtifact.id]: next }));
      setStatus(t("artifactLibrary.updated", { name: next.name }));
      setEditArtifact(null);
    } catch (reason) {
      setEditError(messageFrom(reason));
    } finally {
      setEditBusy(false);
    }
  };

  const confirmDelete = async () => {
    if (!deleteArtifact || !onDelete) return;
    setDeleteBusy(true);
    setActionError("");
    try {
      await onDelete(deleteArtifact);
      setRemovedIds((current) => new Set([...current, deleteArtifact.id]));
      setStatus(t("artifactLibrary.deleted", { name: deleteArtifact.name }));
      if (previewArtifact?.id === deleteArtifact.id) closePreview();
      setDeleteArtifact(null);
    } catch (reason) {
      setActionError(t("artifactLibrary.deleteFailed", {
        name: deleteArtifact.name,
        message: messageFrom(reason),
      }));
      setDeleteArtifact(null);
    } finally {
      setDeleteBusy(false);
    }
  };

  const visibleArtifacts = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return artifacts.filter((artifact) => {
      if (artifact.origin?.region && artifact.origin.region !== region) {
        return false;
      }
      if (activeType !== "all" && artifact.type !== activeType) {
        return false;
      }
      if (!normalizedQuery) return true;
      return [artifact.name, artifact.sessionTitle, artifact.agentName]
        .some((value) => value.toLocaleLowerCase().includes(normalizedQuery));
    });
  }, [activeType, artifacts, query, region]);

  const displayedArtifacts = useMemo(
    () => visibleArtifacts.slice(0, visibleCount),
    [visibleArtifacts, visibleCount],
  );
  const hasMoreArtifacts = visibleCount < visibleArtifacts.length;

  const revealNextBatch = useCallback(() => {
    if (batchAdvancingRef.current) return;
    batchAdvancingRef.current = true;
    setVisibleCount((current) => current + ARTIFACT_BATCH_SIZE);
  }, []);

  useEffect(() => {
    setVisibleCount(ARTIFACT_BATCH_SIZE);
  }, [activationRevision, activeType, query, visibleArtifacts.length]);

  useEffect(() => {
    batchAdvancingRef.current = false;
  }, [visibleCount]);

  useEffect(() => {
    const target = loadMoreRef.current;
    const root = resultsRef.current;
    if (!active || !target || !root || !hasMoreArtifacts) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) revealNextBatch();
      },
      { root, rootMargin: "240px 0px", threshold: 0.01 },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [active, hasMoreArtifacts, revealNextBatch, visibleCount]);

  const handleResultsScroll = () => {
    const results = resultsRef.current;
    if (!active || !results || !hasMoreArtifacts) return;
    if (results.scrollHeight - results.scrollTop - results.clientHeight <= 240) {
      revealNextBatch();
    }
  };

  const hasSearchOrFilter = Boolean(query.trim())
    || activeType !== "all"
    || artifacts.some((artifact) => artifact.origin?.region && artifact.origin.region !== region);

  return (
    <div className="artifact-library-page resource-collection">
      <ResourceToolbar className="artifact-library-toolbar library-resource-toolbar">
        {toolbarLeading}
        <div className="resource-toolbar__actions">
          <ResourceFilterSelect
            id="artifact-type-filter"
            ariaLabel={t("artifactLibrary.typeFilter")}
            value={activeType}
            options={artifactTypeOptions(t)}
            onChange={setActiveType}
          />
          {toolbarFilters}
          <ResourceSearch
            aria-label={t("artifactLibrary.searchAria")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("artifactLibrary.searchPlaceholder")}
          />
        </div>
      </ResourceToolbar>

      {error && artifacts.length > 0 ? (
        <div className="artifact-library-banner" role="alert">
          <span>{error}</span>
          {onRetry ? <button type="button" onClick={onRetry}>{t("artifactLibrary.retry")}</button> : null}
        </div>
      ) : null}
      {actionError ? (
        <div className="artifact-library-banner" role="alert">
          <span>{actionError}</span>
          <button type="button" onClick={() => setActionError("")}>{t("artifactLibrary.close")}</button>
        </div>
      ) : null}

      <ResourceResults
        ref={resultsRef}
        className="artifact-library-results"
        aria-label={t("artifactLibrary.listAria")}
        onScroll={handleResultsScroll}
      >
        <div className="artifact-library-panel">
          {loading && artifacts.length === 0 ? (
            <ResourceLoadingState />
          ) : error && artifacts.length === 0 ? (
            <div className="artifact-library-empty is-error" role="alert">
              <p>{t("artifactLibrary.loadFailed")}</p>
              <span>{error}</span>
              {onRetry ? <button type="button" onClick={onRetry}>{t("artifactLibrary.reload")}</button> : null}
            </div>
          ) : visibleArtifacts.length === 0 ? (
            <div className="artifact-library-empty">
              <p>{hasSearchOrFilter
                ? t("artifactLibrary.noMatch")
                : t("artifactLibrary.noArtifacts")}
              </p>
              <span>
                {hasSearchOrFilter
                  ? t("artifactLibrary.searchHint")
                  : t("artifactLibrary.emptyHint")}
              </span>
            </div>
          ) : (
            <div className="artifact-library-list">
              <table className="artifact-library-table">
                <colgroup>
                  <col className="artifact-library-table__file-column" />
                  <col className="artifact-library-table__source-column" />
                  <col className="artifact-library-table__time-column" />
                  <col className="artifact-library-table__actions-column" />
                </colgroup>
                <thead>
                  <tr>
                    <th scope="col">{t("artifactLibrary.columns.name")}</th>
                    <th scope="col">{t("artifactLibrary.columns.source")}</th>
                    <th scope="col">{t("artifactLibrary.columns.updatedAt")}</th>
                    <th scope="col" className="artifact-library-table__actions-heading">{t("artifactLibrary.columns.actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {displayedArtifacts.map((artifact) => (
                    <ArtifactRow
                      key={artifact.id}
                      artifact={artifact}
                      pendingAction={pendingAction}
                      disabled={!userId && !items}
                      onPreview={(item) => void openPreview(item)}
                      onDownload={(item) => void download(item)}
                      onEdit={onEdit ? (item) => {
                        setEditError("");
                        setEditArtifact(item);
                      } : undefined}
                      onDelete={onDelete ? setDeleteArtifact : undefined}
                      onOpenSource={onOpenSource}
                      t={t}
                      locale={locale}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {hasMoreArtifacts ? (
            <div
              ref={loadMoreRef}
              className="artifact-library-load-more"
              role="status"
              aria-live="polite"
            >
              <TextShimmer as="span" duration={2.4}>{t("artifactLibrary.loadingMore")}</TextShimmer>
            </div>
          ) : null}
        </div>
      </ResourceResults>

      <p className="artifact-library-status" aria-live="polite">{status}</p>

      {previewArtifact ? (
        <div
          className="artifact-library-preview-dialog"
          role="dialog"
          aria-modal="true"
          aria-labelledby="artifact-library-preview-title"
        >
          <button
            type="button"
            className="artifact-library-preview-backdrop"
            aria-label={t("artifactLibrary.preview.close")}
            onClick={closePreview}
          />
          <div ref={previewPanelRef} className="artifact-library-preview-panel">
            <header>
              <div>
                <h2 id="artifact-library-preview-title">{previewArtifact.name}</h2>
                <p>
                  {t("artifactLibrary.preview.meta", {
                    type: artifactTypeLabel(t, previewArtifact.type),
                    version: previewArtifact.version,
                  })}
                </p>
              </div>
              <button
                ref={closePreviewButtonRef}
                type="button"
                aria-label={t("artifactLibrary.preview.close")}
                onClick={closePreview}
              >
                <CloseLibraryIcon />
              </button>
            </header>
            <div className="artifact-library-preview-content">
              <div className="artifact-library-preview-canvas">
                {pendingAction === `preview:${previewArtifact.id}` ? (
                  <TextShimmer as="span" duration={2.4}>{t("artifactLibrary.preview.loading")}</TextShimmer>
                ) : previewUrl && previewArtifact.preview.mode === "image" ? (
                  <img src={previewUrl} alt={t("artifactLibrary.preview.alt", { name: previewArtifact.name })} />
                ) : previewUrl && previewArtifact.preview.mode === "video" ? (
                  <video src={previewUrl} controls aria-label={t("artifactLibrary.preview.alt", { name: previewArtifact.name })} />
                ) : previewUrl && previewArtifact.preview.mode === "frame" ? (
                  <iframe src={previewUrl} title={t("artifactLibrary.preview.alt", { name: previewArtifact.name })} />
                ) : (
                  <div className="artifact-library-preview-unavailable">
                    <ArtifactVisual artifact={previewArtifact} large />
                    <p>
                      {actionError
                        ? t("artifactLibrary.preview.loadFailed")
                        : t("artifactLibrary.preview.unsupported")}
                    </p>
                  </div>
                )}
              </div>
              <aside className="artifact-library-preview-details" aria-label={t("artifactLibrary.preview.sourceAria")}>
                {previewArtifact.description ? (
                  <p className="artifact-library-preview-description">
                    {previewArtifact.description}
                  </p>
                ) : null}
                <dl>
                  <div>
                    <dt>{t("artifactLibrary.preview.agent")}</dt>
                    <dd title={previewArtifact.agentName}>{previewArtifact.agentName}</dd>
                  </div>
                  <div>
                    <dt>{t("artifactLibrary.preview.session")}</dt>
                    <dd title={previewArtifact.sessionTitle}>{previewArtifact.sessionTitle}</dd>
                  </div>
                  {previewArtifact.origin?.toolName ? (
                    <div>
                      <dt>{t("artifactLibrary.preview.tool")}</dt>
                      <dd>{previewArtifact.origin.toolName}</dd>
                    </div>
                  ) : null}
                  <div>
                    <dt>{t("artifactLibrary.preview.createdAt")}</dt>
                    <dd>{formatArtifactTime(
                      previewArtifact.createdAt,
                      locale,
                      t("artifactLibrary.unknownTime"),
                    )}</dd>
                  </div>
                  {previewArtifact.sizeBytes ? (
                    <div>
                      <dt>{t("artifactLibrary.preview.fileSize")}</dt>
                      <dd>{formatArtifactSize(previewArtifact.sizeBytes)}</dd>
                    </div>
                  ) : null}
                </dl>
                {previewArtifact.tags?.length ? (
                  <div className="artifact-library-preview-tags" aria-label={t("artifactLibrary.preview.tags")}>
                    {previewArtifact.tags.map((tag) => <span key={tag}>{tag}</span>)}
                  </div>
                ) : null}
              </aside>
            </div>
            <footer>
              <div className="artifact-library-preview-footer-start">
                {onOpenSource ? (
                  <button
                    type="button"
                    className="is-secondary"
                    onClick={() => {
                      const source = previewArtifact;
                      closePreview();
                      onOpenSource(source);
                    }}
                  >
                    <SourceArtifactIcon />
                    {t("artifactLibrary.preview.viewSession")}
                  </button>
                ) : null}
                {onEdit ? (
                  <button
                    type="button"
                    className="is-secondary"
                    disabled={previewArtifact.canManage === false}
                    onClick={() => {
                      const current = previewArtifact;
                      closePreview();
                      setEditError("");
                      setEditArtifact(current);
                    }}
                  >
                    <EditArtifactIcon />
                    {t("artifactLibrary.edit")}
                  </button>
                ) : null}
              </div>
              <button
                type="button"
                disabled={pendingAction.startsWith("download:") || (!userId && !items)}
                onClick={() => void download(previewArtifact)}
              >
                <DownloadArtifactIcon />
                {t("artifactLibrary.download")}
              </button>
            </footer>
          </div>
        </div>
      ) : null}
      {editArtifact ? (
        <ArtifactEditDialog
          artifact={editArtifact}
          busy={editBusy}
          error={editError}
          onClose={() => {
            if (!editBusy) setEditArtifact(null);
          }}
          onSave={(update) => void saveEdit(update)}
        />
      ) : null}
      {deleteArtifact ? (
        <StudioConfirmDialog
          title={t("artifactLibrary.deleteDialog.title")}
          description={t("artifactLibrary.deleteDialog.description", { name: deleteArtifact.name })}
          confirmLabel={deleteBusy
            ? t("artifactLibrary.deleteDialog.deleting")
            : t("artifactLibrary.deleteDialog.confirm")}
          closeLabel={t("artifactLibrary.deleteDialog.close")}
          variant="danger"
          busy={deleteBusy}
          onCancel={() => {
            if (!deleteBusy) setDeleteArtifact(null);
          }}
          onConfirm={() => void confirmDelete()}
        />
      ) : null}
    </div>
  );
}
