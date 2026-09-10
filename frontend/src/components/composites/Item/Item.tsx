import type { ReactNode } from "react";
import cloudIcon from "./cloud.svg";
import externalLinkIcon from "./external-link.svg";
import "./Item.css";

export type ItemProps = {
  title: string;
  description: string;
  icon?: ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
};

export function Item({ title, description, icon, actionLabel, onAction, className = "" }: ItemProps) {
  const actionIcon = <img src={externalLinkIcon} width={14} height={14} alt="" />;
  return (
    <div className={`studio-item ${className}`.trim()}>
      <span className="studio-item__icon" aria-hidden="true">
        {icon ?? <img src={cloudIcon} width={20} height={20} alt="" />}
      </span>
      <div className="studio-item__content">
        <span className="studio-item__title">{title}</span>
        <span className="studio-item__description">{description}</span>
      </div>
      {onAction ? (
        <button className="studio-item__action" type="button" onClick={onAction} aria-label={actionLabel ?? title}>
          {actionIcon}
        </button>
      ) : <span className="studio-item__action" aria-hidden="true">{actionIcon}</span>}
    </div>
  );
}
