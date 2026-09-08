import { useEffect, useRef, useState, type RefObject } from "react";
import type { TFunction } from "i18next";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Maximize2, X } from "lucide-react";
import type {
  AgentInfo,
  AgentNode,
  SessionEnvironmentMountSelection,
  StudioBffTool,
  StudioEnvironment,
  StudioWorkspace,
} from "../adk/client";
import { AgentBuildCanvas } from "../create/AgentBuildCanvas";
import {
  modelConfigurationFromRuntime,
  modelNameFromRuntime,
} from "../create/runtimeModelName";
import { emptyDraft, type AgentDraft } from "../create/types";
import {
  studioToolLabel,
  StudioToolDialog,
} from "./StudioToolDialog";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import { SessionEnvironmentPicker } from "./SessionEnvironmentPicker";

function totalNodes(node: AgentNode): number {
  return 1 + node.children.reduce((count, child) => count + totalNodes(child), 0);
}

function nodeId(node: AgentNode): string {
  return node.id || node.name;
}

/** Older generated runtimes exposed only Python variable names. Keep those
 * identifiers for event matching, but do not leak them into the UI. */
function legacyDisplayName(node: AgentNode, isRoot: boolean, t: TFunction): string {
  const id = nodeId(node);
  if (node.id && node.name && node.name !== id) return node.name;
  if (isRoot && id === "agent") return t("agentTopology.mainAgent");
  const subAgent = /^agent_sub_(\d+)$/.exec(id);
  return subAgent
    ? t("agentTopology.subAgent", { index: subAgent[1] })
    : node.name || id;
}

function normalizeLegacyNames(
  node: AgentNode,
  t: TFunction,
  isRoot = true,
): AgentNode {
  return {
    ...node,
    id: nodeId(node),
    name: legacyDisplayName(node, isRoot, t),
    children: node.children.map((child) => normalizeLegacyNames(child, t, false)),
  };
}

function graphNodeToCanvasDraft(node: AgentNode): AgentDraft {
  const fallback = emptyDraft();
  const runtimeModel = modelConfigurationFromRuntime(node.model);
  return {
    ...fallback,
    name: node.name,
    description: node.description,
    instruction: node.instruction || fallback.instruction,
    agentType: node.type,
    modelName: runtimeModel.modelName,
    modelProvider: runtimeModel.modelProvider,
    tools: node.tools ?? [],
    skills: (node.skills ?? []).map((skill) => skill.name),
    subAgents: node.children.map(graphNodeToCanvasDraft),
  };
}

function uniqueValues(values: string[]): string[] {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))];
}

