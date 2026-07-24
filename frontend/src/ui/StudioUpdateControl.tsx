import { useCallback, useEffect, useRef, useState } from "react";
import {
  getStudioUpdateStatus,
  startStudioUpdate,
  type StudioUpdateStatus,
} from "../adk/client";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import "./StudioUpdateControl.css";

const CHECK_INTERVAL_MS = 3 * 60 * 1000;
const RELEASE_POLL_INTERVAL_MS = 3_000;
const RELEASE_TIMEOUT_MS = 10 * 60 * 1000;
const STUDIO_UPDATE_STORAGE_KEY = "veadk.studio.pending-update";

type UpdatePhase = "idle" | "confirm" | "submitting" | "published" | "error";
type PendingStudioUpdate = { targetVersion: string; startedAt: number };

const UPDATE_STEPS = [
  { id: "resolving", label: "读取目标版本信息" },
  { id: "downloading", label: "下载并校验完整更新包" },
  { id: "preparing", label: "准备 VeFaaS Function 代码" },
  { id: "submitting", label: "提交 Function 更新" },
  { id: "publishing", label: "发布新 Revision 并重启服务" },
] as const;

function formatElapsed(seconds: number) {
  if (seconds < 60) return `${seconds} 秒`;
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}

function loadPendingUpdate(): PendingStudioUpdate | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STUDIO_UPDATE_STORAGE_KEY);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<PendingStudioUpdate>;
    if (typeof value.targetVersion === "string" && typeof value.startedAt === "number") {
      return { targetVersion: value.targetVersion, startedAt: value.startedAt };
    }
  } catch {
    // Remove malformed state so it cannot keep the update control stuck.
  }
  window.localStorage.removeItem(STUDIO_UPDATE_STORAGE_KEY);
  return null;
}

function persistPendingUpdate(targetVersion: string, startedAt: number) {
  window.localStorage.setItem(
    STUDIO_UPDATE_STORAGE_KEY,
    JSON.stringify({ targetVersion, startedAt }),
  );
}

function clearPendingUpdate() {
  window.localStorage.removeItem(STUDIO_UPDATE_STORAGE_KEY);
}

function StudioUpdateIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M19.2 8.3A8 8 0 1 0 20 13" />
      <path d="M19.2 4.8v3.5h-3.5" />
      <path d="M12 7.8v7.7" />
      <path d="m9.2 12.7 2.8 2.8 2.8-2.8" />
    </svg>
  );
}

