import { useEffect, useState } from "react";
import { Bot, GitBranch, Globe, Repeat, Split } from "lucide-react";
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

function TopoNode({
  node,
  activeAgent,
  seen,
}: {
  node: AgentNode;
  activeAgent: string;
  seen: Set<string>;
}) {
  const meta = TYPE_META[node.type] ?? TYPE_META.llm;
  const Icon = meta.icon;
  const active = Boolean(node.name) && node.name === activeAgent;
  const done = !active && Boolean(node.name) && seen.has(node.name);
  return (
    <div className="topo-branch">
      <div
        className={`topo-node topo-type-${node.type} ${
          active ? "is-active" : ""
        } ${done ? "is-done" : ""}`}
        title={node.description || node.name}
      >
        <Icon className="topo-icon" />
        <span className="topo-name">{node.name || "(未命名)"}</span>
        <span className="topo-badge">{meta.label}</span>
      </div>
      {node.children.length > 0 && (
        <div className="topo-children">
          {node.children.map((c, i) => (
            <TopoNode
              key={`${c.name}-${i}`}
              node={c}
              activeAgent={activeAgent}
              seen={seen}
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
}: {
  appName: string;
  activeAgent: string;
  seenAgents: Set<string>;
}) {
  const [graph, setGraph] = useState<AgentNode | null>(null);

  useEffect(() => {
    let cancelled = false;
    setGraph(null);
    if (!appName) return;
    getAgentInfo(appName)
      .then((info) => {
        if (!cancelled) setGraph(info.graph ?? null);
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

  return (
    <aside className="topo" aria-label="Agent 拓扑">
      <div className="topo-head">
        <span className="topo-head-title">Agent 拓扑</span>
        <span className="topo-head-sub">{totalNodes(graph)} 个</span>
      </div>
      <div className="topo-tree">
        <TopoNode node={graph} activeAgent={activeAgent} seen={seenAgents} />
      </div>
    </aside>
  );
}
