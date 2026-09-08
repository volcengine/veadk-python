import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { CircleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import "./AuthExpiredDialog.css";

interface AuthExpiredDialogProps {
  open: boolean;
  checking: boolean;
  error?: string;
  onLogin: () => void;
}

export function AuthExpiredDialog({
  open,
  checking,
  error,
  onLogin,
}: AuthExpiredDialogProps) {
  const { t } = useTranslation("shell");
  const loginButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    loginButtonRef.current?.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div className="auth-expired-backdrop">
      <section
        className="auth-expired-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="auth-expired-title"
        aria-describedby="auth-expired-description"
      >
        <div className="auth-expired-mark" aria-hidden="true">
          <CircleAlert />
        </div>
        <div className="auth-expired-copy">
          <h2 id="auth-expired-title">{t("authExpired.title")}</h2>
          <p id="auth-expired-description">
            {t("authExpired.description")}
          </p>
          {error && (
            <p className="auth-expired-error" role="alert">
              {error}
            </p>
          )}
        </div>
        <footer className="auth-expired-actions">
          <button
            ref={loginButtonRef}
            type="button"
            onClick={onLogin}
            disabled={checking}
          >
            {checking ? t("authExpired.waiting") : t("authExpired.signInAgain")}
          </button>
        </footer>
      </section>
    </div>,
    document.body,
  );
}
