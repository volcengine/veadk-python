import {
  useEffect,
  useId,
  useRef,
  useState,
  type SVGProps,
} from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import type { IssueFeedbackIssue } from "../adk/issueFeedback";
import "./IssueFeedbackDialog.css";

const ISSUE_OPTIONS: IssueFeedbackIssue[] = [
  "slow",
  "crash",
  "incorrect",
  "tool_error",
  "other",
];

interface IssueFeedbackDialogProps {
  onClose: () => void;
  onSubmit: (feedback: {
    issues: IssueFeedbackIssue[];
    description: string;
  }) => Promise<void>;
}

function DialogCloseIcon(props: SVGProps<SVGSVGElement>) {
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

function DialogCheckIcon(props: SVGProps<SVGSVGElement>) {
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
      <path d="m5 12.5 4.2 4.2L19 7" />
    </svg>
  );
}

export function IssueFeedbackDialog({
  onClose,
  onSubmit,
}: IssueFeedbackDialogProps) {
  const { t } = useTranslation("feedback");
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const busyRef = useRef(false);
  const onCloseRef = useRef(onClose);
  const [selectedIssues, setSelectedIssues] = useState<Set<IssueFeedbackIssue>>(
    () => new Set(),
  );
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);

  busyRef.current = busy;
  onCloseRef.current = onClose;

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const previousFocus =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    document.body.style.overflow = "hidden";
    textareaRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busyRef.current) {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled), textarea:not(:disabled)',
        ) ?? [],
      );
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

  const toggleIssue = (issue: IssueFeedbackIssue) => {
    setSelectedIssues((current) => {
      const next = new Set(current);
      if (next.has(issue)) next.delete(issue);
      else next.add(issue);
      return next;
    });
  };

  const submit = async () => {
    if (busy || submitted) return;
    setBusy(true);
    setError("");
    try {
      await onSubmit({
        issues: [...selectedIssues],
        description: description.trim(),
      });
      setSubmitted(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const canSubmit = selectedIssues.size > 0 || description.trim().length > 0;

  return createPortal(
    <div
      className="issue-feedback-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className="issue-feedback-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={submitted ? `${descriptionId}-success` : descriptionId}
        aria-busy={busy || undefined}
      >
        <header className="issue-feedback-head">
          <h2 id={titleId}>{t("title")}</h2>
          <button
            type="button"
            className="issue-feedback-close"
            onClick={onClose}
            disabled={busy}
            aria-label={t("dialog.close")}
          >
            <DialogCloseIcon />
          </button>
        </header>

        {submitted ? (
          <div className="issue-feedback-success" role="status" aria-live="polite">
            <span className="issue-feedback-success-mark" aria-hidden="true">
              <DialogCheckIcon />
            </span>
            <div>
              <h3>{t("success.title")}</h3>
              <p id={`${descriptionId}-success`}>
                {t("success.description")}
              </p>
            </div>
          </div>
        ) : (
          <div className="issue-feedback-body">
            <p id={descriptionId} className="issue-feedback-intro">
              {t("dialog.intro")}
            </p>
            <p className="issue-feedback-privacy" role="alert">
              {t("dialog.privacy")}
            </p>
            <div className="issue-feedback-chips" aria-label={t("commonIssues")}>
              {ISSUE_OPTIONS.map((issue) => (
                <button
                  key={issue}
                  type="button"
                  className="issue-feedback-chip"
                  aria-pressed={selectedIssues.has(issue)}
                  onClick={() => toggleIssue(issue)}
                  disabled={busy}
                >
                  {t(`dialog.issues.${issue}`)}
                </button>
              ))}
            </div>
            <label className="issue-feedback-field">
              <span>{t("descriptionLabel")}</span>
              <textarea
                ref={textareaRef}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder={t("dialog.descriptionPlaceholder")}
                maxLength={4000}
                rows={5}
                disabled={busy}
              />
            </label>
            {error && (
              <p className="issue-feedback-error" role="alert">{error}</p>
            )}
          </div>
        )}

        <footer className="issue-feedback-actions">
          {submitted ? (
            <button type="button" className="is-primary" onClick={onClose}>
              {t("done")}
            </button>
          ) : (
            <>
              <button type="button" onClick={onClose} disabled={busy}>
                {t("cancel")}
              </button>
              <button
                type="button"
                className="is-primary"
                onClick={() => void submit()}
                disabled={!canSubmit || busy}
              >
                {busy ? t("submitting") : t("submit")}
              </button>
            </>
          )}
        </footer>
      </section>
    </div>,
    document.body,
  );
}
