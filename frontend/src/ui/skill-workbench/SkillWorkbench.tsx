import { useEffect, useRef, useState } from "react";
import { PanelRightOpen, Square, X } from "lucide-react";
import {
  formatSkillVersion,
  listSkillSpacesPage,
  type SkillSpaceRef,
} from "../../create/skills/skillspace";
import { CodeBrowserWorkspace } from "../CodeBrowserDialog";
import { isImeCompositionEvent } from "../composerKeyboard";
import { SkillConversationStream } from "../skill-create/SkillConversationStream";
import { TextShimmer } from "../text-shimmer/TextShimmer";
import {
  downloadSkillWorkbenchTask,
  publishSkillWorkbenchTask,
  refineSkillWorkbenchTask,
} from "./api";
import type {
  SkillWorkbenchArtifact,
  SkillWorkbenchProvisioningTask,
  SkillWorkbenchPublishProgress,
  SkillWorkbenchPublishResult,
  SkillWorkbenchTask,
} from "./types";
import "./skill-workbench.css";

type SkillRegion = "cn-beijing" | "cn-shanghai";
type Action = "publish" | "refine" | "stop" | null;

const TERMINAL = new Set(["ready", "failed", "cancelled", "expired", "published"]);

export interface SkillWorkbenchProps {
  task: SkillWorkbenchTask | null;
  provisioningTask: SkillWorkbenchProvisioningTask | null;
  taskLoading: boolean;
  taskError: string;
  taskRecovering: boolean;
  artifact: SkillWorkbenchArtifact | null;
  artifactLoading: boolean;
  artifactError: string;
  onTaskChanged: (task: SkillWorkbenchTask) => void;
  onCancelProvisioning: (jobId: string) => Promise<void>;
  onStopTask: (
    jobId: string,
    expectedRevision: number,
  ) => Promise<SkillWorkbenchTask>;
  onRetryTask: () => void;
  onRetryArtifact: () => void;
  onBack: () => void;
  onViewPublished: (result: SkillWorkbenchPublishResult) => void;
}

function DownloadIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 4.5v10m0 0-3.5-3.5M12 14.5l3.5-3.5M5.5 17.5v1.25c0 .97.78 1.75 1.75 1.75h9.5c.97 0 1.75-.78 1.75-1.75V17.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 18V6m0 0-4.5 4.5M12 6l4.5 4.5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function stageLabel(task: SkillWorkbenchTask): string {
  if (task.state === "published") return "Skill 已发布";
  if (task.state === "ready") return "Skill 已就绪";
  if (task.state === "failed") return "会话执行失败";
  if (task.state === "cancelled") return "会话已取消";
  if (task.state === "expired") return "DevEnv 已到期";
  if (task.stage === "validating") return "正在校验 Skill";
  if (task.stage === "packaging") return "正在打包 Skill";
  return "Codex 正在处理";
}

function regionLabel(region: SkillRegion): string {
  return region === "cn-shanghai" ? "上海" : "北京";
}

function ttlLabel(seconds: number): string {
  if (seconds % 3600 === 0) return `${seconds / 3600} 小时`;
  return `${Math.ceil(seconds / 60)} 分钟`;
}

function SkillUserTurn({
  intent,
  sourceName,
}: {
  intent: string;
  sourceName?: string;
}) {
  return (
    <div className="skill-workbench__user-turn">
      <div className="skill-workbench__user-bubble">
        {sourceName ? (
          <span className="skill-workbench__turn-context" title={sourceName}>
            Skill · {sourceName}
          </span>
        ) : null}
        <p>{intent}</p>
      </div>
    </div>
  );
}

