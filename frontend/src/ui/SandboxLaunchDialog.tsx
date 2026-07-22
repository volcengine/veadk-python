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
    ? "正在初始化沙箱"
    : state === "error"
      ? "启动失败"
      : "启用临时会话";

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
              正在寻找可用工具并创建临时 Session，通常需要一点时间。
            </p>
          ) : (
            <p id="sandbox-dialog-description">
              将启动 AgentKit 沙箱与 Codex Agent 开启临时会话，您的会话将不会被持久化保存。
            </p>
          )}
        </div>
        <footer className="sandbox-dialog-actions">
          <button ref={cancelButtonRef} type="button" onClick={onCancel}>
            {loading ? "取消启动" : "取消"}
          </button>
          {!loading && (
            <button type="button" className="is-primary" onClick={onConfirm}>
              {state === "error" ? "重新尝试" : "确认开启"}
            </button>
          )}
        </footer>
      </section>
    </div>,
    document.body,
  );
}
