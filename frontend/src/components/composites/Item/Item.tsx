import type { ReactNode } from "react";
import codeIcon from "./code.svg";
import cloudIcon from "./cloud.svg";
import externalLinkIcon from "./external-link.svg";
import "./Item.css";

export type ItemProps = {
  variant?: "default" | "compact";
  title: string;
  description: string;
  icon?: ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
};

export function Item({ variant = "default", title, description, icon, actionLabel, onAction, className = "" }: ItemProps) {
  if (variant === "compact") {
    const content = <>
      <span className="studio-item-compact__icon" aria-hidden="true">{icon ?? <span className="studio-item-compact__code" style={{ maskImage: `url(${codeIcon})` }} />}</span>
      <span className="studio-item-compact__content">
        <span className="studio-item-compact__title">{title}</span>
        <span className="studio-item-compact__description">{description}</span>
      </span>
    </>;
    return onAction
      ? <button type="button" className={`studio-item-compact ${className}`} onClick={onAction} aria-label={actionLabel}>{content}</button>
      : <div className={`studio-item-compact ${className}`}>{content}</div>;
  }
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
