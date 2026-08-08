import { useEffect, useRef, useState } from "react";
import type { CloudProvider, CloudRegion } from "../../adk/cloudProvider";
import { isSupportedCloudRegion } from "../../adk/cloudProvider";
import type { SkillSpaceRef } from "../../create/skills/skillspace";
import { TextShimmer } from "../text-shimmer/TextShimmer";
import { SkillConversationStream } from "../skill-create/SkillConversationStream";
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
import "./skills.css";

const POLL_INTERVAL_MS = 1_200;
const MAX_GROUPS = 3;
const MAX_AUTO_REPAIRS = 2;
const FORMAT_VALIDATION_PATTERN = /SKILL\.md|frontmatter|Skill name|description|根目录|目录名|UTF-8|文本文件|文件数|符号链接|敏感凭证/i;

const STYLE_LABELS: Record<string, string> = {
  concise: "简洁实用",
  strict: "严谨稳健",
  tutorial: "教程友好",
  automation: "自动化优先",
};

const STYLE_OPTIONS = [
  ...Object.entries(STYLE_LABELS).map(([value, label]) => ({ value, label })),
  { value: "custom", label: "自定义" },
];

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
  space: SkillSpaceRef;
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
  if (!task) return "正在准备 Dev Sandbox";
  if (task.state === "ready") return "Skill 已生成并通过格式校验";
  if (task.state === "failed") return "生成失败";
  if (task.state === "cancelled") return "已停止";
  if (task.stage === "validating") return "正在校验 Skill 格式";
  if (task.stage === "packaging") return "正在整理文件";
  return "正在生成 Skill";
}

function isFormatValidationFailure(task: SkillWorkbenchTask): boolean {
  return task.state === "failed"
    && task.validation?.valid === false
    && task.validation.errors.some((error) => FORMAT_VALIDATION_PATTERN.test(error));
}

function repairIntent(task: SkillWorkbenchTask): string {
  const errors = task.validation?.errors.join("\n") || task.error || "Skill 格式校验未通过";
  return [
    "只修复下面列出的 Skill 格式错误，不要改变原有用途和内容范围。",
    "修复后重新检查目录结构、SKILL.md frontmatter 和所有文本文件。",
    errors.slice(0, 2_000),
  ].join("\n\n");
}

