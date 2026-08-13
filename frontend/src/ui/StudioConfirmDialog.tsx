import {
  useEffect,
  useId,
  useRef,
  type SVGProps,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

type StudioConfirmVariant = "warning" | "danger";

interface StudioConfirmDialogProps {
  title: string;
  description: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  closeLabel?: string;
  variant?: StudioConfirmVariant;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

const STUDIO_CONFIRM_FOCUSABLE_SELECTOR =
  'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';

export function trapStudioConfirmDialogFocus(
  event: Pick<KeyboardEvent, "key" | "shiftKey" | "preventDefault">,
  dialog: Pick<HTMLElement, "querySelectorAll" | "focus"> | null,
  activeElement: Element | null,
) {
  if (event.key !== "Tab" || !dialog) return;
  const focusable = Array.from(
    dialog.querySelectorAll<HTMLElement>(STUDIO_CONFIRM_FOCUSABLE_SELECTOR),
  );
  if (focusable.length === 0) {
    event.preventDefault();
    dialog.focus();
    return;
  }

  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (!focusable.includes(activeElement as HTMLElement)) {
    event.preventDefault();
    (event.shiftKey ? last : first).focus();
  } else if (event.shiftKey && activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function ConfirmWarningIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M12 4.2 21 19H3L12 4.2Z" />
      <path d="M12 9.4v4.2" />
      <path d="M12 16.8h.01" />
    </svg>
  );
}

function ConfirmCloseIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      aria-hidden="true"
      {...props}
    >
      <path d="m7 7 10 10" />
      <path d="m17 7-10 10" />
    </svg>
  );
}

export function StudioConfirmDialog({
  title,
  description,
  confirmLabel,
  cancelLabel = "取消",
  closeLabel = "关闭确认框",
  variant = "warning",
  busy = false,
  onCancel,
  onConfirm,
}: StudioConfirmDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLElement>(null);
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
        event.preventDefault();
        onCancelRef.current();
        return;
      }
      trapStudioConfirmDialogFocus(
        event,
        dialogRef.current,
        document.activeElement,
      );
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
        ref={dialogRef}
        className={`studio-confirm-dialog studio-confirm-dialog--${variant}`}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        aria-busy={busy || undefined}
        tabIndex={-1}
      >
        <header className="studio-confirm-head">
          <div className="studio-confirm-title-wrap">
            <span className="studio-confirm-title-icon" aria-hidden="true">
              <ConfirmWarningIcon />
            </span>
            <h2 id={titleId}>{title}</h2>
          </div>
          <button
            type="button"
            className="studio-confirm-close"
            onClick={onCancel}
            disabled={busy}
            aria-label={closeLabel}
          >
            <ConfirmCloseIcon />
          </button>
        </header>
        <div className="studio-confirm-body">
          <p id={descriptionId}>{description}</p>
        </div>
        <footer className="studio-confirm-actions">
          <button
            ref={cancelButtonRef}
            type="button"
            onClick={onCancel}
            disabled={busy}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className="studio-confirm-primary"
            onClick={onConfirm}
            disabled={busy}
          >
            {confirmLabel}
          </button>
        </footer>
      </section>
    </div>,
    document.body,
  );
}