const INTERNAL_AGENT_TOOL_NAMES = new Set(["StudioExternalToolset"]);

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
  const { t } = useTranslation("workspaceTools");
  return (
    <div className="topo-module-title">
      <span className="topo-module-label" title={title}>{title}</span>
      {count !== undefined && (
        <span className="topo-section-count" aria-label={t("agentTopology.itemCount", { count })}>
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
  studioTools?: StudioBffTool[];
  selectedStudioToolIds?: readonly string[];
  managedStudioToolIds?: readonly string[];
  studioToolsLoading?: boolean;
  studioToolsDisabled?: boolean;
  studioToolsUnavailableReason?: string;
  onStudioToolsChange?: (selectedIds: string[]) => void;
  environments?: StudioEnvironment[];
  workspaces?: StudioWorkspace[];
  selectedEnvironments?: readonly SessionEnvironmentMountSelection[];
  selectedEnvironmentWorkspaceIds?: readonly string[];
  environmentsLoading?: boolean;
  environmentsDisabled?: boolean;
  environmentsError?: string;
  onEnvironmentsChange?: (
    value: SessionEnvironmentMountSelection[],
    workspaceIds?: string[],
  ) => void | Promise<void>;
  onEnvironmentsRefresh?: () => void | Promise<void>;
}

/** Agent metadata and optional multi-Agent topology shown in the conversation's
 * right whitespace. The parent owns metadata loading so this display component
 * never issues a duplicate `/web/agent-info` request. */
export function AgentInfoPanel({
  appName,
  info,
  loading,
  variant = "rail",
  studioTools = [],
  selectedStudioToolIds = [],
  managedStudioToolIds = [],
  studioToolsLoading = false,
  studioToolsDisabled = false,
  studioToolsUnavailableReason = "",
  onStudioToolsChange,
  environments = [],
  workspaces = [],
  selectedEnvironments = [],
  selectedEnvironmentWorkspaceIds = [],
  environmentsLoading = false,
  environmentsDisabled = false,
  environmentsError = "",
  onEnvironmentsChange,
  onEnvironmentsRefresh,
}: AgentInfoPanelProps) {
  const { t } = useTranslation("workspaceTools");
  const [dialog, setDialog] = useState<"tool" | null>(null);
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
        aria-label={t("agentTopology.info")}
        aria-live="polite"
      >
        <TextShimmer as="span" className="topo-loading-label" duration={2.2}>
          {t("agentTopology.loadingInfo")}
        </TextShimmer>
      </aside>
    );
  }
  if (!info) return null;
  const modelName = modelNameFromRuntime(info.model);

  const graph = normalizeLegacyNames(
    info.graph ?? {
      id: info.name,
      name: info.name,
      description: info.description,
      type: info.type ?? "llm",
      model: modelName,
      tools: info.tools,
      skills: info.skills,
      path: [info.name],
      mentionable: false,
      children: [],
    },
    t,
  );
  const baseTools = uniqueValues(info.tools)
    .filter((name) => !INTERNAL_AGENT_TOOL_NAMES.has(name))
    .map((name) => ({
      id: `base:tool:${name}`,
      name,
      label: studioToolLabel(name, t),
      custom: false,
      removable: false,
    }));
  const baseToolNames = new Set(baseTools.map((tool) => tool.name));
  const selectedIds = new Set(selectedStudioToolIds);
  const managedIds = new Set(managedStudioToolIds);
  const selectedStudioTools = studioTools
    .filter((tool) => selectedIds.has(tool.id) && !baseToolNames.has(tool.id))
    .map((tool) => ({
      id: `studio:tool:${tool.id}`,
      name: tool.id,
      label: tool.name,
      custom: true,
      removable: !managedIds.has(tool.id),
    }));
  const tools = [...baseTools, ...selectedStudioTools];
  const skills = uniqueSkills(info.skills);
  const canCustomize = Boolean(onStudioToolsChange);
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
      aria-label={t("agentTopology.infoAndTopology")}
    >
      <section className="topo-agent-card" aria-label={t("agentTopology.info")}>
        <div className="topo-agent-heading">
          <h2 title={info.name}>
            {info.name || t("agentTopology.unnamedAgent")}
          </h2>
          {modelName && <span title={modelName}>{modelName}</span>}
        </div>
        {info.description && (
          <p className="topo-description" title={info.description}>
            {info.description}
          </p>
        )}
      </section>

      <div className="topo-module-stack">
        <section className="topo-module-card topo-tools-card" aria-label={t("agentTopology.tools")}>
          <ModuleTitle
            title={t("agentTopology.tools")}
            count={tools.length}
          />
          <div
            className="topo-module-scroll topo-tools-scroll"
            role="region"
            aria-label={t("agentTopology.toolList")}
            tabIndex={0}
          >
            {tools.length > 0 ? (
              <div className="topo-tool-list">
                {tools.map((tool) => (
                  <div key={tool.id} className="topo-tool" title={tool.name}>
                    <span className="topo-capability-title">
                      <span className="topo-capability-copy">
                        <span className="topo-capability-name">{tool.label}</span>
                        <code>{tool.name}</code>
                      </span>
                      {tool.custom && <span className="topo-custom-badge">{t("agentTopology.studioTool")}</span>}
                    </span>
                    {tool.custom && tool.removable && (
                      <button
                        type="button"
                        className="topo-remove-capability"
                        aria-label={t("agentTopology.removeTool", { name: tool.name })}
                        title={t("agentTopology.remove")}
                        disabled={studioToolsDisabled}
                        onClick={() => onStudioToolsChange?.(
                          selectedStudioToolIds.filter((id) => id !== tool.name),
                        )}
                      >
                        ×
                      </button>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="topo-empty">{t("agentTopology.notConfigured")}</div>
            )}
          </div>
          {canCustomize && (
            <div className="topo-capability-add-dock">
              <button
                type="button"
                className="topo-capability-add-slot"
                aria-label={t("agentTopology.addStudioTool")}
                disabled={studioToolsDisabled}
                onClick={() => setDialog("tool")}
              >
                <span aria-hidden="true">＋</span>
              <span>{t("agentTopology.addStudioToolHere")}</span>
              </button>
            </div>
          )}
        </section>

        <section className="topo-module-card topo-skills-card" aria-label={t("agentTopology.skills")}>
          <ModuleTitle
            title={t("agentTopology.skills")}
            count={info.skillsPreviewSupported ? skills.length : undefined}
          />
          <div
            className="topo-module-scroll topo-skills-scroll"
            role="region"
            aria-label={t("agentTopology.skillList")}
            tabIndex={0}
          >
            {!info.skillsPreviewSupported ? (
              <div className="topo-empty">{t("agentTopology.previewUnsupported")}</div>
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
              <div className="topo-empty">{t("agentTopology.notConfigured")}</div>
            )}
          </div>
        </section>

        {(onEnvironmentsChange || selectedEnvironments.length > 0) && (
          <section className="topo-module-card topo-environment-card" aria-label={t("agentTopology.sessionEnvironment")}>
            <ModuleTitle title={t("agentTopology.environment")} count={selectedEnvironments.length} />
            <SessionEnvironmentPicker
              environments={environments}
              workspaces={workspaces}
              value={selectedEnvironments}
              selectedWorkspaceIds={selectedEnvironmentWorkspaceIds}
              loading={environmentsLoading}
              disabled={environmentsDisabled}
              error={environmentsError}
              onChange={onEnvironmentsChange}
              onRefresh={onEnvironmentsRefresh}
            />
          </section>
        )}

        <section className="topo-module-card topo-topology" aria-label={t("agentTopology.agentCanvas")}>
          <div className="topo-canvas-heading">
            <ModuleTitle title={t("agentTopology.topology")} count={totalNodes(graph)} />
            <button
              ref={expandCanvasRef}
              type="button"
              className="topo-canvas-expand"
              aria-label={t("agentTopology.viewCanvasFullscreen")}
              title={t("agentTopology.viewFullscreen")}
              onClick={() => setCanvasExpanded(true)}
            >
              <Maximize2 aria-hidden="true" />
            </button>
          </div>
          <div className="topo-canvas-preview" role="region" aria-label={t("agentTopology.executionCanvas")}>
            {renderCanvas(`conversation-canvas:${appName}`)}
          </div>
        </section>
      </div>
      {dialog === "tool" && onStudioToolsChange && (
        <StudioToolDialog
          agentName={info.name}
          tools={studioTools.filter((tool) =>
            !baseToolNames.has(tool.id) && !managedIds.has(tool.id)
          )}
          selectedIds={selectedStudioToolIds}
          loading={studioToolsLoading}
          disabled={studioToolsDisabled}
          unavailableReason={studioToolsUnavailableReason}
          onChange={onStudioToolsChange}
          onClose={() => setDialog(null)}
        />
      )}
    </aside>
    {canvasExpanded && createPortal(
      <section
        className="topo-canvas-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={t("agentTopology.fullscreenExecutionCanvas")}
      >
        <header className="topo-canvas-dialog-header">
          <div>
            <strong>{t("agentTopology.executionCanvas")}</strong>
            <span>{info.name}</span>
          </div>
          <button
            type="button"
            aria-label={t("agentTopology.closeFullscreenCanvas")}
            title={t("agentTopology.close")}
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
  studioTools,
  selectedStudioToolIds,
  managedStudioToolIds,
  studioToolsLoading,
  studioToolsDisabled,
  studioToolsUnavailableReason,
  onStudioToolsChange,
  environments,
  workspaces,
  selectedEnvironments,
  selectedEnvironmentWorkspaceIds,
  environmentsLoading,
  environmentsDisabled,
  environmentsError,
  onEnvironmentsChange,
  onEnvironmentsRefresh,
  onClose,
  returnFocusRef,
}: {
  appName: string;
  info: AgentInfo | null;
  loading: boolean;
  activeAgent: string;
  seenAgents: Set<string>;
  execPath: string[];
  studioTools?: StudioBffTool[];
  selectedStudioToolIds?: readonly string[];
  managedStudioToolIds?: readonly string[];
  studioToolsLoading?: boolean;
  studioToolsDisabled?: boolean;
  studioToolsUnavailableReason?: string;
  onStudioToolsChange?: (selectedIds: string[]) => void;
  environments?: StudioEnvironment[];
  workspaces?: StudioWorkspace[];
  selectedEnvironments?: readonly SessionEnvironmentMountSelection[];
  selectedEnvironmentWorkspaceIds?: readonly string[];
  environmentsLoading?: boolean;
  environmentsDisabled?: boolean;
  environmentsError?: string;
  onEnvironmentsChange?: (
    value: SessionEnvironmentMountSelection[],
    workspaceIds?: string[],
  ) => void | Promise<void>;
  onEnvironmentsRefresh?: () => void | Promise<void>;
  onClose: () => void;
  returnFocusRef: RefObject<HTMLButtonElement>;
}) {
  const { t } = useTranslation("workspaceTools");
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
              {t("agentTopology.info")}
            </div>
            <div className="drawer-sub">{t("agentTopology.capabilitiesSubtitle")}</div>
          </div>
          <button
            type="button"
            className="drawer-close"
            onClick={onClose}
            aria-label={t("agentTopology.closeInfo")}
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
              studioTools={studioTools}
              selectedStudioToolIds={selectedStudioToolIds}
              managedStudioToolIds={managedStudioToolIds}
              studioToolsLoading={studioToolsLoading}
              studioToolsDisabled={studioToolsDisabled}
              studioToolsUnavailableReason={studioToolsUnavailableReason}
              onStudioToolsChange={onStudioToolsChange}
              environments={environments}
              workspaces={workspaces}
              selectedEnvironments={selectedEnvironments}
              selectedEnvironmentWorkspaceIds={selectedEnvironmentWorkspaceIds}
              environmentsLoading={environmentsLoading}
              environmentsDisabled={environmentsDisabled}
              environmentsError={environmentsError}
              onEnvironmentsChange={onEnvironmentsChange}
              onEnvironmentsRefresh={onEnvironmentsRefresh}
              variant="drawer"
            />
          ) : (
            <div className="drawer-empty">{t("agentTopology.infoUnavailable")}</div>
          )}
        </div>
      </aside>
    </>
  );
}
