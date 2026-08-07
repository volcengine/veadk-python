import {
  useEffect,
  useId,
  useRef,
  useState,
  type SVGProps,
} from "react";

function SelectChevronIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="m7 9.5 5 5 5-5" />
    </svg>
  );
}

function SelectCheckIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="m6.5 12.5 3.5 3.5 7.5-8" />
    </svg>
  );
}

export interface DeploymentSelectOption {
  value: string;
  label: string;
  description?: string;
  badge?: string;
}

interface DeploymentSelectProps {
  ariaLabel: string;
  value: string;
  placeholder: string;
  options: DeploymentSelectOption[];
  disabled?: boolean;
  onChange: (value: string) => void;
}

export function DeploymentSelect({
  ariaLabel,
  value,
  placeholder,
  options,
  disabled = false,
  onChange,
}: DeploymentSelectProps) {
  const listboxId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const selectedOption = options.find((option) => option.value === value);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (
        event.target instanceof Node &&
        rootRef.current &&
        !rootRef.current.contains(event.target)
      ) {
        setOpen(false);
      }
    };
    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    optionRefs.current[activeIndex]?.focus();
  }, [activeIndex, open]);

  const openMenu = (direction: 1 | -1 = 1) => {
    const selectedIndex = options.findIndex((option) => option.value === value);
    const nextIndex =
      selectedIndex >= 0
        ? selectedIndex
        : direction === 1
          ? 0
          : Math.max(0, options.length - 1);
    setActiveIndex(nextIndex);
    setOpen(true);
  };

  const moveActiveOption = (nextIndex: number) => {
    if (options.length === 0) return;
    setActiveIndex((nextIndex + options.length) % options.length);
  };

  const selectOption = (option: DeploymentSelectOption) => {
    onChange(option.value);
    setOpen(false);
    triggerRef.current?.focus();
  };

  return (
    <div
      className="pp-deployment-select"
      ref={rootRef}
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.preventDefault();
          setOpen(false);
          triggerRef.current?.focus();
          return;
        }
        if (event.key === "Tab") {
          setOpen(false);
          return;
        }
        if (event.key === "ArrowDown") {
          event.preventDefault();
          if (!open) openMenu(1);
          else moveActiveOption(activeIndex + 1);
        } else if (event.key === "ArrowUp") {
          event.preventDefault();
          if (!open) openMenu(-1);
          else moveActiveOption(activeIndex - 1);
        } else if (open && event.key === "Home") {
          event.preventDefault();
          setActiveIndex(0);
        } else if (open && event.key === "End") {
          event.preventDefault();
          setActiveIndex(Math.max(0, options.length - 1));
        }
      }}
    >
      <button
        ref={triggerRef}
        type="button"
        className="pp-deployment-select-trigger"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        disabled={disabled || options.length === 0}
        onClick={() => {
          if (open) setOpen(false);
          else openMenu();
        }}
      >
        <span className={!selectedOption ? "is-placeholder" : undefined}>
          {selectedOption?.label ?? placeholder}
        </span>
        <SelectChevronIcon
          className={`pp-deployment-select-chevron${open ? " is-open" : ""}`}
        />
      </button>
      {open && (
        <div
          id={listboxId}
          className="pp-deployment-select-menu"
          role="listbox"
          aria-label={ariaLabel}
        >
          {options.map((option, index) => {
            const selected = option.value === value;
            return (
              <button
                key={option.value}
                ref={(node) => {
                  optionRefs.current[index] = node;
                }}
                type="button"
                role="option"
                aria-selected={selected}
                tabIndex={index === activeIndex ? 0 : -1}
                className={`pp-deployment-select-option${selected ? " is-selected" : ""}`}
                title={option.description}
                onFocus={() => setActiveIndex(index)}
                onClick={() => selectOption(option)}
              >
                <span className="pp-deployment-select-copy">
                  <span className="pp-deployment-select-name">
                    {option.label}
                    {option.badge && (
                      <span className="pp-deployment-select-badge">
                        {option.badge}
                      </span>
                    )}
                  </span>
                  {option.description && <small>{option.description}</small>}
                </span>
                {selected && <SelectCheckIcon />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
