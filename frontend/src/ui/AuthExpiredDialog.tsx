import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { CircleAlert } from "lucide-react";
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
          <h2 id="auth-expired-title">登录状态已过期</h2>
          <p id="auth-expired-description">
            当前编辑内容会保留。重新登录后，刚才的操作将自动继续。
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
            {checking ? "等待登录完成…" : "重新登录"}
          </button>
        </footer>
      </section>
    </div>,
    document.body,
  );
}
