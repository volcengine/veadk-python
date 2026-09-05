import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";
import {
  IntelligentGoalPanel,
  type IntelligentCreateBaseVersion,
  type IntelligentDevelopmentCapabilities,
  type IntelligentPreparationStage,
} from "../create/IntelligentCreate";
import { SourceCloseIcon } from "../ui/icons/SourceWorkspaceIcons";
import "./IntelligentOptimizationDialog.css";

interface IntelligentOptimizationDialogProps {
  baseVersion: IntelligentCreateBaseVersion;
  capabilities: IntelligentDevelopmentCapabilities | null;
  loading: boolean;
  preparationStage: IntelligentPreparationStage | null;
  error: string;
  onCancel: () => void;
  onClose: () => void;
  onCreate: (
    goal: string,
    modelId: string,
    baseVersion: IntelligentCreateBaseVersion,
  ) => Promise<void>;
}

export function IntelligentOptimizationDialog({
  baseVersion,
  capabilities,
  loading,
  preparationStage,
  error,
  onCancel,
  onClose,
  onCreate,
}: IntelligentOptimizationDialogProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const busy = preparationStage !== null;
  const busyRef = useRef(busy);
  const onCloseRef = useRef(onClose);
  busyRef.current = busy;
  onCloseRef.current = onClose;

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    document.body.style.overflow = "hidden";
    window.requestAnimationFrame(() => {
      dialogRef.current?.querySelector<HTMLTextAreaElement>("textarea")?.focus();
    });
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (!busyRef.current) onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )].filter((item) => item.offsetParent !== null);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
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
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  return createPortal(
    <div
      className="migration-optimize-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className="migration-optimize-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-busy={busy || undefined}
      >
        <header className="migration-optimize-dialog__header">
          <div>
            <h2 id={titleId}>优化迁移项目</h2>
            <p title={baseVersion.projectName}>{baseVersion.projectName}</p>
          </div>
          <button
            type="button"
            className="migration-optimize-dialog__close"
            onClick={onClose}
            disabled={busy}
            aria-label="关闭优化窗口"
            title="关闭"
          >
            <SourceCloseIcon />
          </button>
        </header>
        <div className="migration-optimize-dialog__body">
          <IntelligentGoalPanel
            capabilities={capabilities}
            loading={loading}
            preparationStage={preparationStage}
            error={error}
            onCancel={onCancel}
            onCreate={async (goal, modelId) => {
              await onCreate(goal, modelId, baseVersion);
            }}
            baseVersion={baseVersion}
          />
        </div>
      </section>
    </div>,
    document.body,
  );
}
