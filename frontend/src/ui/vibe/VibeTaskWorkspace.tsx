import { useEffect, useMemo, useRef, useState } from "react";
import {
  streamVibeEvents,
  vibeClient,
  type VibeIntentSummary,
  type VibeTask,
} from "../../adk/vibe";
import { StudioConfirmDialog } from "../StudioConfirmDialog";
import "./VibeTaskWorkspace.css";

const STAGES = [
  "provisioning",
  "understanding",
  "building",
  "local_validation",
  "cloud_build",
  "runtime_validation",
  "delivering",
  "cleanup",
  "done",
] as const;

const STAGE_LABELS: Record<string, string> = {
  provisioning: "准备 Sandbox",
  understanding: "理解需求",
  building: "构建项目",
  local_validation: "本地验证",
  cloud_build: "云端构建",
  runtime_validation: "Runtime 验证",
  delivering: "交付结果",
  cleanup: "清理资源",
  done: "完成",
};

const STATE_LABELS: Record<string, string> = {
  provisioning: "准备中",
  ready: "等待凭据",
  running: "执行中",
  completed: "已完成",
  partial: "部分完成",
  blocked: "已阻塞",
  failed: "失败",
  cancelled: "已停止",
  expired: "已过期",
};

const TERMINAL = new Set(["completed", "partial", "blocked", "failed", "cancelled", "expired"]);

function formatTime(value: string): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function IntentSummary({ value }: { value: VibeIntentSummary | null }) {
  if (!value) return <p className="vibe-empty">意图摘要尚未生成。</p>;
  const sections = [
    ["已确认需求", value.confirmedRequirements],
    ["成功标准", value.successCriteria],
    ["待确认问题", value.openQuestions],
  ] as const;
  return (
    <div className="vibe-intent">
      <p>{value.goal || "尚未记录目标"}</p>
      {sections.map(([label, items]) =>
        items.length ? (
          <div key={label} className="vibe-intent__section">
            <strong>{label}</strong>
            <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
        ) : null,
      )}
    </div>
  );
}

export interface VibeTaskWorkspaceProps {
  task: VibeTask;
  tasks: VibeTask[];
  onSelectTask: (task: VibeTask) => void;
  onTaskChange: (task: VibeTask) => void;
  onDeleted: (taskId: string) => void;
}

