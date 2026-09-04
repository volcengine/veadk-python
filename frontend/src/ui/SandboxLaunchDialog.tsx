import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Checkbox } from "@openai/apps-sdk-ui/components/Checkbox";
import {
  SANDBOX_DISPLAY_NAME_MAX_LENGTH,
  type SandboxAgentKind,
} from "../adk/sandbox";
import { SandboxAgentIcon } from "./icons/SandboxAgentIcons";

export type SandboxLaunchState = "confirm" | "loading" | "error";
const DEFAULT_SANDBOX_DISPLAY_NAME = "我的智能体";

export interface SandboxLaunchDialogProps {
  open: boolean;
  state: SandboxLaunchState;
  agentKind?: "codex" | SandboxAgentKind;
  error?: string;
  persistentEnabled?: boolean;
  persistentReason?: string;
  persistentRequired?: boolean;
  storageMode?: "snapshot" | "disk";
  diskGbDefault?: number;
  diskGbMin?: number;
  diskGbMax?: number;
  onCancel: () => void;
  onConfirm: (displayName: string, persistent: boolean, diskGb?: number) => void;
}

export function SandboxLaunchDialog({
  open,
  state,
  agentKind = "codex",
  error,
  persistentEnabled = true,
  persistentReason = "",
  persistentRequired = false,
  storageMode = "snapshot",
  diskGbDefault = 10,
  diskGbMin = 5,
  diskGbMax = 100,
  onCancel,
  onConfirm,
}: SandboxLaunchDialogProps) {
  const agentLabel = agentKind === "codex"
    ? "Codex"
    : agentKind === "deepseek-harness"
      ? "DeepSeek Harness"
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
  const [persistent, setPersistent] = useState(true);
  const [diskGb, setDiskGb] = useState(diskGbDefault);
  onCancelRef.current = onCancel;

  useEffect(() => {
    if (!open) return;
    setDisplayName(defaultDisplayName);
    setPersistent(persistentRequired || persistentEnabled);
    setDiskGb(diskGbDefault);
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
  }, [defaultDisplayName, diskGbDefault, open, persistentEnabled, persistentRequired]);

  if (!open) return null;

  const loading = state === "loading";
  const validDisplayName = displayName.trim();
  const validDiskGb = Number.isInteger(diskGb) && diskGb >= diskGbMin && diskGb <= diskGbMax;
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
            !composingRef.current &&
            validDisplayName &&
            (storageMode !== "disk" || validDiskGb)
          ) {
            onConfirm(
              validDisplayName,
              storageMode === "disk" ? true : persistent,
              storageMode === "disk" ? diskGb : undefined,
            );
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
          {storageMode === "disk" ? (
            <label className="sandbox-dialog-field sandbox-dialog-disk-field">
              <span className="sandbox-dialog-field-label">
                <span>存储大小</span>
                <span>GiB</span>
              </span>
              <input
                type="number"
                required
                min={diskGbMin}
                max={diskGbMax}
                step={1}
                value={diskGb}
                disabled={loading}
                onChange={(event) => setDiskGb(event.currentTarget.valueAsNumber)}
              />
              <span className="sandbox-dialog-field-help">
                数据将持久化保存，可设置 {diskGbMin}–{diskGbMax} GiB。
              </span>
            </label>
          ) : (
            <div
              className="sandbox-dialog-persistence"
              role="group"
              aria-describedby="sandbox-persistence-description"
            >
              <Checkbox
                id="sandbox-persistence"
                className="sandbox-dialog-persistence-control"
                checked={persistent}
                disabled={loading || !persistentEnabled || persistentRequired}
                onCheckedChange={setPersistent}
                label="持久化"
              />
              <p
                id="sandbox-persistence-description"
                className={`sandbox-dialog-persistence-description${
                  persistent ? "" : " is-warning"
                }`}
                role={persistent ? undefined : "status"}
              >
                {!persistentEnabled
                  ? persistentReason || "当前环境不支持快照持久化"
                  : persistent
                  ? "保留智能体数据，后续可继续使用。"
                  : "智能体将在 8 小时后清空"}
              </p>
            </div>
          )}
        </div>
        <footer className="sandbox-dialog-actions">
          <button ref={cancelButtonRef} type="button" onClick={onCancel}>
            {loading ? "取消创建" : "取消"}
          </button>
          {!loading && (
            <button
              type="submit"
              className="is-primary"
              disabled={!validDisplayName || (storageMode === "disk" && !validDiskGb)}
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
