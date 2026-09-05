import {
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  Boxes,
  ChevronLeft,
  ChevronRight,
  Info,
  Loader2,
  Network,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import {
  getCachedRuntimeAgentInfo,
  getCachedRuntimeDetail,
  getRuntimeAgentInfo,
  getRuntimeDetail,
  getRuntimes,
  RuntimeAccessDeniedError,
  RuntimeProbeError,
  type AgentInfo,
  type CloudRuntime,
  type RuntimeScope,
  type RuntimeDetail,
} from "../adk/client";
import { connectRuntime } from "../adk/connections";
import { modelNameFromRuntime } from "../create/runtimeModelName";
import {
  beginAgentConnect,
  classifyTelemetryError,
} from "../telemetry";
import { AgentFaceIcon } from "./AgentFaceIcon";
import { SkillCapabilityIcon, ToolCapabilityIcon } from "./CapabilityIcons";
import { RuntimeIdentityIcon } from "./RuntimeIdentityIcon";

/** A currently-connected cloud runtime. */
export interface SelectedRuntime {
  runtimeId: string;
  name: string;
  region: string;
}

export interface AgentSelectorProps {
  open: boolean;
  onClose: () => void;
  /** Render beside another popover instead of beside the sidebar. */
  variant?: "drawer" | "navbar";
  /** Top offset (px) so the drawer aligns with the sidebar picker row. */
  anchorTop?: number;
  /** local = pick a local app (`--dev`); cloud = pick a runtime. */
  agentsSource: "local" | "cloud";
  /** Local apps served by this server (used only in local mode). */
  localApps: string[];
  /** The currently selected picker id. */
  currentId: string;
  /** The connected runtime, if any — highlighted in the Runtime list. */
  currentRuntime?: SelectedRuntime;
  /** Maximum runtime scope granted by the server. */
  runtimeScope: RuntimeScope;
  /** Called with the picker id once an agent is chosen. */
  onSelect: (id: string) => void | Promise<void>;
}

const PAGE_SIZE = 15;
const LOAD_TIMEOUT_MS = 10_000;

function runtimeMetadataErrorMessage(message: string, t: TFunction<"ui">): string {
  const normalized = message.toLowerCase();
  if (
    normalized.includes("invalidagentkitruntime.notfound") ||
    normalized.includes("specified agentkitruntime does not exist")
  ) {
    return t("agentSelector.errors.notFound");
  }
  if (
    normalized.includes("accessdenied") ||
    normalized.includes("forbidden") ||
    normalized.includes("permission") ||
    normalized.includes("(401)") ||
    normalized.includes("(403)")
  ) {
    return t("agentSelector.errors.accessDenied");
  }
  if (
    normalized.includes("agent-info failed: 404") ||
    normalized.includes("读取 agent 列表失败 (404)")
  ) {
    return t("agentSelector.errors.previewUnsupported");
  }
  return t("agentSelector.errors.unavailable");
}

/** Reject if `p` doesn't settle within `ms` (so a stuck request surfaces). */
function withTimeout<T>(p: Promise<T>, timeoutMessage: string, ms = LOAD_TIMEOUT_MS): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(timeoutMessage)), ms);
    p.then(
      (v) => {
        clearTimeout(timer);
        resolve(v);
      },
      (e) => {
        clearTimeout(timer);
        reject(e);
      },
    );
  });
}

/** Slide-out agent picker anchored to the sidebar's right edge. Local mode lists
 *  this server's apps; cloud mode lists all AgentKit runtimes (client-paginated
 *  15/page, the user's own badged). Each Runtime exposes explicit connect and
 *  tabbed-info actions. */
