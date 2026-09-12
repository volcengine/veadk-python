import { Dialog } from "@base-ui/react/dialog";
import { useRef, type ReactNode } from "react";
import { ModalLayout, type ModalLayoutProps } from "../../layouts/ModalLayout";
import { Button, type ButtonProps } from "../../primitives/Button";
import { ScrollArea } from "../../primitives/ScrollArea";
import "./ModalButton.css";

export interface ModalButtonProps extends ModalLayoutProps {
  /** 入口按钮的内容 */
  label: ReactNode;
  /** 入口复用 Button 的外观、图标、禁用和原生按钮属性 */
  buttonProps?: Omit<ButtonProps, "children">;
  /** 受控弹窗状态 */
  open?: boolean;
  /** 非受控模式的初始状态 */
  defaultOpen?: boolean;
  /** 点击按钮、关闭按钮、遮罩或按 Escape 时通知状态变化 */
  onOpenChange?: (open: boolean) => void;
  /** 点击确认后自动关闭；异步提交时可关闭此项并通过 open 控制 */
  closeOnConfirm?: boolean;
}

export function ModalButton({
  label,
  buttonProps,
  open,
  defaultOpen = false,
  onOpenChange,
  closeOnConfirm = true,
  title,
  children,
  onClose,
  onCancel,
  onConfirm,
  ...layoutProps
}: ModalButtonProps) {
  const actions = useRef<Dialog.Root.Actions | null>(null);

  return <Dialog.Root open={open} defaultOpen={defaultOpen} onOpenChange={onOpenChange} actionsRef={actions} modal>
    <Dialog.Trigger render={<Button {...buttonProps} />}>{label}</Dialog.Trigger>
    <Dialog.Portal>
      <Dialog.Backdrop className="studio-modal-button__backdrop" />
      <Dialog.Popup
        className="studio-modal-button__popup"
        aria-modal="true"
        render={<ModalLayout
          {...layoutProps}
          title={<Dialog.Title render={<span />}>{title}</Dialog.Title>}
          onClose={() => {
            onClose?.();
            actions.current?.close();
          }}
          onCancel={() => {
            onCancel?.();
            actions.current?.close();
          }}
          onConfirm={() => {
            onConfirm?.();
            if (closeOnConfirm) actions.current?.close();
          }}
        >
          {children != null && <ScrollArea className="studio-modal-button__body">{children}</ScrollArea>}
        </ModalLayout>}
      />
    </Dialog.Portal>
  </Dialog.Root>;
}
