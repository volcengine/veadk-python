import { useEffect, useMemo, useRef, useState, type SVGProps } from "react";
import { createPortal } from "react-dom";
import {
  sandboxClient,
  type CodexProjectHandoffPairing,
  type CodexProjectHandoffStatus,
} from "../adk/sandbox";
import "./SandboxProjectUploadDialog.css";

type PluginStatus = "not-installed" | "installed";
type CopyTarget = PluginStatus | "";

interface DialogError {
  message: string;
  retryPairing: boolean;
}

export interface SandboxProjectUploadDialogProps {
  open: boolean;
  onClose: () => void;
  onRefreshAgents: () => void;
  onOpenSession: (sessionId: string) => Promise<void>;
}

function trimStudioUrl(value: string): string {
  return value.trim().replace(/\/+$/, "") || window.location.origin;
}

function codexHandoffPrompt(pairing: CodexProjectHandoffPairing): string {
  const studioUrl = trimStudioUrl(pairing.studioUrl);
  return [
    "使用 AgentKit Studio Plugin 端云接力当前项目和任务。",
    `Studio：${studioUrl}`,
    `配对码：${pairing.pairingCode}`,
  ].join("\n");
}

function installAndHandoffPrompt(pairing: CodexProjectHandoffPairing): string {
  const installCommand = [
    "codex plugin marketplace add evanlowe/veadk-python-fork",
    "--ref feat/codex-project-handoff-plugin",
    "--sparse .agents/plugins",
    "--sparse plugins/agentkit-studio",
    "&& codex plugin add agentkit-studio@veadk-python",
  ].join(" ");
  const studioUrl = trimStudioUrl(pairing.studioUrl);
  return [
    "安装 AgentKit Studio Plugin 后，使用 codex-sandbox-upload Skill 端云接力当前项目和任务。请直接执行，不要让我手动打开终端。",
    `安装命令：${installCommand}`,
    `Studio：${studioUrl}`,
    `配对码：${pairing.pairingCode}`,
  ].join("\n");
}

function CloseIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      aria-hidden="true"
      {...props}
    >
      <path d="m6.5 6.5 11 11M17.5 6.5l-11 11" />
    </svg>
  );
}

function CopyIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <rect x="8" y="8" width="11" height="11" rx="2" />
      <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
    </svg>
  );
}

function CheckIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="m5 12.5 4.25 4.25L19 7" />
    </svg>
  );
}

function RefreshIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M19 8a8 8 0 1 0 .35 7" />
      <path d="M19 4v4h-4" />
    </svg>
  );
}

export function formatPairingCountdown(expireAt: string, nowMs: number): string {
  const remainingSeconds = Math.max(
    0,
    Math.ceil((Date.parse(expireAt) - nowMs) / 1000),
  );
  const hours = Math.floor(remainingSeconds / 3600);
  const minutes = Math.floor((remainingSeconds % 3600) / 60);
  const seconds = remainingSeconds % 60;
  return [hours, minutes, seconds]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
}

type ProgressState = "pending" | "active" | "done" | "failed";

interface HandoffProgressStep {
  id: "request" | "session" | "restore" | "continue";
  label: string;
}

const HANDOFF_PROGRESS_STEPS: readonly HandoffProgressStep[] = [
  { id: "request", label: "等待端侧请求" },
  { id: "session", label: "创建云端 Session" },
  { id: "restore", label: "恢复项目" },
  { id: "continue", label: "发送续跑任务" },
];

function progressRank(status: CodexProjectHandoffStatus): number {
  switch (status.state) {
    case "issued":
      return 0;
    case "creating":
      return 1;
    case "session-created":
      return 2;
    case "continuing":
      return 3;
    case "running":
      return 4;
    case "completed":
      return 4;
    case "failed":
      return status.failedStage === "creating-session" ? 1 : 3;
  }
}

