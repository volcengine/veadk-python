import { useCallback, type ReactNode } from "react";
import { Toast as BaseToast } from "@base-ui/react/toast";
import { Toast, type ToastVariant } from "./Toast";
import { ScrollArea } from "../ScrollArea";

export interface ToastOptions {
  /** 唯一标识；重复使用同一 id 会更新现有通知并重置计时 */
  id?: string;
  /** 主标题，可与 description 单独使用 */
  title?: ReactNode;
  /** 标题下方的说明 */
  description?: ReactNode;
  /** 默认为 info */
  variant?: ToastVariant;
  /** 自动关闭时长，单位毫秒；默认继承 Provider，0 表示不自动关闭 */
  duration?: number;
  /** 自定义操作，可通过 useToast().dismiss(id) 关闭通知 */
  action?: ReactNode;
  /** 关闭按钮的无障碍名称 */
  closeLabel?: string;
  /** 手动关闭或自动消失时的回调 */
  onClose?: () => void;
}

interface ToastData {
  variant: ToastVariant;
  action?: ReactNode;
  closeLabel?: string;
}

export interface ToastProviderProps {
  children: ReactNode;
  /** 默认自动关闭时长，单位毫秒；0 表示不自动关闭 */
  duration?: number;
  /** 通知位置，距视口边缘 16px */
  position?: "top-left" | "top-center" | "top-right" | "bottom-left" | "bottom-center" | "bottom-right";
  /** 通知区域的无障碍名称 */
  label?: string;
}

export interface ToastController {
  /** 添加通知并返回 id；传入已有 id 时更新通知 */
  add: (options: ToastOptions) => string;
  /** 关闭指定通知；不传 id 时关闭全部通知 */
  dismiss: (id?: string) => void;
}

/** 在 ToastProvider 内使用；通知不会抢走当前输入焦点 */
export function useToast(): ToastController {
  const { add, close } = BaseToast.useToastManager<ToastData>();
  const addToast = useCallback(({ id, title, description, variant = "info", duration, action, closeLabel, onClose }: ToastOptions) => add({
    id,
    title,
    description,
    timeout: duration,
    priority: "low",
    onClose,
    data: { variant, action, closeLabel },
  }), [add]);

  return { add: addToast, dismiss: close };
}

function ToastViewport({ position, label }: Pick<ToastProviderProps, "position" | "label">) {
  const { toasts, close } = BaseToast.useToastManager<ToastData>();

  return <BaseToast.Portal>
    <BaseToast.Viewport className="studio-toast-viewport" data-position={position} data-empty={toasts.length === 0 || undefined} aria-label={label} render={<ScrollArea contentClassName="studio-toast-viewport__stack" />}>
      {toasts.map(toast => <BaseToast.Root
        key={toast.id}
        toast={toast}
        className="studio-toast-root"
        swipeDirection={[]}
      >
        <Toast
          role="presentation"
          variant={toast.data?.variant}
          title={toast.title != null ? <BaseToast.Title render={<div />}>{toast.title}</BaseToast.Title> : undefined}
          description={toast.description != null ? <BaseToast.Description render={<div />}>{toast.description}</BaseToast.Description> : undefined}
          action={toast.data?.action}
          closeLabel={toast.data?.closeLabel}
          onDismiss={() => close(toast.id)}
        />
      </BaseToast.Root>)}
    </BaseToast.Viewport>
  </BaseToast.Portal>;
}

/** 最多显示三条通知；悬停或键盘聚焦时暂停关闭计时 */
export function ToastProvider({ children, duration = 4000, position = "top-center", label = "通知" }: ToastProviderProps) {
  return <BaseToast.Provider timeout={duration} limit={3}>
    {children}
    <ToastViewport position={position} label={label} />
  </BaseToast.Provider>;
}
