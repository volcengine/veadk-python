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
import {
  getRuntimeAgentInfo,
  getRuntimeDetail,
  getRuntimes,
  RuntimeAccessDeniedError,
  type AgentInfo,
  type CloudRuntime,
  type RuntimeScope,
  type RuntimeDetail,
} from "../adk/client";
import { connectRuntime } from "../adk/connections";
import { AgentIdentityIcon } from "./AgentIdentityIcon";
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
  onSelect: (id: string) => void;
}

const PAGE_SIZE = 15;
const LOAD_TIMEOUT_MS = 10_000;
type RegionFilter = "cn-beijing" | "cn-shanghai";

const REGION_OPTIONS: { value: RegionFilter; label: string }[] = [
  { value: "cn-beijing", label: "北京" },
  { value: "cn-shanghai", label: "上海" },
];

function regionLabel(region: string): string {
  if (region === "cn-beijing") return "北京";
  if (region === "cn-shanghai") return "上海";
  return region;
}

function runtimeMetadataErrorMessage(message: string): string {
  const normalized = message.toLowerCase();
  if (
    normalized.includes("invalidagentkitruntime.notfound") ||
    normalized.includes("specified agentkitruntime does not exist")
  ) {
    return "该 Runtime 已不存在或列表信息已过期，请刷新列表后重试。";
  }
  if (
    normalized.includes("accessdenied") ||
    normalized.includes("forbidden") ||
    normalized.includes("permission") ||
    normalized.includes("(401)") ||
    normalized.includes("(403)")
  ) {
    return "当前账号无权访问该 Runtime，请检查所属 Project 和访问权限。";
  }
  if (
    normalized.includes("agent-info failed: 404") ||
    normalized.includes("读取 agent 列表失败 (404)")
  ) {
    return "该 Agent Server 版本暂不支持信息预览。";
  }
  return "该 Runtime 暂时无法访问，请确认其状态为“就绪”后重试。";
}

