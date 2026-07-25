import { useEffect, type ReactNode, type RefObject } from "react";
import type { AgentInfo, AgentNode, AgentNodeType } from "../adk/client";
import { AgentIdentityIcon } from "./AgentIdentityIcon";
import { SkillCapabilityIcon, ToolCapabilityIcon } from "./CapabilityIcons";
import { TextShimmer } from "./text-shimmer/TextShimmer";

const TYPE_LABELS: Record<AgentNodeType, string> = {
  llm: "LLM",
  sequential: "顺序",
  parallel: "并行",
  loop: "循环",
  a2a: "A2A",
};

function totalNodes(node: AgentNode): number {
  return 1 + node.children.reduce((count, child) => count + totalNodes(child), 0);
}

function nodeId(node: AgentNode): string {
  return node.id || node.name;
}

/** Older generated runtimes exposed only Python variable names. Keep those
 * identifiers for event matching, but do not leak them into the UI. */
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

function uniqueValues(values: string[]): string[] {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))];
}

function uniqueSkills(skills: AgentInfo["skills"]): AgentInfo["skills"] {
  return [
    ...new Map(
      skills
        .filter((skill) => skill.name.trim())
        .map((skill) => [
          skill.name.trim(),
          { ...skill, name: skill.name.trim() },
        ]),
    ).values(),
  ];
}

interface TopoNodeProps {
  node: AgentNode;
  activeAgent: string;
  seen: Set<string>;
  /** Names on the current delegation chain (root → … → executing). */
  path: Set<string>;
}

