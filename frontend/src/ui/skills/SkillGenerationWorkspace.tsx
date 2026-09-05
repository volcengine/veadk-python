import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { CloudProvider, CloudRegion } from "../../adk/cloudProvider";
import { formatCloudRegion, isSupportedCloudRegion } from "../../adk/cloudProvider";
import type { SkillSpaceRef } from "../../create/skills/skillspace";
import { TextShimmer } from "../text-shimmer/TextShimmer";
import { SkillConversationStream } from "./SkillConversationStream";
import {
  createSkillWorkbenchTask,
  deleteSkillWorkbenchTask,
  downloadSkillWorkbenchTask,
  getSkillWorkbenchArtifact,
  getSkillWorkbenchCapability,
  getSkillWorkbenchTask,
  publishSkillWorkbenchTask,
  refineSkillWorkbenchTask,
  stopSkillWorkbenchTask,
} from "../skill-workbench/api";
import type {
  SkillCenterOptimizationSource,
  SkillWorkbenchArtifact,
  SkillWorkbenchCapability,
  SkillWorkbenchTask,
} from "../skill-workbench/types";
import { SkillConfigSelect } from "./SkillConfigSelect";
import { normalizeSkillError, SkillErrorDetails } from "./SkillErrorDetails";
import { SkillFileTree } from "./SkillFileTree";
import { skillT } from "./i18n";
import "./skills.css";

const POLL_INTERVAL_MS = 1_200;
const MAX_GROUPS = 3;
const MAX_AUTO_REPAIRS = 2;
const FORMAT_VALIDATION_PATTERN = /SKILL\.md|frontmatter|Skill name|description|根目录|目录名|UTF-8|文本文件|文件数|符号链接|敏感凭证/i;

const STYLE_KEYS: Record<string, string> = {
  concise: "generation.styles.concise",
  strict: "generation.styles.strict",
  tutorial: "generation.styles.tutorial",
  automation: "generation.styles.automation",
};

interface GroupConfig {
  id: string;
  model: string;
  style: string;
  customStyle: string;
}

interface CandidateRun {
  id: string;
  config: GroupConfig;
  task?: SkillWorkbenchTask;
  artifact?: SkillWorkbenchArtifact;
  error?: Error;
  pollError?: Error;
  repairError?: Error;
  repairAttempts?: number;
  repairing?: boolean;
  repairMode?: "auto" | "manual";
}

export interface SkillGenerationWorkspaceProps {
  operation: "create" | "optimize";
  cloudProvider: CloudProvider;
  space?: SkillSpaceRef;
  availableSpaces?: SkillSpaceRef[];
  spacesLoading?: boolean;
  initialIntent?: string;
  source?: SkillCenterOptimizationSource;
  onBack: () => void;
  onPublished: () => void;
}

function nextGroup(index: number, capability: SkillWorkbenchCapability): GroupConfig {
  return {
    id: `group-${Date.now()}-${index}`,
    model: capability.models[index % Math.max(1, capability.models.length)]?.id || "",
    style: "concise",
    customStyle: "",
  };
}

function stageLabel(task?: SkillWorkbenchTask): string {
  if (!task) return skillT("generation.stages.preparing");
  if (task.state === "ready") return skillT("generation.stages.ready");
  if (task.state === "failed") return skillT("generation.stages.failed");
  if (task.state === "cancelled") return skillT("generation.stages.cancelled");
  if (task.stage === "validating") return skillT("generation.stages.validating");
  if (task.stage === "packaging") return skillT("generation.stages.packaging");
  return skillT("generation.stages.generating");
}

function isFormatValidationFailure(task: SkillWorkbenchTask): boolean {
  return task.state === "failed"
    && task.validation?.valid === false
    && task.validation.errors.some((error) => FORMAT_VALIDATION_PATTERN.test(error));
}

function repairIntent(task: SkillWorkbenchTask): string {
  const errors = task.validation?.errors.join("\n") || task.error || skillT("generation.validation.fallback");
  return [
    skillT("generation.validation.repairInstruction"),
    skillT("generation.validation.recheckInstruction"),
    errors.slice(0, 2_000),
  ].join("\n\n");
}

