import { useEffect, useRef, useState } from "react";
import {
  getSkillDetail,
  listSkillSpacesPage,
  listSkillsInSpacePage,
  type SkillDetail,
  type SkillSpaceRef,
  type SkillSpaceSkill,
} from "../create/skills/skillspace";
import {
  cloudRegionOptions,
  defaultCloudRegion,
  formatCloudRegion,
  type CloudProvider,
} from "../adk/cloudProvider";
import { CodeBrowserWorkspace } from "./CodeBrowserDialog";
import { isImeCompositionEvent } from "./composerKeyboard";
import { getSkillWorkbenchCapability } from "./skill-workbench/api";
import type {
  SkillCenterOptimizationSource,
  SkillWorkbenchCapability,
  SkillWorkbenchOperation,
  SkillWorkbenchPublishResult,
  SkillWorkbenchTask,
} from "./skill-workbench/types";
import type { StartSkillWorkbenchTaskArgs } from "./skill-workbench/useSkillWorkbenchTasks";

const SPACE_PAGE_SIZE = 6;
const SKILL_PAGE_SIZE = 7;

type SkillRegion = string;

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
  if (["creating", "pending", "running", "updating"].includes(value)) return "is-progress";
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

/** Hand-drawn Skill Space mark: two connected shelves for a skill collection. */
export function SkillSpaceIcon({ className = "icon" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M5.25 7.5h5.25v5.25H5.25zM13.5 7.5h5.25v5.25H13.5zM9.38 15.75h5.24v3H9.38z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M7.88 12.75v1.5c0 .83.67 1.5 1.5 1.5h5.24c.83 0 1.5-.67 1.5-1.5v-1.5M12 4.75V7.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="12" cy="4.75" r="1" fill="currentColor" />
    </svg>
  );
}