function TopoNode({
  node,
  activeAgent,
  seen,
  path,
}: TopoNodeProps) {
  const id = nodeId(node);
  const active = Boolean(id) && id === activeAgent;
  const onPath = Boolean(id) && !active && path.has(id);
  const done = Boolean(id) && !active && !onPath && seen.has(id);

  return (
    <div className="topo-branch">
      <div
        className={`topo-node topo-type-${node.type} ${
          active ? "is-active" : ""
        } ${onPath ? "is-onpath" : ""} ${done ? "is-done" : ""}`}
        title={node.description || node.name}
      >
        <AgentIdentityIcon className="topo-icon" />
        <span className="topo-name">{node.name || "未命名 Agent"}</span>
        <span className="topo-badge">{TYPE_LABELS[node.type] ?? "Agent"}</span>
      </div>
      {active && node.type === "a2a" && (
        <div className="topo-remote">远程执行中…</div>
      )}
      {node.children.length > 0 && (
        <div className="topo-children">
          {node.children.map((child) => (
            <TopoNode
              key={nodeId(child)}
              node={child}
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

interface ModuleTitleProps {
  title: string;
  icon: ReactNode;
  count: number;
}

function ModuleTitle({ title, icon, count }: ModuleTitleProps) {
  return (
    <div className="topo-module-title">
      {icon}
      <span className="topo-module-label" title={title}>{title}</span>
      <span className="topo-section-count" aria-label={`${count} 项`}>
        {count}
      </span>
    </div>
  );
}

interface AgentInfoPanelProps {
  info: AgentInfo | null;
  loading: boolean;
  activeAgent: string;
  seenAgents: Set<string>;
  execPath?: string[];
  variant?: "rail" | "drawer";
}

/** Agent metadata and optional multi-Agent topology shown in the conversation's
 * right whitespace. The parent owns metadata loading so this display component
 * never issues a duplicate `/web/agent-info` request. */
export function AgentInfoPanel({
  info,
  loading,
  activeAgent,
  seenAgents,
  execPath = [],
  variant = "rail",
}: AgentInfoPanelProps) {
  if (loading && !info) {
    return (
      <aside
        className={`topo is-loading${variant === "drawer" ? " is-drawer" : ""}`}
        aria-label="Agent 信息"
        aria-live="polite"
      >
        <TextShimmer as="span" className="topo-loading-label" duration={2.2}>
          正在读取 Agent 信息…
        </TextShimmer>
      </aside>
    );
  }
  if (!info) return null;

  const graph = normalizeLegacyNames(
    info.graph ?? {
      id: info.name,
      name: info.name,
      description: info.description,
      type: info.type ?? "llm",
      model: info.model,
      tools: info.tools,
      skills: info.skills,
      path: [info.name],
      mentionable: false,
      children: [],
    },
  );
  const hasTopology = graph.children.length > 0;
  const tools = uniqueValues(info.tools);
  const skills = uniqueSkills(info.skills);
  const pathSet = new Set(execPath);
  const displayNames = new Map<string, string>();
  collectDisplayNames(graph, displayNames);

  return (
    <aside
      className={`topo${variant === "drawer" ? " is-drawer" : ""}`}
      aria-label="Agent 信息与拓扑"
    >
      <section className="topo-agent-card" aria-label="Agent 信息">
        <div className="topo-agent-heading">
          <h2 title={info.name}>
            {info.name || "未命名 Agent"}
          </h2>
          {info.model && <span title={info.model}>{info.model}</span>}
        </div>
        {info.description && (
          <p className="topo-description" title={info.description}>
            {info.description}
          </p>
        )}
      </section>

      <div className="topo-module-stack">
        <section className="topo-module-card topo-tools-card" aria-label="工具">
          <ModuleTitle
            title="工具"
            count={tools.length}
            icon={<ToolCapabilityIcon className="topo-section-icon" />}
          />
          <div
            className="topo-module-scroll topo-tools-scroll"
            role="region"
            aria-label="工具列表"
            tabIndex={0}
          >
            {tools.length > 0 ? (
              <div className="topo-tool-list">
                {tools.map((tool) => (
                  <span key={tool} className="topo-tool" title={tool}>
                    {tool}
                  </span>
                ))}
              </div>
            ) : (
              <div className="topo-empty">未配置</div>
            )}
          </div>
        </section>

        <section className="topo-module-card topo-skills-card" aria-label="技能">
          <ModuleTitle
            title="技能"
            count={skills.length}
            icon={<SkillCapabilityIcon className="topo-section-icon" />}
          />
          <div
            className="topo-module-scroll topo-skills-scroll"
            role="region"
            aria-label="技能列表"
            tabIndex={0}
          >
            {skills.length > 0 ? (
              <div className="topo-skill-list">
                {skills.map((skill) => (
                  <div
                    key={`${skill.name}:${skill.description}`}
                    className="topo-skill"
                    title={skill.description || skill.name}
                  >
                    <span className="topo-skill-name">{skill.name}</span>
                    {skill.description && (
                      <span className="topo-skill-description">
                        {skill.description}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="topo-empty">未配置</div>
            )}
          </div>
        </section>

        <section className="topo-module-card topo-topology" aria-label="Agent 拓扑">
          <ModuleTitle
            title="拓扑"
            count={totalNodes(graph)}
            icon={<AgentIdentityIcon className="topo-section-icon" />}
          />
          <div
            className="topo-module-scroll topo-topology-scroll"
            role="region"
            aria-label="Agent 拓扑列表"
            tabIndex={0}
          >
            {hasTopology ? (
              <>
                {execPath.length > 0 && (
                  <div className="topo-path" aria-label="执行路径">
                    {execPath.map((name, index) => (
                      <span key={`${name}-${index}`} className="topo-path-seg">
                        <span
                          className={
                            index === execPath.length - 1
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
              </>
            ) : (
              <div className="topo-topology-empty">
                <span className="topo-topology-line" aria-hidden="true" />
                <span>单 Agent，无协作拓扑</span>
              </div>
            )}
          </div>
        </section>
      </div>
    </aside>
  );
}

function CloseIcon() {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  );
}

export function AgentInfoDrawer({
  info,
  loading,
  activeAgent,
  seenAgents,
  execPath,
  onClose,
  returnFocusRef,
}: {
  info: AgentInfo | null;
  loading: boolean;
  activeAgent: string;
  seenAgents: Set<string>;
  execPath: string[];
  onClose: () => void;
  returnFocusRef: RefObject<HTMLButtonElement>;
}) {
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      returnFocusRef.current?.focus();
    };
  }, [onClose, returnFocusRef]);

  return (
    <>
      <div className="drawer-scrim agent-info-scrim" onClick={onClose} />
      <aside
        className="drawer drawer--agent-info"
        role="dialog"
        aria-modal="true"
        aria-labelledby="agent-info-drawer-title"
      >
        <header className="drawer-head">
          <div>
            <div id="agent-info-drawer-title" className="drawer-title">
              Agent 信息
            </div>
            <div className="drawer-sub">能力与协作拓扑</div>
          </div>
          <button
            type="button"
            className="drawer-close"
            onClick={onClose}
            aria-label="关闭 Agent 信息"
            autoFocus
          >
            <CloseIcon />
          </button>
        </header>
        <div className="agent-info-drawer-body">
          {info || loading ? (
            <AgentInfoPanel
              info={info}
              loading={loading}
              activeAgent={activeAgent}
              seenAgents={seenAgents}
              execPath={execPath}
              variant="drawer"
            />
          ) : (
            <div className="drawer-empty">暂时无法读取 Agent 信息。</div>
          )}
        </div>
      </aside>
    </>
  );
}
