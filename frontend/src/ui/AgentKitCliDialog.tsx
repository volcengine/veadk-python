import { useEffect, useState } from "react";
import type { TFunction } from "i18next";
import { LoadingIndicator } from "@openai/apps-sdk-ui/components/Indicator";
import { useTranslation } from "react-i18next";
import {
  agentKitCliClient,
  agentKitCliUnconfiguredMessage,
  type AgentKitCliSession,
} from "../adk/agentkitCli";
import type { SandboxToolLaunch } from "../adk/sandbox";
import { DialogShell } from "./SandboxControls";
import { SandboxTerminalIcon } from "./icons/SandboxControlIcons";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import "./AgentKitCliDialog.css";

type LoadingStage = "searching" | "creating" | "connecting";
type DialogState = LoadingStage | "ready" | "unconfigured" | "error";

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
  t: TFunction,
): Promise<AgentKitCliSession> {
  let session = initial;
  for (let attempt = 0; attempt < SESSION_POLL_ATTEMPTS; attempt += 1) {
    const status = normalizedStatus(session);
    if (status === READY_STATUS) return session;
    if (!ACTIVE_STATUSES.has(status)) {
      throw new Error(t("agentKitCli.initializationFailed", { status: session.status }));
    }
    await waitForPoll(signal);
    const sessions = await agentKitCliClient.listSessions({ signal });
    const refreshed = sessions.find((candidate) => candidate.id === session.id);
    if (!refreshed) {
      throw new Error(t("agentKitCli.sessionExpired"));
    }
    session = refreshed;
  }
  throw new Error(t("agentKitCli.initializationTimeout"));
}

async function initializeTerminal(
  signal: AbortSignal,
  onStage: (stage: LoadingStage) => void,
  t: TFunction,
): Promise<{ launch: SandboxToolLaunch; session: AgentKitCliSession }> {
  onStage("searching");
  const capabilities = await agentKitCliClient.capabilities({ signal });
  if (!capabilities.enabled) {
    throw new Error(capabilities.reason || agentKitCliUnconfiguredMessage());
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
  session = await waitUntilReady(session, signal, t);
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

function recyclingLabel(expireAt: string, now: number, t: TFunction): string {
  const expiresAt = Date.parse(expireAt);
  if (!Number.isFinite(expiresAt)) return t("agentKitCli.nonPersistent");
  const remainingMinutes = Math.max(0, Math.ceil((expiresAt - now) / 60_000));
  const hours = Math.floor(remainingMinutes / 60);
  const minutes = remainingMinutes % 60;
  if (hours > 0) {
    return t("agentKitCli.recyclingHoursMinutes", { hours, minutes });
  }
  return t("agentKitCli.recyclingMinutes", { minutes });
}

function errorMessage(cause: unknown, t: TFunction): string {
  const raw = cause instanceof Error ? cause.message : String(cause);
  if (cause instanceof TypeError) {
    return t("agentKitCli.connectionError", { message: raw });
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
  const { t } = useTranslation("workspaceTools");
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
    void initializeTerminal(controller.signal, setState, t)
      .then(({ launch: nextLaunch, session }) => {
        if (controller.signal.aborted) return;
        setLaunch(nextLaunch);
        setExpireAt(session.expireAt);
        setState("ready");
      })
      .catch((cause) => {
        if (controller.signal.aborted) return;
        const message = errorMessage(cause, t);
        setError(message);
        setState(
          message.includes(agentKitCliUnconfiguredMessage())
            ? "unconfigured"
            : "error",
        );
      });
    return () => controller.abort();
  }, [attempt, expireAt, launch, open, t]);

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
            ? t(`agentKitCli.loading.${state}`)
            : state === "ready"
              ? recyclingLabel(expireAt, now, t)
              : t("agentKitCli.unavailable")}
        </span>
      </div>
      <div className="sandbox-tool-surface agentkit-cli-surface">
        {loading ? (
          <div className="agentkit-cli-state" role="status" aria-live="polite">
            <LoadingIndicator size={20} />
            <TextShimmer as="strong">{t(`agentKitCli.loading.${state}`)}</TextShimmer>
          </div>
        ) : state === "unconfigured" ? (
          <div className="agentkit-cli-state" role="status">
            <SandboxTerminalIcon />
            <strong>{agentKitCliUnconfiguredMessage()}</strong>
          </div>
        ) : state === "error" ? (
          <div className="agentkit-cli-state is-error" role="alert">
            <strong>{t("agentKitCli.requestFailed")}</strong>
            <pre className="agentkit-cli-error-detail">{error}</pre>
            <button type="button" onClick={() => setAttempt((value) => value + 1)}>
              {t("agentKitCli.retry")}
            </button>
          </div>
        ) : launch ? (
          <iframe
            src={launch.url}
            title={t("agentKitCli.terminalTitle")}
            allow="clipboard-read; clipboard-write"
            sandbox="allow-downloads allow-forms allow-modals allow-popups allow-pointer-lock allow-same-origin allow-scripts"
          />
        ) : null}
      </div>
    </DialogShell>
  );
}
