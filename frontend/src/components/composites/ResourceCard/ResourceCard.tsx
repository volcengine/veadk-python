import { useId, type HTMLAttributes, type ReactNode } from "react";
import avatarBackground from "./assets/avatar-background.png";
import avatarLetter from "./assets/avatar-letter-a.svg";
import metadataDivider from "./assets/metadata-divider.svg";
import "./ResourceCard.css";

export interface ResourceCardProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title: string;
  description: string;
  author: string;
  updatedLabel: string;
  avatar?: ReactNode;
}

/** Resource card from Figma node 631:247425 */
export function ResourceCard({ title, description, author, updatedLabel, avatar, className, ...props }: ResourceCardProps) {
  const titleId = useId();
  return (
    <article {...props} className={["studio-resource-card", className].filter(Boolean).join(" ")} aria-labelledby={titleId}>
      <div className="studio-resource-card__content">
        <div className="studio-resource-card__heading">
          <div className="studio-resource-card__avatar" aria-hidden="true">
            {avatar ?? <>
              <img className="studio-resource-card__avatar-background" src={avatarBackground} alt="" />
              <span className="studio-resource-card__avatar-shade" />
              <img className="studio-resource-card__avatar-letter" src={avatarLetter} alt="" />
            </>}
          </div>
          <h3 className="studio-resource-card__title" id={titleId}>{title}</h3>
        </div>
        <p className="studio-resource-card__description" title={description}>{description}</p>
      </div>
      <div className="studio-resource-card__footer">
        <div className="studio-resource-card__metadata">
          <span>{author}</span>
          <span className="studio-resource-card__divider" aria-hidden="true"><img src={metadataDivider} alt="" /></span>
          <span>{updatedLabel}</span>
        </div>
      </div>
    </article>
  );
}
