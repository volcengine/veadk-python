import { Dialog as BaseDialog } from "@base-ui/react/dialog";
import type { ComponentPropsWithoutRef, CSSProperties, ReactElement, ReactNode } from "react";
import { Button } from "../../primitives/Button";
import { ScrollArea } from "../../primitives/ScrollArea";
import "./Drawer.css";

export type DrawerProps = Omit<ComponentPropsWithoutRef<"div">, "title"> & {
  /** 受控打开状态 */
  open?: boolean;
  /** 非受控初始打开状态 */
  defaultOpen?: boolean;
  /** 打开或关闭时调用，包括入口点击、Esc、遮罩和关闭按钮 */
  onOpenChange?: (open: boolean) => void;
  /** 可选入口，使用 Button 等可接收 ref 的按钮元素 */
  trigger?: ReactElement;
  /** 面板标题，未提供时可通过 aria-label 设置无障碍名称 */
  title?: ReactNode;
  /** 标题下方的说明 */
  description?: ReactNode;
  /** 底部操作区，支持 Button 或任意 React 内容 */
  footer?: ReactNode;
  /** 面板宽度，数字单位为 px；窄屏自动限制在屏幕宽度减 32px 内 */
  width?: CSSProperties["width"];
  /** glass 为半透明毛玻璃，solid 为实色背景 */
  surface?: "glass" | "solid";
  /** 关闭按钮的无障碍名称 */
  closeLabel?: string;
};

function DrawerCloseIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" aria-hidden="true">
      <path d="m6.5 6.5 11 11m0-11-11 11" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  );
}

export function Drawer({
  open,
  defaultOpen = false,
  onOpenChange,
  trigger,
  title,
  description,
  children,
  footer,
  width = 480,
  surface = "glass",
  closeLabel = "关闭",
  className = "",
  style,
  ...props
}: DrawerProps) {
  const hasTitle = title != null;

  return (
    <BaseDialog.Root open={open} defaultOpen={defaultOpen} onOpenChange={onOpenChange} modal>
      {trigger && <BaseDialog.Trigger render={trigger} />}
      <BaseDialog.Portal>
        <BaseDialog.Backdrop className="studio-drawer__backdrop" data-surface={surface} />
        <div className="studio-drawer__viewport">
          <BaseDialog.Popup
            {...props}
            className={`studio-drawer ${className}`.trim()}
            data-surface={surface}
            style={{ width, ...style }}
            aria-label={props["aria-label"] ?? (hasTitle ? undefined : "侧边面板")}
          >
            <header className="studio-drawer__header">
              <div className="studio-drawer__heading">
                {hasTitle && <BaseDialog.Title className="studio-drawer__title" render={<div />}>{title}</BaseDialog.Title>}
                {description != null && <BaseDialog.Description className="studio-drawer__description" render={<div />}>{description}</BaseDialog.Description>}
              </div>
              <BaseDialog.Close render={<Button variant="ghost" iconOnly className="studio-drawer__close" aria-label={closeLabel} startIcon={<DrawerCloseIcon />} />} />
            </header>
            <ScrollArea className="studio-drawer__body" contentClassName="studio-drawer__body-content" tabIndex={0} aria-label="面板内容">
              {children}
            </ScrollArea>
            {footer != null && <footer className="studio-drawer__footer">{footer}</footer>}
          </BaseDialog.Popup>
        </div>
      </BaseDialog.Portal>
    </BaseDialog.Root>
  );
}
