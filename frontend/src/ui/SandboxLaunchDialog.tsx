import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  SANDBOX_DISPLAY_NAME_MAX_LENGTH,
  type SandboxAgentKind,
} from "../adk/sandbox";
import { InsightIcon } from "./icons/InsightIcon";

export type SandboxLaunchState = "confirm" | "loading" | "error";
const DEFAULT_SANDBOX_DISPLAY_NAME = "我的智能体";

export interface SandboxLaunchDialogProps {
  open: boolean;
  state: SandboxLaunchState;
  agentKind?: "codex" | SandboxAgentKind;
  error?: string;
  onCancel: () => void;
  onConfirm: (displayName: string) => void;
}

export function SandboxLaunchDialog({
  open,
  state,
  agentKind = "codex",
  error,
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
  onCancelRef.current = onCancel;

  useEffect(() => {
    if (!open) return;
    setDisplayName(defaultDisplayName);
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

  if (!open) return null;

  const loading = state === "loading";
  const validDisplayName = displayName.trim();
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
          if (!loading && !composingRef.current && validDisplayName) {
            onConfirm(validDisplayName);
          }
        }}
      >
        <div className="sandbox-dialog-visual" aria-hidden="true">
          <span className="sandbox-dialog-orbit" />
          <span className="sandbox-dialog-icon">
            {loading ? <span className="sandbox-spinner" /> : <InsightIcon />}
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
        </div>
        <footer className="sandbox-dialog-actions">
          <button ref={cancelButtonRef} type="button" onClick={onCancel}>
            {loading ? "取消创建" : "取消"}
          </button>
          {!loading && (
            <button type="submit" className="is-primary" disabled={!validDisplayName}>
              {state === "error" ? "重新尝试" : "确认创建"}
            </button>
          )}
        </footer>
      </form>
    </div>,
    document.body,
  );
}
