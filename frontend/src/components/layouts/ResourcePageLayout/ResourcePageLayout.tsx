import type { ReactNode } from "react";
import "./ResourcePageLayout.css";

export interface ResourcePageLayoutProps {
  title: ReactNode;
  banner?: ReactNode;
  filters?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

/** Resource content layout from Figma node 625:230094 */
export function ResourcePageLayout({ title, banner, filters, actions, children, className }: ResourcePageLayoutProps) {
  return (
    <section className={["studio-resource-page", className].filter(Boolean).join(" ")}>
      <header className="studio-resource-page__header">
        <h2 className="studio-resource-page__title">{title}</h2>
        {banner}
      </header>
      <div className="studio-resource-page__body">
        <div className="studio-resource-page__toolbar">
          <div>{filters}</div>
          <div className="studio-resource-page__actions">{actions}</div>
        </div>
        <div className="studio-resource-page__grid">{children}</div>
      </div>
    </section>
  );
}
