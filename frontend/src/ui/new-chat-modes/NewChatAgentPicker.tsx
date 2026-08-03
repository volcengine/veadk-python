import { useCallback, useEffect, useRef, useState, type SVGProps } from "react";
import { EmptyMessage } from "@openai/apps-sdk-ui/components/EmptyMessage";

import {
  getRuntimes,
  type CloudRuntime,
  type RuntimeScope,
} from "../../adk/client";
import {
  sandboxClient,
  sandboxStatusLabel,
  type SandboxSession,
} from "../../adk/sandbox";
import { AgentFaceIcon } from "../AgentFaceIcon";
import "./new-chat-agent-picker.css";

type AgentType = "general" | "codex" | "openclaw" | "hermes";

interface AgentTypeOption {
  id: AgentType;
  label: string;
}

const AGENT_TYPES: AgentTypeOption[] = [
  { id: "general", label: "通用智能体" },
  { id: "codex", label: "Codex 智能体" },
  { id: "openclaw", label: "OpenClaw 智能体" },
  { id: "hermes", label: "Hermes 智能体" },
];

const PAGE_SIZE = 15;
const RUNTIME_LOAD_TIMEOUT_MS = 15_000;
const HOVER_OPEN_DELAY_MS = 120;
const HOVER_CLOSE_DELAY_MS = 180;

export interface NewChatAgentPickerProps {
  selectedAgentName?: string;
  selectedRuntimeId?: string;
  runtimeScope: RuntimeScope;
  disabled?: boolean;
  onSelectRuntime: (runtime: CloudRuntime) => Promise<void>;
  onSelectSandboxSession: (session: SandboxSession) => Promise<void>;
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
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {type === "codex" ? (
        <>
          <path d="m12 3 7 4v8l-7 4-7-4V7l7-4Z" />
          <path d="m8 9 4-2.3L16 9v4.5L12 16l-4-2.5V9Z" />
        </>
      ) : type === "openclaw" ? (
        <>
          <path d="M7 19c-2-2.5-2.5-5.5-.8-8.2M17 19c2-2.5 2.5-5.5.8-8.2" />
          <path d="m6.2 10.8-2.7-2M17.8 10.8l2.7-2M9.2 8 7.5 4M14.8 8 16.5 4" />
          <path d="M8.5 18.5h7" />
        </>
      ) : (
        <>
          <path d="M5 18.5V9l7-4 7 4v9.5" />
          <path d="M8.5 13h7M9 18.5v-2.8h6v2.8" />
        </>
      )}
    </svg>
  );
}

