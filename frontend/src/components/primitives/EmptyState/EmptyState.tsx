import { Children, type HTMLAttributes, type ReactNode } from "react";
import "./EmptyState.css";

export interface EmptyStateProps extends Omit<HTMLAttributes<HTMLDivElement>, "title" | "children"> {
  /** 信息区域的标题 */
  title: ReactNode;
  /** 标题下方的详细说明，长文字会自动换行 */
  description?: ReactNode;
  /** 圆形背景内的 18px 图标，默认空文件夹；仅替换图标，传 null 隐藏图标区域 */
  icon?: ReactNode;
  /** 底部操作区域，传入任意数量的 Button，横排显示，空间不足时换行 */
  actions?: ReactNode;
}

function EmptyFolderIcon() {
  return (
    <svg viewBox="0 0 40 40" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d="M3.5 30V11.5A5.5 5.5 0 0 1 9 6h4.5l4 4H27a6 6 0 0 1 6 6v1" />
      <path d="m3.5 30 6.2-10.8a4.5 4.5 0 0 1 3.9-2.2H35a3 3 0 0 1 2.6 4.5l-5.4 9.3a4.5 4.5 0 0 1-3.9 2.2H7a3.5 3.5 0 0 1-3.5-3Z" />
    </svg>
  );
}

export function EmptyState({
  title,
  description,
  icon = <EmptyFolderIcon />,
  actions,
  className = "",
  ...props
}: EmptyStateProps) {
  return (
    <div {...props} className={`studio-empty-state ${className}`.trim()}>
      {Children.toArray(icon).length > 0 && (
        <div className="studio-empty-state__icon" aria-hidden="true">
          <span className="studio-empty-state__icon-glyph">{icon}</span>
        </div>
      )}
      <div className="studio-empty-state__info">
        <div className="studio-empty-state__title">{title}</div>
        {Children.toArray(description).length > 0 && (
          <div className="studio-empty-state__description">{description}</div>
        )}
      </div>
      {Children.toArray(actions).length > 0 && (
        <div className="studio-empty-state__actions">{actions}</div>
      )}
    </div>
  );
}
