import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ComponentProps, ReactNode } from "react";
import "./Sidebar.css";
import "./SidebarItemWithIcon.css";

export type SidebarItemWithIconProps = Omit<ComponentProps<"button">, "children"> & {
  /** 标题，超出可用宽度时渐隐，悬停后缓慢滚动到末尾 */
  label: string;
  /** 可选的前置图标，与原 Sidebar Item 保持相同尺寸 */
  icon?: ReactNode;
  /** 默认尾部图标或图标按钮组，图标尺寸跟随字号 */
  trailing?: ReactNode;
  /** 悬停或键盘聚焦时替换尾部内容，文字区域随尾部宽度调整 */
  hoverTrailing?: ReactNode;
};

const fadeWidth = 12;
const pixelsPerSecond = 24;

export function SidebarItemWithIcon({
  label,
  icon,
  trailing,
  hoverTrailing,
  className = "",
  style,
  disabled = false,
  type = "button",
  title = label,
  ...buttonProps
}: SidebarItemWithIconProps) {
  const viewportRef = useRef<HTMLSpanElement>(null);
  const trackRef = useRef<HTMLSpanElement>(null);
  const textRef = useRef<HTMLSpanElement>(null);
  const [hovered, setHovered] = useState(false);
  const [keyboardFocused, setKeyboardFocused] = useState(false);
  const [distance, setDistance] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(false);
  const active = !disabled && (hovered || keyboardFocused);
  const tail = active && hoverTrailing !== undefined ? hoverTrailing : trailing;
  const hasTail = tail !== undefined && tail !== null && tail !== false;

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    const text = textRef.current;
    if (!viewport || !text) return;
    let disposed = false;
    const measure = () => {
      if (disposed) return;
      const overflow = text.getBoundingClientRect().width - viewport.getBoundingClientRect().width;
      setDistance(overflow > 0.5 ? Math.ceil(overflow + fadeWidth) : 0);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(viewport);
    observer.observe(text);
    void document.fonts.ready.then(measure);
    document.fonts.addEventListener("loadingdone", measure);
    return () => {
      disposed = true;
      observer.disconnect();
      document.fonts.removeEventListener("loadingdone", measure);
    };
  }, [label, active, tail]);

  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(preference.matches);
    update();
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!active || !distance || reducedMotion || !trackRef.current) return;
    const animation = trackRef.current.animate(
      [{ transform: "translateX(0)" }, { transform: `translateX(-${distance}px)` }],
      { duration: Math.max(1500, distance / pixelsPerSecond * 1000), delay: 350, easing: "linear", fill: "forwards" },
    );
    return () => animation.cancel();
  }, [active, distance, reducedMotion, label]);

  return (
    <div
      className={`studio-sidebar-item studio-sidebar-item-with-icon ${className}`.trim()}
      style={style}
      aria-disabled={disabled || undefined}
      data-active={active || undefined}
      data-overflow={distance > 0 || undefined}
      data-has-trailing={hasTail || undefined}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocusCapture={event => {
        if (event.target.classList.contains("studio-sidebar-item-with-icon__main") && event.target.matches(":focus-visible")) {
          setKeyboardFocused(true);
        }
      }}
      onBlurCapture={event => {
        if (!event.currentTarget.contains(event.relatedTarget)) setKeyboardFocused(false);
      }}
    >
      <button
        {...buttonProps}
        className="studio-sidebar-item-with-icon__main"
        type={type}
        disabled={disabled}
        title={title}
      >
        {icon && <span className="studio-sidebar-item__icon" aria-hidden="true">{icon}</span>}
        <span className="studio-sidebar-item-with-icon__viewport" ref={viewportRef}>
          <span className="studio-sidebar-item-with-icon__track" ref={trackRef}>
            <span className="studio-sidebar-item-with-icon__text" ref={textRef}>{label}</span>
          </span>
        </span>
      </button>
      {hasTail && <span className="studio-sidebar-item-with-icon__tail" inert={disabled || undefined}>{tail}</span>}
    </div>
  );
}
