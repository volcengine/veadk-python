import { useId, type HTMLAttributes, type ReactNode } from "react";
import { Button } from "../../primitives/Button";
import closeIcon from "./assets/close.svg";
import "./ModalLayout.css";

export interface ModalLayoutProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title: ReactNode;
  topGlow?: boolean;
  cancelLabel?: string;
  confirmLabel?: string;
  closeLabel?: string;
  onClose?: () => void;
  onCancel?: () => void;
  onConfirm?: () => void;
}

export function ModalLayout({ title, topGlow = true, children, cancelLabel = "Cancel", confirmLabel = "Confirm", closeLabel = "Close", onClose, onCancel, onConfirm, className = "", ...props }: ModalLayoutProps) {
  const titleId = useId();
  return <div role="dialog" aria-labelledby={titleId} {...props} className={`studio-modal-layout ${topGlow ? "studio-modal-layout--glow" : ""} ${className}`.trim()}>
    <header className="studio-modal-layout__header">
      <h3 id={titleId}>{title}</h3>
      <button type="button" className="studio-modal-layout__close" aria-label={closeLabel} onClick={onClose}>
        <img src={closeIcon} alt="" />
      </button>
    </header>
    <div className="studio-modal-layout__body">{children}</div>
    <footer className="studio-modal-layout__footer">
      <Button className="studio-modal-layout__cancel" onClick={onCancel}>{cancelLabel}</Button>
      <Button className="studio-modal-layout__confirm" onClick={onConfirm}>{confirmLabel}</Button>
    </footer>
  </div>;
}
