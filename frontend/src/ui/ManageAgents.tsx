import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Loader2, RefreshCw, Trash2 } from "lucide-react";
import {
  deleteRuntime,
  getMyRuntimes,
  getRuntimeDetail,
  type AgentNode,
  type ManagedRuntime,
  type RuntimeDetail,
} from "../adk/client";
import "./ManageAgents.css";

export interface ManageAgentsViewProps {
  /** The current user identity used to filter runtimes (email / user id). */
  author: string;
}

/** Per-runtime detail state: control-plane detail + (if creds are stored) the
 *  in-container agent graph, loaded lazily when the row is expanded. */
interface DetailState {
  loading: boolean;
  error?: string;
  detail?: RuntimeDetail;
  graphs?: AgentNode[]; // one per app inside the runtime
  graphNote?: string; // why the agent tree isn't shown, if applicable
}

/** Lists the AgentKit runtimes this UI deployed on behalf of `author`, letting
 *  the user inspect their detail + agent structure and delete unwanted ones. */
export function ManageAgentsView({ author }: ManageAgentsViewProps) {
  const [runtimes, setRuntimes] = useState<ManagedRuntime[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deleting, setDeleting] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, DetailState>>({});
  const [regionFilter, setRegionFilter] = useState<string>("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setRuntimes(await getMyRuntimes(author, regionFilter));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [author, regionFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  async function loadDetail(rt: ManagedRuntime) {
    setDetails((p) => ({ ...p, [rt.runtimeId]: { loading: true } }));
    const next: DetailState = { loading: false };
    try {
      next.detail = await getRuntimeDetail(rt.runtimeId, rt.region);
    } catch (e) {
      next.error = e instanceof Error ? e.message : String(e);
    }
    // Show the main agent from control-plane metadata. The runtime's data-plane
    // apikey is a secret and is deliberately never stored in the browser, so the
    // full sub-agent tree (which needs that key) is not fetched client-side.
    if (next.detail) {
      next.graphs = [
        {
          name: next.detail.name,
          description: next.detail.description,
          type: "llm",
          model: next.detail.model,
          tools: [],
          skills: [],
          path: [next.detail.name],
          mentionable: false,
          children: [],
        },
      ];
      next.graphNote = "仅显示主 Agent（控制面信息）。";
    }
    setDetails((p) => ({ ...p, [rt.runtimeId]: next }));
  }

  function toggle(rt: ManagedRuntime) {
    const open = expanded === rt.runtimeId;
    setExpanded(open ? null : rt.runtimeId);
    if (!open && !details[rt.runtimeId]) void loadDetail(rt);
  }

  async function handleDelete(rt: ManagedRuntime) {
    if (deleting) return;
    if (!window.confirm(`确定删除 Agent "${rt.name}"？该 Runtime 将被永久删除。`)) {
      return;
    }
    setDeleting(rt.runtimeId);
    setError("");
    try {
      await deleteRuntime(rt.runtimeId, rt.region);
      setRuntimes((prev) => prev.filter((r) => r.runtimeId !== rt.runtimeId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div className="manage">
      <div className="manage-head">
        <div>
          <h2 className="manage-title">管理 Agent</h2>
          <p className="manage-sub">
            {author
              ? `列出你（${author}）通过本工作台部署到 AgentKit 的 Runtime。`
              : "列出通过本工作台部署到 AgentKit 的 Runtime。"}
          </p>
        </div>
        <div className="manage-head-actions">
          <select
            className="manage-region"
            value={regionFilter}
            onChange={(e) => setRegionFilter(e.target.value)}
            title="按区域筛选"
            aria-label="区域筛选"
          >
            <option value="all">全部区域</option>
            <option value="cn-beijing">北京</option>
            <option value="cn-shanghai">上海</option>
          </select>
          <button
            type="button"
            className="manage-refresh"
            onClick={() => void load()}
            disabled={loading}
            title="刷新"
          >
            <RefreshCw className={`icon ${loading ? "spin" : ""}`} />
            刷新
          </button>
        </div>
      </div>

      {error && <div className="manage-error">{error}</div>}

      {loading ? (
        <div className="manage-empty">
          <Loader2 className="icon spin" /> 加载中…
        </div>
      ) : runtimes.length === 0 ? (
        <div className="manage-empty">暂无你部署的 Agent。</div>
      ) : (
        <ul className="manage-list">
          {runtimes.map((rt) => {
            const open = expanded === rt.runtimeId;
            const d = details[rt.runtimeId];
            return (
              <li key={rt.runtimeId} className="manage-item">
                <div className="manage-item-row">
                  <button
                    type="button"
                    className="manage-item-toggle"
                    onClick={() => toggle(rt)}
                    aria-expanded={open}
                  >
                    {open ? (
                      <ChevronDown className="icon" />
                    ) : (
                      <ChevronRight className="icon" />
                    )}
                    <span className="manage-item-main">
                      <span className="manage-item-name">{rt.name}</span>
                      <span className={`manage-badge is-${statusKind(rt.status)}`}>
                        {rt.status || "-"}
                      </span>
                    </span>
                  </button>
                  <button
                    type="button"
                    className="manage-del"
                    onClick={() => void handleDelete(rt)}
                    disabled={deleting === rt.runtimeId}
                    title="删除该 Runtime"
                  >
                    {deleting === rt.runtimeId ? (
                      <Loader2 className="icon spin" />
                    ) : (
                      <Trash2 className="icon" />
                    )}
                  </button>
                </div>
                <div className="manage-item-meta">
                  <span className="manage-item-id" title={rt.runtimeId}>
                    {rt.runtimeId}
                  </span>
                  <span className="manage-item-dot">·</span>
                  <span>{rt.region}</span>
                  {rt.createdAt && (
                    <>
                      <span className="manage-item-dot">·</span>
                      <span>{formatTime(rt.createdAt)}</span>
                    </>
                  )}
                </div>

                {open && (
                  <div className="manage-detail">
                    {!d || d.loading ? (
                      <div className="manage-detail-loading">
                        <Loader2 className="icon spin" /> 读取详情…
                      </div>
                    ) : (
                      <>
                        {d.error && <div className="manage-error">{d.error}</div>}
                        {d.detail && <RuntimeDetailCard detail={d.detail} />}
                        <div className="manage-tree-head">Agent 结构</div>
                        {d.graphs && d.graphs.length > 0 ? (
                          d.graphs.map((g, i) => <AgentTree key={i} node={g} />)
                        ) : (
                          <div className="manage-tree-note">{d.graphNote}</div>
                        )}
                      </>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** Renders the control-plane detail fields (model, resources, envs, ids). */
function RuntimeDetailCard({ detail }: { detail: RuntimeDetail }) {
  const r = detail.resources;
  const rows: [string, string][] = [];
  if (detail.model) rows.push(["模型", detail.model]);
  if (detail.description) rows.push(["描述", detail.description]);
  if (detail.statusMessage) rows.push(["状态信息", detail.statusMessage]);
  if (detail.project) rows.push(["Project", detail.project]);
  if (detail.currentVersion != null) rows.push(["版本", String(detail.currentVersion)]);
  const res = [
    r.cpuMilli != null ? `CPU ${r.cpuMilli}m` : "",
    r.memoryMb != null ? `内存 ${r.memoryMb}MB` : "",
    r.minInstance != null || r.maxInstance != null
      ? `实例 ${r.minInstance ?? "?"}~${r.maxInstance ?? "?"}`
      : "",
    r.maxConcurrency != null ? `并发 ${r.maxConcurrency}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  if (res) rows.push(["资源", res]);
  if (detail.memoryId) rows.push(["Memory", detail.memoryId]);
  if (detail.toolId) rows.push(["Tool", detail.toolId]);
  if (detail.knowledgeId) rows.push(["Knowledge", detail.knowledgeId]);
  if (detail.mcpToolsetId) rows.push(["MCP Toolset", detail.mcpToolsetId]);
  if (detail.updatedAt) rows.push(["更新时间", formatTime(detail.updatedAt)]);

  return (
    <div className="manage-detail-card">
      <dl className="manage-kv">
        {rows.map(([k, v]) => (
          <div key={k} className="manage-kv-row">
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      {detail.envs.length > 0 && (
        <div className="manage-envs">
          <div className="manage-envs-head">环境变量</div>
          {detail.envs.map((e) => (
            <div key={e.key} className="manage-env">
              <code className="manage-env-k">{e.key}</code>
              <code className="manage-env-v">{e.value}</code>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const TYPE_LABEL: Record<string, string> = {
  llm: "LLM",
  sequential: "Sequential",
  parallel: "Parallel",
  loop: "Loop",
  a2a: "A2A",
};

/** Recursive agent tree: name + type/model/tools, with nested sub-agents. */
function AgentTree({ node, depth = 0 }: { node: AgentNode; depth?: number }) {
  return (
    <div className="manage-tree" style={{ marginLeft: depth ? 16 : 0 }}>
      <div className="manage-tree-node">
        <span className="manage-tree-name">{node.name || "(未命名)"}</span>
        <span className="manage-tree-type">{TYPE_LABEL[node.type] || node.type}</span>
        {node.model && <span className="manage-tree-model">{node.model}</span>}
      </div>
      {node.tools.length > 0 && (
        <div className="manage-tree-tools">
          {node.tools.map((t) => (
            <span key={t} className="manage-tree-tool">
              {t}
            </span>
          ))}
        </div>
      )}
      {node.children.map((c, i) => (
        <AgentTree key={i} node={c} depth={depth + 1} />
      ))}
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

/** Format an ISO / epoch timestamp for display, tolerating either form. */
function formatTime(raw: string): string {
  const n = Number(raw);
  const d = Number.isFinite(n) && String(n) === raw ? new Date(n * 1000) : new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleString();
}
