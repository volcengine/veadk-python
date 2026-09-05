import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type SVGProps,
} from "react";
import { useTranslation } from "react-i18next";

import {
  getCodingAgentCapabilities,
  installCodingAgentSkills,
  type BundledCodingAgentSkill,
  type BundledCodingAgentSkillId,
  type CodingAgentCapabilities,
  type CodingAgentId,
  type CodingAgentInstallation,
} from "../../adk/codingAgents";
import traeLogo from "../../assets/trae-logo.svg";
import { SkillPreviewDialog } from "./SkillPreviewDialog";
import "./CodingAgentsIntegration.css";

interface CodingAgentsIntegrationProps {
  onBack: () => void;
}

type ActionState = {
  tone: "success";
  agentCount: number;
  skillCount: number;
  installations: CodingAgentInstallation[];
} | {
  tone: "error";
  message: string;
  installations?: undefined;
} | null;

function BackIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path d="m9.8 3.5-4.5 4.5 4.5 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ConnectorIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden="true" {...props}>
      <rect x="3.5" y="5" width="16" height="16" rx="4.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="m8.5 11-2.4 2.4 2.4 2.4M11 16.5h3.8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="24.5" cy="10.5" r="2.5" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="24.5" cy="24.5" r="2.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M19.5 10.5H22M18.2 19l4.3 3.7M24.5 13v9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function ClaudeLogo(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden="true" {...props}>
      <g stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
        <path d="M16 4.5v7M16 20.5v7" />
        <path d="m9.3 6.3 3.5 6.1M19.2 19.6l3.5 6.1" />
        <path d="m5.9 11.1 6.2 3.5M19.9 17.4l6.2 3.5" />
        <path d="M4.7 16h7M20.3 16h7" />
        <path d="m5.9 20.9 6.2-3.5M19.9 14.6l6.2-3.5" />
        <path d="m9.3 25.7 3.5-6.1M19.2 12.4l3.5-6.1" />
      </g>
    </svg>
  );
}

function CodexLogo(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 32 32" fill="none" aria-hidden="true" {...props}>
      <path
        d="M15.8 4.2c2.4 0 4.5 1.2 5.7 3.1 2.2-.3 4.5.8 5.6 2.9 1.1 2 .8 4.4-.5 6.1 1.2 1.8 1.3 4.3.1 6.2-1.2 2-3.4 3-5.6 2.6-1.3 1.8-3.5 2.9-5.8 2.7-2.2-.2-4.1-1.5-5.1-3.4-2.2.1-4.4-1-5.4-3.1-1-2-.6-4.4.8-6.1-1.1-1.9-1.1-4.3.2-6.1 1.3-1.9 3.6-2.7 5.7-2.2 1.1-1.7 2.6-2.7 4.3-2.7Z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
      <path d="m10.7 12.2 3.1 3.8-3.1 3.8M17.1 20h4.3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CheckIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path d="m3.4 8.2 3 3L12.8 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function FolderIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <path d="M2.8 6.3h14.4v8.3a1.6 1.6 0 0 1-1.6 1.6H4.4a1.6 1.6 0 0 1-1.6-1.6V6.3Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
      <path d="M2.8 6.3V5.1a1.4 1.4 0 0 1 1.4-1.4h3.4l1.5 1.6h6.5a1.6 1.6 0 0 1 1.6 1.6" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  );
}

