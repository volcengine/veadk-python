import { useId, type HTMLAttributes, type ReactNode } from "react";
import { Button } from "../../primitives/Button";
import "./ModalLayout.css";

export interface ModalLayoutProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title: ReactNode;
  topGlow?: boolean;
  size?: "default" | "large";
  confirmDisabled?: boolean;
  confirmLoading?: boolean;
  cancelLabel?: string;
  confirmLabel?: string;
  closeLabel?: string;
  onClose?: () => void;
  onCancel?: () => void;
  onConfirm?: () => void;
}

export function ModalLayout({ title, topGlow = true, size = "default", confirmDisabled, confirmLoading, children, cancelLabel = "Cancel", confirmLabel = "Confirm", closeLabel = "Close", onClose, onCancel, onConfirm, className = "", ...props }: ModalLayoutProps) {
  const titleId = useId();
  return <div role="dialog" aria-labelledby={titleId} {...props} data-size={size} className={`studio-modal-layout ${topGlow ? "studio-modal-layout--glow" : ""} ${className}`.trim()}>
    <header className="studio-modal-layout__header">
      <h3 id={titleId}>{title}</h3>
      <Button variant="ghost" size="compact" iconOnly className="studio-modal-layout__close" aria-label={closeLabel} onClick={onClose} startIcon={<svg viewBox="0 0 20 20" width="20" height="20" fill="none" aria-hidden="true"><path d="m5 5 10 10M15 5 5 15" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" /></svg>} />
    </header>
    <div className="studio-modal-layout__body">{children}</div>
    <footer className="studio-modal-layout__footer">
      <Button variant="outline" className="studio-modal-layout__cancel" onClick={onCancel}>{cancelLabel}</Button>
      <Button className="studio-modal-layout__confirm" disabled={confirmDisabled} loading={confirmLoading} loadingLabel={confirmLabel} onClick={onConfirm}>{confirmLabel}</Button>
    </footer>
  </div>;
}