function progressStepState(
  status: CodexProjectHandoffStatus,
  index: number,
): ProgressState {
  const rank = progressRank(status);
  if (status.state === "failed" && index === rank) return "failed";
  if (index < rank) return "done";
  if (index === rank && status.state !== "completed") return "active";
  return status.state === "completed" ? "done" : "pending";
}

function handoffStatusLabel(status: CodexProjectHandoffStatus): string {
  switch (status.state) {
    case "issued":
      return "等待请求";
    case "creating":
      return "正在创建 Session";
    case "session-created":
      return "正在迁移项目";
    case "continuing":
      return "正在启动云端任务";
    case "running":
      return "云端执行中";
    case "completed":
      return "接力完成";
    case "failed":
      return "接力失败";
  }
}

export function SandboxProjectUploadDialog({
  open,
  onClose,
  onRefreshAgents,
  onOpenSession,
}: SandboxProjectUploadDialogProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  const requestRef = useRef(0);
  const copyTimerRef = useRef<number | undefined>(undefined);
  const completionNotifiedRef = useRef("");
  const [pluginStatus, setPluginStatus] =
    useState<PluginStatus>("not-installed");
  const [pairing, setPairing] = useState<CodexProjectHandoffPairing | null>(null);
  const [handoffStatus, setHandoffStatus] =
    useState<CodexProjectHandoffStatus | null>(null);
  const [pairingRetryKey, setPairingRetryKey] = useState(0);
  const [loading, setLoading] = useState(false);
  const [countdownNow, setCountdownNow] = useState(Date.now());
  const [enteringSession, setEnteringSession] = useState(false);
  const [error, setError] = useState<DialogError | null>(null);
  const [copyTarget, setCopyTarget] = useState<CopyTarget>("");
  onCloseRef.current = onClose;

  const codexPrompt = useMemo(
    () => pairing ? codexHandoffPrompt(pairing) : "",
    [pairing],
  );
  const activePrompt = useMemo(() => {
    if (!pairing) return "";
    return pluginStatus === "installed"
      ? codexPrompt
      : installAndHandoffPrompt(pairing);
  }, [codexPrompt, pairing, pluginStatus]);

  useEffect(() => {
    if (!open) {
      setPluginStatus("not-installed");
      return;
    }
    setPairing(null);
    setHandoffStatus(null);
    setError(null);
    setCopyTarget("");
    setEnteringSession(false);
    setCountdownNow(Date.now());
    const controller = new AbortController();
    const requestId = ++requestRef.current;
    setLoading(true);
    void sandboxClient
      .createCodexProjectHandoffPairing({ signal: controller.signal })
      .then((value) => {
        if (requestRef.current !== requestId) return;
        setPairing(value);
        setHandoffStatus({ state: "issued", expireAt: value.expireAt });
      })
      .catch((cause) => {
        if ((cause as Error)?.name === "AbortError") return;
        if (requestRef.current === requestId) {
          setError({
            message: cause instanceof Error ? cause.message : String(cause),
            retryPairing: true,
          });
        }
      })
      .finally(() => {
        if (requestRef.current === requestId) setLoading(false);
      });
    return () => {
      controller.abort();
    };
  }, [pairingRetryKey, open]);

  useEffect(() => {
    if (!open || !pairing) return;
    setCountdownNow(Date.now());
    const timer = window.setInterval(() => setCountdownNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [open, pairing]);

  useEffect(() => {
    if (!open || !pairing) return;
    let stopped = false;
    let timer: number | undefined;
    const controller = new AbortController();

    const poll = async () => {
      if (stopped || Date.now() >= Date.parse(pairing.expireAt)) return;
      try {
        const value = await sandboxClient.getCodexProjectHandoffStatus(
          pairing.pairingCode,
          { signal: controller.signal },
        );
        if (stopped) return;
        setHandoffStatus(value);
        if (value.state === "completed" || value.state === "failed") return;
      } catch (cause) {
        if ((cause as Error)?.name === "AbortError" || stopped) return;
        setError({
          message: cause instanceof Error ? cause.message : String(cause),
          retryPairing: false,
        });
      }
      timer = window.setTimeout(() => void poll(), 1500);
    };

    void poll();
    return () => {
      stopped = true;
      controller.abort();
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [open, pairing]);

  useEffect(() => {
    if (
      (handoffStatus?.state !== "running" &&
        handoffStatus?.state !== "completed") ||
      !pairing ||
      completionNotifiedRef.current === pairing.pairingCode
    ) return;
    completionNotifiedRef.current = pairing.pairingCode;
    onRefreshAgents();
  }, [handoffStatus?.state, onRefreshAgents, pairing]);

  useEffect(() => () => {
    if (copyTimerRef.current !== undefined) {
      window.clearTimeout(copyTimerRef.current);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusFrame = window.requestAnimationFrame(() => closeRef.current?.focus());
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const controls = dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), [tabindex]:not([tabindex="-1"])',
      );
      if (!controls?.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  if (!open) return null;

  async function copy(value: string, target: CopyTarget) {
    if (!value || copyTarget) return;
    setError(null);
    setCopyTarget(target);
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("当前浏览器不支持写入剪贴板。");
      }
      await navigator.clipboard.writeText(value);
      if (copyTimerRef.current !== undefined) {
        window.clearTimeout(copyTimerRef.current);
      }
      copyTimerRef.current = window.setTimeout(() => {
        setCopyTarget((current) => current === target ? "" : current);
        copyTimerRef.current = undefined;
      }, 1400);
    } catch (cause) {
      setCopyTarget("");
      setError({
        message: cause instanceof Error ? cause.message : String(cause),
        retryPairing: false,
      });
    }
  }

  async function enterCodexSession() {
    const sessionId = handoffStatus?.sessionId;
    if (!sessionId || enteringSession) return;
    setError(null);
    setEnteringSession(true);
    try {
      await onOpenSession(sessionId);
    } catch (cause) {
      setError({
        message: cause instanceof Error ? cause.message : String(cause),
        retryPairing: false,
      });
      setEnteringSession(false);
    }
  }

  const countdown = pairing
    ? formatPairingCountdown(pairing.expireAt, countdownNow)
    : "00:00:00";
  const pairingExpired = pairing
    ? countdownNow >= Date.parse(pairing.expireAt)
    : false;

  return createPortal(
    <div
      className="sandbox-project-upload-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className="sandbox-project-upload-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="sandbox-project-upload-title"
        aria-describedby="sandbox-project-upload-description"
      >
        <header className="sandbox-project-upload-head">
          <div>
            <h2 id="sandbox-project-upload-title">接力到云端继续执行</h2>
            <p id="sandbox-project-upload-description">
              复制 Prompt 到你的 Codex，它会迁移项目并在云端继续您的任务
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="sandbox-project-upload-close"
            onClick={onClose}
            aria-label="关闭本地迁移引导"
          >
            <CloseIcon />
          </button>
        </header>

        <div className="sandbox-project-upload-body">
          {error ? (
            <div className="sandbox-project-upload-error" role="alert">
              <span>{error.message}</span>
              {error.retryPairing ? (
                <button
                  type="button"
                  onClick={() => setPairingRetryKey((current) => current + 1)}
                >
                  <RefreshIcon />
                  重试
                </button>
              ) : null}
            </div>
          ) : null}

          <div className="sandbox-project-upload-pairing-notice" role="status">
            <span>
              {loading
                ? "正在生成新的配对码"
                : pairingExpired
                  ? "配对码已过期"
                  : <>配对码有效期剩余 <time>{countdown}</time></>}
            </span>
            <button
              type="button"
              disabled={loading}
              onClick={() => setPairingRetryKey((current) => current + 1)}
            >
              <RefreshIcon />
              {loading ? "刷新中" : "刷新配对码"}
            </button>
          </div>

          <fieldset className="sandbox-project-upload-status">
            <legend>是否已经安装 AgentKit Studio Plugin？</legend>
            <div className="sandbox-project-upload-status-options">
              <label data-selected={pluginStatus === "not-installed" ? "true" : undefined}>
                <input
                  type="radio"
                  name="sandbox-project-upload-plugin-status"
                  value="not-installed"
                  checked={pluginStatus === "not-installed"}
                  onChange={() => setPluginStatus("not-installed")}
                />
                <span>
                  <strong>未安装或不确定</strong>
                  <small>Codex 会自动执行安装命令并验证结果</small>
                </span>
              </label>
              <label data-selected={pluginStatus === "installed" ? "true" : undefined}>
                <input
                  type="radio"
                  name="sandbox-project-upload-plugin-status"
                  value="installed"
                  checked={pluginStatus === "installed"}
                  onChange={() => setPluginStatus("installed")}
                />
                <span>
                  <strong>已经安装</strong>
                  <small>直接把当前项目和任务接力到云端</small>
                </span>
              </label>
            </div>
          </fieldset>

          <section className="sandbox-project-upload-command">
            <div className="sandbox-project-upload-command-head">
              <div>
                <span>提示词</span>
                <p>复制后粘贴到当前 Codex 任务中。</p>
              </div>
              <button
                type="button"
                onClick={() => void copy(activePrompt, pluginStatus)}
                disabled={!activePrompt || loading || copyTarget !== ""}
              >
                {copyTarget === pluginStatus ? <CheckIcon /> : <CopyIcon />}
                {copyTarget === pluginStatus ? "已复制" : "复制提示词"}
              </button>
            </div>
            <div className="sandbox-project-upload-command-content">
              {loading ? (
                <div className="sandbox-project-upload-loading" role="status">
                  <i aria-hidden="true" />正在生成配对码
                </div>
              ) : activePrompt ? (
                <pre tabIndex={0}><code>{activePrompt}</code></pre>
              ) : (
                <div className="sandbox-project-upload-loading">配对码尚未生成。</div>
              )}
            </div>
          </section>

          {pairing && handoffStatus ? (
            <section
              className="sandbox-project-upload-progress"
              aria-live="polite"
              aria-label="端云接力状态"
            >
              <header>
                <div>
                  <span>接力状态</span>
                  {handoffStatus.state !== "issued" ? (
                    <p>
                      已收到{handoffStatus.agentName
                        ? `“${handoffStatus.agentName}”`
                        : handoffStatus.projectName
                          ? `“${handoffStatus.projectName}”`
                        : "当前项目"}的端云接力请求
                    </p>
                  ) : (
                    <p>复制提示词后，Codex 的请求会显示在这里。</p>
                  )}
                </div>
                <strong data-state={handoffStatus.state}>
                  {handoffStatusLabel(handoffStatus)}
                </strong>
              </header>
              <ol>
                {HANDOFF_PROGRESS_STEPS.map((step, index) => {
                  const state = progressStepState(handoffStatus, index);
                  return (
                    <li key={step.id} data-state={state}>
                      <span className="sandbox-project-upload-progress-marker">
                        {state === "done" ? <CheckIcon /> : null}
                        {state === "failed" ? <CloseIcon /> : null}
                      </span>
                      <span>{step.label}</span>
                    </li>
                  );
                })}
              </ol>
              {handoffStatus.state === "failed" && handoffStatus.error ? (
                <p className="sandbox-project-upload-progress-error" role="alert">
                  {handoffStatus.error}
                </p>
              ) : null}
            </section>
          ) : null}
        </div>

        <footer className="sandbox-project-upload-actions">
          <button type="button" onClick={onClose}>
            关闭
          </button>
          {(handoffStatus?.state === "running" ||
            handoffStatus?.state === "completed") && handoffStatus.sessionId ? (
            <button
              type="button"
              className="is-primary"
              disabled={enteringSession}
              onClick={() => void enterCodexSession()}
            >
              {enteringSession ? "正在进入" : "进入 Codex"}
            </button>
          ) : null}
        </footer>
      </section>
    </div>,
    document.body,
  );
}
