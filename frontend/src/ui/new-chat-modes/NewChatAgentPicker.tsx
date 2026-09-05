import { useCallback, useEffect, useRef, useState, type SVGProps } from "react";
import { EmptyMessage } from "@openai/apps-sdk-ui/components/EmptyMessage";
import { useTranslation } from "react-i18next";

import {
  getRuntimes,
  type CloudRuntime,
  type RuntimeScope,
} from "../../adk/client";
import {
  sandboxClient,
  sandboxStatusLabel,
  type SandboxAgentResource,
} from "../../adk/sandbox";
import { formatRequestError } from "../../adk/requestError";
import { AgentFaceIcon } from "../AgentFaceIcon";
import { SandboxAgentIcon } from "../icons/SandboxAgentIcons";
import "./new-chat-agent-picker.css";

type AgentType =
  | "general"
  | "codex"
  | "deepseek-harness"
  | "openclaw"
  | "hermes";

interface AgentTypeOption {
  id: AgentType;
  labelKey: string;
}

const AGENT_TYPES: AgentTypeOption[] = [
  { id: "general", labelKey: "agentPicker.types.general" },
  { id: "codex", labelKey: "agentPicker.types.codex" },
  { id: "deepseek-harness", labelKey: "agentPicker.types.deepseekHarness" },
  { id: "openclaw", labelKey: "agentPicker.types.openclaw" },
  { id: "hermes", labelKey: "agentPicker.types.hermes" },
];

const PAGE_SIZE = 15;
const RUNTIME_LOAD_TIMEOUT_MS = 15_000;
const HOVER_OPEN_DELAY_MS = 120;
const HOVER_CLOSE_DELAY_MS = 180;

export interface NewChatAgentPickerProps {
  selectedAgentName?: string;
  selectedRuntimeId?: string;
  agentsSource?: "local" | "cloud";
  localApps?: string[];
  runtimeScope: RuntimeScope;
  disabled?: boolean;
  onSelectLocalApp?: (app: string) => Promise<void>;
  onSelectRuntime: (runtime: CloudRuntime) => Promise<void>;
  onSelectSandboxSession: (session: SandboxAgentResource) => Promise<void>;
}

function ChevronIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path
        d="m5.75 3.75 4.25 4.25-4.25 4.25"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CheckIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path
        d="m3.25 8.25 3 3 6.5-6.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function AgentTypeIcon({
  type,
  className = "new-chat-agent-picker__type-icon",
}: {
  type: AgentType;
  className?: string;
}) {
  if (type === "general") {
    return <AgentFaceIcon className={className} />;
  }
  return <SandboxAgentIcon kind={type} className={className} />;
}

