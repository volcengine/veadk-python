import { useEffect, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import type {
  AgentInfo,
  SessionEnvironmentMountSelection,
  StudioEnvironment,
  StudioWorkspace,
} from "../adk/client";
import { SkillSpacePicker } from "../create/SkillSpacePicker";
import type { SelectedSkill } from "../create/skills/types";
import { modelNameFromRuntime } from "../create/runtimeModelName";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import { SessionEnvironmentPicker } from "./SessionEnvironmentPicker";
import type { BoundSkillState } from "./mpa-agent-info/MpaAgentInfoRail";

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

export interface AgentInfoPanelProps {
  boundSkills?: BoundSkillState;
  onRefresh?: () => void;
  onOpenSkill?: (index: number) => void;
  info: AgentInfo | null;
  loading: boolean;
  variant?: "rail" | "drawer";
  selectedSessionSkills?: readonly SelectedSkill[];
  onSessionSkillsChange?: (skills: SelectedSkill[]) => void;
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
  info,
  loading,
  boundSkills,
  onRefresh,
  onOpenSkill,
  variant = "rail",
  selectedSessionSkills = [],
  onSessionSkillsChange,
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
  const [dialog, setDialog] = useState<"skill" | null>(null);
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
  const isMpa = info.agentCategory === "mpa";
  const documentStatus = info.mpa?.agentsMdStatus ?? "unsupported";
  const agentsInstruction = isMpa
    ? info.mpa?.agentsMd ?? ""
    : info.graph?.instruction ?? info.draft?.instruction ?? "";
  const skills = isMpa ? boundSkills?.skills ?? [] : uniqueSkills([
    ...info.skills,
    ...selectedSessionSkills.map((skill) => ({ name: skill.name, description: skill.description ?? "" })),
  ]);
  const skillError = boundSkills?.error;
  const errorKey = skillError === "forbidden" ? "accessDenied"
    : skillError === "unsupported" ? "skillsUnsupported"
    : skillError === "degraded" ? "skillsDegraded" : "loadFailed";

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
        {onRefresh && (
          <button type="button" className="topo-refresh" onClick={onRefresh}
            disabled={loading || boundSkills?.loading}>
            {t("agentTopology.refresh")}
          </button>
        )}
      </section>

      <div className="topo-module-stack">
        <section className="topo-module-card topo-agents-md-card" aria-label={t("agentTopology.agentsMd")}>
          <ModuleTitle title={t("agentTopology.agentsMd")} />
          <div
            className="topo-module-scroll topo-agents-md-scroll"
            role="region"
            aria-label={t("agentTopology.agentsMd")}
            tabIndex={0}
          >
            {isMpa && documentStatus !== "ready" ? (
              <div className="topo-data-error" role="status">
                {t(`agentTopology.${documentStatus === "forbidden" ? "accessDenied" : documentStatus === "unsupported" ? "documentUnsupported" : "loadFailed"}`)}
              </div>
            ) : agentsInstruction.trim() ? (
              <pre className="topo-agents-md-content">{agentsInstruction}</pre>
            ) : (
              <div className="topo-empty">{t("agentTopology.notConfigured")}</div>
            )}
          </div>
        </section>

        <section className="topo-module-card topo-skills-card" aria-label={t("agentTopology.skills")}>
          <ModuleTitle
            title={t("agentTopology.skills")}
            count={isMpa ? boundSkills?.complete ? skills.length : undefined : info.skillsPreviewSupported ? skills.length : undefined}
          />
          <div
            className="topo-module-scroll topo-skills-scroll"
            role="region"
            aria-label={t("agentTopology.skillList")}
            tabIndex={0}
          >
            {isMpa && boundSkills?.loading && !skills.length ? (
              <TextShimmer as="span">{t("agentTopology.loadingSkills")}</TextShimmer>
            ) : !isMpa && !info.skillsPreviewSupported ? (
              <div className="topo-empty">{t("agentTopology.previewUnsupported")}</div>
            ) : skills.length > 0 ? (
              <div className="topo-skill-list">
                {skills.map((skill, index) => (
                  <div
                    key={`${skill.name}:${skill.description}:${index}`}
                    className="topo-skill"
                    title={skill.description || skill.name}
                  >
                    <div className="topo-skill-title">
                      {isMpa && onOpenSkill && boundSkills?.skills[index]?.skillId && !boundSkills.skills[index].lookupByName ? (
                      <button type="button" className="topo-skill-name topo-skill-open" onClick={() => onOpenSkill(index)}>{skill.name}</button>
                    ) : <span className="topo-skill-name">{skill.name}</span>}
                    </div>
                    {skill.description && (
                      <span className="topo-skill-description">
                        {skill.description}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ) : !skillError ? (
              <div className="topo-empty">{t(isMpa ? info.mpa?.skillSpaces.length ? "agentTopology.noBoundSkills" : "agentTopology.noBoundSpace" : "agentTopology.notConfigured")}</div>
            ) : null}
            {skillError && <div className="topo-data-error" role="status">{t(`agentTopology.${errorKey}`)}</div>}
            {isMpa && boundSkills?.loading && skills.length > 0 && <span role="status">{t("agentTopology.loadingSkills")}</span>}
          </div>
          {!isMpa && onSessionSkillsChange && (
            <div className="topo-capability-add-dock">
              <button
                type="button"
                className="topo-capability-add-slot"
                aria-label={t("agentTopology.addSkill")}
                disabled={environmentsDisabled}
                onClick={() => setDialog("skill")}
              >
                <span aria-hidden="true">＋</span>
                <span>{t("agentTopology.addSkillHere")}</span>
              </button>
            </div>
          )}
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
      </div>
      {dialog === "skill" && onSessionSkillsChange && createPortal(
        <div className="studio-tool-dialog-layer">
          <button
            type="button"
            className="studio-tool-dialog-scrim"
            aria-label={t("agentTopology.close")}
            onClick={() => setDialog(null)}
          />
          <section className="studio-tool-dialog" role="dialog" aria-modal="true">
            <header className="studio-tool-dialog-head is-iconless">
              <div>
                <h2>{t("agentTopology.addSkill")}</h2>
                <p>{t("agentTopology.skillMountNextTurn")}</p>
              </div>
              <button
                type="button"
                className="studio-tool-dialog-close"
                aria-label={t("agentTopology.close")}
                onClick={() => setDialog(null)}
              >
                <X aria-hidden="true" />
              </button>
            </header>
            <div className="studio-tool-dialog-body">
              <SkillSpacePicker
                selected={[...selectedSessionSkills]}
                onChange={onSessionSkillsChange}
              />
            </div>
          </section>
        </div>,
        document.body,
      )}
    </aside>
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
  info,
  loading,
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
  info: AgentInfo | null;
  loading: boolean;
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
              info={info}
              loading={loading}
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
