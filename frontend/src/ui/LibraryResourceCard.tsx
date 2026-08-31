import {
  type ReactNode,
} from "react";
import {
  ResourceCard,
  ResourceCardDescription,
  ResourceCardHeader,
  ResourceIdentityMark,
  ResourceCardMetadata,
  ResourceCardRevealAction,
} from "./ResourceCollection";

export interface LibraryResourceCardAction {
  label: string;
  onClick: () => void;
  icon?: "arrow" | "play" | "plus";
  disabled?: boolean;
  title?: string;
}

export interface LibraryResourceCardMetadata {
  label: string;
  value: ReactNode;
  title?: string;
}

export interface LibraryResourceCardProps {
  className?: string;
  title: string;
  status?: ReactNode;
  description: string;
  metadata: readonly LibraryResourceCardMetadata[];
  detailAction: LibraryResourceCardAction;
  action: LibraryResourceCardAction;
  auxiliaryAction?: Omit<LibraryResourceCardAction, "icon"> & { icon: ReactNode };
}

export function LibraryResourceCard({
  className = "",
  title,
  status,
  description,
  metadata,
  detailAction,
  action,
  auxiliaryAction,
}: LibraryResourceCardProps) {
  return (
    <ResourceCard
      className={`library-resource-card ${className}`.trim()}
      activateLabel={`${detailAction.label} ${title}`}
      onActivate={detailAction.disabled ? undefined : detailAction.onClick}
      footer={(
        <ResourceCardMetadata
          items={metadata.map((item) => ({
            label: item.label,
            value: item.value,
            title: item.title,
            hideLabel: true,
          }))}
        />
      )}
      actions={(
        <>
          {auxiliaryAction ? (
            <ResourceCardRevealAction
              className="library-resource-card__auxiliary-action"
              label={`${auxiliaryAction.label} ${title}`}
              tone="secondary"
              disabled={auxiliaryAction.disabled}
              title={auxiliaryAction.title ?? auxiliaryAction.label}
              onClick={auxiliaryAction.onClick}
            >
              {auxiliaryAction.icon}
            </ResourceCardRevealAction>
          ) : null}
          <ResourceCardRevealAction
            label={`${action.label} ${title}`}
            icon={action.icon}
            disabled={action.disabled}
            title={action.title}
            onClick={action.onClick}
          />
        </>
      )}
    >
      <ResourceCardHeader
        leading={<ResourceIdentityMark seed={title} />}
        title={title}
        titleText={title}
        status={status}
      />
      <ResourceCardDescription title={description}>{description}</ResourceCardDescription>
    </ResourceCard>
  );
}