export function NewChatAgentPicker({
  selectedAgentName = "",
  selectedRuntimeId = "",
  agentsSource = "cloud",
  localApps = [],
  runtimeScope,
  disabled = false,
  onSelectLocalApp,
  onSelectRuntime,
  onSelectSandboxSession,
}: NewChatAgentPickerProps) {
  const { t } = useTranslation("newChat");
  const [open, setOpen] = useState(false);
  const [activeType, setActiveType] = useState<AgentType | null>(null);
  const [activeTypeIndex, setActiveTypeIndex] = useState(0);
  const [activeRuntimeIndex, setActiveRuntimeIndex] = useState(0);
  const [keyboardPanel, setKeyboardPanel] = useState<"types" | "runtimes">("types");
  const [keyboardNavigating, setKeyboardNavigating] = useState(false);
  const [runtimes, setRuntimes] = useState<CloudRuntime[]>([]);
  const [sandboxSessions, setSandboxSessions] = useState<SandboxAgentResource[]>([]);
  const [loadedSandboxType, setLoadedSandboxType] = useState<Exclude<AgentType, "general"> | null>(null);
  const [nextToken, setNextToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [connectingRuntimeId, setConnectingRuntimeId] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const requestIdRef = useRef(0);
  const sandboxAbortRef = useRef<AbortController | null>(null);
  const hoverOpenTimerRef = useRef<number | null>(null);
  const hoverCloseTimerRef = useRef<number | null>(null);
  const activeTypeKey = AGENT_TYPES.find((item) => item.id === activeType)?.labelKey;
  const activeTypeLabel = activeTypeKey
    ? t(activeTypeKey)
    : t("agentPicker.types.agent");

  const close = useCallback((returnFocus = false) => {
    if (hoverOpenTimerRef.current !== null) {
      window.clearTimeout(hoverOpenTimerRef.current);
      hoverOpenTimerRef.current = null;
    }
    if (hoverCloseTimerRef.current !== null) {
      window.clearTimeout(hoverCloseTimerRef.current);
      hoverCloseTimerRef.current = null;
    }
    setOpen(false);
    setActiveType(null);
    setKeyboardPanel("types");
    setKeyboardNavigating(false);
    if (returnFocus) triggerRef.current?.focus();
  }, []);

  const loadRuntimes = useCallback(async (token = "", reset = false) => {
    const requestId = ++requestIdRef.current;
    let timeoutId: number | undefined;
    setLoading(true);
    setError("");
    try {
      const page = await Promise.race([
        getRuntimes({
          scope: runtimeScope,
          region: "all",
          pageSize: PAGE_SIZE,
          nextToken: token,
        }),
        new Promise<never>((_, reject) => {
          timeoutId = window.setTimeout(() => {
            reject(new Error(t("agentPicker.runtimeTimeout")));
          }, RUNTIME_LOAD_TIMEOUT_MS);
        }),
      ]);
      if (requestIdRef.current !== requestId) return;
      setRuntimes((current) => {
        const combined = reset ? page.runtimes : [...current, ...page.runtimes];
        return combined.filter(
          (runtime, index) =>
            combined.findIndex((item) => item.runtimeId === runtime.runtimeId) === index,
        );
      });
      setNextToken(page.nextToken);
      setActiveRuntimeIndex(0);
    } catch (cause) {
      if (requestIdRef.current !== requestId) return;
      setError(formatRequestError(cause, t("agentPicker.loadGeneral"), "GET /web/runtimes"));
    } finally {
      window.clearTimeout(timeoutId);
      if (requestIdRef.current === requestId) setLoading(false);
    }
  }, [runtimeScope, t]);

  const loadSandboxSessions = useCallback(async (
    type: Exclude<AgentType, "general">,
  ) => {
    sandboxAbortRef.current?.abort();
    const controller = new AbortController();
    sandboxAbortRef.current = controller;
    const requestId = ++requestIdRef.current;
    setLoading(true);
    setError("");
    setSandboxSessions([]);
    try {
      const sessions = type === "codex"
        ? await sandboxClient.listSessions({
            signal: controller.signal,
            autoResumeSnapshots: true,
          })
        : await sandboxClient.listAgentSessions(type, {
            signal: controller.signal,
            autoResumeSnapshots: true,
          });
      if (requestIdRef.current !== requestId) return;
      setSandboxSessions(sessions);
      setLoadedSandboxType(type);
      setActiveRuntimeIndex(0);
    } catch (cause) {
      if ((cause as Error)?.name === "AbortError") return;
      if (requestIdRef.current !== requestId) return;
      const typeKey = AGENT_TYPES.find((item) => item.id === type)?.labelKey;
      setError(formatRequestError(
        cause,
        t("agentPicker.loadType", { type: typeKey ? t(typeKey) : type }),
        `GET /web/${type === "codex" ? "sandbox" : type}/sessions`,
      ));
      setLoadedSandboxType(type);
    } finally {
      if (sandboxAbortRef.current === controller) sandboxAbortRef.current = null;
      if (requestIdRef.current === requestId) setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    if (agentsSource === "local" || !open || activeType !== "general" || runtimes.length > 0 || loading || error) return;
    void loadRuntimes("", true);
  }, [activeType, agentsSource, error, loadRuntimes, loading, open, runtimes.length]);

  useEffect(() => {
    if (!open || activeType === null || activeType === "general" || loadedSandboxType === activeType) return;
    void loadSandboxSessions(activeType);
  }, [activeType, loadSandboxSessions, loadedSandboxType, open]);

  useEffect(() => {
    if (!open) return;
    const onOutsideClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) close();
    };
    document.addEventListener("mousedown", onOutsideClick);
    return () => document.removeEventListener("mousedown", onOutsideClick);
  }, [close, open]);

  useEffect(() => () => {
    requestIdRef.current += 1;
    sandboxAbortRef.current?.abort();
    if (hoverOpenTimerRef.current !== null) {
      window.clearTimeout(hoverOpenTimerRef.current);
    }
    if (hoverCloseTimerRef.current !== null) {
      window.clearTimeout(hoverCloseTimerRef.current);
    }
  }, []);

  function openPicker(focusMenu: boolean, fromKeyboard = false) {
    if (hoverOpenTimerRef.current !== null) {
      window.clearTimeout(hoverOpenTimerRef.current);
      hoverOpenTimerRef.current = null;
    }
    if (hoverCloseTimerRef.current !== null) {
      window.clearTimeout(hoverCloseTimerRef.current);
      hoverCloseTimerRef.current = null;
    }
    setOpen(true);
    setActiveType(fromKeyboard ? "general" : null);
    setActiveTypeIndex(0);
    setKeyboardPanel("types");
    setKeyboardNavigating(fromKeyboard);
    if (focusMenu) requestAnimationFrame(() => menuRef.current?.focus());
  }

  function scheduleHoverOpen() {
    if (disabled || open || hoverOpenTimerRef.current !== null) return;
    hoverOpenTimerRef.current = window.setTimeout(() => {
      hoverOpenTimerRef.current = null;
      openPicker(false);
    }, HOVER_OPEN_DELAY_MS);
  }

  function cancelHoverClose() {
    if (hoverCloseTimerRef.current === null) return;
    window.clearTimeout(hoverCloseTimerRef.current);
    hoverCloseTimerRef.current = null;
  }

  function scheduleHoverClose() {
    if (hoverOpenTimerRef.current !== null) {
      window.clearTimeout(hoverOpenTimerRef.current);
      hoverOpenTimerRef.current = null;
    }
    if (!open || hoverCloseTimerRef.current !== null) return;
    hoverCloseTimerRef.current = window.setTimeout(() => {
      hoverCloseTimerRef.current = null;
      close();
    }, HOVER_CLOSE_DELAY_MS);
  }

  function activateType(index: number) {
    const normalized = (index + AGENT_TYPES.length) % AGENT_TYPES.length;
    const nextType = AGENT_TYPES[normalized].id;
    if (nextType !== activeType) {
      requestIdRef.current += 1;
      sandboxAbortRef.current?.abort();
      sandboxAbortRef.current = null;
      setLoading(false);
      setError("");
    }
    setActiveTypeIndex(normalized);
    setActiveType(nextType);
    setActiveRuntimeIndex(0);
  }

  async function chooseRuntime(runtime: CloudRuntime) {
    if (connectingRuntimeId) return;
    setConnectingRuntimeId(runtime.runtimeId);
    setError("");
    try {
      await onSelectRuntime(runtime);
      close(true);
    } catch (cause) {
      setError(formatRequestError(cause, t("agentPicker.connectGeneral")));
    } finally {
      setConnectingRuntimeId("");
    }
  }

  async function chooseLocalApp(app: string) {
    if (connectingRuntimeId || !onSelectLocalApp) return;
    setConnectingRuntimeId(app);
    setError("");
    try {
      await onSelectLocalApp(app);
      close(true);
    } catch (cause) {
      setError(formatRequestError(cause, t("agentPicker.openLocal")));
    } finally {
      setConnectingRuntimeId("");
    }
  }

  async function chooseSandboxSession(session: SandboxAgentResource) {
    if (connectingRuntimeId) return;
    setConnectingRuntimeId(session.id);
    setError("");
    try {
      await onSelectSandboxSession(session);
      close(true);
    } catch (cause) {
      setError(formatRequestError(cause, t("agentPicker.openType", { type: activeTypeLabel })));
    } finally {
      setConnectingRuntimeId("");
    }
  }

  function onMenuKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const generalOptionCount = agentsSource === "local" ? localApps.length : runtimes.length;
    if (event.key === "Escape") {
      event.preventDefault();
      close(true);
      return;
    }
    if (["ArrowDown", "ArrowUp", "ArrowRight", "ArrowLeft", "Enter"].includes(event.key)) {
      setKeyboardNavigating(true);
    }
    if (keyboardPanel === "types") {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        activateType(activeTypeIndex + (event.key === "ArrowDown" ? 1 : -1));
      } else if (event.key === "ArrowRight" || event.key === "Enter") {
        event.preventDefault();
        if (activeType === null) activateType(activeTypeIndex);
        setKeyboardPanel("runtimes");
      }
      return;
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      setKeyboardPanel("types");
    } else if ((activeType === "general" ? generalOptionCount : sandboxSessions.length) > 0 &&
      (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      event.preventDefault();
      const delta = event.key === "ArrowDown" ? 1 : -1;
      const optionCount = activeType === "general" ? generalOptionCount : sandboxSessions.length;
      setActiveRuntimeIndex((index) => (index + delta + optionCount) % optionCount);
    } else if (event.key === "Enter" && activeType === "general" && agentsSource === "local" && localApps[activeRuntimeIndex]) {
      event.preventDefault();
      void chooseLocalApp(localApps[activeRuntimeIndex]);
    } else if (event.key === "Enter" && activeType === "general" && runtimes[activeRuntimeIndex]) {
      event.preventDefault();
      void chooseRuntime(runtimes[activeRuntimeIndex]);
    } else if (event.key === "Enter" && activeType !== "general" && sandboxSessions[activeRuntimeIndex]) {
      event.preventDefault();
      void chooseSandboxSession(sandboxSessions[activeRuntimeIndex]);
    }
  }

  return (
    <div
      className="new-chat-agent-picker"
      ref={rootRef}
      onPointerEnter={(event) => {
        if (event.pointerType === "mouse") cancelHoverClose();
      }}
      onPointerLeave={(event) => {
        if (event.pointerType === "mouse") scheduleHoverClose();
      }}
    >
      <button
        ref={triggerRef}
        type="button"
        className="new-chat-agent-picker__trigger"
        aria-label={t("agentPicker.select")}
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={disabled}
        onPointerEnter={(event) => {
          if (event.pointerType === "mouse") scheduleHoverOpen();
        }}
        onClick={() => open ? close() : openPicker(true)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            if (!open) openPicker(true, true);
          } else if (event.key === "Escape" && open) {
            event.preventDefault();
            close(true);
          }
        }}
      >
        <span title={selectedAgentName || t("agentPicker.select")}>
          {selectedAgentName || t("agentPicker.select")}
        </span>
        <ChevronIcon className="new-chat-agent-picker__trigger-chevron" />
      </button>

      {open ? (
        <div
          ref={menuRef}
          className="new-chat-agent-picker__menus"
          tabIndex={-1}
          onKeyDown={onMenuKeyDown}
          onPointerMove={(event) => {
            if (event.pointerType === "mouse") setKeyboardNavigating(false);
          }}
        >
          <div className="new-chat-agent-picker__menu" role="menu" aria-label={t("agentPicker.typesLabel")}>
            {AGENT_TYPES.map((type, index) => (
              <button
                key={type.id}
                type="button"
                role="menuitem"
                aria-haspopup="menu"
                aria-expanded={activeType === type.id}
                className={`new-chat-agent-picker__type${keyboardNavigating && keyboardPanel === "types" && activeTypeIndex === index ? " is-keyboard-active" : ""}`}
                onMouseEnter={() => activateType(index)}
                onClick={() => {
                  activateType(index);
                  setKeyboardPanel("runtimes");
                }}
              >
                <AgentTypeIcon type={type.id} />
                <span>{t(type.labelKey)}</span>
                <ChevronIcon className="new-chat-agent-picker__nested-chevron" />
              </button>
            ))}
          </div>

          {activeType !== null ? (
            <div
              className="new-chat-agent-picker__submenu"
              role="listbox"
              aria-label={t("agentPicker.listLabel", { type: activeTypeLabel })}
            >
            {activeType !== "general" && loading && sandboxSessions.length === 0 ? (
              <div className="new-chat-agent-picker__status" role="status" aria-live="polite">
                <span className="new-chat-agent-picker__spinner" aria-hidden="true" />
                {t("agentPicker.loading")}
              </div>
            ) : activeType !== "general" && error && sandboxSessions.length === 0 ? (
              <div className="new-chat-agent-picker__error" role="alert">
                <span>{error}</span>
                <button type="button" onClick={() => void loadSandboxSessions(activeType)}>
                  {t("agentPicker.reload")}
                </button>
              </div>
            ) : activeType !== "general" && sandboxSessions.length === 0 ? (
              <EmptyMessage className="new-chat-agent-picker__empty" fill="none">
                <EmptyMessage.Icon size="sm">
                  <AgentTypeIcon
                    type={activeType}
                    className="new-chat-agent-picker__empty-agent-icon"
                  />
                </EmptyMessage.Icon>
                <EmptyMessage.Title>
                  <span className="new-chat-agent-picker__empty-title">
                    {t("agentPicker.empty", { type: activeTypeLabel })}
                  </span>
                </EmptyMessage.Title>
                <EmptyMessage.Description>
                  {t("agentPicker.createHint")}
                </EmptyMessage.Description>
              </EmptyMessage>
            ) : activeType !== "general" ? (
              <div className="new-chat-agent-picker__runtime-list">
                {sandboxSessions.map((session, index) => {
                  const connecting = connectingRuntimeId === session.id;
                  const wakeable = session.resourceType === "snapshot";
                  return (
                    <button
                      key={session.id}
                      type="button"
                      role="option"
                      aria-selected={false}
                      aria-busy={connecting || undefined}
                      className={`new-chat-agent-picker__runtime${keyboardNavigating && keyboardPanel === "runtimes" && activeRuntimeIndex === index ? " is-keyboard-active" : ""}`}
                      disabled={Boolean(connectingRuntimeId)}
                      title={`${session.displayName || activeTypeLabel} · ${session.id}`}
                      onMouseEnter={() => setActiveRuntimeIndex(index)}
                      onClick={() => void chooseSandboxSession(session)}
                    >
                      <AgentTypeIcon
                        type={activeType}
                        className="new-chat-agent-picker__runtime-icon"
                      />
                      <span>{session.displayName || activeTypeLabel}</span>
                      <small>
                        {connecting
                          ? (wakeable ? t("agentPicker.waking") : t("agentPicker.opening"))
                          : sandboxStatusLabel(session.status)}
                      </small>
                    </button>
                  );
                })}
              </div>
            ) : agentsSource === "local" && localApps.length === 0 ? (
              <EmptyMessage className="new-chat-agent-picker__empty" fill="none">
                <EmptyMessage.Icon size="sm">
                  <AgentFaceIcon />
                </EmptyMessage.Icon>
                <EmptyMessage.Title>
                  <span className="new-chat-agent-picker__empty-title">
                    {t("agentPicker.emptyLocal")}
                  </span>
                </EmptyMessage.Title>
                <EmptyMessage.Description>
                  {t("agentPicker.localHint")}
                </EmptyMessage.Description>
              </EmptyMessage>
            ) : agentsSource === "local" ? (
              <div className="new-chat-agent-picker__runtime-list">
                {localApps.map((app, index) => {
                  const connecting = connectingRuntimeId === app;
                  const selected = app === selectedAgentName;
                  return (
                    <button
                      key={app}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      aria-busy={connecting || undefined}
                      className={`new-chat-agent-picker__runtime${keyboardNavigating && keyboardPanel === "runtimes" && activeRuntimeIndex === index ? " is-keyboard-active" : ""}`}
                      disabled={Boolean(connectingRuntimeId)}
                      title={app}
                      onMouseEnter={() => setActiveRuntimeIndex(index)}
                      onClick={() => void chooseLocalApp(app)}
                    >
                      <AgentFaceIcon className="new-chat-agent-picker__runtime-icon" />
                      <span>{app}</span>
                      {connecting ? (
                        <small>{t("agentPicker.opening")}</small>
                      ) : selected ? (
                        <CheckIcon className="new-chat-agent-picker__check" />
                      ) : null}
                    </button>
                  );
                })}
                {error ? <div className="new-chat-agent-picker__inline-error" role="alert">{error}</div> : null}
              </div>
            ) : loading && runtimes.length === 0 ? (
              <div className="new-chat-agent-picker__status" role="status" aria-live="polite">
                <span className="new-chat-agent-picker__spinner" aria-hidden="true" />
                {t("agentPicker.loading")}
              </div>
            ) : error && runtimes.length === 0 ? (
              <div className="new-chat-agent-picker__error" role="alert">
                <span>{error}</span>
                <button type="button" onClick={() => void loadRuntimes("", true)}>
                  {t("agentPicker.reload")}
                </button>
              </div>
            ) : runtimes.length === 0 ? (
              <EmptyMessage className="new-chat-agent-picker__empty" fill="none">
                <EmptyMessage.Icon size="sm">
                  <AgentFaceIcon />
                </EmptyMessage.Icon>
                <EmptyMessage.Title>
                  <span className="new-chat-agent-picker__empty-title">
                    {t("agentPicker.emptyGeneral")}
                  </span>
                </EmptyMessage.Title>
                <EmptyMessage.Description>
                  {t("agentPicker.createHint")}
                </EmptyMessage.Description>
              </EmptyMessage>
            ) : (
              <>
                <div className="new-chat-agent-picker__runtime-list">
                  {runtimes.map((runtime, index) => {
                    const connecting = connectingRuntimeId === runtime.runtimeId;
                    const selected = runtime.runtimeId === selectedRuntimeId;
                    return (
                      <button
                        key={runtime.runtimeId}
                        type="button"
                        role="option"
                        aria-selected={selected}
                        aria-busy={connecting || undefined}
                        className={`new-chat-agent-picker__runtime${keyboardNavigating && keyboardPanel === "runtimes" && activeRuntimeIndex === index ? " is-keyboard-active" : ""}`}
                        disabled={Boolean(connectingRuntimeId)}
                        title={runtime.name}
                        onMouseEnter={() => setActiveRuntimeIndex(index)}
                        onClick={() => void chooseRuntime(runtime)}
                      >
                        <AgentFaceIcon className="new-chat-agent-picker__runtime-icon" />
                        <span>{runtime.name}</span>
                        {connecting ? (
                          <small>{t("agentPicker.connecting")}</small>
                        ) : selected ? (
                          <CheckIcon className="new-chat-agent-picker__check" />
                        ) : null}
                      </button>
                    );
                  })}
                </div>
                {error ? <div className="new-chat-agent-picker__inline-error" role="alert">{error}</div> : null}
                {nextToken ? (
                  <button
                    type="button"
                    className="new-chat-agent-picker__load-more"
                    disabled={loading || Boolean(connectingRuntimeId)}
                    onClick={() => void loadRuntimes(nextToken)}
                  >
                    {loading ? t("agentPicker.loadingMore") : t("agentPicker.loadMore")}
                  </button>
                ) : null}
              </>
            )}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
