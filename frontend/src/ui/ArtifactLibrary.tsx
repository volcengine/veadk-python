import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

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

const ARTIFACT_TYPES: Array<{ id: ArtifactType; label: string }> = [
  { id: "document", label: "文档" },
  { id: "image", label: "图片" },
  { id: "video", label: "视频" },
];

type ArtifactTypeFilter = "all" | ArtifactType;

const ARTIFACT_TYPE_OPTIONS: Array<ResourceFilterOption<ArtifactTypeFilter>> = [
  { value: "all", label: "全部类型" },
  ...ARTIFACT_TYPES.map(({ id, label }) => ({ value: id, label })),
];

const ARTIFACT_LABELS: Record<ArtifactType, string> = {
  document: "文档",
  image: "图片",
  video: "视频",
};

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
}: {
  artifact: ArtifactLibraryItem;
  pendingAction: string;
  disabled: boolean;
  onPreview: (artifact: ArtifactLibraryItem) => void;
  onDownload: (artifact: ArtifactLibraryItem) => void;
  onEdit?: (artifact: ArtifactLibraryItem) => void;
  onDelete?: (artifact: ArtifactLibraryItem) => void;
  onOpenSource?: (artifact: ArtifactLibraryItem) => void;
}) {
  const downloadPending = pendingAction === `download:${artifact.id}`;
  return (
    <tr className="library-artifact-row">
      <td className="library-artifact-file">
        <button
          type="button"
          className="library-artifact-preview-trigger"
          aria-label={`预览 ${artifact.name}`}
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
        {formatArtifactTime(artifact.updatedAt ?? artifact.createdAt)}
      </td>
      <td className="library-artifact-actions-cell">
        <div className="library-artifact-actions">
          <StudioActionMenu
            label={`更多操作 ${artifact.name}`}
            menuLabel={`${artifact.name} 操作`}
            placement="bottom-end"
            items={[
              {
                label: downloadPending ? "下载中" : "下载",
                onSelect: () => onDownload(artifact),
                disabled: disabled || Boolean(pendingAction),
              },
              ...(onEdit ? [{
                label: "编辑信息",
                onSelect: () => onEdit(artifact),
                disabled: disabled || Boolean(pendingAction) || artifact.canManage === false,
              }] : []),
              ...(onDelete ? [{
                label: "删除产物",
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
    () => items ? [...items] : collectArtifactLibraryItems(sources),
    [items, sources],
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
        setActionError(`无法预览“${artifact.name}”：${messageFrom(reason)}`);
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
      setStatus(`已开始下载 ${artifact.name}`);
    } catch (reason) {
      setActionError(`无法下载“${artifact.name}”：${messageFrom(reason)}`);
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
      setStatus(`已更新 ${next.name}`);
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
      setStatus(`已删除 ${deleteArtifact.name}`);
      if (previewArtifact?.id === deleteArtifact.id) closePreview();
      setDeleteArtifact(null);
    } catch (reason) {
      setActionError(`无法删除“${deleteArtifact.name}”：${messageFrom(reason)}`);
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
            ariaLabel="产物类型"
            value={activeType}
            options={ARTIFACT_TYPE_OPTIONS}
            onChange={setActiveType}
          />
          {toolbarFilters}
          <ResourceSearch
            aria-label="搜索产物"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索产物或会话"
          />
        </div>
      </ResourceToolbar>

      {error && artifacts.length > 0 ? (
        <div className="artifact-library-banner" role="alert">
          <span>{error}</span>
          {onRetry ? <button type="button" onClick={onRetry}>重试</button> : null}
        </div>
      ) : null}
      {actionError ? (
        <div className="artifact-library-banner" role="alert">
          <span>{actionError}</span>
          <button type="button" onClick={() => setActionError("")}>关闭</button>
        </div>
      ) : null}

      <ResourceResults
        ref={resultsRef}
        className="artifact-library-results"
        aria-label="产物列表"
        onScroll={handleResultsScroll}
      >
        <div className="artifact-library-panel">
          {loading && artifacts.length === 0 ? (
            <div className="artifact-library-empty" role="status" aria-live="polite">
              <TextShimmer as="p" duration={2.4}>正在加载产物</TextShimmer>
            </div>
          ) : error && artifacts.length === 0 ? (
            <div className="artifact-library-empty is-error" role="alert">
              <p>产物加载失败</p>
              <span>{error}</span>
              {onRetry ? <button type="button" onClick={onRetry}>重新加载</button> : null}
            </div>
          ) : visibleArtifacts.length === 0 ? (
            <div className="artifact-library-empty">
              <p>{hasSearchOrFilter ? "没有找到匹配的产物" : "您还没有任何产物"}</p>
              <span>
                {hasSearchOrFilter
                  ? "请尝试搜索其他名称或切换类型"
                  : "聊天中生成的产物会自动显示在这里"}
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
                    <th scope="col">名称</th>
                    <th scope="col">来源</th>
                    <th scope="col">修改时间</th>
                    <th scope="col" className="artifact-library-table__actions-heading">操作</th>
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
              <TextShimmer as="span" duration={2.4}>正在加载更多产物</TextShimmer>
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
            aria-label="关闭预览"
            onClick={closePreview}
          />
          <div ref={previewPanelRef} className="artifact-library-preview-panel">
            <header>
              <div>
                <h2 id="artifact-library-preview-title">{previewArtifact.name}</h2>
                <p>
                  {ARTIFACT_LABELS[previewArtifact.type]} / 版本 {previewArtifact.version}
                </p>
              </div>
              <button
                ref={closePreviewButtonRef}
                type="button"
                aria-label="关闭预览"
                onClick={closePreview}
              >
                <CloseLibraryIcon />
              </button>
            </header>
            <div className="artifact-library-preview-content">
              <div className="artifact-library-preview-canvas">
                {pendingAction === `preview:${previewArtifact.id}` ? (
                  <TextShimmer as="span" duration={2.4}>正在加载预览</TextShimmer>
                ) : previewUrl && previewArtifact.preview.mode === "image" ? (
                  <img src={previewUrl} alt={`${previewArtifact.name} 预览`} />
                ) : previewUrl && previewArtifact.preview.mode === "video" ? (
                  <video src={previewUrl} controls aria-label={`${previewArtifact.name} 预览`} />
                ) : previewUrl && previewArtifact.preview.mode === "frame" ? (
                  <iframe src={previewUrl} title={`${previewArtifact.name} 预览`} />
                ) : (
                  <div className="artifact-library-preview-unavailable">
                    <ArtifactVisual artifact={previewArtifact} large />
                    <p>
                      {actionError
                        ? "预览加载失败，请稍后重试或下载查看"
                        : "当前格式暂不支持在线预览，请下载查看"}
                    </p>
                  </div>
                )}
              </div>
              <aside className="artifact-library-preview-details" aria-label="产物来源">
                {previewArtifact.description ? (
                  <p className="artifact-library-preview-description">
                    {previewArtifact.description}
                  </p>
                ) : null}
                <dl>
                  <div>
                    <dt>Agent</dt>
                    <dd title={previewArtifact.agentName}>{previewArtifact.agentName}</dd>
                  </div>
                  <div>
                    <dt>会话</dt>
                    <dd title={previewArtifact.sessionTitle}>{previewArtifact.sessionTitle}</dd>
                  </div>
                  {previewArtifact.origin?.toolName ? (
                    <div>
                      <dt>生成工具</dt>
                      <dd>{previewArtifact.origin.toolName}</dd>
                    </div>
                  ) : null}
                  <div>
                    <dt>生成时间</dt>
                    <dd>{formatArtifactTime(previewArtifact.createdAt)}</dd>
                  </div>
                  {previewArtifact.sizeBytes ? (
                    <div>
                      <dt>文件大小</dt>
                      <dd>{formatArtifactSize(previewArtifact.sizeBytes)}</dd>
                    </div>
                  ) : null}
                </dl>
                {previewArtifact.tags?.length ? (
                  <div className="artifact-library-preview-tags" aria-label="标签">
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
                    查看会话
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
                    编辑信息
                  </button>
                ) : null}
              </div>
              <button
                type="button"
                disabled={pendingAction.startsWith("download:") || (!userId && !items)}
                onClick={() => void download(previewArtifact)}
              >
                <DownloadArtifactIcon />
                下载
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
          title="删除产物？"
          description={`“${deleteArtifact.name}”将从产物库永久删除，聊天记录不会受到影响。`}
          confirmLabel={deleteBusy ? "删除中" : "删除"}
          closeLabel="关闭删除确认框"
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
