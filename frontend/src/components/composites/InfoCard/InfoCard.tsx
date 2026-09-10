import { useId, type HTMLAttributes, type ReactNode } from "react";
import "./InfoCard.css";

export interface InfoCardProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title: ReactNode;
}

export function InfoCard({ title, children, className = "", ...props }: InfoCardProps) {
  const titleId = useId();
  return <article aria-labelledby={titleId} {...props} className={`studio-info-card ${className}`.trim()}>
    <InfoCardTitle id={titleId}>{title}</InfoCardTitle>
    {children}
  </article>;
}

export function InfoCardTitle({ children, className = "", ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return <h3 {...props} className={`studio-info-card__title ${className}`.trim()}>{children}</h3>;
}

export interface InfoCardBodyProps extends HTMLAttributes<HTMLDivElement> {
  value?: ReactNode;
  description?: ReactNode;
}

export function InfoCardBody({ value, description, children, className = "", ...props }: InfoCardBodyProps) {
  return <div {...props} className={`studio-info-card__body ${className}`.trim()}>
    {value != null && <p className="studio-info-card__value">{value}</p>}
    {description != null && <p className="studio-info-card__description">{description}</p>}
    {children}
  </div>;
}
