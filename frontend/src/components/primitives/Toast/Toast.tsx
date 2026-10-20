import type { ComponentProps, ReactNode } from "react";
import { Button } from "../Button";
import { ToastCloseIcon, ToastStatusIcon } from "./ToastIcons";
import "./Toast.css";

export type ToastVariant = "info" | "success" | "warning" | "error";

export type ToastProps = Omit<ComponentProps<"div">, "title" | "children"> & {
  /** 状态通过图标与颜色区分，面板保持中性背景 */
  variant?: ToastVariant;
  /** 主标题，可与 description 单独使用 */
  title?: ReactNode;
  /** 标题下方的说明 */
  description?: ReactNode;
  /** 操作内容，支持 Button、链接等 React 内容 */
  action?: ReactNode;
  /** 提供后显示关闭按钮，移除由调用方处理 */
  onDismiss?: () => void;
  /** 关闭按钮的无障碍名称 */
  closeLabel?: string;
};

/** Toast 的展示层；自动消失与堆叠使用 ToastProvider 和 useToast */
export function Toast({
  variant = "info",
  title,
  description,
  action,
  onDismiss,
  closeLabel = "关闭通知",
  className = "",
  role = "status",
  ...props
}: ToastProps) {
  return <div {...props} role={role} className={`studio-toast ${className}`.trim()} data-variant={variant}>
    <ToastStatusIcon variant={variant} className="studio-toast__status" />
    <div className="studio-toast__content">
      {title != null && <div className="studio-toast__title">{title}</div>}
      {description != null && <div className="studio-toast__description">{description}</div>}
      {action != null && <div className="studio-toast__action">{action}</div>}
    </div>
    {onDismiss && <Button
      variant="ghost"
      iconOnly
      startIcon={<ToastCloseIcon />}
      aria-label={closeLabel}
      onClick={onDismiss}
      className="studio-toast__close"
    />}
  </div>;
}