export function AgentSelector({
  open,
  onClose,
  variant = "drawer",
  anchorTop = 0,
  agentsSource,
  localApps,
  currentId,
  currentRuntime,
  runtimeScope,
  onSelect,
}: AgentSelectorProps) {
  const { t } = useTranslation("ui");
  // Lazily-loaded pages of the full list: pageCache[i] holds page i's runtimes,
  // tokens[i] is the next_token that fetches page i (tokens[0] = "").
  const [pageCache, setPageCache] = useState<CloudRuntime[][]>([]);
  const [tokens, setTokens] = useState<string[]>([""]);
  const [page, setPage] = useState(0);
  // "只看我创建的" — the owner's set is small, so fetch it all at once (no pager).
  const [mineOnly, setMineOnly] = useState(runtimeScope === "mine");
  const [mineList, setMineList] = useState<CloudRuntime[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [connecting, setConnecting] = useState<string | null>(null);
  const [unsupported, setUnsupported] = useState<Set<string>>(new Set());
  const [previewed, setPreviewed] = useState<SelectedRuntime | undefined>();
  const [detailTab, setDetailTab] = useState<"agent" | "runtime">("agent");
  const loadedOnce = useRef(false);

  function togglePreview(rt: CloudRuntime) {
    setPreviewed((current) =>
      current?.runtimeId === rt.runtimeId
        ? undefined
        : { runtimeId: rt.runtimeId, name: rt.name, region: rt.region },
    );
  }

  // Fetch one page on demand (lazy). Cached pages just switch instantly.
  const fetchPage = useCallback(
    async (i: number) => {
      if (pageCache[i]) {
        setPage(i); // already loaded — just switch
        return;
      }
      const token = tokens[i];
      if (token === undefined) return; // page not reachable yet
      setLoading(true);
      setError("");
      try {
        const pg = await withTimeout(
          getRuntimes({
            nextToken: token,
            pageSize: PAGE_SIZE,
            region: "all",
            scope: "all",
          }),
          t("agentSelector.errors.timeout"),
        );
        setPageCache((pc) => {
          const n = [...pc];
          n[i] = pg.runtimes;
          return n;
        });
        setTokens((t) => {
          const n = [...t];
          if (pg.nextToken) n[i + 1] = pg.nextToken;
          return n;
        });
        setPage(i);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [tokens, pageCache, t],
  );

  const loadMine = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const acc: CloudRuntime[] = [];
      let token = "";
      do {
        const pg = await withTimeout(
          getRuntimes({
            scope: "mine",
            nextToken: token,
            pageSize: 100,
            region: "all",
          }),
          t("agentSelector.errors.timeout"),
        );
        acc.push(...pg.runtimes);
        token = pg.nextToken;
      } while (token && acc.length < 2000);
      setMineList(acc);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    setMineOnly(runtimeScope === "mine");
    setPageCache([]);
    setTokens([""]);
    setPage(0);
    setMineList(null);
    loadedOnce.current = false;
  }, [runtimeScope]);

  useEffect(() => {
    if (open && agentsSource === "cloud" && !mineOnly && !loadedOnce.current) {
      loadedOnce.current = true;
      void fetchPage(0);
    }
  }, [open, agentsSource, mineOnly, fetchPage]);

  // Toggling "只看我创建的" loads the owner's set the first time.
  useEffect(() => {
    if (mineOnly && mineList === null && agentsSource === "cloud")
      void loadMine();
  }, [mineOnly, mineList, agentsSource, loadMine]);

  // Opening the selector starts with the compact list and no preview panel.
  useEffect(() => {
    if (open) {
      setPreviewed(undefined);
      setDetailTab("agent");
    }
  }, [open]);

  function refresh() {
    setUnsupported(new Set());
    if (mineOnly) {
      setMineList(null);
      void loadMine();
    } else {
      setPageCache([]);
      setTokens([""]);
      setPage(0);
      loadedOnce.current = true;
      setLoading(true);
      setError("");
      void withTimeout(
        getRuntimes({
          nextToken: "",
          pageSize: PAGE_SIZE,
          region: "all",
          scope: "all",
        }),
        t("agentSelector.errors.timeout"),
      )
        .then((pg) => {
          setPageCache([pg.runtimes]);
          setTokens(pg.nextToken ? ["", pg.nextToken] : [""]);
        })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)))
        .finally(() => setLoading(false));
    }
  }

  const hasNext =
    !mineOnly &&
    (pageCache[page + 1] !== undefined || tokens[page + 1] !== undefined);

  function connect(rt: CloudRuntime) {
    const operation = beginAgentConnect({
      targetId: String(rt.runtimeId),
      agentKind: "runtime",
      connectSource: "navbar_picker",
    });
    setConnecting(rt.runtimeId);
    connectRuntime(rt.runtimeId, rt.name, rt.region)
      .then(async (agentId) => {
        await onSelect(agentId);
        operation.succeed({
          runtimeRegion: rt.region,
          runtimeIsMine: rt.isMine ? 1 : 0,
        });
        onClose();
      })
      .catch((error) => {
        operation.fail(classifyTelemetryError(error));
        if (error instanceof RuntimeAccessDeniedError) {
          setError(error.message);
          return;
        }
        if (error instanceof RuntimeProbeError) {
          if (error.unsupported) {
            setUnsupported((current) => new Set(current).add(rt.runtimeId));
          }
          setError(error.message);
          return;
        }
        setUnsupported((s) => new Set(s).add(rt.runtimeId));
      })
      .finally(() => setConnecting(null));
  }

  async function selectLocalApp(app: string) {
    const operation = beginAgentConnect({
      targetId: String(app),
      agentKind: "local",
      connectSource: "navbar_picker",
    });
    try {
      await onSelect(app);
      operation.succeed({});
      onClose();
    } catch (error) {
      operation.fail(classifyTelemetryError(error));
      setError(error instanceof Error ? error.message : String(error));
    }
  }

  if (!open) return null;

  // The visible set: the owner's full list (mineOnly) or the current lazy page,
  // then a client-side name filter over whatever is shown.
  const base = mineOnly ? (mineList ?? []) : (pageCache[page] ?? []);
  const pageItems = base.filter((r) =>
    query ? r.name.toLowerCase().includes(query.toLowerCase()) : true,
  );

  return (
    <>
      {variant === "drawer" ? <div className="menu-scrim" onClick={onClose} /> : null}
      <div
        className={`agentsel agentsel--${variant}${previewed && variant === "drawer" ? " has-detail" : ""}`}
        role="dialog"
        aria-label={t("agentSelector.selectAgent")}
        style={variant === "drawer" ? {
          top: anchorTop,
          height: `min(640px, calc(100dvh - ${anchorTop}px - 10px))`,
        } : undefined}
      >
        <div className="agentsel-main">
          <div className="agentsel-head">
            <span className="agentsel-title">
              <AgentFaceIcon /> {t("agentSelector.selectAgent")}
            </span>
            <div className="agentsel-head-actions">
              {agentsSource === "cloud" && (
                <button
                  className="agentsel-refresh"
                  onClick={refresh}
                  title={t("common.refresh")}
                  disabled={loading}
                >
                  <RefreshCw className={`icon ${loading ? "spin" : ""}`} />
                </button>
              )}
              <button
                className="agentsel-refresh"
                onClick={onClose}
                title={t("common.close")}
              >
                <X className="icon" />
              </button>
            </div>
          </div>

          {agentsSource === "local" ? (
            <div className="agentsel-body">
              {localApps.length === 0 ? (
                <div className="agentsel-empty">{t("agentSelector.noLocalAgents")}</div>
              ) : (
                <ul className="agentsel-list">
                  {localApps.map((app) => (
                    <li key={app}>
                      <button
                        className={`agentsel-item ${app === currentId ? "active" : ""}`}
                        onClick={() => void selectLocalApp(app)}
                      >
                        <AgentFaceIcon />
                        <span className="agentsel-item-name">{app}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <div className="agentsel-body agentsel-body--cloud">
              <div className="agentsel-tools">
                <div className="agentsel-search">
                  <Search className="icon" />
                  <input
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder={t("agentSelector.searchRuntime")}
                  />
                </div>
                {runtimeScope === "all" && (
                  <label className="agentsel-mine">
                    <input
                      type="checkbox"
                      checked={mineOnly}
                      onChange={(e) => setMineOnly(e.target.checked)}
                    />
                    {t("agentSelector.mineOnly")}
                  </label>
                )}
              </div>

              {error && <div className="agentsel-error">{error}</div>}

              {/* Fixed-height list area so paging doesn't resize the drawer;
                  a centered overlay shows while a page loads. */}
              <div className="agentsel-listwrap">
                {pageItems.length === 0 && !loading ? (
                  <div className="agentsel-empty">{t("agentSelector.noRuntimes")}</div>
                ) : (
                  <ul className="agentsel-list">
                    {pageItems.map((rt) => {
                      const bad = unsupported.has(rt.runtimeId);
                      const connectingThis = connecting === rt.runtimeId;
                      const active = currentRuntime?.runtimeId === rt.runtimeId;
                      const isPreviewed = previewed?.runtimeId === rt.runtimeId;
                      return (
                        <li key={rt.runtimeId}>
                          <div
                            className={`agentsel-item agentsel-runtime-item ${active ? "active" : ""} ${isPreviewed ? "is-previewed" : ""}`}
                            title={rt.runtimeId}
                          >
                            <RuntimeIdentityIcon />
                            <div className="agentsel-item-main">
                              <span className="agentsel-item-name" title={rt.name}>
                                {rt.name}
                              </span>
                              <div className="agentsel-item-meta">
                                <span
                                  className={`agentsel-status is-${bad ? "bad" : statusKind(rt.status)}`}
                                >
                                  {bad ? t("agentSelector.unsupported") : runtimeStatusLabel(rt.status, t)}
                                </span>
                                {rt.isMine && (
                                  <span className="runtime-owner-badge">{t("agentSelector.createdByMe")}</span>
                                )}
                              </div>
                            </div>
                            <div className="agentsel-item-actions">
                              <button
                                type="button"
                                className="agentsel-connect"
                                disabled={connectingThis || active}
                                onClick={() => connect(rt)}
                              >
                                {connectingThis
                                  ? t("agentSelector.connecting")
                                  : active
                                    ? t("agentSelector.connected")
                                    : bad
                                      ? t("common.retry")
                                      : t("agentSelector.connect")}
                              </button>
                              {variant === "drawer" ? (
                                <button
                                  type="button"
                                  className={`agentsel-info ${isPreviewed ? "active" : ""}`}
                                  aria-label={t("agentSelector.viewInfoFor", { name: rt.name })}
                                  aria-pressed={isPreviewed}
                                  title={t("agentSelector.viewInfo")}
                                  onClick={() => togglePreview(rt)}
                                >
                                  <Info className="icon" />
                                </button>
                              ) : null}
                            </div>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
                {loading && (
                  <div className="agentsel-loading">
                    <Loader2 className="icon spin" /> {t("common.loading")}
                  </div>
                )}
              </div>

              <div className="agentsel-pager">
                <button
                  disabled={mineOnly || page === 0 || loading}
                  onClick={() => void fetchPage(page - 1)}
                  aria-label={t("common.previousPage")}
                >
                  <ChevronLeft className="icon" />
                </button>
                <span className="agentsel-pager-label">
                  {mineOnly ? 1 : page + 1}
                </span>
                <button
                  disabled={mineOnly || !hasNext || loading}
                  onClick={() => void fetchPage(page + 1)}
                  aria-label={t("common.nextPage")}
                >
                  <ChevronRight className="icon" />
                </button>
              </div>
            </div>
          )}
        </div>

        {variant === "drawer" && agentsSource === "cloud" && previewed && (
          <RuntimePreviewPanel
            runtime={previewed}
            tab={detailTab}
            onTabChange={setDetailTab}
          />
        )}
      </div>
    </>
  );
}

const COMPONENT_KINDS = new Set([
  "knowledgebase",
  "memory",
  "prompt_manager",
  "example_store",
  "run_processor",
  "tracer",
  "toolset",
  "plugin",
  "other",
]);

function componentKindLabel(kind: string, t: TFunction<"ui">): string {
  const normalized = kind.toLowerCase();
  return COMPONENT_KINDS.has(normalized)
    ? t(`agentSelector.componentKinds.${normalized}`)
    : kind;
}

function componentBackendLabel(backend: string, t: TFunction<"ui">): string {
  const labels: Record<string, string> = {
    context_search: "Context Search",
    local: t("agentSelector.local"),
    mem0: "Mem0",
    milvus: "Milvus",
    opensearch: "OpenSearch",
    openviking: "OpenViking",
    redis: "Redis",
    tos_vector: "TOS Vector",
    viking: "VikingDB",
  };
  return labels[backend.toLowerCase()] ?? backend;
}

function RuntimePreviewPanel({
  runtime,
  tab,
  onTabChange,
}: {
  runtime: SelectedRuntime;
  tab: "agent" | "runtime";
  onTabChange: (tab: "agent" | "runtime") => void;
}) {
  const { t } = useTranslation("ui");
  return (
    <section
      className="agentsel-detail agentsel-preview"
      aria-label={t("agentSelector.agentAndRuntimeInfo")}
    >
      <div className="agentsel-head agentsel-preview-head">
        <div
          className={`agentsel-detail-tabs is-${tab}`}
          role="tablist"
          aria-label={t("agentSelector.detailType")}
        >
          <span className="agentsel-detail-tabs-slider" aria-hidden />
          <button
            id="agentsel-agent-tab"
            type="button"
            role="tab"
            aria-selected={tab === "agent"}
            aria-controls="agentsel-agent-panel"
            onClick={() => onTabChange("agent")}
          >
            {t("agentSelector.agentInfo")}
          </button>
          <button
            id="agentsel-runtime-tab"
            type="button"
            role="tab"
            aria-selected={tab === "runtime"}
            aria-controls="agentsel-runtime-panel"
            onClick={() => onTabChange("runtime")}
          >
            {t("agentSelector.runtimeInfo")}
          </button>
        </div>
      </div>
      <div
        id="agentsel-agent-panel"
        className="agentsel-tab-panel"
        role="tabpanel"
        aria-labelledby="agentsel-agent-tab"
        hidden={tab !== "agent"}
      >
        <AgentInfoContent runtime={runtime} />
      </div>
      <div
        id="agentsel-runtime-panel"
        className="agentsel-tab-panel"
        role="tabpanel"
        aria-labelledby="agentsel-runtime-tab"
        hidden={tab !== "runtime"}
      >
        <RuntimeDetailContent runtime={runtime} />
      </div>
    </section>
  );
}

/** Agent Server metadata for a hovered Runtime. This request is intentionally
 *  isolated from Runtime detail: either may fail without hiding the other. */
function AgentInfoContent({ runtime }: { runtime: SelectedRuntime }) {
  const { t } = useTranslation("ui");
  const [info, setInfo] = useState<AgentInfo | null>(() =>
    getCachedRuntimeAgentInfo(runtime.runtimeId, runtime.region),
  );
  const [loading, setLoading] = useState(() =>
    !getCachedRuntimeAgentInfo(runtime.runtimeId, runtime.region),
  );
  const [error, setError] = useState("");
  const runtimeId = runtime.runtimeId;
  const runtimeRegion = runtime.region;

  useEffect(() => {
    let alive = true;
    const cached = getCachedRuntimeAgentInfo(runtimeId, runtimeRegion);
    setInfo(cached);
    setLoading(!cached);
    setError("");
    getRuntimeAgentInfo(runtimeId, runtimeRegion, { force: Boolean(cached) })
      .then((nextInfo) => alive && setInfo(nextInfo))
      .catch((e) => {
        if (!alive) return;
        if (cached) return;
        const message = e instanceof Error ? e.message : String(e);
        setError(runtimeMetadataErrorMessage(message, t));
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [runtimeId, runtimeRegion, t]);

  const components = info?.components ?? [];
  const modelName = modelNameFromRuntime(info?.model);

  return (
    <div className="agentsel-detail-body">
      {loading ? (
        <div className="agentsel-panel-state">
          <Loader2 className="icon spin" /> {t("agentSelector.loadingAgentInfo")}
        </div>
      ) : error ? (
        <div className="agentsel-panel-empty">
          <span>{t("agentSelector.cannotLoadAgentInfo")}</span>
          <small title={error}>{error}</small>
        </div>
      ) : info ? (
        <>
          <div className="agentsel-identity">
            <AgentFaceIcon className="agentsel-identity-icon" />
            <div className="agentsel-identity-copy">
              <strong title={info.name}>{info.name || t("agentSelector.unnamedAgent")}</strong>
              {modelName && <span title={modelName}>{modelName}</span>}
            </div>
          </div>

          {info.description && (
            <section className="agentsel-info-section">
              <h3>{t("common.description")}</h3>
              <p className="agentsel-description" title={info.description}>
                {info.description}
              </p>
            </section>
          )}

            {info.subAgents.length > 0 && (
              <InfoChipSection
                icon={<Network className="icon" />}
                title={t("agentSelector.subagents")}
                values={info.subAgents}
              />
            )}

            {info.tools.length > 0 && (
              <InfoChipSection
                icon={<ToolCapabilityIcon />}
                title={t("agentSelector.tools")}
                values={info.tools}
              />
            )}

          <section className="agentsel-info-section">
            <h3>
              <SkillCapabilityIcon /> {t("agentSelector.skills")}
            </h3>
            {info.skillsPreviewSupported ? (
              info.skills.length > 0 ? (
                <div className="agentsel-info-list">
                  {info.skills.map((skill) => (
                    <div key={skill.name} className="agentsel-info-list-item">
                      <strong title={skill.name}>{skill.name}</strong>
                      {skill.description && (
                        <span title={skill.description}>{skill.description}</span>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="agentsel-info-empty">{t("common.notConfigured")}</div>
              )
            ) : (
              <div className="agentsel-info-empty">{t("agentSelector.previewUnsupported")}</div>
            )}
          </section>

          {components.length > 0 && (
            <section className="agentsel-info-section">
              <h3>
                <Boxes className="icon" /> {t("agentSelector.mountedComponents")}
              </h3>
              <div className="agentsel-info-list">
                {components.map((component, index) => (
                  <div
                    key={`${component.kind}:${component.name}:${index}`}
                    className="agentsel-info-list-item agentsel-component"
                  >
                    <div className="agentsel-component-head">
                      <strong title={component.name}>{component.name}</strong>
                      <span>
                        {componentKindLabel(component.kind, t)}
                        {component.backend
                          ? ` · ${componentBackendLabel(component.backend, t)}`
                          : ""}
                      </span>
                    </div>
                    {component.description && (
                      <span title={component.description}>
                        {component.description}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {!info.description &&
            info.subAgents.length === 0 &&
            info.tools.length === 0 &&
            info.skillsPreviewSupported &&
            info.skills.length === 0 &&
            components.length === 0 && (
              <div className="agentsel-panel-empty">
                {t("agentSelector.noMoreAgentInfo")}
              </div>
            )}
        </>
      ) : null}
    </div>
  );
}

function InfoChipSection({
  icon,
  title,
  values,
}: {
  icon: ReactNode;
  title: string;
  values: string[];
}) {
  return (
    <section className="agentsel-info-section">
      <h3>
        {icon}
        {title}
      </h3>
      <div className="agentsel-chips">
        {values.map((value, index) => (
          <span
            key={`${value}:${index}`}
            className="agentsel-chip"
            title={value}
          >
            {value}
          </span>
        ))}
      </div>
    </section>
  );
}

/** Control-plane detail for the hovered Runtime. */
function RuntimeDetailContent({ runtime }: { runtime: SelectedRuntime }) {
  const { t } = useTranslation("ui");
  const [detail, setDetail] = useState<RuntimeDetail | null>(() =>
    getCachedRuntimeDetail(runtime.runtimeId, runtime.region),
  );
  const [loading, setLoading] = useState(() =>
    !getCachedRuntimeDetail(runtime.runtimeId, runtime.region),
  );
  const [error, setError] = useState("");
  const runtimeId = runtime.runtimeId;
  const runtimeRegion = runtime.region;

  useEffect(() => {
    let alive = true;
    const cached = getCachedRuntimeDetail(runtimeId, runtimeRegion);
    setDetail(cached);
    setLoading(!cached);
    setError("");
    getRuntimeDetail(runtimeId, runtimeRegion, { force: Boolean(cached) })
      .then((d) => alive && setDetail(d))
      .catch(
        (e) =>
          alive &&
          !cached &&
          setError(
            runtimeMetadataErrorMessage(
              e instanceof Error ? e.message : String(e),
              t,
            ),
          ),
      )
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [runtimeId, runtimeRegion, t]);

  const rows: [string, string][] = [];
  if (detail) {
    if (detail.model) rows.push([t("agentSelector.model"), detail.model]);
    if (detail.description) rows.push([t("common.description"), detail.description]);
    if (detail.status) rows.push([t("agentSelector.status"), runtimeStatusLabel(detail.status, t)]);
    const r = detail.resources;
    const res = [
      r.cpuMilli != null ? `CPU ${r.cpuMilli}m` : "",
      r.memoryMb != null ? t("agentSelector.memoryMb", { value: r.memoryMb }) : "",
      r.minInstance != null || r.maxInstance != null
        ? t("agentSelector.instances", { min: r.minInstance ?? "?", max: r.maxInstance ?? "?" })
        : "",
    ]
      .filter(Boolean)
      .join(" · ");
    if (res) rows.push([t("agentSelector.resources"), res]);
    if (detail.currentVersion != null)
      rows.push([t("agentSelector.version"), String(detail.currentVersion)]);
  }

  return (
    <div className="agentsel-detail-body">
      <div className="agentsel-runtime-identity">
        <RuntimeIdentityIcon />
        <div>
          <strong title={runtime.name}>{runtime.name}</strong>
          <span title={runtime.runtimeId}>{runtime.runtimeId}</span>
        </div>
      </div>
      {loading ? (
        <div className="agentsel-apps-note">
          <Loader2 className="icon spin" /> {t("agentSelector.loadingDetails")}
        </div>
      ) : error ? (
        <div className="agentsel-error">{error}</div>
      ) : detail ? (
        <>
          <dl className="agentsel-kv">
            {rows.map(([k, v]) => (
              <div key={k} className="agentsel-kv-row">
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
          {detail.envs.length > 0 && (
            <div className="agentsel-envs">
              <div className="agentsel-envs-head">{t("agentSelector.environmentVariables")}</div>
              {detail.envs.map((e) => (
                <div key={e.key} className="agentsel-env">
                  <span className="agentsel-env-k">{e.key}</span>
                  <span className="agentsel-env-v">{e.value}</span>
                </div>
              ))}
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}

/** Bucket a raw runtime status into a colour class. */
function statusKind(status: string): "ok" | "warn" | "bad" | "muted" {
  const s = (status || "").toLowerCase();
  if (s.includes("run") || s.includes("ready") || s.includes("active"))
    return "ok";
  if (s.includes("creat") || s.includes("pend") || s.includes("deploy"))
    return "warn";
  if (s.includes("fail") || s.includes("error") || s.includes("delet"))
    return "bad";
  return "muted";
}

const RUNTIME_STATUSES = new Set([
  "ready",
  "unreleased",
  "running",
  "active",
  "creating",
  "pending",
  "deploying",
  "updating",
  "failed",
  "error",
  "stopping",
  "stopped",
  "deleting",
  "deleted",
]);

function runtimeStatusLabel(status: string, t: TFunction<"ui">): string {
  const key = status.toLowerCase().replace(/[\s_-]/g, "");
  return RUNTIME_STATUSES.has(key)
    ? t(`agentSelector.runtimeStatus.${key}`)
    : (status || "-");
}
