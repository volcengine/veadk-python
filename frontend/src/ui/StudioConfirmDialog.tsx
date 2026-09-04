import {
  useEffect,
  useId,
  useRef,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { Alert } from "@openai/apps-sdk-ui/components/Alert";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { Warning, X } from "@openai/apps-sdk-ui/components/Icon";
import { useTranslation } from "react-i18next";

type StudioConfirmVariant = "warning" | "danger";

interface StudioConfirmDialogProps {
  title: string;
  description: ReactNode;
  error?: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  closeLabel?: string;
  variant?: StudioConfirmVariant;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function StudioConfirmDialog({
  title,
  description,
  error,
  confirmLabel,
  cancelLabel: cancelLabelProp,
  closeLabel: closeLabelProp,
  variant = "warning",
  busy = false,
  onCancel,
  onConfirm,
}: StudioConfirmDialogProps) {
  const { t } = useTranslation("shell");
  const cancelLabel = cancelLabelProp ?? t("confirm.cancel");
  const closeLabel = closeLabelProp ?? t("confirm.close");
  const titleId = useId();
  const descriptionId = useId();
  const cancelButtonRef = useRef<HTMLButtonElement>(null);
  const busyRef = useRef(busy);
  const onCancelRef = useRef(onCancel);

  useEffect(() => {
    busyRef.current = busy;
    onCancelRef.current = onCancel;
  }, [busy, onCancel]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const previousFocus =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    document.body.style.overflow = "hidden";
    cancelButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busyRef.current) {
        onCancelRef.current();
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
      className="studio-confirm-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel();
      }}
    >
      <section
        className={`studio-confirm-dialog studio-confirm-dialog--${variant}`}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        aria-busy={busy || undefined}
      >
        <header className="studio-confirm-head">
          <div className="studio-confirm-title-wrap">
            <span className="studio-confirm-title-icon" aria-hidden="true">
              <Warning />
            </span>
            <h2 id={titleId}>{title}</h2>
          </div>
          <Button
            type="button"
            className="studio-confirm-close"
            color="secondary"
            variant="ghost"
            size="lg"
            uniform
            pill={false}
            onClick={onCancel}
            disabled={busy}
            aria-label={closeLabel}
          >
            <X />
          </Button>
        </header>
        <div className="studio-confirm-body">
          <p id={descriptionId}>{description}</p>
          {error ? <Alert className="studio-confirm-error" color="danger" variant="soft" description={error} /> : null}
        </div>
        <footer className="studio-confirm-actions">
          <Button
            ref={cancelButtonRef}
            type="button"
            color="secondary"
            variant="ghost"
            size="lg"
            pill={false}
            onClick={onCancel}
            disabled={busy}
          >
            {cancelLabel}
          </Button>
          <Button
            type="button"
            className="studio-confirm-primary"
            color={variant === "danger" ? "danger" : "primary"}
            size="lg"
            pill={false}
            loading={busy}
            onClick={onConfirm}
            disabled={busy}
          >
            {confirmLabel}
          </Button>
        </footer>
      </section>
    </div>,
    document.body,
  );
}
