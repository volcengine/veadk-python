import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  SANDBOX_DISPLAY_NAME_MAX_LENGTH,
  type SandboxAgentKind,
  type SandboxLaunchCapabilities,
  type SandboxRetentionMode,
} from "../adk/sandbox";
import { SandboxAgentIcon } from "./icons/SandboxAgentIcons";
import { TextShimmer } from "./text-shimmer/TextShimmer";

export type SandboxLaunchState = "confirm" | "loading" | "error";
const DEFAULT_SANDBOX_DISPLAY_NAME = "我的智能体";

export interface SandboxLaunchDialogProps {
  open: boolean;
  state: SandboxLaunchState;
  agentKind?: "codex" | SandboxAgentKind;
  error?: string;
  capabilities?: SandboxLaunchCapabilities | null;
  capabilitiesLoading?: boolean;
  capabilitiesError?: string;
  onRetryCapabilities?: () => void;
  onCancel: () => void;
  onConfirm: (
    displayName: string,
    retentionMode: SandboxRetentionMode,
  ) => void;
}

export function SandboxLaunchDialog({
  open,
  state,
  agentKind = "codex",
  error,
  capabilities,
  capabilitiesLoading = false,
  capabilitiesError,
  onRetryCapabilities,
  onCancel,
  onConfirm,
}: SandboxLaunchDialogProps) {
  const agentLabel = agentKind === "codex"
    ? "Codex"
    : agentKind === "openclaw" ? "OpenClaw" : "Hermes";
  const defaultDisplayName = agentKind === "codex"
    ? DEFAULT_SANDBOX_DISPLAY_NAME
    : `我的 ${agentLabel}`;
  const dialogRef = useRef<HTMLFormElement>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);
  const composingRef = useRef(false);
  const onCancelRef = useRef(onCancel);
  const [displayName, setDisplayName] = useState(defaultDisplayName);
  const [retentionMode, setRetentionMode] =
    useState<SandboxRetentionMode>("recoverable");
  onCancelRef.current = onCancel;

  useEffect(() => {
    if (!open) return;
    setDisplayName(defaultDisplayName);
    setRetentionMode("recoverable");
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusFrame = window.requestAnimationFrame(() => {
      nameInputRef.current?.focus();
      nameInputRef.current?.select();
    });
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancelRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const controls = dialogRef.current?.querySelectorAll<HTMLElement>(
        "input:not(:disabled), button:not(:disabled)",
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
  }, [defaultDisplayName, open]);

  useEffect(() => {
    if (!open || !capabilities) return;
    setRetentionMode((current) => {
      if (capabilities.retentionModes[current].enabled) return current;
      const preferred = capabilities.defaultRetentionMode;
      if (capabilities.retentionModes[preferred].enabled) return preferred;
      return capabilities.retentionModes.recoverable.enabled
        ? "recoverable"
        : "temporary";
    });
  }, [capabilities, open]);

  if (!open) return null;

  const loading = state === "loading";
  const validDisplayName = displayName.trim();
  const selectedModeEnabled = Boolean(
    capabilities?.retentionModes[retentionMode].enabled,
  );
  const title = loading
    ? `正在创建 ${agentLabel} 智能体`
    : state === "error"
      ? "启动失败"
      : `创建 ${agentLabel} 智能体`;

  return createPortal(
    <div
      className="sandbox-dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !loading) onCancel();
      }}
    >
      <form
        ref={dialogRef}
        className="sandbox-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="sandbox-dialog-title"
        aria-describedby={state === "confirm" ? undefined : "sandbox-dialog-description"}
        onSubmit={(event) => {
          event.preventDefault();
          if (
            !loading &&
            !capabilitiesLoading &&
            !capabilitiesError &&
            !composingRef.current &&
            validDisplayName &&
            selectedModeEnabled
          ) {
            onConfirm(validDisplayName, retentionMode);
          }
        }}
      >
        <div className="sandbox-dialog-visual" aria-hidden="true">
          <span className="sandbox-dialog-orbit" />
          <span className="sandbox-dialog-icon">
            {loading ? (
              <span className="sandbox-spinner" />
            ) : (
              <SandboxAgentIcon kind={agentKind} />
            )}
          </span>
        </div>
        <div className="sandbox-dialog-copy">
          <h2 id="sandbox-dialog-title">{title}</h2>
          {state === "error" ? (
            <p id="sandbox-dialog-description" className="sandbox-dialog-error" role="alert">
              {error || "AgentKit 沙箱初始化失败，请稍后重新尝试。"}
            </p>
          ) : loading ? (
            <p id="sandbox-dialog-description" aria-live="polite">
              正在创建并等待 {agentLabel} 智能体就绪，这通常需要半分钟
            </p>
          ) : null}
          <label className="sandbox-dialog-field">
            <span className="sandbox-dialog-field-label">
              <span>智能体名称</span>
              <span aria-hidden="true">
                {displayName.length}/{SANDBOX_DISPLAY_NAME_MAX_LENGTH}
              </span>
            </span>
            <input
              ref={nameInputRef}
              type="text"
              required
              value={displayName}
              maxLength={SANDBOX_DISPLAY_NAME_MAX_LENGTH}
              disabled={loading}
              placeholder={defaultDisplayName}
              autoComplete="off"
              onChange={(event) => setDisplayName(event.target.value)}
              onCompositionStart={() => {
                composingRef.current = true;
              }}
              onCompositionEnd={() => {
                composingRef.current = false;
              }}
              onKeyDown={(event) => {
                const { nativeEvent } = event;
                if (
                  event.key === "Enter" &&
                  (composingRef.current ||
                    nativeEvent.isComposing ||
                    nativeEvent.keyCode === 229)
                ) {
                  event.preventDefault();
                }
              }}
            />
          </label>
          <fieldset className="sandbox-dialog-retention">
            <legend>会话类型</legend>
            {capabilitiesLoading ? (
              <TextShimmer
                as="p"
                className="sandbox-dialog-capabilities-loading"
                duration={2.2}
              >
                正在读取可用会话类型
              </TextShimmer>
            ) : capabilitiesError ? (
              <div className="sandbox-dialog-capabilities-error" role="alert">
                <span>{capabilitiesError}</span>
                {onRetryCapabilities ? (
                  <button type="button" onClick={onRetryCapabilities}>
                    重试
                  </button>
                ) : null}
              </div>
            ) : (
              <div className="sandbox-dialog-retention-options">
                <RetentionOption
                  mode="recoverable"
                  label="可恢复会话"
                  description="到期后保存工作区快照，可再次唤醒并继续使用"
                  capability={capabilities?.retentionModes.recoverable}
                  selected={retentionMode === "recoverable"}
                  disabled={loading}
                  onSelect={setRetentionMode}
                />
                <RetentionOption
                  mode="temporary"
                  label="临时会话"
                  description="到期后自动销毁，不保留工作区和快照"
                  capability={capabilities?.retentionModes.temporary}
                  selected={retentionMode === "temporary"}
                  disabled={loading}
                  onSelect={setRetentionMode}
                />
              </div>
            )}
          </fieldset>
        </div>
        <footer className="sandbox-dialog-actions">
          <button ref={cancelButtonRef} type="button" onClick={onCancel}>
            {loading ? "取消创建" : "取消"}
          </button>
          {!loading && (
            <button
              type="submit"
              className="is-primary"
              disabled={
                !validDisplayName ||
                capabilitiesLoading ||
                Boolean(capabilitiesError) ||
                !selectedModeEnabled
              }
            >
              {state === "error" ? "重新尝试" : "确认创建"}
            </button>
          )}
        </footer>
      </form>
    </div>,
    document.body,
  );
}

function RetentionOption({
  mode,
  label,
  description,
  capability,
  selected,
  disabled,
  onSelect,
}: {
  mode: SandboxRetentionMode;
  label: string;
  description: string;
  capability?: { enabled: boolean; reason?: string };
  selected: boolean;
  disabled: boolean;
  onSelect: (mode: SandboxRetentionMode) => void;
}) {
  const unavailable = !capability?.enabled;
  return (
    <label
      className="sandbox-dialog-retention-option"
      data-selected={selected || undefined}
      data-disabled={unavailable || undefined}
    >
      <input
        type="radio"
        name="sandbox-retention-mode"
        value={mode}
        checked={selected}
        disabled={disabled || unavailable}
        onChange={() => onSelect(mode)}
      />
      <span className="sandbox-dialog-retention-copy">
        <strong>{label}</strong>
        <small>{description}</small>
        {unavailable && capability?.reason ? (
          <small className="sandbox-dialog-retention-reason">
            {capability.reason}
          </small>
        ) : null}
      </span>
    </label>
  );
}