function candidateStageLabel(run: CandidateRun): string {
  if (run.repairing || (run.task?.state === "running" && run.repairMode)) {
    if (run.repairMode === "manual") return skillT("generation.stages.repairingAgain");
    const attempt = Math.max(1, run.repairAttempts || 1);
    return skillT("generation.stages.autoRepairing", { attempt, max: MAX_AUTO_REPAIRS });
  }
  return stageLabel(run.task);
}

function LoadingSpinner() {
  return (
    <svg className="skill-generation__spinner" viewBox="0 0 20 20" aria-hidden="true">
      <circle cx="10" cy="10" r="7" />
      <path d="M10 3a7 7 0 0 1 7 7" />
    </svg>
  );
}

function remainingLabel(task?: SkillWorkbenchTask, now = Date.now()): string {
  if (!task?.expiresAt) return skillT("generation.sessionMax");
  const remaining = Math.max(0, new Date(task.expiresAt).getTime() - now);
  const minutes = Math.floor(remaining / 60_000);
  const seconds = Math.floor((remaining % 60_000) / 1_000);
  return skillT("generation.remaining", { minutes, seconds: String(seconds).padStart(2, "0") });
}

function skillNameProblem(name: string): string {
  if (!name) return "";
  if (name.length > 64) return skillT("generation.validation.nameTooLong");
  if (!/^[a-z0-9-]+$/.test(name)) {
    return skillT("generation.validation.invalidName");
  }
  return "";
}

function modelNameProblem(model: string): string {
  if (!model) return "";
  if (model.length > 128) return skillT("generation.validation.modelTooLong");
  if (!/^[A-Za-z0-9][A-Za-z0-9._:/-]*$/.test(model)) {
    return skillT("generation.validation.invalidModel");
  }
  return "";
}

function publishSpaceKey(space: SkillSpaceRef): string {
  return `${space.region || ""}:${space.id}`;
}

function BackIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="m14.5 6-6 6 6 6"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function SkillGenerationWorkspace({
  operation,
  cloudProvider,
  space,
  availableSpaces = [],
  spacesLoading = false,
  initialIntent = "",
  source,
  onBack,
  onPublished,
}: SkillGenerationWorkspaceProps) {
  const { t } = useTranslation("skills");
  const [capability, setCapability] = useState<SkillWorkbenchCapability | null>(null);
  const [capabilityError, setCapabilityError] = useState<Error | null>(null);
  const [intent, setIntent] = useState(initialIntent);
  const [name, setName] = useState("");
  const [groups, setGroups] = useState<GroupConfig[]>([]);
  const [runs, setRuns] = useState<CandidateRun[]>([]);
  const [activeId, setActiveId] = useState("");
  const [started, setStarted] = useState(false);
  const [followUp, setFollowUp] = useState("");
  const [action, setAction] = useState<"refine" | "publish" | "download" | "">("");
  const [actionError, setActionError] = useState<Error | null>(null);
  const [publishProgress, setPublishProgress] = useState("");
  const [publishedId, setPublishedId] = useState("");
  const [selectedPublishSpaceKey, setSelectedPublishSpaceKey] = useState(
    space ? publishSpaceKey(space) : "",
  );
  const [now, setNow] = useState(Date.now());
  const runsRef = useRef<CandidateRun[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    void getSkillWorkbenchCapability(controller.signal)
      .then((value) => {
        setCapability(value);
        setGroups([nextGroup(0, value)]);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setCapabilityError(normalizeSkillError(error, skillT("generation.errors.loadCapability")));
        }
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    runsRef.current = runs;
  }, [runs]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (!runsRef.current.some((run) => run.task?.state === "running" || run.repairing)) return;
      event.preventDefault();
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      for (const run of runsRef.current) {
        if (!run.task?.jobId) continue;
        void deleteSkillWorkbenchTask(run.task.jobId).catch(() => undefined);
      }
    };
  }, []);

  useEffect(() => {
    if (!runs.some((run) => run.task?.state === "running" || run.repairing)) return;
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      const current = runsRef.current;
      const updated = await Promise.all(current.map(async (run) => {
        if (run.task?.state !== "running") return run;
        try {
          const task = await getSkillWorkbenchTask(run.task.jobId);
          if (isFormatValidationFailure(task) && (run.repairAttempts || 0) < MAX_AUTO_REPAIRS) {
            const repairAttempts = (run.repairAttempts || 0) + 1;
            setRuns((items) => items.map((item) => item.id === run.id ? {
              ...item,
              task,
              repairing: true,
              repairMode: "auto",
              repairAttempts,
              repairError: undefined,
            } : item));
            try {
              const repairedTask = await refineSkillWorkbenchTask({
                jobId: task.jobId,
                intent: repairIntent(task),
                expectedRevision: task.revision,
              });
              return {
                ...run,
                task: repairedTask,
                artifact: undefined,
                repairing: false,
                repairMode: "auto" as const,
                repairAttempts,
                repairError: undefined,
                error: undefined,
                pollError: undefined,
              };
            } catch (error) {
              return {
                ...run,
                task,
                repairing: false,
                repairMode: undefined,
                repairAttempts,
                repairError: normalizeSkillError(error, skillT("generation.errors.autoRepair")),
                pollError: undefined,
              };
            }
          }
          let artifact = run.artifact;
          if (task.state === "ready") {
            artifact = await getSkillWorkbenchArtifact(task.jobId, task.revision);
          }
          return {
            ...run,
            task,
            artifact,
            repairing: false,
            repairMode: task.state === "running" ? run.repairMode : undefined,
            repairError: undefined,
            error: undefined,
            pollError: undefined,
          };
        } catch (error) {
          return {
            ...run,
            pollError: normalizeSkillError(error, skillT("generation.errors.pollCandidate")),
          };
        }
      }));
      if (cancelled) return;
      setRuns(updated);
      timer = window.setTimeout(() => void poll(), POLL_INTERVAL_MS);
    };
    void poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [runs.some((run) => run.task?.state === "running" || run.repairing)]);

  const active = runs.find((run) => run.id === activeId) || runs[0];
  const needsPublishSpace = operation === "create" && !space;
  const selectedPublishSpace = availableSpaces.find(
    (item) => publishSpaceKey(item) === selectedPublishSpaceKey,
  ) ?? null;
  const publishSpace = space ?? selectedPublishSpace;
  const publishSpaceOptions = availableSpaces.map((item) => ({
    value: publishSpaceKey(item),
    label: `${item.name.trim() || t("generation.unnamedSpace")} · ${formatCloudRegion(item.region || "cn-beijing", cloudProvider)}`,
  }));
  const nameError = skillNameProblem(name);
  const canGenerate = Boolean(
    capability?.enabled
    && intent.trim()
    && !nameError
    && groups.length > 0
    && groups.every((group) => group.model.trim() && !modelNameProblem(group.model.trim())),
  );

  const updateGroup = (id: string, patch: Partial<GroupConfig>) => {
    setGroups((current) => current.map((group) => group.id === id ? { ...group, ...patch } : group));
  };

  const createRun = async (config: GroupConfig): Promise<CandidateRun> => {
    const normalizedConfig = { ...config, model: config.model.trim() };
    const style = config.style === "custom" ? config.customStyle.trim() : config.style;
    try {
      const task = await createSkillWorkbenchTask({
        operation,
        intent: intent.trim(),
        model: normalizedConfig.model,
        style,
        name: name.trim() || undefined,
        source,
      });
      return { id: config.id, config: normalizedConfig, task };
    } catch (error) {
      return {
        id: config.id,
        config: normalizedConfig,
        error: normalizeSkillError(error, skillT("generation.errors.createCandidate")),
      };
    }
  };

  const generate = async () => {
    if (!canGenerate) return;
    setStarted(true);
    setActionError(null);
    const placeholders = groups.map((config) => ({ id: config.id, config }));
    setRuns(placeholders);
    setActiveId(groups[0].id);
    const created = await Promise.all(groups.map(createRun));
    setRuns(created);
  };

  const retry = async (run: CandidateRun) => {
    setRuns((current) => current.map((item) => item.id === run.id ? { ...item, error: undefined } : item));
    const next = await createRun(run.config);
    setRuns((current) => current.map((item) => item.id === run.id ? next : item));
  };

  const refine = async () => {
    if (!active?.task || !followUp.trim() || active.task.state !== "ready") return;
    setAction("refine");
    setActionError(null);
    try {
      const task = await refineSkillWorkbenchTask({
        jobId: active.task.jobId,
        intent: followUp.trim(),
        expectedRevision: active.task.revision,
      });
      setRuns((current) => current.map((run) => run.id === active.id
        ? { ...run, task, artifact: undefined }
        : run));
      setFollowUp("");
    } catch (error) {
      setActionError(normalizeSkillError(error, skillT("generation.errors.refine")));
    } finally {
      setAction("");
    }
  };

  const repairAgain = async () => {
    if (!active?.task || !isFormatValidationFailure(active.task)) return;
    setAction("refine");
    setActionError(null);
    setRuns((current) => current.map((run) => run.id === active.id ? {
      ...run,
      repairing: true,
      repairMode: "manual",
      repairError: undefined,
    } : run));
    try {
      const task = await refineSkillWorkbenchTask({
        jobId: active.task.jobId,
        intent: repairIntent(active.task),
        expectedRevision: active.task.revision,
      });
      setRuns((current) => current.map((run) => run.id === active.id ? {
        ...run,
        task,
        artifact: undefined,
        repairing: false,
        repairMode: "manual",
        repairError: undefined,
      } : run));
    } catch (error) {
      setRuns((current) => current.map((run) => run.id === active.id ? {
        ...run,
        repairing: false,
        repairMode: undefined,
        repairError: normalizeSkillError(error, skillT("generation.errors.repairAgain")),
      } : run));
    } finally {
      setAction("");
    }
  };

  const publish = async () => {
    if (!active?.task || active.task.state !== "ready" || publishedId) return;
    setAction("publish");
    setActionError(null);
    try {
      if (!publishSpace) throw new Error(skillT("generation.errors.selectSpace"));
      const artifact = active.artifact || await getSkillWorkbenchArtifact(active.task.jobId, active.task.revision);
      const rawRegion = source?.region || publishSpace.region || "";
      if (!isSupportedCloudRegion(rawRegion)) throw new Error(skillT("generation.errors.unsupportedRegion"));
      await publishSkillWorkbenchTask({
        jobId: active.task.jobId,
        expectedRevision: active.task.revision,
        expectedArtifactSha256: artifact.sha256,
        disposition: operation === "optimize" ? "update-source" : "create-new",
        skillSpaceIds: [publishSpace.id],
        projectName: source?.projectName || publishSpace.projectName,
        region: rawRegion as CloudRegion,
        onProgress: (progress) => setPublishProgress(progress.message),
      });
      setPublishedId(active.id);
      onPublished();
    } catch (error) {
      setActionError(normalizeSkillError(error, skillT("generation.errors.upload")));
    } finally {
      setAction("");
      setPublishProgress("");
    }
  };

  const download = async () => {
    if (!active?.task || active.task.state !== "ready") return;
    setAction("download");
    try {
      const artifact = active.artifact || await getSkillWorkbenchArtifact(active.task.jobId, active.task.revision);
      await downloadSkillWorkbenchTask(active.task.jobId, active.task.revision, artifact.sha256);
    } catch (error) {
      setActionError(normalizeSkillError(error, skillT("generation.errors.download")));
    } finally {
      setAction("");
    }
  };

  const leave = async () => {
    if (runs.some((run) => run.task?.state === "running") && !window.confirm(skillT("generation.leaveConfirmation"))) return;
    await Promise.allSettled(runs.flatMap((run) => run.task?.state === "running"
      ? [stopSkillWorkbenchTask({ jobId: run.task.jobId, expectedRevision: run.task.revision })]
      : []));
    onBack();
  };

  const title = operation === "create"
    ? t("generation.createTitle")
    : t("generation.optimizeTitle", { name: source?.name || t("generation.skillFallback") });
  const modelLabel = (model: string) => capability?.models.find((item) => item.id === model)?.label || model;
  const styleLabel = (run: CandidateRun) => run.config.style === "custom"
    ? (run.config.customStyle.trim() || t("generation.styles.customFallback"))
    : t(STYLE_KEYS[run.config.style]);
  const styleOptions = [
    ...Object.entries(STYLE_KEYS).map(([value, key]) => ({ value, label: t(key) })),
    { value: "custom", label: t("generation.styles.custom") },
  ];
  const progressLabel = (run: CandidateRun) => run.error || run.repairError ? t("generation.stages.failed") : candidateStageLabel(run);
  const isRunPending = (run: CandidateRun) => !run.error
    && !run.repairError
    && (run.repairing || !run.task || run.task.state === "running");
  const hasReady = runs.some((run) => run.task?.state === "ready");

  return (
    <section className="skill-generation">
      <header className="skill-generation__header">
        <button type="button" className="skillcenter-back" onClick={() => void leave()} aria-label={t("generation.back")}>
          <BackIcon />
        </button>
        <div>
          <h1>{title}</h1>
          <p>{space?.name || t("generation.home")}</p>
        </div>
        {runs.length > 0 ? <span className="skill-generation__ttl">{remainingLabel(active?.task, now)}</span> : null}
      </header>

      {!started ? (
        <div className="skill-generation__setup">
          <div className="skill-generation__section-head is-basic">
            <div><strong>{t("generation.basicInfo")}</strong></div>
          </div>
          <label>
            <span>{t("generation.goal")}<span className="skill-required-mark" aria-hidden="true">*</span></span>
            <textarea required value={intent} onChange={(event) => setIntent(event.target.value)} placeholder={operation === "create" ? t("generation.createIntentPlaceholder") : t("generation.optimizeIntentPlaceholder")} />
          </label>
          <label>
            <span>{t("generation.skillName")}</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t("generation.autoNamePlaceholder")}
              aria-invalid={Boolean(nameError)}
              aria-describedby="skill-name-help"
            />
            {nameError ? (
              <span id="skill-name-help" className="skill-generation__field-error" role="alert">{nameError}</span>
            ) : (
              <span id="skill-name-help" className="skill-generation__field-help">{t("generation.nameHelp")}</span>
            )}
          </label>

          <div className="skill-generation__section-head">
            <div>
              <strong>{operation === "create" ? t("generation.createPlans") : t("generation.optimizePlans")}</strong>
              <span>{operation === "create" ? t("generation.createPlansDescription") : t("generation.optimizePlansDescription")}</span>
            </div>
          </div>
          <div className="skill-generation__groups">
            {groups.map((group, index) => (
              <article key={group.id} className="skill-generation__group">
                <header><strong>{t("generation.plan", { count: index + 1 })}</strong>{groups.length > 1 ? <button type="button" onClick={() => setGroups((current) => current.filter((item) => item.id !== group.id))}>{t("generation.remove")}</button> : null}</header>
                <SkillConfigSelect
                  label={t("generation.model")}
                  required
                  value={group.model}
                  options={capability?.models.map((model) => ({ value: model.id, label: model.label })) || []}
                  onChange={(model) => updateGroup(group.id, { model })}
                  allowCustom
                  placeholder={t("generation.modelPlaceholder")}
                  error={modelNameProblem(group.model.trim())}
                />
                <SkillConfigSelect
                  label={t("generation.style")}
                  required
                  value={group.style}
                  options={styleOptions}
                  onChange={(style) => updateGroup(group.id, { style })}
                />
                {group.style === "custom" ? <label><span>{t("generation.customStyle")}</span><textarea value={group.customStyle} onChange={(event) => updateGroup(group.id, { customStyle: event.target.value })} placeholder={t("generation.customStylePlaceholder")} /></label> : null}
              </article>
            ))}
            {capability && groups.length < MAX_GROUPS ? (
              <button
                type="button"
                className="skill-generation__add-group"
                onClick={() => setGroups((current) => [...current, nextGroup(current.length, capability)])}
              >
                {t("generation.addConfiguration")}
              </button>
            ) : null}
          </div>
          {capabilityError ? <div className="skill-inline-error"><SkillErrorDetails error={capabilityError} /></div> : null}
          {capability && !capability.enabled ? <div className="skill-inline-notice">{t("generation.notConfigured")}</div> : null}
          <div className="skill-generation__setup-actions">
            <button type="button" className="skill-button skill-button--primary" disabled={!canGenerate} onClick={() => void generate()}>{t("generation.generate")}</button>
          </div>
        </div>
      ) : (
        <div className="skill-generation__workspace">
          <div className="skill-generation__candidate-tabs" role="tablist" aria-label={t("generation.candidates")}>
            {runs.map((run) => (
              <button key={run.id} type="button" role="tab" aria-selected={active?.id === run.id} className={active?.id === run.id ? "is-active" : ""} onClick={() => setActiveId(run.id)}>
                <span className="skill-generation__summary-row"><span>{t("generation.style")}</span><strong>{styleLabel(run)}</strong></span>
                <span className="skill-generation__summary-row"><span>{t("generation.model")}</span><strong>{modelLabel(run.config.model)}</strong></span>
                <span className="skill-generation__summary-row"><span>{t("generation.progress")}</span><strong>{isRunPending(run) ? <LoadingSpinner /> : null}{progressLabel(run)}</strong></span>
              </button>
            ))}
          </div>

          {active ? (
            <div className="skill-generation__candidate">
              <section className="skill-generation__activity">
                <header>
                  <div className="skill-generation__candidate-summary">
                    <div className="skill-generation__summary-row"><span>{t("generation.style")}</span><strong>{styleLabel(active)}</strong></div>
                    <div className="skill-generation__summary-row"><span>{t("generation.model")}</span><strong>{modelLabel(active.config.model)}</strong></div>
                    <div className="skill-generation__summary-row" aria-live="polite"><span>{t("generation.progress")}</span><strong>{isRunPending(active) ? <LoadingSpinner /> : null}{isRunPending(active) ? <TextShimmer>{progressLabel(active)}</TextShimmer> : progressLabel(active)}</strong></div>
                  </div>
                </header>
                {active.task ? <SkillConversationStream activities={active.task.activities} /> : null}
                {active.pollError ? <div className="skill-inline-notice"><SkillErrorDetails error={active.pollError} /></div> : null}
                {active.repairError ? <div className="skill-inline-notice"><SkillErrorDetails error={active.repairError} /></div> : null}
                {active.error ? <div className="skill-inline-error"><SkillErrorDetails error={active.error} /><button type="button" onClick={() => void retry(active)}>{t("generation.retryCandidate")}</button></div> : null}
                {active.task?.validation && !active.task.validation.valid && !active.repairing && active.task.state === "failed" ? (
                  <div className="skill-validation-errors">
                    <strong>{t("generation.formatValidationFailed")}</strong>
                    {active.task.validation.errors.map((error) => <p key={error}>{error}</p>)}
                    {isFormatValidationFailure(active.task) ? (
                      <button type="button" disabled={Boolean(action)} onClick={() => void repairAgain()}>{t("generation.repairAgain")}</button>
                    ) : null}
                  </div>
                ) : null}
              </section>
              <section className="skill-generation__files">
                <header><h2>{t("generation.files")}</h2>{active.task?.state === "ready" ? <button type="button" onClick={() => void download()} disabled={Boolean(action)}>{t("generation.downloadZip")}</button> : null}</header>
                {active.artifact ? <SkillFileTree files={active.artifact.files} /> : <div className="skill-generation__files-empty">{active.task?.state === "ready" ? t("generation.loadingFiles") : t("generation.filesPending")}</div>}
              </section>
              {active.task?.state === "ready" ? (
                <div className="skill-generation__ready-actions">
                  {needsPublishSpace ? (
                    <div className="skill-generation__publish-target">
                      <SkillConfigSelect
                        label={t("generation.uploadToSpace")}
                        value={selectedPublishSpaceKey}
                        options={publishSpaceOptions}
                        onChange={setSelectedPublishSpaceKey}
                        disabled={spacesLoading}
                        placeholder={spacesLoading ? t("generation.loadingSpaces") : t("generation.selectSpace")}
                      />
                    </div>
                  ) : null}
                  <footer className="skill-generation__followup">
                    <textarea value={followUp} onChange={(event) => setFollowUp(event.target.value)} placeholder={t("generation.continuePlaceholder")} />
                    <button type="button" className="skill-button" disabled={!followUp.trim() || Boolean(action)} onClick={() => void refine()}>{t("generation.continue")}</button>
                    <button type="button" className="skill-button skill-button--primary" disabled={Boolean(action) || Boolean(publishedId) || !publishSpace} onClick={() => void publish()}>{action === "publish" ? publishProgress || t("generation.uploading") : operation === "optimize" ? t("generation.overwrite") : needsPublishSpace ? t("generation.uploadToSelectedSpace") : t("generation.uploadToCurrentSpace")}</button>
                  </footer>
                </div>
              ) : null}
              {actionError ? <div className="skill-inline-error skill-generation__action-error"><SkillErrorDetails error={actionError} /></div> : null}
            </div>
          ) : null}
          {!hasReady && runs.every((run) => run.error) ? <div className="skill-inline-error">{t("generation.allCandidatesFailed")}</div> : null}
        </div>
      )}
    </section>
  );
}