function AgentLogo({ agentId }: { agentId: CodingAgentId }) {
  if (agentId === "trae") {
    return <img src={traeLogo} alt="" aria-hidden="true" />;
  }
  if (agentId === "claude-code") {
    return <ClaudeLogo />;
  }
  return <CodexLogo />;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

export function CodingAgentsIntegration({ onBack }: CodingAgentsIntegrationProps) {
  const { t } = useTranslation("automations");
  const [capabilities, setCapabilities] = useState<CodingAgentCapabilities | null>(null);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(true);
  const [capabilitiesError, setCapabilitiesError] = useState<string | null>(null);
  const [capabilitiesReload, setCapabilitiesReload] = useState(0);
  const [selectedAgentIds, setSelectedAgentIds] = useState<Set<CodingAgentId>>(new Set());
  const [selectedSkillIds, setSelectedSkillIds] = useState<Set<BundledCodingAgentSkillId>>(new Set());
  const [previewSkill, setPreviewSkill] = useState<BundledCodingAgentSkill | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionState, setActionState] = useState<ActionState>(null);
  const actionAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setCapabilitiesLoading(true);
    setCapabilitiesError(null);
    void getCodingAgentCapabilities(controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setCapabilities(result);
        const availableAgents = result.agents.filter((agent) => agent.available);
        setSelectedAgentIds((current) => {
          const retained = availableAgents.filter((agent) => current.has(agent.id));
          return new Set((retained.length ? retained : availableAgents.slice(0, 1)).map((agent) => agent.id));
        });
        setSelectedSkillIds((current) => {
          const retained = result.skills.filter((skill) => current.has(skill.id));
          return new Set((retained.length ? retained : result.skills).map((skill) => skill.id));
        });
      })
      .catch((error: unknown) => {
        if (!isAbortError(error) && !controller.signal.aborted) {
          setCapabilities(null);
          setCapabilitiesError(errorMessage(error, ""));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setCapabilitiesLoading(false);
      });
    return () => controller.abort();
  }, [capabilitiesReload]);

  useEffect(() => () => actionAbortRef.current?.abort(), []);

  const selectedAgents = useMemo(
    () => capabilities?.agents.filter((agent) => agent.available && selectedAgentIds.has(agent.id)) || [],
    [capabilities, selectedAgentIds],
  );
  const selectedSkills = useMemo(
    () => capabilities?.skills.filter((skill) => selectedSkillIds.has(skill.id)) || [],
    [capabilities, selectedSkillIds],
  );
  const canConfigure = Boolean(!actionBusy && selectedAgents.length && selectedSkills.length);

  const toggleAgent = (agentId: CodingAgentId, available: boolean) => {
    if (!available || actionBusy) return;
    setActionState(null);
    setSelectedAgentIds((current) => {
      const next = new Set(current);
      if (next.has(agentId)) next.delete(agentId);
      else next.add(agentId);
      return next;
    });
  };

  const toggleSkill = (skillId: BundledCodingAgentSkillId) => {
    if (actionBusy) return;
    setActionState(null);
    setSelectedSkillIds((current) => {
      const next = new Set(current);
      if (next.has(skillId)) next.delete(skillId);
      else next.add(skillId);
      return next;
    });
  };

  const configure = async () => {
    if (!canConfigure) return;
    actionAbortRef.current?.abort();
    const controller = new AbortController();
    actionAbortRef.current = controller;
    setActionBusy(true);
    setActionState(null);
    try {
      const result = await installCodingAgentSkills({
        agents: selectedAgents.map((agent) => agent.id),
        skills: selectedSkills.map((skill) => skill.id),
      }, controller.signal);
      if (controller.signal.aborted) return;
      const installations: CodingAgentInstallation[] = result.installations;
      setActionState({
        tone: "success",
        agentCount: selectedAgents.length,
        skillCount: selectedSkills.length,
        installations,
      });
    } catch (error) {
      if (!isAbortError(error) && !controller.signal.aborted) {
        setActionState({
          tone: "error",
          message: errorMessage(error, ""),
        });
      }
    } finally {
      if (actionAbortRef.current === controller) actionAbortRef.current = null;
      if (!controller.signal.aborted) setActionBusy(false);
    }
  };

  return (
    <section className="coding-agents-page">
      <header className="coding-agents-header">
        <button type="button" className="coding-agents-back" onClick={onBack} disabled={actionBusy} aria-label={t("backToAutomations")}>
          <BackIcon />
        </button>
        <ConnectorIcon className="coding-agents-logo" />
        <div>
          <h1>{t("codingAgents.title")}</h1>
          <p>{t("codingAgents.description")}</p>
        </div>
      </header>

      <div className="coding-agents-scroll">
        <div className="coding-agents-content">
          <section className="coding-agents-section" aria-label={t("codingAgents.clients.ariaLabel")}>
            <div className="coding-agents-section-heading">
              <div><span>1</span><h2>{t("codingAgents.clients.title")}</h2></div>
              <button type="button" onClick={() => setCapabilitiesReload((value) => value + 1)} disabled={capabilitiesLoading || actionBusy}>{t("codingAgents.clients.detectAgain")}</button>
            </div>
            {capabilitiesLoading ? (
              <div className="coding-agents-inline-state"><i />{t("codingAgents.clients.detecting")}</div>
            ) : capabilitiesError !== null ? (
              <div className="coding-agents-error-row" role="alert"><span>{capabilitiesError || t("codingAgents.errors.detect")}</span><button type="button" onClick={() => setCapabilitiesReload((value) => value + 1)}>{t("codingAgents.retry")}</button></div>
            ) : (
              <div className="coding-agents-agent-grid">
                {capabilities?.agents.map((agent) => (
                  <button
                    type="button"
                    key={agent.id}
                    className={`coding-agents-agent ${selectedAgentIds.has(agent.id) ? "is-selected" : ""}`}
                    aria-pressed={selectedAgentIds.has(agent.id)}
                    disabled={!agent.available || actionBusy}
                    onClick={() => toggleAgent(agent.id, agent.available)}
                    title={agent.available ? agent.name : agent.reason}
                  >
                    <span className={`coding-agents-agent-mark is-${agent.id}`}><AgentLogo agentId={agent.id} /></span>
                    <span className="coding-agents-agent-copy">
                      <strong>{agent.name}</strong>
                      <small>{agent.available ? agent.version || t("codingAgents.clients.detected") : agent.reason}</small>
                    </span>
                    <span className={`coding-agents-status ${agent.available ? "is-ready" : ""}`}>{agent.available ? t("codingAgents.clients.available") : t("codingAgents.clients.unavailable")}</span>
                    <span className="coding-agents-check"><CheckIcon /></span>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="coding-agents-section" aria-label={t("codingAgents.skills.ariaLabel")}>
            <div className="coding-agents-section-heading">
              <div><span>2</span><h2>{t("codingAgents.skills.title")}</h2></div>
            </div>
            <div className="coding-agents-skill-list">
              {capabilities?.skills.map((skill) => (
                <div
                  key={skill.id}
                  className={`coding-agents-skill ${selectedSkillIds.has(skill.id) ? "is-selected" : ""}`}
                >
                  <label>
                    <input
                      type="checkbox"
                      checked={selectedSkillIds.has(skill.id)}
                      onChange={() => toggleSkill(skill.id)}
                      disabled={actionBusy}
                    />
                    <span className="coding-agents-skill-check" aria-hidden="true"><CheckIcon /></span>
                    <span><strong>{t(`codingAgents.skills.items.${skill.id}.name`, { defaultValue: skill.name })}</strong><small>{t(`codingAgents.skills.items.${skill.id}.description`, { defaultValue: skill.description })}</small></span>
                  </label>
                  <button type="button" onClick={() => setPreviewSkill(skill)}>{t("codingAgents.skills.viewFiles")}</button>
                </div>
              ))}
            </div>

            <div className="coding-agents-global" aria-label={t("codingAgents.global.ariaLabel")}>
              <div className="coding-agents-global-heading">
                <FolderIcon />
                <div><strong>{t("codingAgents.global.title")}</strong><span>{t("codingAgents.global.description")}</span></div>
              </div>
              {selectedAgents.length ? (
                <dl>
                  {selectedAgents.map((agent) => (
                    <div key={agent.id}><dt>{agent.name}</dt><dd>{agent.globalSkillsPath}</dd></div>
                  ))}
                </dl>
              ) : (
                <p>{t("codingAgents.global.empty")}</p>
              )}
            </div>
          </section>

          {actionState ? (
            <div className={`coding-agents-result is-${actionState.tone}`} role={actionState.tone === "error" ? "alert" : "status"}>
              <strong>{actionState.tone === "success"
                ? t("codingAgents.success", { agentCount: actionState.agentCount, skillCount: actionState.skillCount })
                : actionState.message || t("codingAgents.errors.configure")}</strong>
              {actionState.installations?.length ? <ul>{actionState.installations.map((item) => (
                <li key={`${item.agent}:${item.skillId}`}>
                  {item.agentName} · {t(`codingAgents.skills.items.${item.skillId}.name`, { defaultValue: item.skill })} → {item.displayPath}
                </li>
              ))}</ul> : null}
            </div>
          ) : null}

          <div className="coding-agents-actions">
            <span>{selectedAgents.length
              ? t("codingAgents.selection", { agentCount: selectedAgents.length, skillCount: selectedSkills.length })
              : t("codingAgents.selectClient")}</span>
            <button type="button" onClick={() => void configure()} disabled={!canConfigure}>
              {actionBusy ? t("codingAgents.configuring") : t("codingAgents.configure")}
            </button>
          </div>
        </div>
      </div>
      {previewSkill ? (
        <SkillPreviewDialog skill={previewSkill} onClose={() => setPreviewSkill(null)} />
      ) : null}
    </section>
  );
}
