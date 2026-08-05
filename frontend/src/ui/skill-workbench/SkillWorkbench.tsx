import { useEffect, useRef, useState } from "react";
import {
  listSkillSpacesPage,
  type SkillSpaceRef,
} from "../../create/skills/skillspace";
import { CodeBrowserWorkspace } from "../CodeBrowserDialog";
import { isImeCompositionEvent } from "../composerKeyboard";
import { SkillConversationStream } from "../skill-create/SkillConversationStream";
import { StudioConfirmDialog } from "../StudioConfirmDialog";
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
type Action = "delete" | "publish" | "refine" | null;

const TERMINAL = new Set(["ready", "failed", "cancelled", "expired", "published"]);

export interface SkillWorkbenchProps {
  task: SkillWorkbenchTask | null;
  provisioningTask: SkillWorkbenchProvisioningTask | null;
  taskLoading: boolean;
  taskError: string;
  artifact: SkillWorkbenchArtifact | null;
  artifactLoading: boolean;
  artifactError: string;
  onTaskChanged: (task: SkillWorkbenchTask) => void;
  onDeleteTask: (jobId: string) => Promise<void>;
  onCancelProvisioning: (jobId: string) => Promise<void>;
  onRetryTask: () => void;
  onRetryArtifact: () => void;
  onBack: () => void;
  onViewPublished: (result: SkillWorkbenchPublishResult) => void;
}

function MoreIcon() {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="5.5" cy="12" r="1.25" fill="currentColor" />
      <circle cx="12" cy="12" r="1.25" fill="currentColor" />
      <circle cx="18.5" cy="12" r="1.25" fill="currentColor" />
    </svg>
  );
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
  if (task.state === "expired") return "DevEnv Session 已过期";
  if (task.stage === "validating") return "正在校验 Skill";
  if (task.stage === "packaging") return "正在打包 Skill";
  return "Codex 正在处理";
}

function regionLabel(region: SkillRegion): string {
  return region === "cn-shanghai" ? "上海" : "北京";
}

function ExecutionStages({ task }: { task: SkillWorkbenchTask }) {
  const statusStages = task.activities.flatMap((activity) =>
    activity.kind === "status"
      ? [{
          id: activity.id,
          text: activity.text,
          done: activity.status === "done",
        }]
      : [],
  );
  const stages = [
    { id: "session", text: "DevEnv 已就绪", done: true },
    {
      id: "codex",
      text: task.operation === "create" ? "Codex 正在创建 Skill" : "Codex 正在分析并优化 Skill",
      done: task.stage === "validating" || task.stage === "packaging" || TERMINAL.has(task.state),
    },
    ...statusStages,
    ...(task.stage === "validating" || task.stage === "packaging" || TERMINAL.has(task.state)
      ? [{ id: "validating", text: "校验 Skill 结构与内容", done: task.stage === "packaging" || TERMINAL.has(task.state) }]
      : []),
    ...(task.stage === "packaging" || TERMINAL.has(task.state)
      ? [{ id: "packaging", text: "生成可下载产物", done: TERMINAL.has(task.state) }]
      : []),
  ].filter((stage, index, values) =>
    values.findIndex((candidate) => candidate.text === stage.text) === index
  );

  return (
    <ol className="skill-workbench__execution-stages" aria-label="执行阶段">
      {stages.map((stage, index) => {
        const active = !stage.done && stages.slice(0, index).every((item) => item.done);
        return (
          <li
            key={stage.id}
            className={stage.done ? "is-done" : active ? "is-active" : ""}
          >
            <span>{stage.text}</span>
            <small>{stage.done ? "已完成" : active ? "进行中" : "等待中"}</small>
          </li>
        );
      })}
    </ol>
  );
}