function LoadingConversation({
  operation,
  intent,
  sourceName,
  refinement,
  stopping,
  onRefinementChange,
  onStop,
}: {
  operation: "create" | "optimize" | null;
  intent: string;
  sourceName?: string;
  refinement: string;
  stopping: boolean;
  onRefinementChange: (value: string) => void;
  onStop: () => void;
}) {
  return (
    <div className="skill-workbench__run-grid is-process-only">
      <section className="skill-workbench__timeline" aria-live="polite">
        <div className="skill-workbench__activity">
          <SkillUserTurn intent={intent} sourceName={sourceName} />
          <div className="skill-workbench__assistant-turn">
            <TextShimmer duration={2.2} spread={16}>正在创建 DevEnv</TextShimmer>
            <p className="skill-workbench__stage-note">
              正在准备隔离环境，随后会自动开始
            {operation === "create"
              ? "创建 Skill"
              : operation === "optimize"
                ? "优化 Skill"
                : "处理 Skill"}
              。
            </p>
          </div>
        </div>
        <div className="composer composer--new-chat skill-workbench__composer">
          <div className="composer-box">
            <div className="composer-input-stack">
              <textarea
                className="comp-input scroll"
                rows={4}
                maxLength={20_000}
                value={refinement}
                disabled={stopping}
                aria-label="下一步 Skill 调整要求"
                placeholder="可以先输入下一步要求，DevEnv 就绪后会保留在这里…"
                onChange={(event) => onRefinementChange(event.target.value)}
              />
            </div>
            <button
              type="button"
              className="comp-send is-stop"
              disabled={stopping}
              onClick={onStop}
              aria-label="停止创建 DevEnv"
              title="停止创建 DevEnv"
            >
              <Square className="icon" size={16} fill="currentColor" strokeWidth={0} aria-hidden />
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

export function SkillWorkbench({
  task,
  provisioningTask,
  taskLoading,
  taskError,
  taskRecovering,
  artifact,
  artifactLoading,
  artifactError,
  onTaskChanged,
  onCancelProvisioning,
  onStopTask,
  onRetryTask,
  onRetryArtifact,
  onBack,
  onViewPublished,
}: SkillWorkbenchProps) {
  const [action, setAction] = useState<Action>(null);
  const [error, setError] = useState("");
  const [refinement, setRefinement] = useState("");
  const [publishRegion, setPublishRegion] = useState<SkillRegion>(
    task?.source?.region === "cn-shanghai" ? "cn-shanghai" : "cn-beijing",
  );
  const [publishSpaces, setPublishSpaces] = useState<SkillSpaceRef[]>([]);
  const [publishSpacesLoading, setPublishSpacesLoading] = useState(false);
  const [publishSpacesError, setPublishSpacesError] = useState("");
  const [selectedPublishSpaceId, setSelectedPublishSpaceId] = useState("");
  const [publishProgress, setPublishProgress] =
    useState<SkillWorkbenchPublishProgress | null>(null);
  const [publishResult, setPublishResult] =
    useState<SkillWorkbenchPublishResult | null>(null);
  const [artifactPanelOpen, setArtifactPanelOpen] = useState(false);
  const publishControllerRef = useRef<AbortController | null>(null);
  const activityRef = useRef<HTMLDivElement>(null);
  const followActivityRef = useRef(true);
  const artifactToggleRef = useRef<HTMLButtonElement>(null);
  const artifactCloseRef = useRef<HTMLButtonElement>(null);

  const ready = task?.state === "ready" || task?.state === "published";
  const persistedPublication = task && task.publication?.revision === task.revision
    ? task.publication
    : null;
  const effectivePublishResult = publishResult ?? persistedPublication;
  const recoveryUnavailable =
    task?.state === "expired" && task.recoveryAvailable === false;
  const canRefine = task && task.state !== "running" && !recoveryUnavailable;

  useEffect(() => {
    if (!ready) return;
    let active = true;
    setPublishSpacesLoading(true);
    setPublishSpacesError("");
    void listSkillSpacesPage({
      region: publishRegion,
      page: 1,
      pageSize: 100,
    })
      .then((response) => {
        if (!active) return;
        setPublishSpaces(response.items);
        setSelectedPublishSpaceId((current) =>
          response.items.some((space) => space.id === current)
            ? current
            : response.items[0]?.id ?? ""
        );
      })
      .catch((cause) => {
        if (!active) return;
        setPublishSpaces([]);
        setSelectedPublishSpaceId("");
        setPublishSpacesError(cause instanceof Error ? cause.message : String(cause));
      })
      .finally(() => {
        if (active) setPublishSpacesLoading(false);
      });
    return () => { active = false; };
  }, [publishRegion, ready]);

  useEffect(() => () => publishControllerRef.current?.abort(), []);

  useEffect(() => {
    followActivityRef.current = true;
    setArtifactPanelOpen(false);
  }, [task?.jobId]);

  useEffect(() => {
    if (!artifactPanelOpen) return;
    const frame = requestAnimationFrame(() => artifactCloseRef.current?.focus());
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setArtifactPanelOpen(false);
      artifactToggleRef.current?.focus();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [artifactPanelOpen]);

  useEffect(() => {
    if (!task || !followActivityRef.current) return;
    const frame = requestAnimationFrame(() => {
      if (!activityRef.current || !followActivityRef.current) return;
      activityRef.current.scrollTop = activityRef.current.scrollHeight;
    });
    return () => cancelAnimationFrame(frame);
  }, [task?.activities, task?.stage, task?.state]);

  const handleActivityScroll = () => {
    if (!activityRef.current) return;
    const { scrollHeight, scrollTop, clientHeight } = activityRef.current;
    followActivityRef.current = scrollHeight - scrollTop - clientHeight <= 48;
  };

  async function refine() {
    if (!canRefine || !refinement.trim() || action) return;
    setAction("refine");
    setError("");
    try {
      const next = await refineSkillWorkbenchTask({
        jobId: task.jobId,
        intent: refinement.trim(),
        expectedRevision: task.revision,
      });
      onTaskChanged(next);
      setRefinement("");
      setPublishResult(null);
      setPublishProgress(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setAction(null);
    }
  }

  async function stop() {
    const jobId = task?.jobId ?? provisioningTask?.jobId;
    if (!jobId || action) return;
    setAction("stop");
    setError("");
    try {
      if (task?.state === "running") {
        await onStopTask(task.jobId, task.revision);
      } else if (provisioningTask) {
        await onCancelProvisioning(provisioningTask.jobId);
        onBack();
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setAction(null);
    }
  }

  async function publish(disposition: "create-new" | "update-source") {
    if (!task || action) return;
    const selectedSpace = publishSpaces.find(
      (space) => space.id === selectedPublishSpaceId,
    );
    if (disposition === "create-new" && !selectedSpace) {
      setError("请选择发布目标 Skill 空间。");
      return;
    }
    const controller = new AbortController();
    publishControllerRef.current = controller;
    setAction("publish");
    setError("");
    setPublishResult(null);
    setPublishProgress({ phase: "preparing", message: "正在准备发布" });
    const skillSpaceIds = disposition === "update-source"
      ? task.source?.skillSpaceId ? [task.source.skillSpaceId] : []
      : [selectedSpace!.id];
    try {
      const result = await publishSkillWorkbenchTask({
        jobId: task.jobId,
        expectedRevision: task.revision,
        disposition,
        skillSpaceIds,
        region: disposition === "update-source"
          ? task.source?.region === "cn-shanghai" ? "cn-shanghai" : "cn-beijing"
          : publishRegion,
        projectName: disposition === "update-source"
          ? task.source?.projectName
          : selectedSpace?.projectName,
        signal: controller.signal,
        onProgress: setPublishProgress,
      });
      setPublishResult(result);
      setPublishProgress(null);
    } catch (cause) {
      if (!controller.signal.aborted) {
        setError(cause instanceof Error ? cause.message : String(cause));
        setPublishProgress(null);
      }
    } finally {
      if (publishControllerRef.current === controller) {
        publishControllerRef.current = null;
        setAction(null);
      }
    }
  }

  const submitRefinement = () => {
    if (canRefine && refinement.trim() && !action) void refine();
  };

  const operation = provisioningTask?.operation ?? task?.operation ?? null;
  const title = operation === "optimize"
    ? "优化 Skill"
    : operation === "create"
      ? "创建 Skill"
      : "Skill 会话";

  return (
    <section className="skill-workbench" aria-label="Skill 会话">
      <header className="skill-workbench__head">
        <div>
          <button type="button" className="skill-workbench__back" onClick={onBack}>
            返回技能中心
          </button>
          <h1>{title}</h1>
        </div>
        {ready ? (
          <button
            ref={artifactToggleRef}
            type="button"
            className="skill-workbench__artifact-toggle"
            aria-controls="skill-workbench-artifact-panel"
            aria-expanded={artifactPanelOpen}
            onClick={() => setArtifactPanelOpen(true)}
          >
            <PanelRightOpen size={16} aria-hidden />
            <span>查看产物</span>
          </button>
        ) : null}
      </header>

      {error ? <div className="skill-workbench__error" role="alert">{error}</div> : null}
      {taskError ? (
        <div
          className={taskRecovering
            ? "skill-workbench__connection"
            : "skill-workbench__error"}
          role={taskRecovering ? "status" : "alert"}
        >
          <span>{taskError}</span>
          {taskRecovering ? (
            <button type="button" onClick={onRetryTask}>立即重试</button>
          ) : null}
        </div>
      ) : null}

      {provisioningTask ? (
        <LoadingConversation
          operation={provisioningTask.operation}
          intent={provisioningTask.intent}
          sourceName={provisioningTask.sourceName}
          refinement={refinement}
          stopping={action === "stop"}
          onRefinementChange={setRefinement}
          onStop={() => void stop()}
        />
      ) : !task ? (
        <div className="skill-workbench__loading" aria-live="polite">
          {taskLoading || taskRecovering ? (
            <TextShimmer duration={2.2} spread={16}>
              {taskRecovering ? "正在重新连接 DevEnv" : "正在读取会话"}
            </TextShimmer>
          ) : (
            <>
              <strong>会话不存在或已删除</strong>
              <button type="button" onClick={onBack}>返回技能中心</button>
            </>
          )}
        </div>
      ) : (
        <div className={`skill-workbench__run-grid${ready ? "" : " is-process-only"}`}>
          <section className="skill-workbench__timeline" aria-live="polite">
            <div
              ref={activityRef}
              className="skill-workbench__activity"
              onScroll={handleActivityScroll}
            >
              <SkillUserTurn
                intent={task.intent}
                sourceName={task.source?.name}
              />
              <div className="skill-workbench__assistant-turn">
                <div className="skill-workbench__assistant-head">
                  {TERMINAL.has(task.state) ? (
                    <strong>{stageLabel(task)}</strong>
                  ) : (
                    <TextShimmer duration={2.2} spread={16}>
                      {stageLabel(task)}
                    </TextShimmer>
                  )}
                </div>
                {task.toolId || task.sessionId ? (
                  <dl className="skill-workbench__runtime-meta">
                    {task.toolId ? (
                      <div>
                        <dt>Tool ID</dt>
                        <dd title={task.toolId}>{task.toolId}</dd>
                      </div>
                    ) : null}
                    {task.sessionId ? (
                      <div>
                        <dt>Session ID</dt>
                        <dd title={task.sessionId}>{task.sessionId}</dd>
                      </div>
                    ) : null}
                  </dl>
                ) : null}
                <SkillConversationStream activities={task.activities} />
                {task.error ? (
                  <div className="skill-workbench__error" role="alert">{task.error}</div>
                ) : null}
                {["failed", "cancelled", "expired"].includes(task.state) ? (
                  <div className="skill-workbench__recovery">
                    <p>
                      {task.state === "expired"
                        ? task.recoveryAvailable === true
                          ? "当前 DevEnv 已释放，当前产物无法下载或发布。提交后将创建新的 DevEnv，并从最近的恢复点继续。"
                          : task.recoveryAvailable === false
                            ? "当前 DevEnv 已释放，当前产物无法下载或发布，并且没有可用恢复点。请返回技能中心重新创建。"
                            : "当前 DevEnv 已释放，当前产物无法下载或发布。提交后会尝试从最近可用的恢复点创建新 DevEnv；如果恢复点不可用，系统会提示重新创建。"
                        : task.state === "cancelled"
                          ? "当前任务已停止，DevEnv 和已完成内容仍保留。可以在下方继续输入。"
                          : "本轮执行失败，但 DevEnv 和已完成内容仍保留。调整要求后可以继续。"}
                    </p>
                    {recoveryUnavailable ? (
                      <button type="button" onClick={onBack}>返回技能中心</button>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
            <div className="composer composer--new-chat skill-workbench__composer">
              <div className="composer-box">
                <div className="composer-input-stack">
                  <textarea
                    className="comp-input scroll"
                    rows={4}
                    maxLength={20_000}
                    value={refinement}
                    disabled={Boolean(action) || recoveryUnavailable}
                    aria-label="Skill 调整要求"
                    placeholder={task.state === "running"
                      ? "可以先输入下一步要求；停止当前任务后即可提交…"
                      : task.state === "expired"
                        ? recoveryUnavailable
                          ? "当前会话没有可用恢复点"
                          : "描述下一步 Skill 调整，提交后将恢复到新的 DevEnv…"
                        : "继续告诉 Codex 需要调整什么…"}
                    onChange={(event) => setRefinement(event.target.value)}
                    onKeyDown={(event) => {
                      if (isImeCompositionEvent(event.nativeEvent)) return;
                      if (
                        event.key === "Enter" &&
                        !event.shiftKey &&
                        canRefine
                      ) {
                        event.preventDefault();
                        submitRefinement();
                      }
                    }}
                  />
                </div>
                {task.state === "running" ? (
                  <button
                    type="button"
                    className="comp-send is-stop"
                    disabled={Boolean(action)}
                    onClick={() => void stop()}
                    aria-label="停止当前任务"
                    title="停止当前任务"
                  >
                    <Square className="icon" size={16} fill="currentColor" strokeWidth={0} aria-hidden />
                  </button>
                ) : (
                  <button
                    type="button"
                    className="comp-send"
                    disabled={
                      !refinement.trim() || Boolean(action) || recoveryUnavailable
                    }
                    onClick={submitRefinement}
                    aria-label="提交调整"
                  >
                    <SendIcon />
                  </button>
                )}
              </div>
            </div>
          </section>

          {ready ? (
            <>
              {artifactPanelOpen ? (
                <button
                  type="button"
                  className="skill-workbench__artifact-scrim"
                  aria-label="关闭产物预览"
                  onClick={() => setArtifactPanelOpen(false)}
                />
              ) : null}
              <section
                id="skill-workbench-artifact-panel"
                className={`skill-workbench__result${artifactPanelOpen ? " is-open" : ""}`}
                role={artifactPanelOpen ? "dialog" : undefined}
                aria-modal={artifactPanelOpen ? "true" : undefined}
                aria-labelledby="skill-workbench-artifact-title"
              >
                <>
                  <header className="skill-workbench__artifact-head">
                    <div className="skill-workbench__artifact-copy">
                    <strong id="skill-workbench-artifact-title">
                      {artifact?.name || task.name || "Skill 产物"}
                    </strong>
                    <span>
                      {artifact?.description || task.description || "已完成生成与校验"}
                    </span>
                    </div>
                    <div className="skill-workbench__artifact-actions">
                    <button
                      type="button"
                      className="skill-workbench__download"
                      onClick={() => void downloadSkillWorkbenchTask(task.jobId).catch((cause) =>
                        setError(cause instanceof Error ? cause.message : String(cause))
                      )}
                      title="下载 ZIP"
                    >
                      <DownloadIcon />
                      <span>下载 ZIP</span>
                    </button>
                    <button
                      ref={artifactCloseRef}
                      type="button"
                      className="skill-workbench__artifact-close"
                      aria-label="关闭产物预览"
                      title="关闭产物预览"
                      onClick={() => {
                        setArtifactPanelOpen(false);
                        artifactToggleRef.current?.focus();
                      }}
                    >
                      <X size={17} aria-hidden />
                    </button>
                    </div>
                  </header>

                  {task.sessionTtlSeconds ? (
                    <div className="skill-workbench__ttl-note" role="note">
                      DevEnv 最长保留 {ttlLabel(task.sessionTtlSeconds)}，从创建时开始计算。
                      请及时下载或发布。超过保留时间后将无法下载或发布。
                    </div>
                  ) : null}

                  <div className="skill-workbench__artifact">
                  {artifactLoading ? (
                    <div className="skill-workbench__result-empty">
                      <TextShimmer duration={2.2} spread={16}>生成已完成，正在同步文件预览</TextShimmer>
                      <span>文件预览正在同步，下载与发布仍可使用。</span>
                    </div>
                  ) : artifactError ? (
                    <div className="skill-workbench__result-empty" role="alert">
                      <strong>无法读取文件预览</strong>
                      <span>{artifactError}</span>
                      <button type="button" onClick={onRetryArtifact}>重试</button>
                    </div>
                  ) : artifact ? (
                    <CodeBrowserWorkspace
                      project={{
                        name: artifact.name,
                        files: artifact.files.map((file) => ({
                          path: file.path,
                          content: file.content,
                        })),
                      }}
                      readOnly
                      renderMarkdown
                    />
                  ) : (
                    <div className="skill-workbench__result-empty">
                      <strong>暂无可预览文件</strong>
                    </div>
                  )}
                  </div>

                  <footer className="skill-workbench__publish">
                  {effectivePublishResult ? (
                    <div className="skill-workbench__publish-success" role="status">
                      <div>
                        <strong>{task.state === "published" ? "该版本已发布" : "Skill 已发布"}</strong>
                        <span>
                          {regionLabel(effectivePublishResult.region)} · {effectivePublishResult.projectName}
                          {" · "}{effectivePublishResult.skillSpaceIds[0] || "未关联空间"}
                          {" · "}{formatSkillVersion(effectivePublishResult.version)}
                        </span>
                        <small title={effectivePublishResult.skillId}>{effectivePublishResult.skillId}</small>
                      </div>
                      <button type="button" onClick={() => onViewPublished(effectivePublishResult)}>
                        在技能中心查看
                      </button>
                    </div>
                  ) : publishProgress ? (
                    <div className="skill-workbench__publish-progress" role="status">
                      <TextShimmer duration={2.2} spread={16}>
                        {publishProgress.message}
                      </TextShimmer>
                      <span>发布会持续到 Skill 版本生效，请保持当前会话打开。</span>
                    </div>
                  ) : (
                    <div className="skill-workbench__publish-controls">
                      <div className="skill-workbench__publish-target">
                        <div className="skill-workbench__publish-regions" aria-label="发布地域">
                          {(["cn-beijing", "cn-shanghai"] as const).map((region) => (
                            <button
                              key={region}
                              type="button"
                              className={publishRegion === region ? "is-active" : ""}
                              disabled={Boolean(action)}
                              onClick={() => setPublishRegion(region)}
                            >
                              {regionLabel(region)}
                            </button>
                          ))}
                        </div>
                        <select
                          aria-label="发布目标 Skill 空间"
                          value={selectedPublishSpaceId}
                          disabled={publishSpacesLoading || Boolean(action)}
                          onChange={(event) => setSelectedPublishSpaceId(event.target.value)}
                        >
                          {publishSpaces.length === 0 ? (
                            <option value="">
                              {publishSpacesLoading ? "正在读取 Skill 空间…" : "暂无可用 Skill 空间"}
                            </option>
                          ) : publishSpaces.map((space) => (
                            <option key={space.id} value={space.id}>
                              {space.name} · {space.projectName || "default"}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="skill-workbench__publish-actions">
                        {task.source?.kind === "skill-center" && task.source.skillId ? (
                          <button
                            type="button"
                            disabled={Boolean(action)}
                            onClick={() => void publish("update-source")}
                          >
                            更新原 Skill
                          </button>
                        ) : null}
                        <button
                          type="button"
                          className="is-primary"
                          disabled={!selectedPublishSpaceId || publishSpacesLoading || Boolean(action)}
                          onClick={() => void publish("create-new")}
                        >
                          发布为新 Skill
                        </button>
                      </div>
                      {publishSpacesError ? (
                        <span className="skill-workbench__publish-error" role="alert">
                          {publishSpacesError}
                        </span>
                      ) : null}
                    </div>
                  )}
                  </footer>
                </>
              </section>
            </>
          ) : null}
        </div>
      )}

    </section>
  );
}