/** Hand-drawn Skill mark: a compact instruction card with an activation spark. */
function SkillIcon({ className = "icon" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M6.25 4.75h8.6l2.9 2.9v11.6h-11.5z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M14.75 4.9v3h2.85M8.9 11.1h4.2M8.9 14h5.7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="m17.85 13.85.42 1.13 1.13.42-1.13.42-.42 1.13-.42-1.13-1.13-.42 1.13-.42z" fill="currentColor" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="m7.5 7.5 9 9m0-9-9 9" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
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

function ComposerSendIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 18V6m0 0-4.5 4.5M12 6l4.5 4.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ComposerUploadIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 16.5V5m0 0L8.5 8.5M12 5l3.5 3.5M5.5 14.5v3.25c0 .97.78 1.75 1.75 1.75h9.5c.97 0 1.75-.78 1.75-1.75V14.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SkillCenterComposer({
  operation,
  setOperation,
  source,
  setSource,
  file,
  setFile,
  intent,
  setIntent,
  capability,
  busy,
  error,
  onError,
  composerRef,
  onStartTask,
}: {
  operation: SkillWorkbenchOperation;
  setOperation: (operation: SkillWorkbenchOperation) => void;
  source: SkillCenterOptimizationSource | null;
  setSource: (source: SkillCenterOptimizationSource | null) => void;
  file: File | null;
  setFile: (file: File | null) => void;
  intent: string;
  setIntent: (intent: string) => void;
  capability: SkillWorkbenchCapability | null;
  busy: boolean;
  error: string;
  onError: (message: string) => void;
  composerRef: React.RefObject<HTMLTextAreaElement | null>;
  onStartTask?: (args: StartSkillWorkbenchTaskArgs) => Promise<SkillWorkbenchTask>;
}) {
  const hasSource = Boolean(source || file);
  const canSubmit = Boolean(
    onStartTask &&
    capability?.enabled &&
    intent.trim() &&
    (operation === "create" || hasSource) &&
    !busy,
  );

  const submit = () => {
    if (!canSubmit || !onStartTask) return;
    void onStartTask({
      operation,
      intent: intent.trim(),
      ...(source ? { source } : {}),
      ...(file ? { file } : {}),
    }).catch(() => {
      // The persistent task controller exposes the same failure in the workbench.
    });
  };

  return (
    <section className="skillcenter-composer-wrap" aria-label="创建或优化 Skill">
      <div className="skillcenter-composer-head">
        <h1>技能中心</h1>
        <div className="skillcenter-composer-modes" role="radiogroup" aria-label="Skill 操作">
          {(["create", "optimize"] as const).map((value) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={operation === value}
              className={operation === value ? "is-active" : ""}
              onClick={() => {
                setOperation(value);
                if (value === "create") {
                  setSource(null);
                  setFile(null);
                }
                requestAnimationFrame(() => composerRef.current?.focus());
              }}
            >
              {value === "create" ? "创建 Skill" : "优化 Skill"}
            </button>
          ))}
        </div>
      </div>

      <div className="composer composer--new-chat skillcenter-composer">
        <div className="composer-box">
          {operation === "optimize" ? (
            <div className="skillcenter-composer-source">
              {source ? (
                <button
                  type="button"
                  className="skillcenter-source-chip"
                  onClick={() => setSource(null)}
                  title="移除所选 Skill"
                >
                  <SkillIcon />
                  <span>{source.name}</span>
                  <small>v{source.version}</small>
                  <CloseIcon />
                </button>
              ) : file ? (
                <button
                  type="button"
                  className="skillcenter-source-chip"
                  onClick={() => setFile(null)}
                  title="移除 ZIP"
                >
                  <ComposerUploadIcon />
                  <span>{file.name}</span>
                  <CloseIcon />
                </button>
              ) : (
                <span>选择下方 Skill，或上传 ZIP</span>
              )}
            </div>
          ) : null}
          <div className="composer-input-stack">
            <textarea
              ref={composerRef}
              className="comp-input scroll"
              rows={4}
              maxLength={20_000}
              value={intent}
              disabled={busy || capability?.enabled === false}
              placeholder={operation === "create"
                ? "描述你希望创建的 Skill…"
                : "描述希望如何优化这个 Skill…"}
              onChange={(event) => setIntent(event.target.value)}
              onKeyDown={(event) => {
                if (isImeCompositionEvent(event.nativeEvent)) return;
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  submit();
                }
              }}
            />
          </div>
          {operation === "optimize" ? (
            <label className="skillcenter-composer-upload" title="上传 ZIP">
              <ComposerUploadIcon />
              <span>上传 ZIP</span>
              <input
                type="file"
                accept=".zip,application/zip"
                disabled={busy}
                onChange={(event) => {
                  const nextFile = event.target.files?.[0] ?? null;
                  if (
                    nextFile &&
                    capability?.maxUploadBytes &&
                    nextFile.size > capability.maxUploadBytes
                  ) {
                    const limitMiB = capability.maxUploadBytes / (1024 * 1024);
                    onError(`Skill ZIP 不能超过 ${limitMiB} MiB`);
                    event.target.value = "";
                    return;
                  }
                  setFile(nextFile);
                  if (nextFile) {
                    setSource(null);
                    onError("");
                  }
                  event.target.value = "";
                  requestAnimationFrame(() => composerRef.current?.focus());
                }}
              />
            </label>
          ) : null}
          <button
            type="button"
            className="comp-send"
            disabled={!canSubmit}
            onClick={submit}
            aria-label={operation === "create" ? "开始创建 Skill" : "开始优化 Skill"}
          >
            <ComposerSendIcon />
          </button>
        </div>
      </div>
      {capability?.enabled === false ? (
        <div className="skillcenter-composer-error" role="alert">{capability.reason || "DevEnv 暂不可用"}</div>
      ) : error ? (
        <div className="skillcenter-composer-error" role="alert">{error}</div>
      ) : null}
    </section>
  );
}