function LoadingConversation({
  operation,
  intent,
}: {
  operation: "create" | "optimize";
  intent: string;
}) {
  return (
    <div className="skill-workbench__run-grid is-process-only">
      <section className="skill-workbench__timeline" aria-live="polite">
        <div className="skill-workbench__state is-running">
          <TextShimmer duration={2.2} spread={16}>正在创建 DevEnv</TextShimmer>
          <span className="skill-workbench__user-intent">{intent}</span>
        </div>
        <div className="skill-workbench__activity">
          <p className="skill-workbench__stage-note">
            正在分配隔离环境并准备 Codex。完成后会自动开始
            {operation === "create" ? "创建" : "优化"}，离开页面不会中断任务。
          </p>
        <ol className="skill-workbench__provisioning-steps">
          <li className="is-done">会话已建立</li>
          <li className="is-active">正在创建 DevEnv</li>
          <li>准备 Skill 工作区</li>
          <li>{operation === "create" ? "开始创建 Skill" : "开始优化 Skill"}</li>
        </ol>
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
  artifact,
  artifactLoading,
  artifactError,
  onTaskChanged,
  onDeleteTask,
  onCancelProvisioning,
  onRetryTask,
  onRetryArtifact,
  onBack,
  onViewPublished,
}: SkillWorkbenchProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
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
  const publishControllerRef = useRef<AbortController | null>(null);

  const ready = task?.state === "ready" || task?.state === "published";
  const persistedPublication = task && task.publication?.revision === task.revision
    ? task.publication
    : null;
  const effectivePublishResult = publishResult ?? persistedPublication;
  const canDeleteFromHeader = task
    ? task.state !== "ready" && task.state !== "published"
    : Boolean(provisioningTask);

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

  async function deleteConversation() {
    const jobId = task?.jobId ?? provisioningTask?.jobId;
    if (!jobId || action) return;
    setAction("delete");
    setError("");
    try {
      if (provisioningTask) await onCancelProvisioning(jobId);
      else await onDeleteTask(jobId);
      setConfirmDelete(false);
      onBack();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setAction(null);
    }
  }

  async function refine() {
    if (!task || !refinement.trim() || action) return;
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
    if (refinement.trim() && !action) void refine();
  };

  const deleteLabel = provisioningTask || task?.state === "running"
    ? "取消并删除会话"
    : "删除会话";
  const title = provisioningTask?.operation === "optimize" || task?.operation === "optimize"
    ? "优化 Skill"
    : "创建 Skill";

  return (
    <section className="skill-workbench" aria-label="Skill 会话">
      <header className="skill-workbench__head">
        <div>
          <button type="button" className="skill-workbench__back" onClick={onBack}>
            返回技能中心
          </button>
          <h1>{title}</h1>
        </div>
        {canDeleteFromHeader ? (
          <div className="skill-workbench__more">
            <button
              type="button"
              className="skill-workbench__icon-button"
              aria-label="会话操作"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((value) => !value)}
            >
              <MoreIcon />
            </button>
            {menuOpen ? (
              <>
                <button
                  type="button"
                  className="skill-workbench__menu-scrim"
                  aria-label="关闭会话操作"
                  onClick={() => setMenuOpen(false)}
                />
                <div className="skill-workbench__menu">
                  <button
                    type="button"
                    onClick={() => {
                      setMenuOpen(false);
                      setConfirmDelete(true);
                    }}
                  >
                    {deleteLabel}
                  </button>
                </div>
              </>
            ) : null}
          </div>
        ) : null}
      </header>

      {error ? <div className="skill-workbench__error" role="alert">{error}</div> : null}
      {taskError ? (
        <div className="skill-workbench__error" role="alert">
          <span>{taskError}</span>
          <button type="button" onClick={onRetryTask}>重试</button>
        </div>
      ) : null}

      {provisioningTask ? (
        <LoadingConversation
          operation={provisioningTask.operation}
          intent={provisioningTask.intent}
        />
      ) : !task ? (
        <div className="skill-workbench__loading" aria-live="polite">
          {taskLoading ? (
            <TextShimmer duration={2.2} spread={16}>正在读取会话</TextShimmer>
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
            <div className={`skill-workbench__state is-${task.state}`}>
              {TERMINAL.has(task.state) ? (
                <strong>{stageLabel(task)}</strong>
              ) : (
                <TextShimmer duration={2.2} spread={16}>{stageLabel(task)}</TextShimmer>
              )}
              <span className="skill-workbench__user-intent">{task.intent}</span>
            </div>
            <div className="skill-workbench__activity">
              <ExecutionStages task={task} />
              <SkillConversationStream activities={task.activities} />
              {task.error ? (
                <div className="skill-workbench__error" role="alert">{task.error}</div>
              ) : null}
              {task.state === "failed" || task.state === "expired" ? (
                <div className="skill-workbench__recovery">
                  <p>返回技能中心后可以调整意图或重新选择来源，再开始一段新会话。</p>
                  <button type="button" onClick={onBack}>返回技能中心</button>
                </div>
              ) : null}
            </div>
            {ready ? (
              <div className="composer composer--new-chat skill-workbench__composer">
                <div className="composer-box">
                  <div className="composer-input-stack">
                    <textarea
                      className="comp-input scroll"
                      rows={4}
                      maxLength={20_000}
                      value={refinement}
                      disabled={Boolean(action)}
                      placeholder="继续告诉 Codex 需要调整什么…"
                      onChange={(event) => setRefinement(event.target.value)}
                      onKeyDown={(event) => {
                        if (isImeCompositionEvent(event.nativeEvent)) return;
                        if (event.key === "Enter" && !event.shiftKey) {
                          event.preventDefault();
                          submitRefinement();
                        }
                      }}
                    />
                  </div>
                  <button
                    type="button"
                    className="comp-send"
                    disabled={!refinement.trim() || Boolean(action)}
                    onClick={submitRefinement}
                    aria-label="提交调整"
                  >
                    <SendIcon />
                  </button>
                </div>
              </div>
            ) : null}
          </section>

          {ready ? (
            <section className="skill-workbench__result" aria-label="Skill 产物">
              <>
                <header className="skill-workbench__artifact-head">
                  <div>
                    <strong>{artifact?.name || task.name || "Skill 产物"}</strong>
                    <span>
                      {artifact?.description || task.description || "已完成生成与校验"}
                    </span>
                  </div>
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
                </header>

                <div className="skill-workbench__artifact">
                  {artifactLoading ? (
                    <div className="skill-workbench__result-empty">
                      <TextShimmer duration={2.2} spread={16}>生成已完成，正在同步文件预览</TextShimmer>
                      <span>下载与发布能力将在产物校验完成后可用。</span>
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
                          {" · "}v{effectivePublishResult.version}
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
                      <span>发布会持续到 AgentKit 版本生效，请保持当前会话打开。</span>
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
          ) : null}
        </div>
      )}

      {confirmDelete ? (
        <StudioConfirmDialog
          title={`${deleteLabel}？`}
          description={task?.state === "running" || provisioningTask
            ? "这会停止当前处理、删除临时 DevEnv，并从会话列表移除。"
            : "这会删除临时 DevEnv，并从会话列表移除。"}
          confirmLabel={action === "delete" ? "正在删除…" : deleteLabel}
          variant="danger"
          busy={action === "delete"}
          onCancel={() => setConfirmDelete(false)}
          onConfirm={() => void deleteConversation()}
        />
      ) : null}
    </section>
  );
}
