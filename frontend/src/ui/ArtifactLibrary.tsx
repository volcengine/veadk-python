import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  downloadArtifact as downloadAdkArtifact,
  previewArtifact as previewAdkArtifact,
} from "../adk/client";
import {
  CloseLibraryIcon,
  DocumentArtifactIcon,
  DownloadArtifactIcon,
  ImageArtifactIcon,
  PreviewArtifactIcon,
  SearchLibraryIcon,
  VideoArtifactIcon,
} from "./icons/LibraryIcons";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import {
  collectArtifactLibraryItems,
  formatArtifactTime,
  type ArtifactLibraryItem,
  type ArtifactSessionSource,
  type ArtifactType,
} from "./artifactLibraryModel";
import "./ArtifactLibrary.css";

export interface ArtifactLibraryProps {
  sources?: readonly ArtifactSessionSource[];
  userId?: string;
  active?: boolean;
  activationRevision?: number;
  loading?: boolean;
  error?: string;
  onRetry?: () => void;
}

const ARTIFACT_BATCH_SIZE = 40;

const ARTIFACT_TYPES: Array<{ id: ArtifactType; label: string }> = [
  { id: "document", label: "文档" },
  { id: "image", label: "图片" },
  { id: "video", label: "视频" },
];

const ARTIFACT_LABELS: Record<ArtifactType, string> = {
  document: "文档",
  image: "图片",
  video: "视频",
};

function messageFrom(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}

