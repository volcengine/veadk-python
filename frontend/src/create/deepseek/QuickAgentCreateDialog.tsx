import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import { SourceCloseIcon } from "../../ui/icons/SourceWorkspaceIcons";
import "../CustomCreate.css";
import "./QuickAgentCreateDialog.css";

export type QuickAgentKind = "veadk" | "deepseek";

interface Props {
  open: boolean;
  onClose: () => void;
  onSelect: (kind: QuickAgentKind) => void;
}

export default function QuickAgentCreateDialog({ open, onClose, onSelect }: Props) {
  const { t } = useTranslation("deepseek");
  const id = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  const [kind, setKind] = useState<QuickAgentKind>("veadk");
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    const background = document.getElementById("root");
    const previousInert = background?.inert ?? false;
    if (background) background.inert = true;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing) return;
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const items = [...dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input[type="radio"]:checked',
      )].filter((item) => item.getClientRects().length > 0);
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => {
      window.removeEventListener("keydown", handleKey);
      document.body.style.overflow = previousOverflow;
      if (background) background.inert = previousInert;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div className="cw-skill-dialog-backdrop quick-agent-type-backdrop" onClick={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="cw-skill-dialog quick-agent-type-dialog" role="dialog" aria-modal="true" aria-labelledby={`${id}-title`} ref={dialogRef}>
        <header className="cw-skill-dialog-head">
          <h2 id={`${id}-title`}>{t("agentType")}</h2>
          <button type="button" className="cw-skill-dialog-close" onClick={onClose} ref={closeRef} aria-label={t("close")}>
            <SourceCloseIcon />
          </button>
        </header>
        <form onSubmit={(event) => { event.preventDefault(); onSelect(kind); }}>
          <fieldset className="cw-agent-type-options quick-agent-type-options" role="radiogroup" aria-label={t("agentType")}>
            {(["veadk", "deepseek"] as const).map((value) => (
              <label key={value} className={`cw-agent-type-option quick-agent-type-option${kind === value ? " is-on" : ""}`}>
                <input type="radio" name={`${id}-kind`} value={value} checked={kind === value} onChange={() => setKind(value)} />
                <span>{value === "veadk" ? "VeADK Agent" : "DeepSeek Harness"}</span>
                {value === "deepseek" && <Badge className="quick-agent-beta" color="secondary" variant="soft" size="sm">Beta</Badge>}
              </label>
            ))}
          </fieldset>
          <footer className="quick-agent-type-actions">
            <Button type="button" className="cw-btn cw-btn-ghost" color="secondary" variant="ghost" onClick={onClose}>{t("cancel")}</Button>
            <Button type="submit" className="cw-btn cw-btn-primary" color="primary">{t("continue")}</Button>
          </footer>
        </form>
      </section>
    </div>,
    document.body,
  );
}