function SkillDetailDialog({
  skill,
  space,
  region,
  cloudProvider,
  detail,
  loading,
  error,
  onClose,
  onOptimize,
}: {
  skill: SkillSpaceSkill;
  space: SkillSpaceRef;
  region: SkillRegion;
  cloudProvider: CloudProvider;
  detail: SkillDetail | null;
  loading: boolean;
  error: string;
  onClose: () => void;
  onOptimize?: (source: SkillCenterOptimizationSource) => void;
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
            <span className="skillcenter-symbol skillcenter-symbol--skill"><SkillIcon /></span>
            <div>
              <h2 id="skill-detail-title">{detail?.name || skill.skillName}</h2>
              <p>{detail?.description || skill.skillDescription || "暂无描述"}</p>
            </div>
          </div>
          <div className="skill-detail-actions">
            {onOptimize ? (
              <button
                type="button"
                className="skillcenter-primary-action"
                onClick={() => onOptimize({
                  kind: "skill-center",
                  skillId: skill.skillId,
                  version: detail?.version || skill.version,
                  region,
                  projectName: space.projectName,
                  skillSpaceId: space.id,
                  name: detail?.name || skill.skillName,
                  description: detail?.description || skill.skillDescription,
                })}
              >
                优化 Skill
              </button>
            ) : null}
            <button type="button" className="skill-detail-close" onClick={onClose} aria-label="关闭技能详情">
              <CloseIcon />
            </button>
          </div>
        </header>

        <dl className="skill-detail-meta">
          <div><dt>技能 ID</dt><dd title={skill.skillId}>{skill.skillId}</dd></div>
          <div><dt>版本</dt><dd>{detail?.version || skill.version || "—"}</dd></div>
          <div><dt>状态</dt><dd>{statusLabel(skill.skillStatus)}</dd></div>
          <div><dt>技能空间</dt><dd title={space.name}>{space.name}</dd></div>
          <div><dt>Project</dt><dd title={space.projectName || "default"}>{space.projectName || "default"}</dd></div>
          <div><dt>地域</dt><dd>{formatCloudRegion(region, cloudProvider)}</dd></div>
        </dl>

        <div className="skill-detail-content">
          {loading ? (
            <div className="skillcenter-loading"><LoadingMark />正在读取技能内容…</div>
          ) : error ? (
            <div className="skillcenter-error">{error}</div>
          ) : detail?.skillMd ? (
            <CodeBrowserWorkspace
              project={{
                name: detail.name || skill.skillName,
                files: detail.files?.length
                  ? detail.files
                  : [{ path: "SKILL.md", content: detail.skillMd }],
              }}
              readOnly
            />
          ) : (
            <EmptyState>该技能暂无 SKILL.md 内容</EmptyState>
          )}
        </div>
      </section>
    </div>
  );
}

/** Sidebar entry that opens the skill center view in the main panel. */
export function SkillCenterButton({ onClick }: { onClick: () => void }) {
  return (
    <button className="new-chat" onClick={onClick} aria-label="技能中心" title="技能中心">
      <SkillSpaceIcon />
      <span className="sidebar-nav-label">技能中心</span>
    </button>
  );
}

