import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type SVGProps,
} from "react";
import "./StudioActionMenu.css";

export interface StudioActionMenuItem {
  label: string;
  onSelect: () => void;
  disabled?: boolean;
  danger?: boolean;
  title?: string;
}

interface StudioActionMenuProps {
  label: string;
  menuLabel: string;
  items: readonly StudioActionMenuItem[];
  className?: string;
  placement?: "top-end" | "bottom-end";
}

function MoreIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" {...props}>
      <circle cx="5.5" cy="12" r="1.4" />
      <circle cx="12" cy="12" r="1.4" />
      <circle cx="18.5" cy="12" r="1.4" />
    </svg>
  );
}

export function StudioActionMenu({
  label,
  menuLabel,
  items,
  className = "",
  placement = "bottom-end",
}: StudioActionMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    if (!open) return;
    const closeOnPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setOpen(false);
      triggerRef.current?.focus();
    };
    window.addEventListener("pointerdown", closeOnPointerDown);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("pointerdown", closeOnPointerDown);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    itemRefs.current.find((item) => item && !item.disabled)?.focus();
  }, [open]);

  const moveFocus = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (!open || !["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      return;
    }
    event.preventDefault();
    const enabled = itemRefs.current.filter(
      (item): item is HTMLButtonElement => Boolean(item && !item.disabled),
    );
    if (enabled.length === 0) return;
    const currentIndex = enabled.indexOf(document.activeElement as HTMLButtonElement);
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? enabled.length - 1
        : (currentIndex + (event.key === "ArrowDown" ? 1 : -1) + enabled.length)
          % enabled.length;
    enabled[nextIndex]?.focus();
  };

  return (
    <div className="studio-action-menu" ref={rootRef} onKeyDown={moveFocus}>
      <button
        ref={triggerRef}
        type="button"
        className={`studio-action-menu__trigger ${className}`.trim()}
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={items.length === 0}
        onClick={() => setOpen((current) => !current)}
      >
        <MoreIcon />
      </button>
      {open ? (
        <div
          className={`studio-action-menu__popover studio-action-menu__popover--${placement}`}
          role="menu"
          aria-label={menuLabel}
        >
          {items.map((item, index) => (
            <button
              key={item.label}
              ref={(element) => {
                itemRefs.current[index] = element;
              }}
              type="button"
              role="menuitem"
              className={`studio-action-menu__item${item.danger ? " is-danger" : ""}`}
              disabled={item.disabled}
              title={item.title}
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