export function VibeTaskWorkspace({
  task,
  tasks,
  onSelectTask,
  onTaskChange,
  onDeleted,
}: VibeTaskWorkspaceProps) {
  const [intent, setIntent] = useState<VibeIntentSummary | null>(null);
  const [accessKeyId, setAccessKeyId] = useState("");
  const [secretAccessKey, setSecretAccessKey] = useState("");
  const [sessionToken, setSessionToken] = useState("");
  const [busy, setBusy] = useState<"credentials" | "stop" | "delete" | "">("");
  const [error, setError] = useState("");
  const [confirm, setConfirm] = useState<"stop" | "delete" | null>(null);
  const taskRef = useRef(task);
  taskRef.current = task;

  useEffect(() => {
    setAccessKeyId("");
    setSecretAccessKey("");
    setSessionToken("");
    setError("");
    setIntent(null);
    const controller = new AbortController();
    void vibeClient.intent(task.taskId, controller.signal)
      .then(setIntent)
      .catch((cause) => {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : String(cause));
      });
    return () => controller.abort();
  }, [task.taskId, task.intentRevision]);

  useEffect(() => {
    if (TERMINAL.has(task.state)) return;
    const controller = new AbortController();
    void (async () => {
      try {
        for await (const event of streamVibeEvents(task.taskId, {
          after: task.lastSequence,
          signal: controller.signal,
        })) {
          const current = taskRef.current;
          if (current.taskId !== task.taskId) return;
          const next = await vibeClient.get(task.taskId, controller.signal);
          onTaskChange(next);
          if (event.eventType === "vibe.intent.updated") {
            setIntent(await vibeClient.intent(task.taskId, controller.signal));
          }
        }
      } catch (cause) {
        if (!controller.signal.aborted && (cause as Error)?.name !== "AbortError") {
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      }
    })();
    return () => controller.abort();
  }, [task.taskId, task.state]);

  const currentStage = Math.max(0, STAGES.indexOf(task.stage as (typeof STAGES)[number]));
  const canStop = !TERMINAL.has(task.state);
  const needsCredentials = !task.credentialsConfigured && !TERMINAL.has(task.state);
  const sortedTasks = useMemo(
    () => [...tasks].sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt)),
    [tasks],
  );

  async function submitCredentials(event: React.FormEvent) {
    event.preventDefault();
    if (!accessKeyId.trim() || !secretAccessKey) return;
    setBusy("credentials");
    setError("");
    try {
      const next = await vibeClient.credentials(
        task.taskId,
        accessKeyId.trim(),
        secretAccessKey,
        sessionToken.trim(),
      );
      setAccessKeyId("");
      setSecretAccessKey("");
      setSessionToken("");
      onTaskChange(next);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy("");
    }
  }

  async function performConfirmedAction() {
    if (!confirm) return;
    const action = confirm;
    setBusy(action);
    setError("");
    try {
      if (action === "stop") {
        onTaskChange(await vibeClient.stop(task.taskId, "用户从 Studio 停止任务"));
      } else {
        await vibeClient.remove(task.taskId);
        onDeleted(task.taskId);
      }
      setConfirm(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="vibe-workspace" aria-label="Vibe Task 工作区">
      <aside className="vibe-task-list" aria-label="Vibe Task 列表">
        <h2>Vibe Tasks</h2>
        <div className="vibe-task-list__scroll">
          {sortedTasks.map((item) => (
            <button
              type="button"
              key={item.taskId}
              className={`vibe-task-list__item${item.taskId === task.taskId ? " is-active" : ""}`}
              aria-current={item.taskId === task.taskId ? "true" : undefined}
              onClick={() => onSelectTask(item)}
            >
              <span title={item.displayName || item.goal}>{item.displayName || item.goal}</span>
              <small>{STATE_LABELS[item.state] || item.state}</small>
            </button>
          ))}
        </div>
      </aside>

      <div className="vibe-workspace__main">
        <header className="vibe-header">
          <div>
            <h1>{task.displayName || "Vibe Task"}</h1>
            <p>{task.goal}</p>
          </div>
          <div className="vibe-header__actions">
            <span className={`vibe-status is-${task.state}`}>{STATE_LABELS[task.state] || task.state}</span>
            <button type="button" onClick={() => setConfirm("stop")} disabled={!canStop || Boolean(busy)}>停止</button>
            <button type="button" className="is-danger" onClick={() => setConfirm("delete")} disabled={Boolean(busy)}>删除</button>
          </div>
        </header>

        {error ? <div className="vibe-error" role="alert">{error}</div> : null}
        {task.error ? <div className="vibe-error" role="alert">{task.error}</div> : null}
        {task.warnings.length ? (
          <div className="vibe-warning" role="status">
            <strong>注意事项</strong>
            <ul>{task.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
          </div>
        ) : null}

        <div className="vibe-grid">
          <section className="vibe-panel vibe-panel--timeline">
            <h2>执行进度</h2>
            <ol className="vibe-timeline">
              {STAGES.map((stage, index) => (
                <li key={stage} className={index < currentStage ? "is-done" : index === currentStage ? "is-current" : ""}>
                  <span className="vibe-timeline__mark" aria-hidden="true" />
                  <span>{STAGE_LABELS[stage]}</span>
                </li>
              ))}
            </ol>
          </section>

          <div className="vibe-stack">
            <section className="vibe-panel">
              <h2>任务信息</h2>
              <dl className="vibe-meta">
                <div><dt>Sandbox Session</dt><dd title={task.sandboxSessionId}>{task.sandboxSessionId || "准备中"}</dd></div>
                <div><dt>Validation Runtime</dt><dd title={task.validationRuntimeId}>{task.validationRuntimeId || "尚未创建"}</dd></div>
                <div><dt>Runtime 状态</dt><dd>{task.validationRuntimeStatus || "—"}</dd></div>
                <div><dt>云端尝试</dt><dd>第 {task.attempt} 次</dd></div>
                <div><dt>创建时间</dt><dd>{formatTime(task.createdAt)}</dd></div>
                <div><dt>过期时间</dt><dd>{formatTime(task.expiresAt)}</dd></div>
              </dl>
            </section>

            {needsCredentials ? (
              <section className="vibe-panel">
                <h2>云端凭据</h2>
                <form className="vibe-credentials" onSubmit={submitCredentials}>
                  <label>Access Key ID<input value={accessKeyId} onChange={(event) => setAccessKeyId(event.target.value)} autoComplete="off" disabled={Boolean(busy)} /></label>
                  <label>Secret Access Key<input type="password" value={secretAccessKey} onChange={(event) => setSecretAccessKey(event.target.value)} autoComplete="new-password" disabled={Boolean(busy)} /></label>
                  <label>Session Token（可选）<input type="password" value={sessionToken} onChange={(event) => setSessionToken(event.target.value)} autoComplete="new-password" disabled={Boolean(busy)} /></label>
                  <button type="submit" className="vibe-primary" disabled={busy === "credentials" || !accessKeyId.trim() || !secretAccessKey}>
                    {busy === "credentials" ? "正在提交…" : "提交并开始执行"}
                  </button>
                </form>
              </section>
            ) : null}

            <section className="vibe-panel">
              <h2>意图摘要</h2>
              <IntentSummary value={intent} />
            </section>
          </div>
        </div>
      </div>

      {confirm ? (
        <StudioConfirmDialog
          title={confirm === "stop" ? "停止 Vibe Task？" : "删除 Vibe Task？"}
          description={confirm === "stop" ? "任务执行将被取消，已创建的临时资源会进入清理流程。" : "任务记录和临时资源将被删除，此操作无法撤销。"}
          confirmLabel={confirm === "stop" ? "停止任务" : "确认删除"}
          variant="danger"
          busy={busy === confirm}
          onCancel={() => setConfirm(null)}
          onConfirm={() => void performConfirmedAction()}
        />
      ) : null}
    </section>
  );
}
