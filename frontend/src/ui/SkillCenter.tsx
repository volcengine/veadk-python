import { useCallback, useDeferredValue, useEffect, useId, useMemo, useRef, useState, type ReactNode, type SVGProps } from "react";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { EmptyMessage } from "@openai/apps-sdk-ui/components/EmptyMessage";
import { PlusLg18pxAdd } from "@openai/apps-sdk-ui/components/Icon";
import {
  getSkillDetail,
  listSkillsInSpacePage,
  type SkillDetail,
  type SkillSpaceRef,
  type SkillSpaceSkill,
} from "../create/skills/skillspace";
import {
  deleteSkillSpace,
  deleteManagedSkill,
  downloadManagedSkillArchive,
  getManagedSkillFiles,
  listManagedSkillSpaces,
  type ManagedSkillFile,
} from "../adk/skills";
import {
  cloudRegionOptions,
  defaultCloudRegion,
  formatCloudRegion,
  type CloudProvider,
  type CloudRegion,
} from "../adk/cloudProvider";
import { getSkillWorkbenchCapability } from "./skill-workbench/api";
import type {
  SkillCenterOptimizationSource,
  SkillWorkbenchCapability,
} from "./skill-workbench/types";
import { SkillGenerationWorkspace } from "./skills/SkillGenerationWorkspace";
import { normalizeSkillError, SkillErrorDetails } from "./skills/SkillErrorDetails";
import { SkillFileTree } from "./skills/SkillFileTree";
import { LibraryResourceCard } from "./LibraryResourceCard";
import {
  ResourceCreateCard,
  ResourceDetailLayout,
  ResourceDetailSectionHeader,
  ResourceDetailSummary,
  ResourceGrid,
  ResourceLoadingState,
  ResourceResults,
  ResourceSearch,
  ResourceToolbar,
} from "./ResourceCollection";
import {
  CreateSkillSpaceDialog,
  EditSkillSpaceDialog,
  UploadSkillDialog,
} from "./skills/SkillManagementDialogs";
import { formatRelativeTimeLabel } from "./relativeTime";
import "./skills/skills.css";

const SPACE_PAGE_SIZE = 12;
const SKILL_PAGE_SIZE = 12;

type SkillRegion = string;

interface SpaceRegionLoadState {
  nextPage: number;
  loadedCount: number;
  done: boolean;
  error: Error | null;
}

function SandboxDisabledAction({
  disabled,
  placement = "top",
  children,
}: {
  disabled: boolean;
  placement?: "top" | "bottom" | "inside";
  children: ReactNode;
}) {
  const tooltipId = useId();

  return (
    <span
      className={`skillcenter-disabled-action${disabled ? " is-disabled" : ""} is-${placement}`}
      tabIndex={disabled ? 0 : undefined}
      aria-describedby={disabled ? tooltipId : undefined}
    >
      {children}
      {disabled ? (
        <span id={tooltipId} className="skillcenter-disabled-tooltip" role="tooltip">
          管理员未配置 Dev Sandbox
        </span>
      ) : null}
    </span>
  );
}

const STATUS_LABELS: Record<string, string> = {
  active: "可用",
  available: "可用",
  creating: "创建中",
  disabled: "已停用",
  enabled: "已启用",
  failed: "异常",
  inactive: "未启用",
  pending: "等待中",
  published: "已发布",
  ready: "就绪",
  released: "已发布",
  running: "运行中",
  success: "正常",
  unavailable: "不可用",
  unreleased: "未发布",
  updating: "更新中",
};

function statusLabel(status?: string): string {
  return STATUS_LABELS[(status || "").trim().toLowerCase()] || "未知";
}

function statusTone(status?: string): string {
  const value = (status || "").toLowerCase();
  if (["active", "available", "enabled", "published", "ready", "released", "success"].includes(value)) {
    return "is-positive";
  }
  if (value === "running") return "is-positive";
  if (["creating", "pending", "updating"].includes(value)) return "is-progress";
  if (["failed", "unavailable"].includes(value)) return "is-danger";
  return "is-muted";
}

