import type { HTMLAttributes, ReactNode } from "react";
import "./DetailPageLayout.css";

export interface DetailPageLayoutProps extends HTMLAttributes<HTMLDivElement> {
  back: ReactNode;
  header: ReactNode;
  tabs: ReactNode;
  runtime?: ReactNode;
  runtimeLabel?: ReactNode;
}

export function DetailPageLayout({ back, header, tabs, children, runtime, runtimeLabel = "Runtime", className = "", ...props }: DetailPageLayoutProps) {
  return <div {...props} className={`studio-detail-page-layout ${className}`.trim()}>
    <div className="studio-detail-page-layout__glow" aria-hidden="true" />
    <div className="studio-detail-page-layout__back">{back}</div>
    <div className="studio-detail-page-layout__header">{header}</div>
    <div className="studio-detail-page-layout__tabs">{tabs}</div>
    <main className="studio-detail-page-layout__content">{children}</main>
    <h2 className="studio-detail-page-layout__runtime-title">{runtimeLabel}</h2>
    <section className="studio-detail-page-layout__runtime" aria-label={typeof runtimeLabel === "string" ? runtimeLabel : undefined}>{runtime}</section>
  </div>;
}
