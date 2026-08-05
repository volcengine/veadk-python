import { useEffect, useRef, useState } from "react";
import type { SkillSpaceRef, SkillSpaceSkill } from "../../create/skills/skillspace";
import { SkillConversationStream } from "../skill-create/SkillConversationStream";
import { StudioConfirmDialog } from "../StudioConfirmDialog";
import { TextShimmer } from "../text-shimmer/TextShimmer";
import {
  createSkillWorkbenchTask,
  deleteSkillWorkbenchTask,
  downloadSkillWorkbenchTask,
  getSkillWorkbenchCapability,
  publishSkillWorkbenchTask,
  refineSkillWorkbenchTask,
} from "./api";
import type {
  SkillCenterOptimizationSource,
  SkillWorkbenchCapability,
  SkillWorkbenchOperation,
  SkillWorkbenchTask,
} from "./types";
import "./skill-workbench.css";

const TERMINAL = new Set(["ready", "failed", "cancelled", "expired", "published"]);

export interface SkillWorkbenchProps {
  initialSource?: SkillCenterOptimizationSource | null;
  task: SkillWorkbenchTask | null;
  taskLoading: boolean;
  taskError: string;
  onTaskChanged: (task: SkillWorkbenchTask) => void;
  onTaskDeleted: (jobId: string) => void;
  onRetryTask: () => void;
  onStartOver: () => void;
  onBack: () => void;
  onChooseCenterSource: () => void;
  onPublished?: () => void;
}

function stageLabel(task: SkillWorkbenchTask): string {
  if (task.state === "ready") return "Skill 已就绪";
  if (task.state === "failed") return "任务执行失败";
  if (task.state === "expired") return "DevEnv Session 已过期";
  if (task.stage === "validating") return "正在校验 Skill";
  if (task.stage === "packaging") return "正在打包 Skill";
  return "Codex 正在处理任务";
}