function updatedAtLabel(value?: string): string {
  if (!value) return "";
  const trimmed = value.trim();
  const numeric = Number(trimmed);
  const date = /^\d+(?:\.\d+)?$/.test(trimmed)
    ? new Date(numeric < 1_000_000_000_000 ? numeric * 1000 : numeric)
    : new Date(trimmed);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function updatedAtTimestamp(value?: string): number {
  if (!value) return 0;
  const trimmed = value.trim();
  const numeric = Number(trimmed);
  const date = /^\d+(?:\.\d+)?$/.test(trimmed)
    ? new Date(numeric < 1_000_000_000_000 ? numeric * 1000 : numeric)
    : new Date(trimmed);
  return Number.isNaN(date.getTime()) ? 0 : date.getTime();
}

function skillSpaceKey(space: SkillSpaceRef): string {
  return `${space.region || "default"}:${space.projectName || "default"}:${space.id}`;
}

function mergeSkillSpaces(current: SkillSpaceRef[], incoming: SkillSpaceRef[]): SkillSpaceRef[] {
  const byKey = new Map(current.map((space) => [skillSpaceKey(space), space]));
  for (const space of incoming) byKey.set(skillSpaceKey(space), space);
  return [...byKey.values()].sort(
    (left, right) => updatedAtTimestamp(right.updatedAt) - updatedAtTimestamp(left.updatedAt),
  );
}

function skillMarkdownBody(value: string): string {
  const normalized = value.replace(/\r\n/g, "\n");
  if (!normalized.startsWith("---\n")) return value;
  const closingDelimiter = normalized.indexOf("\n---\n", 4);
  return closingDelimiter >= 0
    ? normalized.slice(closingDelimiter + 5).trimStart()
    : value;
}

function skillDescriptionLabel(value?: string): string {
  const description = (value || "").trim();
  return !description || [">", ">-", "|", "|-"].includes(description)
    ? "暂无描述"
    : description;
}

function CloseIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="m7.5 7.5 9 9m0-9-9 9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function AddIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" {...props}>
      <path d="M12 5.5v13M5.5 12h13" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  );
}

