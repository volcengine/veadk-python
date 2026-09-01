import { useEffect, useState } from "react";
import { LoadingIndicator } from "@openai/apps-sdk-ui/components/Indicator";
import {
  AGENTKIT_CLI_UNCONFIGURED_MESSAGE,
  agentKitCliClient,
  type AgentKitCliSession,
} from "../adk/agentkitCli";
import type { SandboxToolLaunch } from "../adk/sandbox";
import { DialogShell } from "./SandboxControls";
import { SandboxTerminalIcon } from "./icons/SandboxControlIcons";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import "./AgentKitCliDialog.css";

type LoadingStage = "searching" | "creating" | "connecting";
type DialogState = LoadingStage | "ready" | "unconfigured" | "error";

const LOADING_LABELS: Record<LoadingStage, string> = {
  searching: "正在查找已有环境",
  creating: "环境初始化中",
  connecting: "正在连接已有环境",
};

const ACTIVE_STATUSES = new Set([
  "creating",
  "pending",
  "running",
  "starting",
  "initializing",
]);
const READY_STATUS = "ready";
const SESSION_POLL_INTERVAL_MS = 1_500;
const SESSION_POLL_ATTEMPTS = 80;

function normalizedStatus(session: AgentKitCliSession): string {
  return session.status.trim().toLowerCase();
}

function waitForPoll(signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, SESSION_POLL_INTERVAL_MS);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

async function waitUntilReady(
  initial: AgentKitCliSession,
  signal: AbortSignal,
): Promise<AgentKitCliSession> {
  let session = initial;
  for (let attempt = 0; attempt < SESSION_POLL_ATTEMPTS; attempt += 1) {
    const status = normalizedStatus(session);
    if (status === READY_STATUS) return session;
    if (!ACTIVE_STATUSES.has(status)) {
      throw new Error(`AgentKit CLI 环境初始化失败，当前状态：${session.status}。`);
    }
    await waitForPoll(signal);
    const sessions = await agentKitCliClient.listSessions({ signal });
    const refreshed = sessions.find((candidate) => candidate.id === session.id);
    if (!refreshed) {
      throw new Error("AgentKit CLI Session 不存在或已过期，请重试。");
    }
    session = refreshed;
  }
  throw new Error("AgentKit CLI 环境初始化超时，请稍后重试。");
}

async function initializeTerminal(
  signal: AbortSignal,
  onStage: (stage: LoadingStage) => void,
): Promise<{ launch: SandboxToolLaunch; session: AgentKitCliSession }> {
  onStage("searching");
  const capabilities = await agentKitCliClient.capabilities({ signal });
  if (!capabilities.enabled) {
    throw new Error(capabilities.reason || AGENTKIT_CLI_UNCONFIGURED_MESSAGE);
  }
  const sessions = await agentKitCliClient.listSessions({ signal });
  let session = sessions.find((candidate) => normalizedStatus(candidate) === READY_STATUS)
    ?? sessions.find((candidate) => ACTIVE_STATUSES.has(normalizedStatus(candidate)));
  if (!session) {
    onStage("creating");
    session = await agentKitCliClient.createSession({ signal });
  } else {
    onStage("connecting");
  }
  session = await waitUntilReady(session, signal);
  onStage("connecting");
  await agentKitCliClient.openSession(session.id, { signal });
  return {
    launch: await agentKitCliClient.launchTerminal(session.id, { signal }),
    session,
  };
}

function isLoadingState(state: DialogState): state is LoadingStage {
  return state === "searching" || state === "creating" || state === "connecting";
}

function isLaunchReusable(expireAt: string, now: number): boolean {
  const expiresAt = Date.parse(expireAt);
  return Number.isFinite(expiresAt) && expiresAt > now;
}

function recyclingLabel(expireAt: string, now: number): string {
  const expiresAt = Date.parse(expireAt);
  if (!Number.isFinite(expiresAt)) return "非持久化环境";
  const remainingMinutes = Math.max(0, Math.ceil((expiresAt - now) / 60_000));
  const hours = Math.floor(remainingMinutes / 60);
  const minutes = remainingMinutes % 60;
  if (hours > 0) return `${hours} 小时 ${minutes} 分钟后环境回收`;
  return `${minutes} 分钟后环境回收`;
}

function errorMessage(cause: unknown): string {
  const raw = cause instanceof Error ? cause.message : String(cause);
  if (cause instanceof TypeError) {
    return `无法连接 Studio 服务，未收到服务端响应。\n原始错误：${raw}`;
  }
  return raw;
}

export function AgentKitCliDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [state, setState] = useState<DialogState>("searching");
  const [launch, setLaunch] = useState<SandboxToolLaunch | null>(null);
  const [expireAt, setExpireAt] = useState("");
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!open || !expireAt) return undefined;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, [expireAt, open]);

  useEffect(() => {
    if (!open) return undefined;
    if (launch && isLaunchReusable(expireAt, Date.now())) {
      setError("");
      setState("ready");
      return undefined;
    }
    const controller = new AbortController();
    setState("searching");
    setLaunch(null);
    setExpireAt("");
    setError("");
    void initializeTerminal(controller.signal, setState)
      .then(({ launch: nextLaunch, session }) => {
        if (controller.signal.aborted) return;
        setLaunch(nextLaunch);
        setExpireAt(session.expireAt);
        setState("ready");
      })
      .catch((cause) => {
        if (controller.signal.aborted) return;
        const message = errorMessage(cause);
        setError(message);
        setState(
          message.includes(AGENTKIT_CLI_UNCONFIGURED_MESSAGE)
            ? "unconfigured"
            : "error",
        );
      });
    return () => controller.abort();
  }, [attempt, expireAt, launch, open]);

  const loading = isLoadingState(state);

  return (
    <DialogShell
      open={open}
      keepMounted
      title="AgentKit CLI"
      icon={<SandboxTerminalIcon />}
      className="sandbox-tool-dialog sandbox-tool-dialog--terminal agentkit-cli-dialog"
      onClose={onClose}
    >
      <div className="sandbox-tool-toolbar">
        <span>
          <i className={loading ? "is-loading" : state === "ready" ? "is-ready" : ""} />
          {loading
            ? LOADING_LABELS[state]
            : state === "ready"
              ? recyclingLabel(expireAt, now)
              : "连接不可用"}
        </span>
      </div>
      <div className="sandbox-tool-surface agentkit-cli-surface">
        {loading ? (
          <div className="agentkit-cli-state" role="status" aria-live="polite">
            <LoadingIndicator size={20} />
            <TextShimmer as="strong">{LOADING_LABELS[state]}</TextShimmer>
          </div>
        ) : state === "unconfigured" ? (
          <div className="agentkit-cli-state" role="status">
            <SandboxTerminalIcon />
            <strong>{AGENTKIT_CLI_UNCONFIGURED_MESSAGE}</strong>
          </div>
        ) : state === "error" ? (
          <div className="agentkit-cli-state is-error" role="alert">
            <strong>AgentKit CLI 请求失败</strong>
            <pre className="agentkit-cli-error-detail">{error}</pre>
            <button type="button" onClick={() => setAttempt((value) => value + 1)}>
              重试
            </button>
          </div>
        ) : launch ? (
          <iframe
            src={launch.url}
            title="AgentKit CLI 终端"
            allow="clipboard-read; clipboard-write"
            sandbox="allow-downloads allow-forms allow-modals allow-popups allow-pointer-lock allow-same-origin allow-scripts"
          />
        ) : null}
      </div>
    </DialogShell>
  );
}
