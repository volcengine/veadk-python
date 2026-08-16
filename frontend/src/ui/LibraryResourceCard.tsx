import {
  type ReactNode,
} from "react";
import "./MyAgents.css";
import "./LibraryResourceCard.css";
import { StudioActionMenu } from "./StudioActionMenu";

export interface LibraryResourceCardAction {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  title?: string;
}

export interface LibraryResourceCardMenuAction extends LibraryResourceCardAction {
  danger?: boolean;
}

export interface LibraryResourceCardMetadata {
  label: string;
  value: ReactNode;
  title?: string;
}

export interface LibraryResourceCardProps {
  className?: string;
  title: string;
  status: ReactNode;
  description: string;
  metadata: readonly LibraryResourceCardMetadata[];
  secondaryAction: LibraryResourceCardAction;
  primaryAction: LibraryResourceCardAction;
  menuLabel: string;
  menuAriaLabel: string;
  menuActions: readonly LibraryResourceCardMenuAction[];
}

interface LibraryResourceCardActionsProps {
  secondaryAction: LibraryResourceCardAction;
  primaryAction: LibraryResourceCardAction;
  menuLabel: string;
  menuAriaLabel: string;
  menuActions: readonly LibraryResourceCardMenuAction[];
}

function LibraryResourceCardActions({
  secondaryAction,
  primaryAction,
  menuLabel,
  menuAriaLabel,
  menuActions,
}: LibraryResourceCardActionsProps) {
  return (
    <footer className="library-resource-card__actions">
      <button
        type="button"
        className="library-resource-card__action library-resource-card__action--secondary"
        disabled={secondaryAction.disabled}
        title={secondaryAction.title}
        onClick={secondaryAction.onClick}
      >
        {secondaryAction.label}
      </button>
      <button
        type="button"
        className="library-resource-card__action library-resource-card__action--primary"
        disabled={primaryAction.disabled}
        title={primaryAction.title}
        onClick={primaryAction.onClick}
      >
        {primaryAction.label}
      </button>
      <StudioActionMenu
        label={menuLabel}
        menuLabel={menuAriaLabel}
        className="library-resource-card__action library-resource-card__more"
        placement="top-end"
        items={menuActions.map((action) => ({
          label: action.label,
          onSelect: action.onClick,
          disabled: action.disabled,
          danger: action.danger,
          title: action.title,
        }))}
      />
    </footer>
  );
}

export function LibraryResourceCard({
  className = "",
  title,
  status,
  description,
  metadata,
  secondaryAction,
  primaryAction,
  menuLabel,
  menuAriaLabel,
  menuActions,
}: LibraryResourceCardProps) {
  return (
    <article className={`my-agent-card library-resource-card ${className}`.trim()}>
      <div className="my-agent-card-content">
        <div className="my-agent-card-title">
          <div className="my-agent-card-title-copy">
            <h3 title={title}>{title}</h3>
          </div>
          {status}
        </div>
        <p className="my-agent-description" title={description}>{description}</p>
        <dl className="my-agent-meta">
          {metadata.map((item, index) => (
            <div key={`${item.label}:${index}`} className={index === 0 ? "my-agent-created-at" : "my-agent-region"}>
              <dt>{item.label}</dt>
              <dd title={item.title}>{item.value}</dd>
            </div>
          ))}
        </dl>
      </div>
      <LibraryResourceCardActions
        secondaryAction={secondaryAction}
        primaryAction={primaryAction}
        menuLabel={menuLabel}
        menuAriaLabel={menuAriaLabel}
        menuActions={menuActions}
      />
    </article>
  );
}