/** Native AgentKit Skill space browser. */
export function SkillCenterView({
  cloudProvider = "volcengine",
  onStartTask,
  focus,
  onFocusHandled,
}: {
  cloudProvider?: CloudProvider;
  onStartTask?: (args: StartSkillWorkbenchTaskArgs) => Promise<SkillWorkbenchTask>;
  focus?: SkillWorkbenchPublishResult | null;
  onFocusHandled?: () => void;
}) {
  const [operation, setOperation] = useState<SkillWorkbenchOperation>("create");
  const [source, setSource] = useState<SkillCenterOptimizationSource | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [intent, setIntent] = useState("");
  const [capability, setCapability] = useState<SkillWorkbenchCapability | null>(null);
  const [composerBusy, setComposerBusy] = useState(false);
  const [composerError, setComposerError] = useState("");
  const regionOptions = cloudRegionOptions(cloudProvider);
  const [region, setRegion] = useState<SkillRegion>(
    focus?.region ?? defaultCloudRegion(cloudProvider),
  );
  const [spaces, setSpaces] = useState<SkillSpaceRef[]>([]);
  const [spacePage, setSpacePage] = useState(1);
  const [spaceTotal, setSpaceTotal] = useState(0);
  const [spacesLoading, setSpacesLoading] = useState(false);
  const [spacesError, setSpacesError] = useState("");
  const [selectedSpace, setSelectedSpace] = useState<SkillSpaceRef | null>(null);
  const [skills, setSkills] = useState<SkillSpaceSkill[]>([]);
  const [skillPage, setSkillPage] = useState(1);
  const [skillTotal, setSkillTotal] = useState(0);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const [skillsError, setSkillsError] = useState("");
  const [detailSkill, setDetailSkill] = useState<SkillSpaceSkill | null>(null);
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const detailRequest = useRef(0);
  const handledFocus = useRef("");
  const composerRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    void getSkillWorkbenchCapability(controller.signal)
      .then(setCapability)
      .catch((cause) => {
        if (!controller.signal.aborted) {
          setComposerError(cause instanceof Error ? cause.message : String(cause));
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!focus) return;
    const key = `${focus.region}:${focus.skillSpaceIds[0] || ""}:${focus.skillId}:${focus.version}`;
    if (handledFocus.current === key) return;
    setRegion(focus.region);
    setSpacePage(1);
    setSkillPage(1);
    setSelectedSpace(null);
    setSkills([]);
    closeDetail();
  }, [focus]);

  useEffect(() => {
    if (regionOptions.some((option) => option.value === region)) return;
    closeDetail();
    setRegion(defaultCloudRegion(cloudProvider));
    setSpacePage(1);
    setSkillPage(1);
    setSelectedSpace(null);
    setSkills([]);
  }, [cloudProvider, region, regionOptions]);

  useEffect(() => {
    let active = true;
    setSpacesLoading(true);
    setSpacesError("");
    void listSkillSpacesPage({ region, page: spacePage, pageSize: SPACE_PAGE_SIZE })
      .then((result) => {
        if (!active) return;
        const items = result.items || [];
        setSpaces(items);
        setSpaceTotal(result.totalCount || 0);
        setSelectedSpace((current) => {
          const focusedSpaceId = focus?.region === region ? focus.skillSpaceIds[0] : "";
          return items.find((space) => space.id === focusedSpaceId)
            || items.find((space) => space.id === current?.id)
            || items[0]
            || null;
        });
      })
      .catch((error: unknown) => {
        if (!active) return;
        setSpaces([]);
        setSpaceTotal(0);
        setSelectedSpace(null);
        setSpacesError(error instanceof Error ? error.message : "读取技能空间失败，请稍后重试");
      })
      .finally(() => {
        if (active) setSpacesLoading(false);
      });
    return () => { active = false; };
  }, [focus, region, spacePage]);

  useEffect(() => {
    if (!selectedSpace) {
      setSkills([]);
      setSkillTotal(0);
      return;
    }
    let active = true;
    setSkillsLoading(true);
    setSkillsError("");
    void listSkillsInSpacePage(selectedSpace.id, {
      region,
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
        setSkillsError(error instanceof Error ? error.message : "读取技能失败，请稍后重试");
      })
      .finally(() => {
        if (active) setSkillsLoading(false);
      });
    return () => { active = false; };
  }, [region, selectedSpace, skillPage]);

  const changeRegion = (nextRegion: SkillRegion) => {
    if (nextRegion === region) return;
    closeDetail();
    setRegion(nextRegion);
    setSpacePage(1);
    setSkillPage(1);
    setSelectedSpace(null);
    setSkills([]);
  };

  const selectSpace = (space: SkillSpaceRef) => {
    closeDetail();
    setSelectedSpace(space);
    setSkillPage(1);
  };

  const closeDetail = () => {
    detailRequest.current += 1;
    setDetailSkill(null);
    setDetail(null);
    setDetailError("");
    setDetailLoading(false);
  };

  const openDetail = async (skill: SkillSpaceSkill) => {
    if (!selectedSpace) return;
    const request = detailRequest.current + 1;
    detailRequest.current = request;
    setDetailSkill(skill);
    setDetail(null);
    setDetailError("");
    setDetailLoading(true);
    try {
      const result = await getSkillDetail(
        selectedSpace.id,
        skill.skillId,
        skill.version,
        region,
        selectedSpace.projectName,
      );
      if (detailRequest.current === request) setDetail(result);
    } catch (error) {
      if (detailRequest.current === request) {
        setDetailError(error instanceof Error ? error.message : "读取技能详情失败，请稍后重试");
      }
    } finally {
      if (detailRequest.current === request) setDetailLoading(false);
    }
  };

  useEffect(() => {
    if (!focus || !selectedSpace || selectedSpace.id !== focus.skillSpaceIds[0]) return;
    const key = `${focus.region}:${selectedSpace.id}:${focus.skillId}:${focus.version}`;
    if (handledFocus.current === key) return;
    const skill = skills.find((item) => item.skillId === focus.skillId);
    if (!skill) return;
    handledFocus.current = key;
    void openDetail(skill);
    onFocusHandled?.();
  }, [focus, onFocusHandled, selectedSpace, skills]);

  const chooseOptimizationSource = (nextSource: SkillCenterOptimizationSource) => {
    setOperation("optimize");
    setSource(nextSource);
    setFile(null);
    closeDetail();
    requestAnimationFrame(() => composerRef.current?.focus());
  };

  const startTask = async (args: StartSkillWorkbenchTaskArgs) => {
    if (!onStartTask || composerBusy) throw new Error("Skill 会话当前不可用。");
    setComposerBusy(true);
    setComposerError("");
    try {
      return await onStartTask(args);
    } catch (cause) {
      setComposerError(cause instanceof Error ? cause.message : String(cause));
      throw cause;
    } finally {
      setComposerBusy(false);
    }
  };

  return (
    <section className="skillcenter">
      <SkillCenterComposer
        operation={operation}
        setOperation={setOperation}
        source={source}
        setSource={setSource}
        file={file}
        setFile={setFile}
        intent={intent}
        setIntent={setIntent}
        capability={capability}
        busy={composerBusy}
        error={composerError}
        onError={setComposerError}
        composerRef={composerRef}
        onStartTask={startTask}
      />
      <div className="skillcenter-browser">
          <section className="skillcenter-panel" aria-label="技能空间列表">
            <header className="skillcenter-panel-head">
              <div>
                <h2>技能空间</h2>
                <span className="skillcenter-count-badge">{spaceTotal}</span>
              </div>
              <div className="skillcenter-regions" aria-label="地域">
                {regionOptions.map((option) => (
                  <button
                    type="button"
                    key={option.value}
                    className={region === option.value ? "active" : ""}
                    onClick={() => changeRegion(option.value)}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </header>
            <div className="skillcenter-listwrap">
              {spacesLoading && <div className="skillcenter-loading skillcenter-loading--overlay"><LoadingMark />正在读取技能空间…</div>}
              {spacesError ? (
                <div className="skillcenter-error">{spacesError}</div>
              ) : spaces.length === 0 && !spacesLoading ? (
                <EmptyState>当前地域暂无可访问的技能空间</EmptyState>
              ) : (
                <div className="skillcenter-list">
                  {spaces.map((space) => (
                    <button
                      type="button"
                      key={`${space.projectName || "default"}:${space.id}`}
                      className={`skillcenter-space-item ${selectedSpace?.id === space.id ? "active" : ""}`}
                      onClick={() => selectSpace(space)}
                    >
                      <span className="skillcenter-item-body">
                        <span className="skillcenter-item-title" title={space.name}>{space.name}</span>
                        <span className="skillcenter-item-description">{space.description || "暂无描述"}</span>
                        <span className="skillcenter-item-meta">
                          <span className={`skillcenter-status ${statusTone(space.status)}`}>{statusLabel(space.status)}</span>
                          <span className="skillcenter-meta-text" title={space.projectName || "default"}>Project · {space.projectName || "default"}</span>
                          <span className="skillcenter-meta-text">{space.skillCount ?? 0} 个技能</span>
                          {space.updatedAt && <span className="skillcenter-meta-text">更新于 {updatedAtLabel(space.updatedAt)}</span>}
                        </span>
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <Pager page={spacePage} total={spaceTotal} pageSize={SPACE_PAGE_SIZE} onPage={setSpacePage} />
          </section>

          <section className="skillcenter-panel" aria-label="技能列表">
            {!selectedSpace ? (
              <EmptyState>点击 Skill 空间以查看详情</EmptyState>
            ) : (
              <>
                <header className="skillcenter-panel-head">
                  <div><h2 title={selectedSpace.name}>{selectedSpace.name} · 技能</h2></div>
                  <span>{skillTotal}</span>
                </header>
                <div className="skillcenter-listwrap">
                  {skillsLoading && <div className="skillcenter-loading skillcenter-loading--overlay"><LoadingMark />正在读取技能…</div>}
                  {skillsError ? (
                    <div className="skillcenter-error">{skillsError}</div>
                  ) : skills.length === 0 && !skillsLoading ? (
                    <EmptyState>这个空间中暂无技能</EmptyState>
                  ) : (
                    <div className="skillcenter-list skillcenter-list--skills">
                      {skills.map((skill) => (
                        <button type="button" key={`${skill.skillId}:${skill.version}`} className="skillcenter-skill-item" onClick={() => void openDetail(skill)}>
                          <span className="skillcenter-item-body">
                            <span className="skillcenter-item-title" title={skill.skillName}>{skill.skillName}</span>
                            <span className="skillcenter-item-description">{skill.skillDescription || "暂无描述"}</span>
                            <span className="skillcenter-item-meta">
                              <span className={`skillcenter-status ${statusTone(skill.skillStatus)}`}>{statusLabel(skill.skillStatus)}</span>
                              <span className="skillcenter-meta-text">版本 · {skill.version || "—"}</span>
                            </span>
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <Pager page={skillPage} total={skillTotal} pageSize={SKILL_PAGE_SIZE} onPage={setSkillPage} />
              </>
            )}
          </section>
      </div>

      {detailSkill && selectedSpace && (
        <SkillDetailDialog
          skill={detailSkill}
          space={selectedSpace}
          region={region}
          cloudProvider={cloudProvider}
          detail={detail}
          loading={detailLoading}
          error={detailError}
          onClose={closeDetail}
          onOptimize={chooseOptimizationSource}
        />
      )}
    </section>
  );
}
