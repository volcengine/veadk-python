import { useId, type HTMLAttributes, type ReactNode } from "react";
import faceIcon from "./assets/face-id-square.svg";
import closeIcon from "./assets/close.svg";
import "./CardLayout.css";

export interface CardLayoutProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title: string;
  icon?: ReactNode;
  onClose?: () => void;
  closeLabel?: string;
}

export function CardLayout({ title, icon, onClose, closeLabel = "Close", children, className = "", ...props }: CardLayoutProps) {
  const titleId = useId();
  return (
    <section aria-labelledby={titleId} {...props} className={`studio-card-layout ${className}`.trim()}>
      <header className="studio-card-layout__header">
        <span className="studio-card-layout__icon" aria-hidden="true">{icon ?? <img src={faceIcon} alt="" />}</span>
        <h3 className="studio-card-layout__title" id={titleId}>{title}</h3>
        <button type="button" className="studio-card-layout__close" aria-label={closeLabel} onClick={onClose}>
          <img src={closeIcon} alt="" />
        </button>
      </header>
      <div className="studio-card-layout__content">{children}</div>
    </section>
  );
}
