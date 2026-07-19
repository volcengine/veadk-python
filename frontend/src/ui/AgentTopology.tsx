import { useEffect, useState } from "react";
import { Bot, ChevronRight, GitBranch, Globe, Repeat, Split } from "lucide-react";
import {
  getAgentInfo,
  type AgentNode,
  type AgentNodeType,
} from "../adk/client";

/** Icon + Chinese label for each agent type, shared with the create wizard. */
const TYPE_META: Record<AgentNodeType, { icon: typeof Bot; label: string }> = {
  llm: { icon: Bot, label: "LLM" },
  sequential: { icon: GitBranch, label: "顺序" },
  parallel: { icon: Split, label: "并行" },
  loop: { icon: Repeat, label: "循环" },
  a2a: { icon: Globe, label: "A2A" },
};

/** Count nodes below (and including) a node — used to decide whether a
 *  topology is worth showing at all. */
function totalNodes(node: AgentNode): number {
  return 1 + node.children.reduce((n, c) => n + totalNodes(c), 0);
}

function nodeId(node: AgentNode): string {
  return node.id || node.name;
}

/** Older generated runtimes exposed only Python variable names. Keep those
 *  identifiers for event matching, but do not leak them into the UI. */
function legacyDisplayName(node: AgentNode, isRoot: boolean): string {
  const id = nodeId(node);
  if (node.id && node.name && node.name !== id) return node.name;
  if (isRoot && id === "agent") return "主 Agent";
  const subAgent = /^agent_sub_(\d+)$/.exec(id);
  return subAgent ? `子 Agent ${subAgent[1]}` : node.name || id;
}

function normalizeLegacyNames(node: AgentNode, isRoot = true): AgentNode {
  return {
    ...node,
    id: nodeId(node),
    name: legacyDisplayName(node, isRoot),
    children: node.children.map((child) => normalizeLegacyNames(child, false)),
  };
}

function collectDisplayNames(node: AgentNode, names: Map<string, string>): void {
  names.set(nodeId(node), node.name || nodeId(node));
  node.children.forEach((child) => collectDisplayNames(child, names));
}

function TopoNode({
  node,
  activeAgent,
  seen,
  path,
}: {
  node: AgentNode;
  activeAgent: string;
  seen: Set<string>;
  /** Names on the current delegation chain (root → … → executing). */
  path: Set<string>;
}) {
  const meta = TYPE_META[node.type] ?? TYPE_META.llm;
  const Icon = meta.icon;
  const id = nodeId(node);
  const named = Boolean(id);
  const active = named && id === activeAgent;
  // On the delegation chain but not the leaf being executed → an ancestor that
  // handed off. Highlighted more softly than the active node.
  const onPath = named && !active && path.has(id);
  const done = named && !active && !onPath && seen.has(id);
  return (
    <div className="topo-branch">
      <div
        className={`topo-node topo-type-${node.type} ${
          active ? "is-active" : ""
        } ${onPath ? "is-onpath" : ""} ${done ? "is-done" : ""}`}
        title={node.description || node.name}
      >
        <Icon className="topo-icon" />
        <span className="topo-name">{node.name || "(未命名)"}</span>
        <span className="topo-badge">{meta.label}</span>
      </div>
      {/* Remote agents are a black box — while one runs we can only show that
          it's executing remotely, not its internal steps. */}
      {active && node.type === "a2a" && (
        <div className="topo-remote">远程执行中…</div>
      )}
      {node.children.length > 0 && (
        <div className="topo-children">
          {node.children.map((c, i) => (
            <TopoNode
              key={`${nodeId(c)}-${i}`}
              node={c}
              activeAgent={activeAgent}
              seen={seen}
              path={path}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** A compact topology of an agent and its sub-agents, rendered in the
 *  whitespace beside the conversation. Only shows when the agent actually has
 *  sub-agents; silently renders nothing otherwise (single-agent apps, remote
 *  AgentKit apps whose server has no `/web/agent-info`, or fetch errors). */
export function AgentTopology({
  appName,
  activeAgent,
  seenAgents,
  execPath = [],
}: {
  appName: string;
  activeAgent: string;
  seenAgents: Set<string>;
  /** Current delegation chain (root → … → executing agent), from the stream. */
  execPath?: string[];
}) {
  const [graph, setGraph] = useState<AgentNode | null>(null);

  useEffect(() => {
    let cancelled = false;
    setGraph(null);
    if (!appName) return;
    getAgentInfo(appName)
      .then((info) => {
        if (!cancelled) {
          setGraph(info.graph ? normalizeLegacyNames(info.graph) : null);
        }
      })
      .catch(() => {
        if (!cancelled) setGraph(null);
      });
    return () => {
      cancelled = true;
    };
  }, [appName]);

  // Nothing to show for a lone agent — the panel only earns its space when
  // there is a sub-agent structure to reveal.
  if (!graph || graph.children.length === 0) return null;

  const pathSet = new Set(execPath);
  const displayNames = new Map<string, string>();
  collectDisplayNames(graph, displayNames);

  return (
    <aside className="topo" aria-label="Agent 拓扑">
      <div className="topo-head">
        <span className="topo-head-title">Agent 拓扑</span>
        <span className="topo-head-sub">{totalNodes(graph)} 个</span>
      </div>
      {/* Live delegation breadcrumb: root › planner › searcher */}
      {execPath.length > 0 && (
        <div className="topo-path" aria-label="执行路径">
          {execPath.map((name, i) => (
            <span key={`${name}-${i}`} className="topo-path-seg">
              {i > 0 && <ChevronRight className="topo-path-sep" />}
              <span
                className={
                  i === execPath.length - 1
                    ? "topo-path-name is-current"
                    : "topo-path-name"
                }
              >
                {displayNames.get(name) ?? name}
              </span>
            </span>
          ))}
        </div>
      )}
      <div className="topo-tree">
        <TopoNode
          node={graph}
          activeAgent={activeAgent}
          seen={seenAgents}
          path={pathSet}
        />
      </div>
    </aside>
  );
}
