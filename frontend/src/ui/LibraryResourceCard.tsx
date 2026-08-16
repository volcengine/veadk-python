import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type SVGProps,
} from "react";
import "./MyAgents.css";
import "./LibraryResourceCard.css";

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

function ResourceMoreIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" {...props}>
      <circle cx="5.5" cy="12" r="1.4" />
      <circle cx="12" cy="12" r="1.4" />
      <circle cx="18.5" cy="12" r="1.4" />
    </svg>
  );
}

function LibraryResourceCardActions({
  secondaryAction,
  primaryAction,
  menuLabel,
  menuAriaLabel,
  menuActions,
}: LibraryResourceCardActionsProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const closeMenu = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("pointerdown", closeMenu);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("pointerdown", closeMenu);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [menuOpen]);

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
      <div className="library-resource-card__menu" ref={menuRef}>
        <button
          type="button"
          className="library-resource-card__action library-resource-card__more"
          aria-label={menuLabel}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((current) => !current)}
        >
          <ResourceMoreIcon />
        </button>
        {menuOpen ? (
          <div className="library-resource-card__popover" role="menu" aria-label={menuAriaLabel}>
            {menuActions.map((action) => (
              <button
                key={action.label}
                type="button"
                role="menuitem"
                className={`library-resource-card__menu-action${action.danger ? " is-danger" : ""}`}
                disabled={action.disabled}
                title={action.title}
                onClick={() => {
                  setMenuOpen(false);
                  action.onClick();
                }}
              >
                {action.label}
              </button>
            ))}
          </div>
        ) : null}
      </div>
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