export function StudioUpdateControl() {
  const [initialPending] = useState<PendingStudioUpdate | null>(loadPendingUpdate);
  const [status, setStatus] = useState<StudioUpdateStatus | null>(null);
  const [phase, setPhase] = useState<UpdatePhase>(
    initialPending ? "submitting" : "idle",
  );
  const [dialogOpen, setDialogOpen] = useState(false);
  const [message, setMessage] = useState("");
  const [selectedVersion, setSelectedVersion] = useState(
    initialPending?.targetVersion ?? "",
  );
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const targetVersionRef = useRef(initialPending?.targetVersion ?? "");
  const startedAtRef = useRef(initialPending?.startedAt ?? 0);

  const refresh = useCallback(async () => {
    const next = await getStudioUpdateStatus(targetVersionRef.current || undefined);
    setStatus(next);
    return next;
  }, []);

  useEffect(() => {
    let active = true;
    const check = () => {
      void refresh().catch(() => {
        if (active) setStatus((current) => current);
      });
    };
    check();
    const timer = window.setInterval(check, CHECK_INTERVAL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [refresh]);

  useEffect(() => {
    if (phase !== "submitting") return;
    const timer = window.setInterval(() => {
      void refresh()
        .then((next) => {
          const target = targetVersionRef.current;
          if (
            (target && next.currentVersion === target) ||
            (!target && !next.available && Boolean(next.latestVersion))
          ) {
            window.clearInterval(timer);
            clearPendingUpdate();
            setPhase("published");
            setMessage("Studio 已更新，刷新页面即可使用新版本");
            return;
          }
          if (next.state === "error") {
            window.clearInterval(timer);
            clearPendingUpdate();
            setPhase("error");
            setMessage(next.message || "Studio 更新失败");
            return;
          }
          if (Date.now() - startedAtRef.current > RELEASE_TIMEOUT_MS) {
            window.clearInterval(timer);
            clearPendingUpdate();
            setPhase("error");
            setMessage("等待 VeFaaS 发布超时，请稍后重新检查版本");
          }
        })
        .catch(() => {
          // Replacing the current Revision may briefly interrupt this request.
        });
    }, RELEASE_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [phase, refresh]);

  useEffect(() => {
    if (phase !== "idle" || status?.state !== "updating") return;
    targetVersionRef.current = status.targetVersion;
    startedAtRef.current = status.startedAt || Date.now();
    persistPendingUpdate(status.targetVersion, startedAtRef.current);
    setSelectedVersion(status.targetVersion);
    setPhase("submitting");
  }, [phase, status]);

  useEffect(() => {
    if (phase !== "submitting") {
      setElapsedSeconds(0);
      return;
    }
    const updateElapsed = () => {
      const startedAt = startedAtRef.current || Date.now();
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)));
    };
    updateElapsed();
    const timer = window.setInterval(updateElapsed, 1_000);
    return () => window.clearInterval(timer);
  }, [phase]);

  if (!status?.enabled) return null;
  const visible = status.available || status.state === "updating" || phase !== "idle";
  if (!visible) return null;
  const releases = status.releases ?? [];
  const targetVersion = selectedVersion || releases[0]?.version || status.latestVersion;
  const targetRelease = releases.find(
    (release) => release.version === targetVersion,
  );

  const beginUpdate = async () => {
    targetVersionRef.current = targetVersion;
    startedAtRef.current = Date.now();
    persistPendingUpdate(targetVersion, startedAtRef.current);
    setPhase("submitting");
    setMessage("");
    try {
      const result = await startStudioUpdate(targetVersion);
      targetVersionRef.current = result.version;
      persistPendingUpdate(result.version, startedAtRef.current);
      setMessage("更新已提交，正在等待 VeFaaS 发布新版本");
    } catch (error) {
      if (error instanceof TypeError) {
        setMessage("连接已切换，正在确认新版本状态");
        return;
      }
      clearPendingUpdate();
      setPhase("error");
      setMessage(error instanceof Error ? error.message : "Studio 更新失败");
    }
  };

  return (
    <>
      <button
        type="button"
        className={`studio-update-trigger is-${phase}`}
        title={
          phase === "submitting"
            ? "正在更新 Studio"
            : phase === "published"
              ? "Studio 已更新"
              : `更新 Studio 至 ${status.latestVersion}`
        }
        onClick={() => {
          if (phase === "published") {
            window.location.reload();
          } else if (phase === "submitting" || phase === "error") {
            setDialogOpen(true);
          } else {
            setSelectedVersion(releases[0]?.version || status.latestVersion);
            setPhase("confirm");
            setDialogOpen(true);
          }
        }}
      >
        <StudioUpdateIcon className="studio-update-icon" />
        {phase === "submitting" ? (
          <TextShimmer as="span">正在更新</TextShimmer>
        ) : phase === "published" ? (
          <span>刷新使用新版</span>
        ) : phase === "error" ? (
          <span>更新失败</span>
        ) : (
          <span>有新版更新</span>
        )}
      </button>

      {dialogOpen && phase !== "idle" && (
        <div className="confirm-scrim" role="presentation">
          <section
            className="confirm-box studio-update-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="studio-update-title"
          >
            <div className="studio-update-dialog-mark">
              <StudioUpdateIcon />
            </div>
            <div id="studio-update-title" className="confirm-title">
              {phase === "error"
                ? "Studio 更新失败"
                : phase === "submitting"
                  ? "正在更新 Studio"
                  : phase === "published"
                    ? "Studio 更新完成"
                    : "发现新版本"}
            </div>
            {phase === "error" ? (
              <p className="confirm-text studio-update-error">{message}</p>
            ) : phase === "submitting" || phase === "published" ? (
              <>
                <div className="studio-update-progress-summary">
                  <div>
                    <span>目标版本</span>
                    <strong>{targetVersionRef.current || targetVersion}</strong>
                  </div>
                  <div>
                    <span>{phase === "published" ? "更新状态" : "已用时"}</span>
                    <strong>
                      {phase === "published" ? "已完成" : formatElapsed(elapsedSeconds)}
                    </strong>
                  </div>
                </div>
                <ol className="studio-update-progress" aria-label="Studio 更新进度">
                  {UPDATE_STEPS.map((step, index) => {
                    const currentIndex = UPDATE_STEPS.findIndex(
                      (item) => item.id === status.progressStage,
                    );
                    const completed = phase === "published" || index < currentIndex;
                    const active =
                      phase === "submitting" && step.id === status.progressStage;
                    return (
                      <li
                        key={step.id}
                        className={completed ? "is-complete" : active ? "is-active" : ""}
                      >
                        <span className="studio-update-progress-dot" aria-hidden />
                        <div>
                          <span>{step.label}</span>
                          {active && (
                            <TextShimmer as="small">
                              {status.progressMessage || message || "正在处理"}
                            </TextShimmer>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ol>
                <p className="studio-update-progress-note">
                  发布阶段会短暂中断连接；关闭此窗口不会停止更新，可随时点击右上角按钮重新查看。
                </p>
              </>
            ) : (
              <>
                <p className="confirm-text">
                  更新会重启 Studio 服务，预计约 3–5 分钟完成更新与发布。期间正在进行的对话、
                  流式响应或部署任务可能中断，登录态不会受到影响。
                </p>
                <label className="studio-update-field" htmlFor="studio-update-version">
                  <span>选择版本</span>
                  <select
                    id="studio-update-version"
                    value={targetVersion}
                    onChange={(event) => setSelectedVersion(event.target.value)}
                  >
                    {releases.map((release) => (
                      <option key={release.version} value={release.version}>
                        {release.version}
                      </option>
                    ))}
                  </select>
                </label>
                <dl className="studio-update-versions">
                  <div>
                    <dt>当前版本</dt>
                    <dd>{status.currentVersion}</dd>
                  </div>
                  <div>
                    <dt>目标版本</dt>
                    <dd>{targetVersion}</dd>
                  </div>
                  <div>
                    <dt>Commit</dt>
                    <dd>{(targetRelease?.gitSha || status.latestGitSha).slice(0, 8)}</dd>
                  </div>
                </dl>
                <section className="studio-update-changelog" aria-labelledby="studio-update-changelog-title">
                  <div id="studio-update-changelog-title">更新内容</div>
                  {targetRelease?.changelog.length ? (
                    <ul>
                      {targetRelease.changelog.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>暂无更新说明</p>
                  )}
                </section>
              </>
            )}
            <div className="confirm-actions">
              <button
                type="button"
                className="confirm-btn"
                onClick={() => {
                  setDialogOpen(false);
                  if (phase === "confirm") {
                    setPhase("idle");
                    setMessage("");
                  }
                }}
              >
                {phase === "submitting" ? "后台运行" : phase === "confirm" ? "取消" : "关闭"}
              </button>
              {phase === "confirm" && (
                <button
                  type="button"
                  className="confirm-btn studio-update-confirm"
                  onClick={() => void beginUpdate()}
                >
                  立即更新
                </button>
              )}
            </div>
          </section>
        </div>
      )}
    </>
  );
}
