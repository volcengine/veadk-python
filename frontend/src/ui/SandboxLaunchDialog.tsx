import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { InsightIcon } from "./icons/InsightIcon";

export type SandboxLaunchState = "confirm" | "loading" | "error";

export interface SandboxLaunchDialogProps {
  open: boolean;
  state: SandboxLaunchState;
  error?: string;
  onCancel: () => void;
  onConfirm: () => void;
}

export function SandboxLaunchDialog({
  open,
  state,
  error,
  onCancel,
  onConfirm,
}: SandboxLaunchDialogProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    cancelButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
        return;
      }
      if (event.key !== "Tab") return;
      const controls = dialogRef.current?.querySelectorAll<HTMLButtonElement>(
        "button:not(:disabled)",
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
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onCancel, open]);

  if (!open) return null;

  const loading = state === "loading";
  const title = loading
    ? "正在创建沙箱"
    : state === "error"
      ? "启动失败"
      : "创建 Codex 智能体";

  return createPortal(
    <div
      className="sandbox-dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !loading) onCancel();
      }}
    >
      <section
        ref={dialogRef}
        className="sandbox-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="sandbox-dialog-title"
        aria-describedby="sandbox-dialog-description"
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
              正在创建 AgentKit Session 并等待沙箱就绪，通常需要一点时间。
            </p>
          ) : (
            <p id="sandbox-dialog-description">
              创建一个可重复进入的 AgentKit 沙箱，并将它作为 Codex 智能体显示在列表中。
            </p>
          )}
        </div>
        <footer className="sandbox-dialog-actions">
          <button ref={cancelButtonRef} type="button" onClick={onCancel}>
            {loading ? "取消创建" : "取消"}
          </button>
          {!loading && (
            <button type="button" className="is-primary" onClick={onConfirm}>
              {state === "error" ? "重新尝试" : "确认创建"}
            </button>
          )}
        </footer>
      </section>
    </div>,
    document.body,
  );
}