function ArrowIcon({ direction }: { direction: "left" | "right" }) {
  return (
    <svg className="icon" viewBox="0 0 20 20" fill="none" aria-hidden>
      <path
        d={direction === "left" ? "m11.7 5.5-4.2 4.5 4.2 4.5" : "m8.3 5.5 4.2 4.5-4.2 4.5"}
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function LoadingMark() {
  return <span className="skillcenter-loading-mark" aria-hidden />;
}

function Pager({
  page,
  total,
  pageSize,
  onPage,
}: {
  page: number;
  total: number;
  pageSize: number;
  onPage: (page: number) => void;
}) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  return (
    <footer className="skillcenter-pager">
      <span>共 {total} 项</span>
      <div className="skillcenter-pager-actions">
        <button type="button" onClick={() => onPage(page - 1)} disabled={page <= 1} aria-label="上一页">
          <ArrowIcon direction="left" />
        </button>
        <span>{page} / {pageCount}</span>
        <button type="button" onClick={() => onPage(page + 1)} disabled={page >= pageCount} aria-label="下一页">
          <ArrowIcon direction="right" />
        </button>
      </div>
    </footer>
  );
}

function EmptyState({ children }: { children: string }) {
  return <div className="skillcenter-empty">{children}</div>;
}

function PageState({
  kind,
  title,
  description,
  error,
  action,
}: {
  kind: "empty" | "error";
  title: string;
  description?: string;
  error?: Error;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className={`skillcenter-page-state is-${kind}`} role={kind === "error" ? "alert" : "status"}>
      <EmptyMessage fill="none">
        <EmptyMessage.Title>{title}</EmptyMessage.Title>
        {description ? <EmptyMessage.Description>{description}</EmptyMessage.Description> : null}
        {error ? <SkillErrorDetails error={error} /> : null}
        {action ? (
          <EmptyMessage.ActionRow>
            <Button color="secondary" size="lg" onClick={action.onClick}>{action.label}</Button>
          </EmptyMessage.ActionRow>
        ) : null}
      </EmptyMessage>
    </div>
  );
}

function SpaceLoadErrors({
  errors,
  cloudProvider,
  fullPage = false,
  onRetry,
}: {
  errors: Array<{ region: string; error: Error }>;
  cloudProvider: CloudProvider;
  fullPage?: boolean;
  onRetry: () => void;
}) {
  return (
    <div
      className={`skillcenter-space-errors${fullPage ? " is-full-page" : ""}`}
      role="alert"
    >
      <div className="skillcenter-space-errors__content">
        <strong>{fullPage ? "无法加载技能空间" : "部分技能空间加载失败"}</strong>
        {errors.map(({ region, error }) => (
          <section key={region}>
            <span>{formatCloudRegion(region, cloudProvider)}</span>
            <SkillErrorDetails error={error} />
          </section>
        ))}
      </div>
      <button type="button" onClick={onRetry}>重新加载</button>
    </div>
  );
}

function SkillDetailDialog({
  skill,
  space,
  region,
  cloudProvider,
  detail,
  files,
  loading,
  error,
  canOptimize,
  onOptimize,
  onDownload,
  onClose,
}: {
  skill: SkillSpaceSkill;
  space: SkillSpaceRef;
  region: SkillRegion;
  cloudProvider: CloudProvider;
  detail: SkillDetail | null;
  files: ManagedSkillFile[];
  loading: boolean;
  error: Error | null;
  canOptimize: boolean;
  onOptimize: () => void;
  onDownload: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div className="skill-detail-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="skill-detail-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="skill-detail-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="skill-detail-head">
          <div className="skill-detail-heading">
            <div>
              <h2 id="skill-detail-title">{detail?.name || skill.skillName}</h2>
              <p>{skillDescriptionLabel(detail?.description || skill.skillDescription)}</p>
            </div>
          </div>
          <div className="skill-detail-actions">
            <button type="button" onClick={onDownload} disabled={files.length === 0}>下载 ZIP</button>
            <SandboxDisabledAction disabled={!canOptimize} placement="bottom">
              <button type="button" onClick={onOptimize} disabled={!canOptimize}>优化</button>
            </SandboxDisabledAction>
            <button type="button" className="skill-detail-close" onClick={onClose} aria-label="关闭技能详情"><CloseIcon /></button>
          </div>
        </header>

        <dl className="skill-detail-meta">
          <div><dt>技能 ID</dt><dd title={skill.skillId}>{skill.skillId}</dd></div>
          <div><dt>版本</dt><dd>{detail?.version || skill.version || "—"}</dd></div>
          <div><dt>状态</dt><dd>{statusLabel(skill.skillStatus)}</dd></div>
          <div><dt>技能空间</dt><dd title={space.name}>{space.name}</dd></div>
          <div><dt>地域</dt><dd>{formatCloudRegion(region, cloudProvider)}</dd></div>
        </dl>

        <div className="skill-detail-content skill-detail-content--files">
          <div className="skill-detail-content-title">完整文件</div>
          {loading ? (
            <div className="skillcenter-loading"><LoadingMark />正在读取技能内容…</div>
          ) : error ? (
            <div className="skillcenter-error"><SkillErrorDetails error={error} /></div>
          ) : files.length > 0 ? (
            <SkillFileTree files={files.map((file) => file.path.endsWith("SKILL.md") && file.content ? { ...file, content: skillMarkdownBody(file.content) } : file)} />
          ) : (
            <EmptyState>该技能暂无 SKILL.md 内容</EmptyState>
          )}
        </div>
      </section>
    </div>
  );
}

function AddSkillDialog({
  space,
  canUseSandbox,
  onUpload,
  onSandbox,
  onClose,
}: {
  space: SkillSpaceRef;
  canUseSandbox: boolean;
  onUpload: () => void;
  onSandbox: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div className="skill-dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="skill-dialog skill-add-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="skill-add-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header>
          <div>
            <h2 id="skill-add-dialog-title">添加技能</h2>
            <p title={space.name}>{space.name}</p>
          </div>
          <button type="button" onClick={onClose}>取消</button>
        </header>
        <div className="skill-add-dialog__options">
          <button type="button" onClick={onUpload}>
            <strong>本地上传</strong>
            <span>选择 ZIP 文件，校验通过后上传到技能空间</span>
          </button>
          <SandboxDisabledAction disabled={!canUseSandbox} placement="inside">
            <button
              type="button"
              disabled={!canUseSandbox}
              onClick={onSandbox}
            >
              <strong>自动创建</strong>
              <span>选择模型和风格，通过对话生成技能</span>
            </button>
          </SandboxDisabledAction>
        </div>
      </section>
    </div>
  );
}

export interface SkillCenterWorkspaceLaunch {
  operation: "create" | "optimize";
  initialIntent?: string;
  space?: SkillSpaceRef;
  source?: SkillCenterOptimizationSource;
  selectPublishSpace?: boolean;
}

type SkillSpaceDetailSection = "overview" | "skills";

/** Native AgentKit Skill space browser. */
export function SkillCenterView({
  cloudProvider = "volcengine",
  region,
  active = true,
  activationRevision = 0,
  initialWorkspace = null,
  onInitialWorkspaceConsumed,
  onPageTitleChange,
  toolbarLeading,
  toolbarFilters,
}: {
  cloudProvider?: CloudProvider;
  region: CloudRegion;
  active?: boolean;
  activationRevision?: number;
  initialWorkspace?: SkillCenterWorkspaceLaunch | null;
  onInitialWorkspaceConsumed?: () => void;
  onPageTitleChange?: (title: string) => void;
  toolbarLeading?: ReactNode;
  toolbarFilters?: ReactNode;
}) {
  const spaceRegions = useMemo(
    () => [region],
    [region],
  );
  const [spaces, setSpaces] = useState<SkillSpaceRef[]>([]);
  const [spaceRegionState, setSpaceRegionState] = useState<Record<string, SpaceRegionLoadState>>({});
  const [spacesLoading, setSpacesLoading] = useState(false);
  const [spaceQuery, setSpaceQuery] = useState("");
  const [selectedSpace, setSelectedSpace] = useState<SkillSpaceRef | null>(initialWorkspace?.space ?? null);
  const [skills, setSkills] = useState<SkillSpaceSkill[]>([]);
  const [skillPage, setSkillPage] = useState(1);
  const [skillTotal, setSkillTotal] = useState(0);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillsError, setSkillsError] = useState<Error | null>(null);
  const [skillQuery, setSkillQuery] = useState("");
  const [detailSection, setDetailSection] = useState<SkillSpaceDetailSection>("overview");
  const [detailSkill, setDetailSkill] = useState<SkillSpaceSkill | null>(null);
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [detailFiles, setDetailFiles] = useState<ManagedSkillFile[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<Error | null>(null);
  const [capability, setCapability] = useState<SkillWorkbenchCapability | null>(null);
  const [createSpaceOpen, setCreateSpaceOpen] = useState(false);
  const [editingSpace, setEditingSpace] = useState<SkillSpaceRef | null>(null);
  const [addingSpace, setAddingSpace] = useState<SkillSpaceRef | null>(null);
  const [uploadSpace, setUploadSpace] = useState<SkillSpaceRef | null>(null);
  const [spaceRevision, setSpaceRevision] = useState(0);
  const [skillRevision, setSkillRevision] = useState(0);
  const [deletingSkillId, setDeletingSkillId] = useState("");
  const [deletingSpaceId, setDeletingSpaceId] = useState("");
  const [actionError, setActionError] = useState<Error | null>(null);
  const [workspace, setWorkspace] = useState<SkillCenterWorkspaceLaunch | null>(initialWorkspace);
  const detailRequest = useRef(0);
  const spaceRequest = useRef(0);
  const spaceLoading = useRef(false);
  const spaceAbort = useRef<AbortController | null>(null);
  const spaceResultsRef = useRef<HTMLElement>(null);
  const spaceLoadMoreRef = useRef<HTMLDivElement>(null);
  const deferredSpaceQuery = useDeferredValue(spaceQuery);
  const deferredSkillQuery = useDeferredValue(skillQuery);
  const workspaceTitle = workspace && (selectedSpace || workspace.selectPublishSpace)
    ? workspace.operation === "create"
      ? "创建技能"
      : `优化 ${workspace.source?.name || "技能"}`
    : "";
  const pageTitle = workspaceTitle || selectedSpace?.name || "技能库";

  useEffect(() => {
    if (active) onPageTitleChange?.(pageTitle);
  }, [active, onPageTitleChange, pageTitle]);

  useEffect(() => {
    if (initialWorkspace) onInitialWorkspaceConsumed?.();
  }, [initialWorkspace, onInitialWorkspaceConsumed]);
  const visibleSpaces = useMemo(() => {
    const query = deferredSpaceQuery.trim().toLocaleLowerCase();
    if (!query) return spaces;
    return spaces.filter((space) =>
      `${space.name} ${space.description || ""} ${space.projectName || ""}`
        .toLocaleLowerCase()
        .includes(query),
    );
  }, [deferredSpaceQuery, spaces]);
  const visibleSkills = useMemo(() => {
    const query = deferredSkillQuery.trim().toLocaleLowerCase();
    if (!query) return skills;
    return skills.filter((skill) =>
      `${skill.skillName} ${skill.skillDescription || ""}`
        .toLocaleLowerCase()
        .includes(query),
    );
  }, [deferredSkillQuery, skills]);
  const selectedRegion = selectedSpace?.region || defaultCloudRegion(cloudProvider);
  const spaceErrors = useMemo(
    () => spaceRegions.flatMap((region) => {
      const error = spaceRegionState[region]?.error;
      return error ? [{ region, error }] : [];
    }),
    [spaceRegionState, spaceRegions],
  );
  const canLoadMoreSpaces = spaceRegions.some((region) => {
    const state = spaceRegionState[region];
    return Boolean(state && !state.done && !state.error);
  });
  const allSpaceRegionsFailed = spaceErrors.length === spaceRegions.length;

  useEffect(() => {
    const controller = new AbortController();
    void getSkillWorkbenchCapability(controller.signal)
      .then(setCapability)
      .catch(() => setCapability({
        enabled: false,
        reason: "管理员未配置",
        operations: ["create", "optimize"],
        models: [],
        styles: {},
      }));
    return () => controller.abort();
  }, []);

  const fetchSpacePages = useCallback(async (
    requests: Array<{ region: string; page: number }>,
    reset: boolean,
  ) => {
    if (spaceLoading.current || requests.length === 0) return;
    spaceLoading.current = true;
    setSpacesLoading(true);
    if (reset) {
      spaceAbort.current?.abort();
      setSpaces([]);
      setSpaceRegionState(Object.fromEntries(requests.map(({ region }) => [region, {
        nextPage: 1,
        loadedCount: 0,
        done: false,
        error: null,
      }])));
    }
    const controller = new AbortController();
    spaceAbort.current = controller;
    const requestId = ++spaceRequest.current;
    const results = await Promise.allSettled(requests.map(async ({ region, page }) => ({
      region,
      page,
      result: await listManagedSkillSpaces({
        region,
        page,
        pageSize: SPACE_PAGE_SIZE,
        signal: controller.signal,
      }),
    })));
    if (spaceRequest.current !== requestId) return;

    const prepared = results.map((settled, index) => {
      const request = requests[index];
      if (settled.status === "rejected") {
        return {
          request,
          error: normalizeSkillError(settled.reason, "读取技能空间失败，请稍后重试"),
          items: [] as SkillSpaceRef[],
          totalCount: 0,
        };
      }
      return {
        request,
        error: null,
        items: (settled.value.result.items || []).map((space) => ({
          ...space,
          region: space.region || settled.value.region,
        })),
        totalCount: settled.value.result.totalCount || 0,
      };
    });
    const incoming = prepared.flatMap((result) => result.items);
    setSpaceRegionState((current) => {
      const next = { ...current };
      prepared.forEach(({ request, error, items, totalCount }) => {
        const previous = next[request.region] || {
          nextPage: request.page,
          loadedCount: 0,
          done: false,
          error: null,
        };
        if (error) {
          next[request.region] = {
            ...previous,
            error,
          };
          return;
        }
        const loadedCount = previous.loadedCount + items.length;
        next[request.region] = {
          nextPage: request.page + 1,
          loadedCount,
          done: items.length === 0 || loadedCount >= totalCount,
          error: null,
        };
      });
      return next;
    });
    setSpaces((current) => mergeSkillSpaces(reset ? [] : current, incoming));
    setSelectedSpace((current) => {
      if (!current) return current;
      return incoming.find((space) => skillSpaceKey(space) === skillSpaceKey(current)) || current;
    });
    spaceLoading.current = false;
    setSpacesLoading(false);
  }, []);

  const loadMoreSpaces = useCallback(() => {
    if (spaceLoading.current) return;
    const requests = spaceRegions.flatMap((region) => {
      const state = spaceRegionState[region];
      return state && !state.done && !state.error
        ? [{ region, page: state.nextPage }]
        : [];
    });
    void fetchSpacePages(requests, false);
  }, [fetchSpacePages, spaceRegionState, spaceRegions]);

  useEffect(() => {
    closeDetail();
    setSelectedSpace(null);
    setSkills([]);
    setSkillPage(1);
  }, [cloudProvider]);

  useEffect(() => {
    if (!active) return;
    void fetchSpacePages(spaceRegions.map((region) => ({ region, page: 1 })), true);
    return () => {
      spaceRequest.current += 1;
      spaceAbort.current?.abort();
      spaceLoading.current = false;
    };
  }, [active, activationRevision, fetchSpacePages, spaceRegions, spaceRevision]);

  useEffect(() => {
    const target = spaceLoadMoreRef.current;
    const root = spaceResultsRef.current;
    if (!target || !root || !canLoadMoreSpaces || spacesLoading) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) loadMoreSpaces();
      },
      { root, rootMargin: "240px 0px", threshold: 0.01 },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [canLoadMoreSpaces, loadMoreSpaces, spacesLoading]);

  const handleSpaceResultsScroll = () => {
    const results = spaceResultsRef.current;
    if (!results || !canLoadMoreSpaces || spacesLoading) return;
    if (results.scrollHeight - results.scrollTop - results.clientHeight <= 240) {
      loadMoreSpaces();
    }
  };

  useEffect(() => {
    if (!selectedSpace) {
      setSkills([]);
      setSkillTotal(0);
      return;
    }
    let active = true;
    setSkillsLoading(true);
    setSkillsError(null);
    void listSkillsInSpacePage(selectedSpace.id, {
      region: selectedRegion,
      page: skillPage,
      pageSize: SKILL_PAGE_SIZE,
      project: selectedSpace.projectName,
    })
      .then((result) => {
        if (!active) return;
        setSkills(result.items || []);
        setSkillTotal(result.totalCount || 0);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setSkills([]);
        setSkillTotal(0);
        setSkillsError(normalizeSkillError(error, "读取技能失败，请稍后重试"));
      })
      .finally(() => {
        if (active) setSkillsLoading(false);
      });
    return () => { active = false; };
  }, [selectedRegion, selectedSpace, skillPage, skillRevision]);

  const selectSpace = (space: SkillSpaceRef) => {
    closeDetail();
    setSelectedSpace(space);
    setDetailSection("overview");
    setSkillPage(1);
    setSkillQuery("");
  };

  const closeSpace = () => {
    closeDetail();
    setSelectedSpace(null);
    setSkills([]);
    setSkillTotal(0);
    setDetailSection("overview");
    setSkillPage(1);
    setSkillQuery("");
    setActionError(null);
  };

  const closeDetail = () => {
    detailRequest.current += 1;
    setDetailSkill(null);
    setDetail(null);
    setDetailFiles([]);
    setDetailError(null);
    setDetailLoading(false);
  };

  const openDetail = async (skill: SkillSpaceSkill) => {
    if (!selectedSpace) return;
    const request = detailRequest.current + 1;
    detailRequest.current = request;
    setDetailSkill(skill);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const [result, files] = await Promise.all([
        getSkillDetail(
          selectedSpace.id,
          skill.skillId,
          skill.version,
          selectedRegion,
          selectedSpace.projectName,
          skill.skillName,
          selectedSpace.name,
        ),
        getManagedSkillFiles({
          spaceId: selectedSpace.id,
          skillId: skill.skillId,
          version: skill.version,
          region: selectedRegion,
          skillSpaceName: selectedSpace.name,
          skillName: skill.skillName,
        }),
      ]);
      if (detailRequest.current === request) {
        setDetail(result);
        setDetailFiles(files);
      }
    } catch (error) {
      if (detailRequest.current === request) {
        setDetailError(normalizeSkillError(error, "读取技能详情失败，请稍后重试"));
      }
    } finally {
      if (detailRequest.current === request) setDetailLoading(false);
    }
  };

  const optimizationSource = (skill: SkillSpaceSkill): SkillCenterOptimizationSource | undefined => {
    if (!selectedSpace) return undefined;
    return {
      kind: "skill-center",
      skillId: skill.skillId,
      version: skill.version,
      region: selectedRegion,
      projectName: selectedSpace.projectName,
      skillSpaceId: selectedSpace.id,
      skillSpaceName: selectedSpace.name,
      name: skill.skillName,
      description: skill.skillDescription,
    };
  };

  const startOptimization = (skill: SkillSpaceSkill) => {
    const source = optimizationSource(skill);
    if (!source || !capability?.enabled) return;
    closeDetail();
    setWorkspace({ operation: "optimize", source });
  };

  const removeSkill = async (skill: SkillSpaceSkill) => {
    if (!selectedSpace || !window.confirm(`确定删除整个 Skill“${skill.skillName}”吗？此操作会影响所有引用它的空间。`)) return;
    setDeletingSkillId(skill.skillId);
    setActionError(null);
    try {
      await deleteManagedSkill({
        spaceId: selectedSpace.id,
        skillId: skill.skillId,
        region: selectedRegion,
      });
      setSkillRevision((value) => value + 1);
      setSpaceRevision((value) => value + 1);
    } catch (error) {
      setActionError(normalizeSkillError(error, "删除 Skill 失败"));
    } finally {
      setDeletingSkillId("");
    }
  };

  const removeSpace = async (space: SkillSpaceRef) => {
    if (!window.confirm(`确定删除 Skill 空间“${space.name}”吗？请先确认空间中的技能已删除。`)) return;
    const key = skillSpaceKey(space);
    setDeletingSpaceId(key);
    setActionError(null);
    try {
      await deleteSkillSpace({
        spaceId: space.id,
        region: space.region || defaultCloudRegion(cloudProvider),
      });
      if (selectedSpace && skillSpaceKey(selectedSpace) === key) closeSpace();
      setSpaceRevision((value) => value + 1);
    } catch (error) {
      setActionError(normalizeSkillError(error, "删除 Skill 空间失败"));
    } finally {
      setDeletingSpaceId("");
    }
  };

  if (workspace && (selectedSpace || workspace.selectPublishSpace)) {
    return (
      <SkillGenerationWorkspace
        operation={workspace.operation}
        cloudProvider={cloudProvider}
        space={selectedSpace ?? undefined}
        availableSpaces={spaces}
        spacesLoading={spacesLoading}
        initialIntent={workspace.initialIntent}
        source={workspace.source}
        onBack={() => setWorkspace(null)}
        onPublished={() => {
          setSkillRevision((value) => value + 1);
          setSpaceRevision((value) => value + 1);
        }}
      />
    );
  }

  return (
    <section className={`skillcenter${selectedSpace ? " is-space" : " resource-collection"}`}>
      {selectedSpace ? (
        <ResourceDetailLayout
          className="skillcenter-detail"
          title={selectedSpace.name}
          description={selectedSpace.description || "管理空间中的技能并创建新的版本"}
          identitySeed={selectedSpace.name}
          backLabel="返回技能空间列表"
          onBack={closeSpace}
          sections={[
            {
              key: "overview",
              label: "概览",
              content: (
                <>
                  {actionError ? <div className="skillcenter-inline-error" role="alert"><SkillErrorDetails error={actionError} /></div> : null}
                  <section className="skillcenter-overview">
                    <ResourceDetailSummary className="skillcenter-detail-facts">
                      <div><dt>技能数量</dt><dd>{skillTotal}</dd></div>
                      <div><dt>更新时间</dt><dd>{selectedSpace.updatedAt ? updatedAtLabel(selectedSpace.updatedAt) : "—"}</dd></div>
                    </ResourceDetailSummary>
                  </section>
                </>
              ),
            },
            {
              key: "skills",
              label: "技能",
              content: (
                <>
                  {actionError ? <div className="skillcenter-inline-error" role="alert"><SkillErrorDetails error={actionError} /></div> : null}
                  <section className="skillcenter-results" aria-label={`${selectedSpace.name}中的技能`}>
                    <ResourceDetailSectionHeader
                      title="技能"
                      description={`共 ${skillTotal} 项`}
                      actions={(
                        <ResourceSearch
                          aria-label="搜索技能"
                          value={skillQuery}
                          onChange={(event) => setSkillQuery(event.target.value)}
                          placeholder="搜索技能"
                        />
                      )}
                    />
                    {skillsLoading && skills.length === 0 ? (
                      <ResourceLoadingState />
                    ) : skillsError && skills.length === 0 ? (
                      <PageState
                        kind="error"
                        title="无法加载技能"
                        error={skillsError}
                        action={{ label: "重新加载", onClick: () => setSkillRevision((value) => value + 1) }}
                      />
                    ) : visibleSkills.length === 0 ? (
                      <PageState
                        kind="empty"
                        title={skillQuery.trim() ? "没有匹配的技能" : "暂无技能"}
                        description={skillQuery.trim() ? "请尝试搜索其他名称" : "本地上传 Skill，或自动创建"}
                        action={!skillQuery.trim() ? { label: "本地上传", onClick: () => setUploadSpace(selectedSpace) } : undefined}
                      />
                    ) : (
                      <div className="skillcenter-table-wrap">
                        <table className="skillcenter-table">
                          <thead><tr><th scope="col">技能</th><th scope="col">状态</th><th scope="col" className="skillcenter-table__actions-heading">操作</th></tr></thead>
                          <tbody>
                            {visibleSkills.map((skill) => (
                              <tr key={`${skill.skillId}:${skill.version}`}>
                                <td className="skillcenter-table__skill">
                                  <button type="button" onClick={() => void openDetail(skill)}>
                                    <span className="skillcenter-table__title-row">
                                      <strong title={skill.skillName}>{skill.skillName}</strong>
                                      {skill.version ? <span className="skillcenter-table__version-badge">{skill.version}</span> : null}
                                    </span>
                                    <span className="skillcenter-table__description">{skillDescriptionLabel(skill.skillDescription)}</span>
                                  </button>
                                </td>
                                <td><span className={`skillcenter-status ${statusTone(skill.skillStatus)}`}>{statusLabel(skill.skillStatus)}</span></td>
                                <td><div className="skillcenter-table__actions">
                                  <button type="button" onClick={() => void openDetail(skill)}>查看</button>
                                  <SandboxDisabledAction disabled={!capability?.enabled}>
                                    <button type="button" disabled={!capability?.enabled} onClick={() => startOptimization(skill)}>优化</button>
                                  </SandboxDisabledAction>
                                  <button type="button" className="is-danger" disabled={deletingSkillId === skill.skillId} onClick={() => void removeSkill(skill)}>{deletingSkillId === skill.skillId ? "删除中…" : "删除"}</button>
                                </div></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                    {!skillQuery.trim() && !skillsLoading && !skillsError && skillTotal > 0 ? (
                      <Pager page={skillPage} total={skillTotal} pageSize={SKILL_PAGE_SIZE} onPage={setSkillPage} />
                    ) : null}
                  </section>
                </>
              ),
            },
          ]}
          activeSectionKey={detailSection}
          navigationLabel="技能空间详情"
          onSectionChange={(key) => setDetailSection(key as SkillSpaceDetailSection)}
          actionsClassName="skillcenter-toolbar-actions"
          actions={(
            <>
              <Button
                type="button"
                color="secondary"
                variant="outline"
                size="lg"
                pill={false}
                onClick={() => setEditingSpace(selectedSpace)}
              >
                编辑空间
              </Button>
              <Button
                type="button"
                color="danger"
                variant="soft"
                size="lg"
                pill={false}
                disabled={deletingSpaceId === skillSpaceKey(selectedSpace)}
                onClick={() => void removeSpace(selectedSpace)}
              >
                {deletingSpaceId === skillSpaceKey(selectedSpace) ? "删除中…" : "删除空间"}
              </Button>
              <Button type="button" color="secondary" variant="outline" size="lg" pill={false} onClick={() => setUploadSpace(selectedSpace)}>本地上传</Button>
              <SandboxDisabledAction disabled={!capability?.enabled}>
                <Button
                  type="button"
                  color="primary"
                  size="lg"
                  pill={false}
                  disabled={!capability?.enabled}
                  onClick={() => setWorkspace({ operation: "create" })}
                >
                  <PlusLg18pxAdd aria-hidden="true" />
                  <span>创建技能</span>
                </Button>
              </SandboxDisabledAction>
            </>
          )}
        />
      ) : (
        <>
          <ResourceToolbar className="skillcenter-list-toolbar library-resource-toolbar">
            {toolbarLeading}
            <div className="resource-toolbar__actions">
              {toolbarFilters}
              <ResourceSearch
                aria-label="搜索技能空间"
                value={spaceQuery}
                onChange={(event) => setSpaceQuery(event.target.value)}
                placeholder="搜索技能空间"
              />
            </div>
          </ResourceToolbar>

          {actionError ? <div className="skillcenter-inline-error" role="alert"><SkillErrorDetails error={actionError} /></div> : null}

          <ResourceResults
            className="skillcenter-list-results"
            ref={spaceResultsRef}
            aria-label="技能空间列表"
            onScroll={handleSpaceResultsScroll}
          >
            {spaceErrors.length > 0 && !allSpaceRegionsFailed ? (
              <SpaceLoadErrors
                errors={spaceErrors}
                cloudProvider={cloudProvider}
                onRetry={() => setSpaceRevision((value) => value + 1)}
              />
            ) : null}
            {spacesLoading && spaces.length === 0 ? (
              <ResourceLoadingState />
            ) : allSpaceRegionsFailed && spaces.length === 0 ? (
              <SpaceLoadErrors
                errors={spaceErrors}
                cloudProvider={cloudProvider}
                fullPage
                onRetry={() => setSpaceRevision((value) => value + 1)}
              />
            ) : visibleSpaces.length === 0 && spaceQuery.trim() ? (
              <PageState
                kind="empty"
                title="没有匹配的技能空间"
                description="请尝试搜索其他名称"
              />
            ) : (
              <ResourceGrid>
                {!spaceQuery.trim() ? (
                  <ResourceCreateCard
                    aria-label="新建技能空间"
                    icon={<AddIcon />}
                    onClick={() => setCreateSpaceOpen(true)}
                  >
                    新建空间
                  </ResourceCreateCard>
                ) : null}
                  {visibleSpaces.map((space) => {
                    const spaceKey = skillSpaceKey(space);
                    return (
                  <LibraryResourceCard
                    key={spaceKey}
                    className="skillcenter-space-card"
                    title={space.name}
                    description={space.description || "暂无描述"}
                    metadata={[
                      { label: "技能数量", value: `${space.skillCount ?? 0} 技能` },
                      { label: "更新时间", value: formatRelativeTimeLabel(space.updatedAt) },
                    ]}
                    action={{ label: "添加技能", icon: "plus", onClick: () => setAddingSpace(space) }}
                    detailAction={{ label: "查看详情", onClick: () => selectSpace(space) }}
                  />
                    );
                  })}
              </ResourceGrid>
            )}
            {!allSpaceRegionsFailed && spaces.length > 0 ? (
              <div className="my-agent-load-more" ref={spaceLoadMoreRef} aria-live="polite">
                {spacesLoading ? (
                  <>
                    <span className="my-agent-loading-mark" aria-hidden="true" />
                    <span>正在加载更多技能空间</span>
                  </>
                ) : canLoadMoreSpaces ? (
                  <span>继续下滑加载更多</span>
                ) : spaceErrors.length > 0 ? (
                  <span>部分技能空间加载失败</span>
                ) : (
                  <span>已加载全部技能空间</span>
                )}
              </div>
            ) : null}
          </ResourceResults>
        </>
      )}

      {detailSkill && selectedSpace && (
        <SkillDetailDialog
          skill={detailSkill}
          space={selectedSpace}
          region={selectedRegion}
          cloudProvider={cloudProvider}
          detail={detail}
          files={detailFiles}
          loading={detailLoading}
          error={detailError}
          canOptimize={capability?.enabled === true}
          onOptimize={() => startOptimization(detailSkill)}
          onDownload={() => void downloadManagedSkillArchive({
            spaceId: selectedSpace.id,
            skillId: detailSkill.skillId,
            version: detailSkill.version,
            region: selectedRegion,
            fallbackName: detailSkill.skillName,
            skillSpaceName: selectedSpace.name,
            skillName: detailSkill.skillName,
          }).catch((error: unknown) => setDetailError(normalizeSkillError(error, "下载 Skill 失败")))}
          onClose={closeDetail}
        />
      )}
      {createSpaceOpen ? (
        <CreateSkillSpaceDialog
          region={region}
          regionOptions={cloudRegionOptions(cloudProvider)}
          onClose={() => setCreateSpaceOpen(false)}
          onCreated={(space) => {
            setCreateSpaceOpen(false);
            setSpaceRevision((value) => value + 1);
            setSelectedSpace({
              ...space,
              region: space.region || region,
            });
          }}
        />
      ) : null}
      {editingSpace ? (
        <EditSkillSpaceDialog
          space={editingSpace}
          region={editingSpace.region || defaultCloudRegion(cloudProvider)}
          onClose={() => setEditingSpace(null)}
          onUpdated={(space) => {
            const updatedSpace = {
              ...space,
              region: space.region || editingSpace.region || defaultCloudRegion(cloudProvider),
            };
            setEditingSpace(null);
            setSelectedSpace((current) => current && skillSpaceKey(current) === skillSpaceKey(updatedSpace)
              ? updatedSpace
              : current);
            setSpaces((items) => items.map((item) => skillSpaceKey(item) === skillSpaceKey(updatedSpace)
              ? updatedSpace
              : item));
            setSpaceRevision((value) => value + 1);
          }}
        />
      ) : null}
      {addingSpace ? (
        <AddSkillDialog
          space={addingSpace}
          canUseSandbox={capability?.enabled === true}
          onClose={() => setAddingSpace(null)}
          onUpload={() => {
            setUploadSpace(addingSpace);
            setAddingSpace(null);
          }}
          onSandbox={() => {
            const space = addingSpace;
            setAddingSpace(null);
            selectSpace(space);
            setWorkspace({ operation: "create" });
          }}
        />
      ) : null}
      {uploadSpace ? (
        <UploadSkillDialog
          space={uploadSpace}
          region={uploadSpace.region || defaultCloudRegion(cloudProvider)}
          onClose={() => setUploadSpace(null)}
          onUploaded={() => {
            setUploadSpace(null);
            setSkillRevision((value) => value + 1);
            setSpaceRevision((value) => value + 1);
          }}
        />
      ) : null}
    </section>
  );
}