function candidateStageLabel(run: CandidateRun): string {
  if (run.repairing || (run.task?.state === "running" && run.repairMode)) {
    if (run.repairMode === "manual") return "正在再次修复";
    const attempt = Math.max(1, run.repairAttempts || 1);
    return `正在自动修复（${attempt}/${MAX_AUTO_REPAIRS}）`;
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
  if (!task?.expiresAt) return "Session 最长保留 1 小时";
  const remaining = Math.max(0, new Date(task.expiresAt).getTime() - now);
  const minutes = Math.floor(remaining / 60_000);
  const seconds = Math.floor((remaining % 60_000) / 1_000);
  return `剩余 ${minutes}:${String(seconds).padStart(2, "0")}`;
}

function skillNameProblem(name: string): string {
  if (!name) return "";
  if (name.length > 64) return "Skill 名称不能超过 64 个字符";
  if (!/^[a-z0-9-]+$/.test(name)) {
    return "Skill 名称只能包含小写字母、数字和连字符";
  }
  return "";
}

function modelNameProblem(model: string): string {
  if (!model) return "";
  if (model.length > 128) return "模型 ID 不能超过 128 个字符";
  if (!/^[A-Za-z0-9][A-Za-z0-9._:/-]*$/.test(model)) {
    return "模型 ID 只能包含字母、数字、点、下划线、连字符、斜杠和冒号";
  }
  return "";
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
  space,
  source,
  onBack,
  onPublished,
}: SkillGenerationWorkspaceProps) {
  const [capability, setCapability] = useState<SkillWorkbenchCapability | null>(null);
  const [capabilityError, setCapabilityError] = useState<Error | null>(null);
  const [intent, setIntent] = useState("");
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
          setCapabilityError(normalizeSkillError(error, "读取 Dev Sandbox 配置失败"));
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
                repairError: normalizeSkillError(error, "自动修复格式错误失败"),
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
            pollError: normalizeSkillError(error, "读取候选方案状态失败，正在重试"),
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
        error: normalizeSkillError(error, "创建候选方案失败"),
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
      setActionError(normalizeSkillError(error, "继续调整失败"));
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
        repairError: normalizeSkillError(error, "再次修复格式错误失败"),
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
      const artifact = active.artifact || await getSkillWorkbenchArtifact(active.task.jobId, active.task.revision);
      const rawRegion = source?.region || space.region || "";
      if (!isSupportedCloudRegion(rawRegion)) throw new Error("当前 Skill 地域不受支持");
      await publishSkillWorkbenchTask({
        jobId: active.task.jobId,
        expectedRevision: active.task.revision,
        expectedArtifactSha256: artifact.sha256,
        disposition: operation === "optimize" ? "update-source" : "create-new",
        skillSpaceIds: [source?.skillSpaceId || space.id],
        projectName: source?.projectName || space.projectName,
        region: rawRegion as CloudRegion,
        onProgress: (progress) => setPublishProgress(progress.message),
      });
      setPublishedId(active.id);
      onPublished();
    } catch (error) {
      setActionError(normalizeSkillError(error, "上传 Skill 失败"));
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
      setActionError(normalizeSkillError(error, "下载失败"));
    } finally {
      setAction("");
    }
  };

  const leave = async () => {
    if (runs.some((run) => run.task?.state === "running") && !window.confirm("离开后将停止并释放正在运行的 Dev Sandbox，确定离开吗？")) return;
    await Promise.allSettled(runs.flatMap((run) => run.task?.state === "running"
      ? [stopSkillWorkbenchTask({ jobId: run.task.jobId, expectedRevision: run.task.revision })]
      : []));
    onBack();
  };

  const title = operation === "create" ? "创建技能" : `优化 ${source?.name || "技能"}`;
  const modelLabel = (model: string) => capability?.models.find((item) => item.id === model)?.label || model;
  const styleLabel = (run: CandidateRun) => run.config.style === "custom"
    ? (run.config.customStyle.trim() || "自定义风格")
    : STYLE_LABELS[run.config.style];
  const progressLabel = (run: CandidateRun) => run.error || run.repairError ? "失败" : candidateStageLabel(run);
  const isRunPending = (run: CandidateRun) => !run.error
    && !run.repairError
    && (run.repairing || !run.task || run.task.state === "running");
  const hasReady = runs.some((run) => run.task?.state === "ready");

  return (
    <section className="skill-generation">
      <header className="skill-generation__header">
        <button type="button" className="skillcenter-back" onClick={() => void leave()} aria-label="返回技能空间">
          <BackIcon />
        </button>
        <div>
          <h1>{title}</h1>
          <p>{space.name}</p>
        </div>
        {runs.length > 0 ? <span className="skill-generation__ttl">{remainingLabel(active?.task, now)}</span> : null}
      </header>

      {!started ? (
        <div className="skill-generation__setup">
          <label>
            <span>目标</span>
            <textarea value={intent} onChange={(event) => setIntent(event.target.value)} placeholder={operation === "create" ? "描述希望这个 Skill 完成什么任务" : "描述希望如何优化当前 Skill"} />
          </label>
          <label>
            <span>Skill 名称（可选）</span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="留空时自动生成"
              aria-invalid={Boolean(nameError)}
              aria-describedby="skill-name-help"
            />
            {nameError ? (
              <span id="skill-name-help" className="skill-generation__field-error" role="alert">{nameError}</span>
            ) : (
              <span id="skill-name-help" className="skill-generation__field-help">仅支持小写字母、数字和连字符；留空时自动生成。</span>
            )}
          </label>

          <div className="skill-generation__groups-head">
            <div><strong>生成配置</strong><span>每组会启动独立 Session</span></div>
          </div>
          <div className="skill-generation__groups">
            {groups.map((group, index) => (
              <article key={group.id} className="skill-generation__group">
                <header><strong>方案 {index + 1}</strong>{groups.length > 1 ? <button type="button" onClick={() => setGroups((current) => current.filter((item) => item.id !== group.id))}>移除</button> : null}</header>
                <SkillConfigSelect
                  label="模型"
                  value={group.model}
                  options={capability?.models.map((model) => ({ value: model.id, label: model.label })) || []}
                  onChange={(model) => updateGroup(group.id, { model })}
                  allowCustom
                  placeholder="选择或输入模型 ID"
                  error={modelNameProblem(group.model.trim())}
                />
                <SkillConfigSelect
                  label="风格"
                  value={group.style}
                  options={STYLE_OPTIONS}
                  onChange={(style) => updateGroup(group.id, { style })}
                />
                {group.style === "custom" ? <label><span>自定义风格</span><textarea value={group.customStyle} onChange={(event) => updateGroup(group.id, { customStyle: event.target.value })} placeholder="描述表达方式、严谨程度或输出偏好" /></label> : null}
              </article>
            ))}
            {capability && groups.length < MAX_GROUPS ? (
              <button
                type="button"
                className="skill-generation__add-group"
                onClick={() => setGroups((current) => [...current, nextGroup(current.length, capability)])}
              >
                添加配置
              </button>
            ) : null}
          </div>
          {capabilityError ? <div className="skill-inline-error"><SkillErrorDetails error={capabilityError} /></div> : null}
          {capability && !capability.enabled ? <div className="skill-inline-notice">管理员未配置</div> : null}
          <div className="skill-generation__setup-actions">
            <button type="button" className="skill-button skill-button--primary" disabled={!canGenerate} onClick={() => void generate()}>生成</button>
          </div>
        </div>
      ) : (
        <div className="skill-generation__workspace">
          <div className="skill-generation__candidate-tabs" role="tablist" aria-label="候选方案">
            {runs.map((run) => (
              <button key={run.id} type="button" role="tab" aria-selected={active?.id === run.id} className={active?.id === run.id ? "is-active" : ""} onClick={() => setActiveId(run.id)}>
                <span className="skill-generation__summary-row"><span>风格</span><strong>{styleLabel(run)}</strong></span>
                <span className="skill-generation__summary-row"><span>模型</span><strong>{modelLabel(run.config.model)}</strong></span>
                <span className="skill-generation__summary-row"><span>进度</span><strong>{isRunPending(run) ? <LoadingSpinner /> : null}{progressLabel(run)}</strong></span>
              </button>
            ))}
          </div>

          {active ? (
            <div className="skill-generation__candidate">
              <section className="skill-generation__activity">
                <header>
                  <div className="skill-generation__candidate-summary">
                    <div className="skill-generation__summary-row"><span>风格</span><strong>{styleLabel(active)}</strong></div>
                    <div className="skill-generation__summary-row"><span>模型</span><strong>{modelLabel(active.config.model)}</strong></div>
                    <div className="skill-generation__summary-row" aria-live="polite"><span>进度</span><strong>{isRunPending(active) ? <LoadingSpinner /> : null}{isRunPending(active) ? <TextShimmer>{progressLabel(active)}</TextShimmer> : progressLabel(active)}</strong></div>
                  </div>
                </header>
                {active.task ? <SkillConversationStream activities={active.task.activities} /> : null}
                {active.pollError ? <div className="skill-inline-notice"><SkillErrorDetails error={active.pollError} /></div> : null}
                {active.repairError ? <div className="skill-inline-notice"><SkillErrorDetails error={active.repairError} /></div> : null}
                {active.error ? <div className="skill-inline-error"><SkillErrorDetails error={active.error} /><button type="button" onClick={() => void retry(active)}>重试此方案</button></div> : null}
                {active.task?.validation && !active.task.validation.valid && !active.repairing && active.task.state === "failed" ? (
                  <div className="skill-validation-errors">
                    <strong>格式校验未通过</strong>
                    {active.task.validation.errors.map((error) => <p key={error}>{error}</p>)}
                    {isFormatValidationFailure(active.task) ? (
                      <button type="button" disabled={Boolean(action)} onClick={() => void repairAgain()}>再次修复</button>
                    ) : null}
                  </div>
                ) : null}
              </section>
              <section className="skill-generation__files">
                <header><h2>文件</h2>{active.task?.state === "ready" ? <button type="button" onClick={() => void download()} disabled={Boolean(action)}>下载 ZIP</button> : null}</header>
                {active.artifact ? <SkillFileTree files={active.artifact.files} /> : <div className="skill-generation__files-empty">{active.task?.state === "ready" ? "正在读取文件…" : "生成过程中会在这里显示完整文件树"}</div>}
              </section>
              {active.task?.state === "ready" ? (
                <footer className="skill-generation__followup">
                  <textarea value={followUp} onChange={(event) => setFollowUp(event.target.value)} placeholder="继续调整这个候选方案" />
                  <button type="button" className="skill-button" disabled={!followUp.trim() || Boolean(action)} onClick={() => void refine()}>继续调整</button>
                  <button type="button" className="skill-button skill-button--primary" disabled={Boolean(action) || Boolean(publishedId)} onClick={() => void publish()}>{action === "publish" ? publishProgress || "上传中…" : operation === "optimize" ? "覆盖原 Skill" : "上传到当前空间"}</button>
                </footer>
              ) : null}
              {actionError ? <div className="skill-inline-error skill-generation__action-error"><SkillErrorDetails error={actionError} /></div> : null}
            </div>
          ) : null}
          {!hasReady && runs.every((run) => run.error) ? <div className="skill-inline-error">所有方案均创建失败，可分别重试。</div> : null}
        </div>
      )}
    </section>
  );
}