/** Reject if `p` doesn't settle within `ms` (so a stuck request surfaces). */
function withTimeout<T>(p: Promise<T>, ms = LOAD_TIMEOUT_MS): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error("加载超时，请重试")), ms);
    p.then(
      (v) => {
        clearTimeout(t);
        resolve(v);
      },
      (e) => {
        clearTimeout(t);
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
  anchorTop = 0,
  agentsSource,
  localApps,
  currentId,
  currentRuntime,
  runtimeScope,
  onSelect,
}: AgentSelectorProps) {
  // Lazily-loaded pages of the full list: pageCache[i] holds page i's runtimes,
  // tokens[i] is the next_token that fetches page i (tokens[0] = "").
  const [pageCache, setPageCache] = useState<CloudRuntime[][]>([]);
  const [tokens, setTokens] = useState<string[]>([""]);
  const [page, setPage] = useState(0);
  // "只看我创建的" — the owner's set is small, so fetch it all at once (no pager).
  const [mineOnly, setMineOnly] = useState(runtimeScope === "mine");
  const [mineList, setMineList] = useState<CloudRuntime[] | null>(null);
  const [regionFilter, setRegionFilter] = useState<RegionFilter>("cn-beijing");
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
            region: regionFilter,
            scope: "all",
          }),
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
    [tokens, pageCache, regionFilter],
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
            region: regionFilter,
          }),
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
  }, [regionFilter]);

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
          region: regionFilter,
          scope: "all",
        }),
      )
        .then((pg) => {
          setPageCache([pg.runtimes]);
          setTokens(pg.nextToken ? ["", pg.nextToken] : [""]);
        })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)))
        .finally(() => setLoading(false));
    }
  }

  function changeRegion(nextRegion: RegionFilter) {
    if (nextRegion === regionFilter) return;
    setRegionFilter(nextRegion);
    setPageCache([]);
    setTokens([""]);
    setPage(0);
    setMineList(null);
    setUnsupported(new Set());
    loadedOnce.current = false;
  }

  const hasNext =
    !mineOnly &&
    (pageCache[page + 1] !== undefined || tokens[page + 1] !== undefined);

  function connect(rt: CloudRuntime) {
    setConnecting(rt.runtimeId);
    connectRuntime(rt.runtimeId, rt.name, rt.region)
      .then((agentId) => {
        onSelect(agentId);
        onClose();
      })
      .catch((error) => {
        if (error instanceof RuntimeAccessDeniedError) {
          setError(error.message);
          return;
        }
        setUnsupported((s) => new Set(s).add(rt.runtimeId));
      })
      .finally(() => setConnecting(null));
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
      <div className="menu-scrim" onClick={onClose} />
      <div
        className={`agentsel ${previewed ? "has-detail" : ""}`}
        role="dialog"
        aria-label="选择 Agent"
        style={{
          top: anchorTop,
          height: `min(640px, calc(100dvh - ${anchorTop}px - 10px))`,
        }}
      >
        <div className="agentsel-main">
          <div className="agentsel-head">
            <span className="agentsel-title">
              <AgentIdentityIcon /> 选择 Agent
            </span>
            <div className="agentsel-head-actions">
              {agentsSource === "cloud" && (
                <button
                  className="agentsel-refresh"
                  onClick={refresh}
                  title="刷新"
                  disabled={loading}
                >
                  <RefreshCw className={`icon ${loading ? "spin" : ""}`} />
                </button>
              )}
              <button
                className="agentsel-refresh"
                onClick={onClose}
                title="关闭"
              >
                <X className="icon" />
              </button>
            </div>
          </div>

          {agentsSource === "local" ? (
            <div className="agentsel-body">
              {localApps.length === 0 ? (
                <div className="agentsel-empty">暂无本地 Agent。</div>
              ) : (
                <ul className="agentsel-list">
                  {localApps.map((app) => (
                    <li key={app}>
                      <button
                        className={`agentsel-item ${app === currentId ? "active" : ""}`}
                        onClick={() => {
                          onSelect(app);
                          onClose();
                        }}
                      >
                        <AgentIdentityIcon />
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
                    placeholder="搜索 Runtime 名称"
                  />
                </div>
                <div className="agentsel-regions" aria-label="按部署地域筛选">
                  {REGION_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={regionFilter === option.value ? "active" : ""}
                      aria-pressed={regionFilter === option.value}
                      onClick={() => changeRegion(option.value)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                {runtimeScope === "all" && (
                  <label className="agentsel-mine">
                    <input
                      type="checkbox"
                      checked={mineOnly}
                      onChange={(e) => setMineOnly(e.target.checked)}
                    />
                    只看我创建的
                  </label>
                )}
              </div>

              {error && <div className="agentsel-error">{error}</div>}

              {/* Fixed-height list area so paging doesn't resize the drawer;
                  a centered overlay shows while a page loads. */}
              <div className="agentsel-listwrap">
                {pageItems.length === 0 && !loading ? (
                  <div className="agentsel-empty">暂无 Runtime。</div>
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
                                  {bad ? "不支持" : runtimeStatusLabel(rt.status)}
                                </span>
                                {rt.isMine && (
                                  <span className="agentsel-badge">我创建的</span>
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
                                {connectingThis ? "连接中…" : active ? "已连接" : bad ? "重试" : "连接"}
                              </button>
                              <button
                                type="button"
                                className={`agentsel-info ${isPreviewed ? "active" : ""}`}
                                aria-label={`查看 ${rt.name} 信息`}
                                aria-pressed={isPreviewed}
                                title="查看信息"
                                onClick={() => togglePreview(rt)}
                              >
                                <Info className="icon" />
                              </button>
                            </div>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                )}
                {loading && (
                  <div className="agentsel-loading">
                    <Loader2 className="icon spin" /> 加载中…
                  </div>
                )}
              </div>

              <div className="agentsel-pager">
                <button
                  disabled={mineOnly || page === 0 || loading}
                  onClick={() => void fetchPage(page - 1)}
                  aria-label="上一页"
                >
                  <ChevronLeft className="icon" />
                </button>
                <span className="agentsel-pager-label">
                  {mineOnly ? 1 : page + 1}
                </span>
                <button
                  disabled={mineOnly || !hasNext || loading}
                  onClick={() => void fetchPage(page + 1)}
                  aria-label="下一页"
                >
                  <ChevronRight className="icon" />
                </button>
              </div>
            </div>
          )}
        </div>

        {agentsSource === "cloud" && previewed && (
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

const COMPONENT_KIND_LABELS: Record<string, string> = {
  knowledgebase: "知识库",
  memory: "记忆",
  prompt_manager: "提示词管理",
  example_store: "样例库",
  run_processor: "运行处理器",
  tracer: "链路追踪",
  toolset: "工具集",
  plugin: "插件",
  other: "其他",
};

function componentKindLabel(kind: string): string {
  return COMPONENT_KIND_LABELS[kind.toLowerCase()] ?? kind;
}

function componentBackendLabel(backend: string): string {
  const labels: Record<string, string> = {
    context_search: "Context Search",
    local: "本地",
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
  return (
    <section
      className="agentsel-detail agentsel-preview"
      aria-label="Agent 与 Runtime 信息"
    >
      <div className="agentsel-head agentsel-preview-head">
        <div
          className={`agentsel-detail-tabs is-${tab}`}
          role="tablist"
          aria-label="详情类型"
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
            Agent 信息
          </button>
          <button
            id="agentsel-runtime-tab"
            type="button"
            role="tab"
            aria-selected={tab === "runtime"}
            aria-controls="agentsel-runtime-panel"
            onClick={() => onTabChange("runtime")}
          >
            Runtime 信息
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
  const [info, setInfo] = useState<AgentInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const runtimeId = runtime.runtimeId;
  const runtimeRegion = runtime.region;

  useEffect(() => {
    let alive = true;
    setInfo(null);
    setLoading(true);
    setError("");
    getRuntimeAgentInfo(runtimeId, runtimeRegion)
      .then((nextInfo) => alive && setInfo(nextInfo))
      .catch((e) => {
        if (!alive) return;
        const message = e instanceof Error ? e.message : String(e);
        setError(runtimeMetadataErrorMessage(message));
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [runtimeId, runtimeRegion]);

  const components = info?.components ?? [];

  return (
    <div className="agentsel-detail-body">
      {loading ? (
        <div className="agentsel-panel-state">
          <Loader2 className="icon spin" /> 读取 Agent 信息…
        </div>
      ) : error ? (
        <div className="agentsel-panel-empty">
          <span>暂时无法读取 Agent 信息</span>
          <small title={error}>{error}</small>
        </div>
      ) : info ? (
        <>
          <div className="agentsel-identity">
            <AgentIdentityIcon className="agentsel-identity-icon" />
            <div className="agentsel-identity-copy">
              <strong title={info.name}>{info.name || "未命名 Agent"}</strong>
              {info.model && <span title={info.model}>{info.model}</span>}
            </div>
          </div>

          {info.description && (
            <section className="agentsel-info-section">
              <h3>描述</h3>
              <p className="agentsel-description" title={info.description}>
                {info.description}
              </p>
            </section>
          )}

            {info.subAgents.length > 0 && (
              <InfoChipSection
                icon={<Network className="icon" />}
                title="子 Agent"
                values={info.subAgents}
              />
            )}

            {info.tools.length > 0 && (
              <InfoChipSection
                icon={<ToolCapabilityIcon />}
                title="工具"
                values={info.tools}
              />
            )}

          {info.skills.length > 0 && (
              <section className="agentsel-info-section">
                <h3>
                  <SkillCapabilityIcon /> 技能
                </h3>
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
            </section>
          )}

          {components.length > 0 && (
            <section className="agentsel-info-section">
              <h3>
                <Boxes className="icon" /> 挂载组件
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
                        {componentKindLabel(component.kind)}
                        {component.backend
                          ? ` · ${componentBackendLabel(component.backend)}`
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
            info.skills.length === 0 &&
            components.length === 0 && (
              <div className="agentsel-panel-empty">
                暂无更多 Agent 配置信息。
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
  const [detail, setDetail] = useState<RuntimeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const runtimeId = runtime.runtimeId;
  const runtimeRegion = runtime.region;

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    setDetail(null);
    getRuntimeDetail(runtimeId, runtimeRegion)
      .then((d) => alive && setDetail(d))
      .catch(
        (e) =>
          alive &&
          setError(
            runtimeMetadataErrorMessage(
              e instanceof Error ? e.message : String(e),
            ),
          ),
      )
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [runtimeId, runtimeRegion]);

  const rows: [string, string][] = [];
  if (detail) {
    if (detail.model) rows.push(["模型", detail.model]);
    if (detail.description) rows.push(["描述", detail.description]);
    if (detail.status) rows.push(["状态", runtimeStatusLabel(detail.status)]);
    if (detail.region) rows.push(["区域", regionLabel(detail.region)]);
    const r = detail.resources;
    const res = [
      r.cpuMilli != null ? `CPU ${r.cpuMilli}m` : "",
      r.memoryMb != null ? `内存 ${r.memoryMb}MB` : "",
      r.minInstance != null || r.maxInstance != null
        ? `实例 ${r.minInstance ?? "?"}~${r.maxInstance ?? "?"}`
        : "",
    ]
      .filter(Boolean)
      .join(" · ");
    if (res) rows.push(["资源", res]);
    if (detail.currentVersion != null)
      rows.push(["版本", String(detail.currentVersion)]);
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
          <Loader2 className="icon spin" /> 读取详情…
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
              <div className="agentsel-envs-head">环境变量</div>
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

const RUNTIME_STATUS_LABELS: Record<string, string> = {
  ready: "就绪",
  unreleased: "未发布",
  running: "运行中",
  active: "运行中",
  creating: "创建中",
  pending: "等待中",
  deploying: "部署中",
  updating: "更新中",
  failed: "失败",
  error: "异常",
  stopping: "停止中",
  stopped: "已停止",
  deleting: "删除中",
  deleted: "已删除",
};

function runtimeStatusLabel(status: string): string {
  const key = status.toLowerCase().replace(/[\s_-]/g, "");
  return RUNTIME_STATUS_LABELS[key] ?? (status || "-");
}
