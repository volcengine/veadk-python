import { useCallback, useEffect, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Cpu,
  Loader2,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import {
  getRuntimeDetail,
  getRuntimes,
  type CloudRuntime,
  type RuntimeDetail,
} from "../adk/client";
import { connectRuntime } from "../adk/connections";
import { AgentIdentityIcon } from "./AgentIdentityIcon";

/** A currently-connected cloud runtime (drives the detail panel). */
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
  /** The currently selected picker id (for the active highlight). */
  currentId: string;
  /** The connected runtime, if any — shown in the side detail panel. */
  currentRuntime?: SelectedRuntime;
  /** Identity used to badge "我创建的" runtimes. */
  author: string;
  /** Called with the picker id once an agent is chosen. */
  onSelect: (id: string) => void;
}

const PAGE_SIZE = 15;
const LOAD_TIMEOUT_MS = 10_000;
type RegionFilter = "all" | "cn-beijing" | "cn-shanghai";

const REGION_OPTIONS: { value: RegionFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "cn-beijing", label: "北京" },
  { value: "cn-shanghai", label: "上海" },
];

function regionLabel(region: string): string {
  if (region === "cn-beijing") return "北京";
  if (region === "cn-shanghai") return "上海";
  return region;
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
 *  15/page, the user's own badged) — clicking a runtime connects to it directly.
 *  When a runtime is connected, a second panel shows its detail. */
export function AgentSelector({
  open,
  onClose,
  anchorTop = 0,
  agentsSource,
  localApps,
  currentId,
  currentRuntime,
  author,
  onSelect,
}: AgentSelectorProps) {
  // Lazily-loaded pages of the full list: pageCache[i] holds page i's runtimes,
  // tokens[i] is the next_token that fetches page i (tokens[0] = "").
  const [pageCache, setPageCache] = useState<CloudRuntime[][]>([]);
  const [tokens, setTokens] = useState<string[]>([""]);
  const [page, setPage] = useState(0);
  // "只看我创建的" — the owner's set is small, so fetch it all at once (no pager).
  const [mineOnly, setMineOnly] = useState(false);
  const [mineList, setMineList] = useState<CloudRuntime[] | null>(null);
  const [regionFilter, setRegionFilter] = useState<RegionFilter>("all");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [connecting, setConnecting] = useState<string | null>(null);
  const [unsupported, setUnsupported] = useState<Set<string>>(new Set());
  const [focused, setFocused] = useState<SelectedRuntime | undefined>(currentRuntime);
  const loadedOnce = useRef(false);

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
          getRuntimes(author, {
            nextToken: token,
            pageSize: PAGE_SIZE,
            region: regionFilter,
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
    [author, tokens, pageCache, regionFilter],
  );

  const loadMine = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const acc: CloudRuntime[] = [];
      let token = "";
      do {
        const pg = await withTimeout(
          getRuntimes(author, {
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
  }, [author, regionFilter]);

  useEffect(() => {
    if (open && agentsSource === "cloud" && !mineOnly && !loadedOnce.current) {
      loadedOnce.current = true;
      void fetchPage(0);
    }
  }, [open, agentsSource, mineOnly, fetchPage]);

  // Toggling "只看我创建的" loads the owner's set the first time.
  useEffect(() => {
    if (mineOnly && mineList === null && agentsSource === "cloud") void loadMine();
  }, [mineOnly, mineList, agentsSource, loadMine]);

  // When the drawer (re)opens, focus the connected runtime's detail.
  useEffect(() => {
    if (open) setFocused(currentRuntime);
  }, [open, currentRuntime]);

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
        getRuntimes(author, {
          nextToken: "",
          pageSize: PAGE_SIZE,
          region: regionFilter,
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

  const hasNext = !mineOnly && (pageCache[page + 1] !== undefined || tokens[page + 1] !== undefined);

  function connect(rt: CloudRuntime) {
    setConnecting(rt.runtimeId);
    connectRuntime(rt.runtimeId, rt.name, rt.region)
      .then((agentId) => {
        onSelect(agentId);
        setFocused({ runtimeId: rt.runtimeId, name: rt.name, region: rt.region });
        onClose();
      })
      .catch(() => setUnsupported((s) => new Set(s).add(rt.runtimeId)))
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
        className="agentsel"
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
                <button className="agentsel-refresh" onClick={refresh} title="刷新" disabled={loading}>
                  <RefreshCw className={`icon ${loading ? "spin" : ""}`} />
                </button>
              )}
              <button className="agentsel-refresh" onClick={onClose} title="关闭">
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
                        <Cpu className="icon" />
                        <span className="agentsel-item-name">{app}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <div className="agentsel-body">
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
                <label className="agentsel-mine">
                  <input
                    type="checkbox"
                    checked={mineOnly}
                    onChange={(e) => setMineOnly(e.target.checked)}
                  />
                  只看我创建的
                </label>
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
                      const active = focused?.runtimeId === rt.runtimeId;
                      return (
                        <li key={rt.runtimeId}>
                          <button
                            className={`agentsel-item ${active ? "active" : ""}`}
                            onClick={() => connect(rt)}
                            disabled={connectingThis}
                            title={rt.runtimeId}
                          >
                            {connectingThis ? (
                              <Loader2 className="icon spin" />
                            ) : (
                              <Cpu className="icon" />
                            )}
                            <span className="agentsel-item-name">{rt.name}</span>
                            <span className="agentsel-region">{regionLabel(rt.region)}</span>
                            {rt.isMine && <span className="agentsel-badge">我创建的</span>}
                            {bad ? (
                              <span className="agentsel-status is-bad">不支持</span>
                            ) : (
                              <span className={`agentsel-status is-${statusKind(rt.status)}`}>
                                {rt.status || "-"}
                              </span>
                            )}
                          </button>
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

              {!mineOnly && (page > 0 || hasNext) && (
                <div className="agentsel-pager">
                  <button
                    disabled={page === 0 || loading}
                    onClick={() => void fetchPage(page - 1)}
                    aria-label="上一页"
                  >
                    <ChevronLeft className="icon" />
                  </button>
                  <span className="agentsel-pager-label">{page + 1}</span>
                  <button
                    disabled={!hasNext || loading}
                    onClick={() => void fetchPage(page + 1)}
                    aria-label="下一页"
                  >
                    <ChevronRight className="icon" />
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {agentsSource === "cloud" && focused && (
          <RuntimeDetailPanel runtime={focused} />
        )}
      </div>
    </>
  );
}

/** Side panel: control-plane detail (model, status, resources, envs) for the
 *  connected/focused runtime. */
function RuntimeDetailPanel({ runtime }: { runtime: SelectedRuntime }) {
  const [detail, setDetail] = useState<RuntimeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    setDetail(null);
    getRuntimeDetail(runtime.runtimeId, runtime.region)
      .then((d) => alive && setDetail(d))
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [runtime.runtimeId, runtime.region]);

  const rows: [string, string][] = [];
  if (detail) {
    if (detail.model) rows.push(["模型", detail.model]);
    if (detail.description) rows.push(["描述", detail.description]);
    if (detail.status) rows.push(["状态", detail.status]);
    if (detail.region) rows.push(["区域", detail.region]);
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
    if (detail.currentVersion != null) rows.push(["版本", String(detail.currentVersion)]);
  }

  return (
    <div className="agentsel-detail">
      <div className="agentsel-head">
        <span className="agentsel-title">{runtime.name}</span>
      </div>
      <div className="agentsel-detail-body">
        <div className="agentsel-detail-id" title={runtime.runtimeId}>
          {runtime.runtimeId}
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
                    <code className="agentsel-env-k">{e.key}</code>
                    <code className="agentsel-env-v">{e.value}</code>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}

/** Bucket a raw runtime status into a colour class. */
function statusKind(status: string): "ok" | "warn" | "bad" | "muted" {
  const s = (status || "").toLowerCase();
  if (s.includes("run") || s.includes("ready") || s.includes("active")) return "ok";
  if (s.includes("creat") || s.includes("pend") || s.includes("deploy")) return "warn";
  if (s.includes("fail") || s.includes("error") || s.includes("delet")) return "bad";
  return "muted";
}