export function NewChatAgentPicker({
  selectedAgentName = "",
  selectedRuntimeId = "",
  runtimeScope,
  disabled = false,
  onSelectRuntime,
  onSelectSandboxSession,
}: NewChatAgentPickerProps) {
  const [open, setOpen] = useState(false);
  const [activeType, setActiveType] = useState<AgentType>("general");
  const [activeTypeIndex, setActiveTypeIndex] = useState(0);
  const [activeRuntimeIndex, setActiveRuntimeIndex] = useState(0);
  const [keyboardPanel, setKeyboardPanel] = useState<"types" | "runtimes">("types");
  const [runtimes, setRuntimes] = useState<CloudRuntime[]>([]);
  const [sandboxSessions, setSandboxSessions] = useState<SandboxSession[]>([]);
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
  const activeTypeLabel = AGENT_TYPES.find((item) => item.id === activeType)?.label ?? "智能体";

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
    setKeyboardPanel("types");
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
            reject(new Error("加载智能体超时（15 秒），请检查网络或 Runtime 服务后重试"));
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
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      window.clearTimeout(timeoutId);
      if (requestIdRef.current === requestId) setLoading(false);
    }
  }, [runtimeScope]);

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
        ? await sandboxClient.listSessions({ signal: controller.signal })
        : await sandboxClient.listAgentSessions(type, { signal: controller.signal });
      if (requestIdRef.current !== requestId) return;
      setSandboxSessions(sessions);
      setLoadedSandboxType(type);
      setActiveRuntimeIndex(0);
    } catch (cause) {
      if ((cause as Error)?.name === "AbortError") return;
      if (requestIdRef.current !== requestId) return;
      setError(cause instanceof Error ? cause.message : String(cause));
      setLoadedSandboxType(type);
    } finally {
      if (sandboxAbortRef.current === controller) sandboxAbortRef.current = null;
      if (requestIdRef.current === requestId) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open || activeType !== "general" || runtimes.length > 0 || loading || error) return;
    void loadRuntimes("", true);
  }, [activeType, error, loadRuntimes, loading, open, runtimes.length]);

  useEffect(() => {
    if (!open || activeType === "general" || loadedSandboxType === activeType) return;
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

  function openPicker(focusMenu: boolean) {
    if (hoverOpenTimerRef.current !== null) {
      window.clearTimeout(hoverOpenTimerRef.current);
      hoverOpenTimerRef.current = null;
    }
    if (hoverCloseTimerRef.current !== null) {
      window.clearTimeout(hoverCloseTimerRef.current);
      hoverCloseTimerRef.current = null;
    }
    setOpen(true);
    setKeyboardPanel("types");
    setActiveTypeIndex(AGENT_TYPES.findIndex((item) => item.id === activeType));
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
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setConnectingRuntimeId("");
    }
  }

  async function chooseSandboxSession(session: SandboxSession) {
    if (connectingRuntimeId) return;
    setConnectingRuntimeId(session.id);
    setError("");
    try {
      await onSelectSandboxSession(session);
      close(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setConnectingRuntimeId("");
    }
  }

  function onMenuKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      close(true);
      return;
    }
    if (keyboardPanel === "types") {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        activateType(activeTypeIndex + (event.key === "ArrowDown" ? 1 : -1));
      } else if (event.key === "ArrowRight" || event.key === "Enter") {
        event.preventDefault();
        setKeyboardPanel("runtimes");
      }
      return;
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      setKeyboardPanel("types");
    } else if ((activeType === "general" ? runtimes : sandboxSessions).length > 0 &&
      (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      event.preventDefault();
      const delta = event.key === "ArrowDown" ? 1 : -1;
      const optionCount = activeType === "general" ? runtimes.length : sandboxSessions.length;
      setActiveRuntimeIndex((index) => (index + delta + optionCount) % optionCount);
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
        aria-label="选择智能体"
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
            if (!open) openPicker(true);
          } else if (event.key === "Escape" && open) {
            event.preventDefault();
            close(true);
          }
        }}
      >
        <AgentFaceIcon className="new-chat-agent-picker__trigger-icon" />
        <span title={selectedAgentName || "选择智能体"}>
          {selectedAgentName || "选择智能体"}
        </span>
        <ChevronIcon className="new-chat-agent-picker__trigger-chevron" />
      </button>

      {open ? (
        <div
          ref={menuRef}
          className="new-chat-agent-picker__menus"
          tabIndex={-1}
          onKeyDown={onMenuKeyDown}
        >
          <div className="new-chat-agent-picker__menu" role="menu" aria-label="智能体类型">
            {AGENT_TYPES.map((type, index) => (
              <button
                key={type.id}
                type="button"
                role="menuitem"
                aria-haspopup="menu"
                aria-expanded={activeType === type.id}
                className={`new-chat-agent-picker__type${activeType === type.id ? " is-active" : ""}${keyboardPanel === "types" && activeTypeIndex === index ? " is-keyboard-active" : ""}`}
                onMouseEnter={() => activateType(index)}
                onClick={() => {
                  activateType(index);
                  setKeyboardPanel("runtimes");
                }}
              >
                <AgentTypeIcon type={type.id} />
                <span>{type.label}</span>
                <ChevronIcon className="new-chat-agent-picker__nested-chevron" />
              </button>
            ))}
          </div>

          <div
            className="new-chat-agent-picker__submenu"
            role="listbox"
            aria-label={`${activeTypeLabel}列表`}
          >
            {activeType !== "general" && loading && sandboxSessions.length === 0 ? (
              <div className="new-chat-agent-picker__status" role="status" aria-live="polite">
                <span className="new-chat-agent-picker__spinner" aria-hidden="true" />
                正在加载智能体
              </div>
            ) : activeType !== "general" && error && sandboxSessions.length === 0 ? (
              <div className="new-chat-agent-picker__error" role="alert">
                <span>{error}</span>
                <button type="button" onClick={() => void loadSandboxSessions(activeType)}>
                  重新加载
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
                    暂无 {activeTypeLabel}
                  </span>
                </EmptyMessage.Title>
                <EmptyMessage.Description>
                  请前往智能体页创建
                </EmptyMessage.Description>
              </EmptyMessage>
            ) : activeType !== "general" ? (
              <div className="new-chat-agent-picker__runtime-list">
                {sandboxSessions.map((session, index) => {
                  const connecting = connectingRuntimeId === session.id;
                  return (
                    <button
                      key={session.id}
                      type="button"
                      role="option"
                      aria-selected={false}
                      aria-busy={connecting || undefined}
                      className={`new-chat-agent-picker__runtime${keyboardPanel === "runtimes" && activeRuntimeIndex === index ? " is-keyboard-active" : ""}`}
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
                      <small>{connecting ? "正在打开" : sandboxStatusLabel(session.status)}</small>
                    </button>
                  );
                })}
              </div>
            ) : loading && runtimes.length === 0 ? (
              <div className="new-chat-agent-picker__status" role="status" aria-live="polite">
                <span className="new-chat-agent-picker__spinner" aria-hidden="true" />
                正在加载智能体
              </div>
            ) : error && runtimes.length === 0 ? (
              <div className="new-chat-agent-picker__error" role="alert">
                <span>{error}</span>
                <button type="button" onClick={() => void loadRuntimes("", true)}>
                  重新加载
                </button>
              </div>
            ) : runtimes.length === 0 ? (
              <EmptyMessage className="new-chat-agent-picker__empty" fill="none">
                <EmptyMessage.Icon size="sm">
                  <AgentFaceIcon />
                </EmptyMessage.Icon>
                <EmptyMessage.Title>
                  <span className="new-chat-agent-picker__empty-title">
                    暂无通用智能体
                  </span>
                </EmptyMessage.Title>
                <EmptyMessage.Description>
                  请前往智能体页创建
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
                        className={`new-chat-agent-picker__runtime${keyboardPanel === "runtimes" && activeRuntimeIndex === index ? " is-keyboard-active" : ""}`}
                        disabled={Boolean(connectingRuntimeId)}
                        title={runtime.name}
                        onMouseEnter={() => setActiveRuntimeIndex(index)}
                        onClick={() => void chooseRuntime(runtime)}
                      >
                        <AgentFaceIcon className="new-chat-agent-picker__runtime-icon" />
                        <span>{runtime.name}</span>
                        {connecting ? (
                          <small>正在连接</small>
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
                    {loading ? "加载中" : "加载更多"}
                  </button>
                ) : null}
              </>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
