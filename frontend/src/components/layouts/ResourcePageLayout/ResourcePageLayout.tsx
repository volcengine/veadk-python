import type { ReactNode } from "react";
import { Loading } from "../../primitives/Loading";
import "./ResourcePageLayout.css";

export interface ResourcePageLayoutProps {
  title: ReactNode;
  banner?: ReactNode;
  filters?: ReactNode;
  actions?: ReactNode;
  /** 首次请求资源时显示 Infinity Path，内容就绪后传入 false */
  loading?: boolean;
  /** 仅供屏幕阅读器读取的加载状态文案 */
  loadingLabel?: string;
  children: ReactNode;
  className?: string;
}

/** Resource content layout from Figma node 625:230094 */
export function ResourcePageLayout({ title, banner, filters, actions, loading = false, loadingLabel = "正在加载资源", children, className }: ResourcePageLayoutProps) {
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
        {loading ? (
          <div className="studio-resource-page__loading">
            <Loading label={loadingLabel} />
          </div>
        ) : (
          <div className="studio-resource-page__grid">{children}</div>
        )}
      </div>
    </section>
  );
}