function ArtifactTypeIcon({ type }: { type: ArtifactType }) {
  if (type === "document") return <DocumentArtifactIcon />;
  if (type === "image") return <ImageArtifactIcon />;
  return <VideoArtifactIcon />;
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
      {artifact.type === "document" ? (
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
}: {
  artifact: ArtifactLibraryItem;
  pendingAction: string;
  disabled: boolean;
  onPreview: (artifact: ArtifactLibraryItem) => void;
  onDownload: (artifact: ArtifactLibraryItem) => void;
}) {
  const previewPending = pendingAction === `preview:${artifact.id}`;
  const downloadPending = pendingAction === `download:${artifact.id}`;
  return (
    <article className="library-artifact-row">
      <div className="library-artifact-thumbnail">
        <ArtifactVisual artifact={artifact} />
      </div>
      <div className="library-artifact-row-body">
        <div className="library-artifact-row-title">
          <span className="library-artifact-card-icon">
            <ArtifactTypeIcon type={artifact.type} />
          </span>
          <h3 title={artifact.name}>{artifact.name}</h3>
          <span className="artifact-type-badge">{ARTIFACT_LABELS[artifact.type]}</span>
        </div>
        <div className="library-artifact-row-meta">
          <span title={artifact.sessionTitle}>来自会话：{artifact.sessionTitle}</span>
          <span>{formatArtifactTime(artifact.createdAt)}</span>
          <span aria-hidden="true">·</span>
          <span>版本 {artifact.version}</span>
        </div>
      </div>
      <div className="library-artifact-actions">
        <button
          type="button"
          className="library-artifact-action"
          aria-label={`预览 ${artifact.name}`}
          disabled={disabled || Boolean(pendingAction)}
          onClick={() => onPreview(artifact)}
        >
          {previewPending ? (
            <TextShimmer as="span" className="library-artifact-pending">加载中</TextShimmer>
          ) : (
            <>
              <PreviewArtifactIcon />
              <span>预览</span>
            </>
          )}
        </button>
        <button
          type="button"
          className="library-artifact-action is-primary"
          aria-label={`下载 ${artifact.name}`}
          disabled={disabled || Boolean(pendingAction)}
          onClick={() => onDownload(artifact)}
        >
          {downloadPending ? (
            <TextShimmer as="span" className="library-artifact-pending">下载中</TextShimmer>
          ) : (
            <>
              <DownloadArtifactIcon />
              <span>下载</span>
            </>
          )}
        </button>
      </div>
    </article>
  );
}

export function ArtifactLibrary({
  sources = [],
  userId = "",
  active = true,
  activationRevision = 0,
  loading = false,
  error = "",
  onRetry,
}: ArtifactLibraryProps) {
  const [activeType, setActiveType] = useState<ArtifactType | null>(null);
  const [query, setQuery] = useState("");
  const [previewArtifact, setPreviewArtifact] = useState<ArtifactLibraryItem | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [pendingAction, setPendingAction] = useState("");
  const [actionError, setActionError] = useState("");
  const [status, setStatus] = useState("");
  const [visibleCount, setVisibleCount] = useState(ARTIFACT_BATCH_SIZE);
  const closePreviewButtonRef = useRef<HTMLButtonElement>(null);
  const requestGenerationRef = useRef(0);
  const resultsRef = useRef<HTMLElement>(null);
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const batchAdvancingRef = useRef(false);

  const artifacts = useMemo(() => collectArtifactLibraryItems(sources), [sources]);

  useEffect(() => () => {
    requestGenerationRef.current += 1;
  }, []);

  useEffect(() => () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  useEffect(() => {
    if (!previewArtifact) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    closePreviewButtonRef.current?.focus();
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        setPreviewArtifact(null);
        setPreviewUrl("");
      }
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      previouslyFocused?.focus();
    };
  }, [previewArtifact]);

  const closePreview = () => {
    requestGenerationRef.current += 1;
    setPreviewArtifact(null);
    setPreviewUrl("");
    setPendingAction("");
  };

  const openPreview = async (artifact: ArtifactLibraryItem) => {
    const generation = requestGenerationRef.current + 1;
    requestGenerationRef.current = generation;
    setActionError("");
    setPreviewUrl("");
    setPreviewArtifact(artifact);
    if (artifact.preview.mode === "unavailable") return;
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
      await downloadAdkArtifact(
        artifact.appName,
        userId,
        artifact.sessionId,
        artifact.name,
        artifact.version,
      );
      setStatus(`已开始下载 ${artifact.name}`);
    } catch (reason) {
      setActionError(`无法下载“${artifact.name}”：${messageFrom(reason)}`);
    } finally {
      setPendingAction("");
    }
  };

  const visibleArtifacts = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return artifacts.filter((artifact) => {
      if (activeType && artifact.type !== activeType) {
        return false;
      }
      if (!normalizedQuery) return true;
      return [artifact.name, artifact.sessionTitle, artifact.agentName]
        .some((value) => value.toLocaleLowerCase().includes(normalizedQuery));
    });
  }, [activeType, artifacts, query]);

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

  const hasSearchOrFilter = Boolean(query.trim()) || activeType !== null;

  return (
    <div className="artifact-library-page">
      <div className="artifact-library-toolbar library-resource-toolbar">
        <nav className="artifact-type-pills" aria-label="产物类型">
          {ARTIFACT_TYPES.map((type) => (
            <button
              key={type.id}
              type="button"
              className={`artifact-type-pill${activeType === type.id ? " is-active" : ""}`}
              aria-pressed={activeType === type.id}
              onClick={() => setActiveType((current) => current === type.id ? null : type.id)}
            >
              {type.label}
            </button>
          ))}
        </nav>
        <label className="artifact-library-search">
          <SearchLibraryIcon />
          <input
            type="search"
            aria-label="搜索产物"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索产物或会话"
          />
        </label>
      </div>

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

      <section
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
              {displayedArtifacts.map((artifact) => (
                  <ArtifactRow
                    key={artifact.id}
                    artifact={artifact}
                    pendingAction={pendingAction}
                  disabled={!userId}
                  onPreview={(item) => void openPreview(item)}
                  onDownload={(item) => void download(item)}
                />
              ))}
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
      </section>

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
          <div className="artifact-library-preview-panel">
            <header>
              <div>
                <h2 id="artifact-library-preview-title">{previewArtifact.name}</h2>
                <p>
                  {ARTIFACT_LABELS[previewArtifact.type]} · 版本 {previewArtifact.version}
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
            <footer>
              <button
                type="button"
                disabled={pendingAction.startsWith("download:") || !userId}
                onClick={() => void download(previewArtifact)}
              >
                <DownloadArtifactIcon />
                下载
              </button>
            </footer>
          </div>
        </div>
      ) : null}
    </div>
  );
}