export function SkillWorkbench({
  initialSource = null,
  task,
  taskLoading,
  taskError,
  onTaskChanged,
  onTaskDeleted,
  onRetryTask,
  onStartOver,
  onBack,
  onChooseCenterSource,
}: SkillWorkbenchProps) {
  const [operation, setOperation] = useState<SkillWorkbenchOperation>(
    initialSource ? "optimize" : "create",
  );
  const [source, setSource] = useState(initialSource);
  const [file, setFile] = useState<File | null>(null);
  const [intent, setIntent] = useState("");
  const [capability, setCapability] = useState<SkillWorkbenchCapability | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [refinement, setRefinement] = useState("");
  const [publishResult, setPublishResult] = useState("");
  const requestRef = useRef(0);

  useEffect(() => {
    setSource(initialSource);
    if (initialSource) setOperation("optimize");
  }, [initialSource]);

  useEffect(() => {
    const controller = new AbortController();
    void getSkillWorkbenchCapability(controller.signal)
      .then(setCapability)
      .catch((cause) => setError(cause instanceof Error ? cause.message : String(cause)));
    return () => controller.abort();
  }, []);

  const hasSource = Boolean(source || file);
  const canSubmit =
    capability?.enabled === true &&
    intent.trim().length > 0 &&
    (operation === "create" || hasSource) &&
    !busy;

  async function submit() {
    if (!canSubmit) return;
    const run = ++requestRef.current;
    setBusy(true);
    setError("");
    try {
      const next = await createSkillWorkbenchTask({
        operation,
        intent: intent.trim(),
        ...(source ? { source } : {}),
        ...(file ? { file } : {}),
      });
      if (requestRef.current === run) onTaskChanged(next);
    } catch (cause) {
      if (requestRef.current === run) {
        setError(cause instanceof Error ? cause.message : String(cause));
      }
    } finally {
      if (requestRef.current === run) setBusy(false);
    }
  }

  async function cleanup() {
    if (!task) return;
    setBusy(true);
    setError("");
    try {
      await deleteSkillWorkbenchTask(task.jobId);
      onTaskDeleted(task.jobId);
      setIntent("");
      setConfirmCancel(false);
      onBack();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function refine() {
    if (!task || !refinement.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const next = await refineSkillWorkbenchTask({
        jobId: task.jobId,
        intent: refinement.trim(),
        expectedRevision: task.revision,
      });
      onTaskChanged(next);
      setRefinement("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  async function publish(disposition: "create-new" | "update-source") {
    if (!task || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await publishSkillWorkbenchTask({
        jobId: task.jobId,
        expectedRevision: task.revision,
        disposition,
        projectName: task.source?.projectName,
        skillSpaceIds: task.source?.skillSpaceId ? [task.source.skillSpaceId] : [],
      });
      setPublishResult(`已发布版本 ${result.version}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  }

  function changeOperation(next: SkillWorkbenchOperation) {
    if (task || next === operation) return;
    setOperation(next);
    setError("");
    if (next === "create") {
      setSource(null);
      setFile(null);
    }
  }

  if (!task && (taskLoading || taskError)) {
    return (
      <section className="skill-workbench" aria-label="Skill 工作台">
        <header className="skill-workbench__head">
          <div>
            <button type="button" className="skill-workbench__back" onClick={onBack}>
              返回技能中心
            </button>
            <h1>Skill 任务</h1>
          </div>
        </header>
        <div className="skill-workbench__start" aria-live="polite">
          {taskLoading && !taskError ? <TextShimmer duration={2.2} spread={16}>正在读取任务进度</TextShimmer> : null}
          {taskError ? (
            <div className="skill-workbench__notice" role="alert">
              <strong>无法读取 Skill 任务</strong>
              <span>{taskError}</span>
              <div className="skill-workbench__actions">
                <button type="button" onClick={onRetryTask}>重试</button>
                <button type="button" onClick={onBack}>返回技能中心</button>
              </div>
            </div>
          ) : null}
        </div>
      </section>
    );
  }

  if (task) {
    return (
      <section className="skill-workbench" aria-label="Skill 工作台">
        <header className="skill-workbench__head">
          <div>
            <button type="button" className="skill-workbench__back" onClick={onBack}>
              返回技能中心
            </button>
            <h1>{task.operation === "create" ? "创建 Skill" : "优化 Skill"}</h1>
          </div>
          <button
            type="button"
            className="skill-workbench__danger"
            onClick={() => setConfirmCancel(true)}
          >
            取消并清理
          </button>
        </header>

        {error ? <div className="skill-workbench__error" role="alert">{error}</div> : null}
        {taskError ? (
          <div className="skill-workbench__error" role="alert">
            {taskError} <button type="button" onClick={onRetryTask}>重试更新</button>
          </div>
        ) : null}

        <div className="skill-workbench__run-grid">
          <section className="skill-workbench__timeline" aria-live="polite">
            <div className={`skill-workbench__state is-${task.state}`}>
              {TERMINAL.has(task.state) ? (
                <strong>{stageLabel(task)}</strong>
              ) : (
                <TextShimmer duration={2.2} spread={16}>{stageLabel(task)}</TextShimmer>
              )}
              <span>{task.intent}</span>
            </div>
            <SkillConversationStream activities={task.activities} />
            {task.error ? <div className="skill-workbench__error" role="alert">{task.error}</div> : null}
            {task.state === "failed" || task.state === "expired" ? (
              <div className="skill-workbench__recovery">
                <button type="button" onClick={onStartOver}>修改意图后重试</button>
                {operation === "optimize" ? (
                  <button type="button" onClick={() => { onStartOver(); onChooseCenterSource(); }}>
                    更换来源
                  </button>
                ) : null}
                <button type="button" onClick={onBack}>返回技能中心</button>
              </div>
            ) : null}
          </section>

          <section className="skill-workbench__result" aria-label="Skill 结果">
            {task.state === "ready" || task.state === "published" ? (
              <>
                <div className="skill-workbench__summary">
                  <span>Skill</span>
                  <strong>{task.name ?? "未命名 Skill"}</strong>
                  <span>文件</span>
                  <strong>{task.files.length}</strong>
                  <span>校验</span>
                  <strong>{task.validation?.valid === false ? "未通过" : "已通过"}</strong>
                </div>
                {task.description ? <p>{task.description}</p> : null}
                {task.skillMd ? <pre><code>{task.skillMd}</code></pre> : null}
                <label className="skill-workbench__intent skill-workbench__refine">
                  <span>继续调整</span>
                  <textarea
                    value={refinement}
                    rows={4}
                    maxLength={20_000}
                    placeholder="描述下一轮希望达到的结果，Codex 会基于当前 Skill 自主完成调整"
                    onChange={(event) => setRefinement(event.target.value)}
                  />
                </label>
                <div className="skill-workbench__actions">
                  <button type="button" className="is-primary" disabled={!refinement.trim() || busy} onClick={() => void refine()}>
                    {busy ? "处理中…" : "提交调整"}
                  </button>
                  {task.source?.kind === "skill-center" && task.source.skillId ? (
                    <button type="button" disabled={busy} onClick={() => void publish("update-source")}>
                      更新原 Skill
                    </button>
                  ) : null}
                  <button type="button" disabled={busy} onClick={() => void publish("create-new")}>
                    发布为新 Skill
                  </button>
                  <button
                    type="button"
                    onClick={() => void downloadSkillWorkbenchTask(task.jobId).catch((cause) =>
                      setError(cause instanceof Error ? cause.message : String(cause))
                    )}
                  >
                    下载 ZIP
                  </button>
                  <button type="button" onClick={onBack}>返回技能中心</button>
                </div>
                {publishResult ? <div className="skill-workbench__notice" role="status">{publishResult}</div> : null}
              </>
            ) : (
              <div className="skill-workbench__result-empty">
                <strong>结果将在完成后显示</strong>
                <span>可以离开当前页面，稍后从左侧“Skill 任务”继续查看进度。</span>
                <button type="button" onClick={onBack}>安全离开</button>
              </div>
            )}
          </section>
        </div>

        {confirmCancel ? (
          <StudioConfirmDialog
            title="取消并清理 Skill 任务？"
            description="这会删除对应的 DevEnv Session。已完成的结果请先下载。"
            confirmLabel="确认取消并清理"
            variant="danger"
            busy={busy}
            onCancel={() => setConfirmCancel(false)}
            onConfirm={() => void cleanup()}
          />
        ) : null}
      </section>
    );
  }

  return (
    <section className="skill-workbench" aria-label="Skill 工作台">
      <header className="skill-workbench__head">
        <div>
          <button type="button" className="skill-workbench__back" onClick={onBack}>
            返回技能中心
          </button>
          <h1>Skill 工作台</h1>
        </div>
      </header>

      <div className="skill-workbench__start">
        <div className="skill-workbench__tabs" role="tablist" aria-label="Skill 操作">
          <button
            type="button"
            role="tab"
            aria-selected={operation === "create"}
            className={operation === "create" ? "is-active" : ""}
            onClick={() => changeOperation("create")}
          >
            创建 Skill
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={operation === "optimize"}
            className={operation === "optimize" ? "is-active" : ""}
            onClick={() => changeOperation("optimize")}
          >
            优化 Skill
          </button>
        </div>

        {capability && !capability.enabled ? (
          <div className="skill-workbench__notice" role="alert">
            <strong>DevEnv 暂不可用</strong>
            <span>{capability.reason}</span>
            <div><button type="button" onClick={onBack}>返回技能中心</button></div>
          </div>
        ) : null}

        {operation === "optimize" ? (
          <section className="skill-workbench__source" aria-label="优化来源">
            <div className="skill-workbench__source-actions">
              <button type="button" onClick={onChooseCenterSource}>从技能中心选择</button>
              <label className="skill-workbench__upload">
                上传 ZIP
                <input
                  type="file"
                  accept=".zip,application/zip"
                  onChange={(event) => {
                    const next = event.target.files?.[0] ?? null;
                    setFile(next);
                    if (next) setSource(null);
                    event.target.value = "";
                  }}
                />
              </label>
            </div>
            {source ? (
              <div className="skill-workbench__source-card">
                <strong>{source.name}</strong>
                <span>版本 {source.version} · {source.region}</span>
                <button type="button" onClick={onChooseCenterSource}>更换来源</button>
              </div>
            ) : file ? (
              <div className="skill-workbench__source-card">
                <strong>{file.name}</strong>
                <span>{file.size.toLocaleString()} bytes</span>
                <button type="button" onClick={() => setFile(null)}>移除</button>
              </div>
            ) : (
              <p>请选择一个已有 Skill 或上传 ZIP。选择后仍可更换，不会立即创建 DevEnv。</p>
            )}
          </section>
        ) : null}

        <label className="skill-workbench__intent">
          <span>{operation === "create" ? "描述你希望 Skill 完成的工作" : "描述希望如何优化这个 Skill"}</span>
          <textarea
            value={intent}
            rows={7}
            maxLength={20_000}
            placeholder={operation === "create"
              ? "例如：创建一个能把发布记录整理为面向用户的更新说明的 Skill"
              : "例如：保留现有能力，并让错误处理更清晰、步骤更可复用"}
            onChange={(event) => setIntent(event.target.value)}
          />
          <small>{intent.length.toLocaleString()} / 20,000</small>
        </label>

        {error ? <div className="skill-workbench__error" role="alert">{error}</div> : null}
        <footer className="skill-workbench__start-actions">
          <button type="button" onClick={onBack}>取消并返回</button>
          <button type="button" className="is-primary" disabled={!canSubmit} onClick={() => void submit()}>
            {busy ? "正在创建 DevEnv…" : operation === "create" ? "开始创建" : "开始优化"}
          </button>
        </footer>
      </div>
    </section>
  );
}

export function skillSourceFromCenter(
  space: SkillSpaceRef,
  skill: SkillSpaceSkill,
  region: string,
): SkillCenterOptimizationSource {
  return {
    kind: "skill-center",
    skillId: skill.skillId,
    version: skill.version,
    region,
    projectName: space.projectName,
    skillSpaceId: space.id,
    name: skill.skillName,
    description: skill.skillDescription,
  };
}
