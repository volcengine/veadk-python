import { useEffect, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { Maximize2, X } from "lucide-react";
import type {
  AddSessionCapability,
  AgentInfo,
  AgentNode,
  SessionCapabilities,
} from "../adk/client";
import { AgentBuildCanvas } from "../create/AgentBuildCanvas";
import { emptyDraft, type AgentDraft } from "../create/types";
import {
  sessionToolLabel,
  SkillCapabilityDialog,
  ToolCapabilityDialog,
} from "./SessionCapabilityDialogs";
import { TextShimmer } from "./text-shimmer/TextShimmer";

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

function graphNodeToCanvasDraft(node: AgentNode): AgentDraft {
  const fallback = emptyDraft();
  return {
    ...fallback,
    name: node.name,
    description: node.description,
    instruction: node.instruction || fallback.instruction,
    agentType: node.type,
    modelName: node.model,
    tools: node.tools ?? [],
    skills: (node.skills ?? []).map((skill) => skill.name),
    subAgents: node.children.map(graphNodeToCanvasDraft),
  };
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

interface ModuleTitleProps {
  title: string;
  count?: number;
}

function ModuleTitle({ title, count }: ModuleTitleProps) {
  return (
    <div className="topo-module-title">
      <span className="topo-module-label" title={title}>{title}</span>
      {count !== undefined && (
        <span className="topo-section-count" aria-label={`${count} 项`}>
          {count}
        </span>
      )}
    </div>
  );
}

interface AgentInfoPanelProps {
  appName: string;
  info: AgentInfo | null;
  loading: boolean;
  activeAgent: string;
  seenAgents: Set<string>;
  execPath?: string[];
  variant?: "rail" | "drawer";
  capabilities?: SessionCapabilities | null;
  capabilityLoading?: boolean;
  capabilityMutating?: boolean;
  builtinTools?: string[];
  onAddCapability?: (capability: AddSessionCapability) => Promise<boolean>;
  onRemoveCapability?: (capabilityId: string) => void;
}

/** Agent metadata and optional multi-Agent topology shown in the conversation's
 * right whitespace. The parent owns metadata loading so this display component
 * never issues a duplicate `/web/agent-info` request. */
export function AgentInfoPanel({
  appName,
  info,
  loading,
  variant = "rail",
  capabilities = null,
  capabilityLoading = false,
  capabilityMutating = false,
  builtinTools = [],
  onAddCapability,
  onRemoveCapability,
}: AgentInfoPanelProps) {
  const [dialog, setDialog] = useState<"tool" | "skill" | null>(null);
  const [canvasExpanded, setCanvasExpanded] = useState(false);
  const expandCanvasRef = useRef<HTMLButtonElement>(null);
  const closeCanvas = () => {
    setCanvasExpanded(false);
    window.requestAnimationFrame(() => expandCanvasRef.current?.focus());
  };
  useEffect(() => {
    if (!canvasExpanded) return;
    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeCanvas();
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [canvasExpanded]);
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
  const tools = capabilities?.tools ?? uniqueValues(info.tools).map((name) => ({
    id: `base:tool:${name}`,
    kind: "tool" as const,
    name,
    custom: false,
  }));
  const skills = capabilities?.skills ?? uniqueSkills(info.skills).map((skill) => ({
    id: `base:skill:${skill.name}`,
    kind: "skill" as const,
    name: skill.name,
    description: skill.description,
    custom: false,
  }));
  const canCustomize = Boolean(capabilities && onAddCapability && onRemoveCapability);
  const canvasDraft = graphNodeToCanvasDraft(graph);
  const renderCanvas = (key: string) => (
    <AgentBuildCanvas
      key={key}
      draft={canvasDraft}
      direction="horizontal"
      selectedPath={[]}
      onSelect={() => undefined}
      onAdd={() => undefined}
      onInsert={() => undefined}
      onDelete={() => undefined}
      readOnly
      interactivePreview
    />
  );

  return (
    <>
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
                  <div key={tool.id} className="topo-tool" title={tool.name}>
                    <span className="topo-capability-title">
                      <span className="topo-capability-copy">
                        <span className="topo-capability-name">{sessionToolLabel(tool.name)}</span>
                        <code>{tool.name}</code>
                      </span>
                      {tool.custom && <span className="topo-custom-badge">自定义</span>}
                    </span>
                    {tool.custom && (
                      <button
                        type="button"
                        className="topo-remove-capability"
                        aria-label={`移除工具 ${tool.name}`}
                        title="移除"
                        disabled={capabilityMutating}
                        onClick={() => onRemoveCapability?.(tool.id)}
                      >
                        ×
                      </button>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="topo-empty">未配置</div>
            )}
          </div>
          {canCustomize && (
            <div className="topo-capability-add-dock">
              <button
                type="button"
                className="topo-capability-add-slot"
                aria-label="添加内置工具"
                disabled={capabilityLoading || capabilityMutating}
                onClick={() => setDialog("tool")}
              >
                <span aria-hidden="true">＋</span>
                <span>在此对话中添加工具</span>
              </button>
            </div>
          )}
        </section>

        <section className="topo-module-card topo-skills-card" aria-label="技能">
          <ModuleTitle
            title="技能"
            count={info.skillsPreviewSupported ? skills.length : undefined}
          />
          <div
            className="topo-module-scroll topo-skills-scroll"
            role="region"
            aria-label="技能列表"
            tabIndex={0}
          >
            {!info.skillsPreviewSupported ? (
              <div className="topo-empty">暂不支持预览</div>
            ) : skills.length > 0 ? (
              <div className="topo-skill-list">
                {skills.map((skill) => (
                  <div
                    key={`${skill.name}:${skill.description}`}
                    className="topo-skill"
                    title={skill.description || skill.name}
                  >
                    <div className="topo-skill-title">
                      <span className="topo-skill-name">{skill.name}</span>
                      {skill.custom && <span className="topo-custom-badge">自定义</span>}
                      {skill.custom && (
                        <button
                          type="button"
                          className="topo-remove-capability"
                          aria-label={`移除技能 ${skill.name}`}
                          title="移除"
                          disabled={capabilityMutating}
                          onClick={() => onRemoveCapability?.(skill.id)}
                        >
                          ×
                        </button>
                      )}
                    </div>
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
          {canCustomize && (
            <div className="topo-capability-add-dock">
              <button
                type="button"
                className="topo-capability-add-slot"
                aria-label="添加技能"
                disabled={capabilityLoading || capabilityMutating}
                onClick={() => setDialog("skill")}
              >
                <span aria-hidden="true">＋</span>
                <span>在此对话中添加技能</span>
              </button>
            </div>
          )}
        </section>

        <section className="topo-module-card topo-topology" aria-label="Agent 画布">
          <div className="topo-canvas-heading">
            <ModuleTitle title="画布" count={totalNodes(graph)} />
            <button
              ref={expandCanvasRef}
              type="button"
              className="topo-canvas-expand"
              aria-label="全屏查看 Agent 画布"
              title="全屏查看"
              onClick={() => setCanvasExpanded(true)}
            >
              <Maximize2 aria-hidden="true" />
            </button>
          </div>
          <div className="topo-canvas-preview" role="region" aria-label="Agent 执行画布">
            {renderCanvas(`conversation-canvas:${appName}`)}
          </div>
        </section>
      </div>
      {dialog === "tool" && onAddCapability && (
        <ToolCapabilityDialog
          agentName={info.name}
          tools={builtinTools}
          selectedNames={tools.map((tool) => tool.name)}
          mutating={capabilityMutating}
          onAdd={onAddCapability}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "skill" && onAddCapability && (
        <SkillCapabilityDialog
          appName={appName}
          agentName={info.name}
          selectedNames={skills.map((skill) => skill.name)}
          mutating={capabilityMutating}
          onAdd={onAddCapability}
          onClose={() => setDialog(null)}
        />
      )}
    </aside>
    {canvasExpanded && createPortal(
      <section
        className="topo-canvas-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="全屏 Agent 执行画布"
      >
        <header className="topo-canvas-dialog-header">
          <div>
            <strong>Agent 执行画布</strong>
            <span>{info.name}</span>
          </div>
          <button
            type="button"
            aria-label="关闭全屏画布"
            title="关闭"
            onClick={closeCanvas}
            autoFocus
          >
            <X aria-hidden="true" />
          </button>
        </header>
        <div className="topo-canvas-dialog-body">
          {renderCanvas(`conversation-canvas-fullscreen:${appName}`)}
        </div>
      </section>,
      document.body,
    )}
    </>
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
  appName,
  info,
  loading,
  activeAgent,
  seenAgents,
  execPath,
  capabilities,
  capabilityLoading,
  capabilityMutating,
  builtinTools,
  onAddCapability,
  onRemoveCapability,
  onClose,
  returnFocusRef,
}: {
  appName: string;
  info: AgentInfo | null;
  loading: boolean;
  activeAgent: string;
  seenAgents: Set<string>;
  execPath: string[];
  capabilities?: SessionCapabilities | null;
  capabilityLoading?: boolean;
  capabilityMutating?: boolean;
  builtinTools?: string[];
  onAddCapability?: (capability: AddSessionCapability) => Promise<boolean>;
  onRemoveCapability?: (capabilityId: string) => void;
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
              appName={appName}
              info={info}
              loading={loading}
              activeAgent={activeAgent}
              seenAgents={seenAgents}
              execPath={execPath}
              capabilities={capabilities}
              capabilityLoading={capabilityLoading}
              capabilityMutating={capabilityMutating}
              builtinTools={builtinTools}
              onAddCapability={onAddCapability}
              onRemoveCapability={onRemoveCapability}
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
