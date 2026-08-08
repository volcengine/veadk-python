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
  valueLabel?: string;
  placeholder: string;
  options: DeploymentSelectOption[];
  disabled?: boolean;
  searchValue?: string;
  searchPlaceholder?: string;
  loading?: boolean;
  hasMore?: boolean;
  emptyMessage?: string;
  onSearchChange?: (value: string) => void;
  onLoadMore?: () => void;
  onChange: (value: string) => void;
}

export function DeploymentSelect({
  ariaLabel,
  value,
  valueLabel,
  placeholder,
  options,
  disabled = false,
  searchValue,
  searchPlaceholder = "搜索资源名称",
  loading = false,
  hasMore = false,
  emptyMessage = "暂无可用选项",
  onSearchChange,
  onLoadMore,
  onChange,
}: DeploymentSelectProps) {
  const listboxId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const optionsRef = useRef<HTMLDivElement>(null);
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const selectedOption = options.find((option) => option.value === value);
  const selectedLabel = selectedOption?.label ?? (value ? valueLabel : undefined);
  const searchable = searchValue !== undefined && Boolean(onSearchChange);

  const closeMenu = () => {
    setOpen(false);
    if (searchable && searchValue) onSearchChange?.("");
  };

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (
        event.target instanceof Node &&
        rootRef.current &&
        !rootRef.current.contains(event.target)
      ) {
        closeMenu();
      }
    };
    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, [open, onSearchChange, searchValue, searchable]);

  useEffect(() => {
    if (!open) return;
    if (searchable) {
      searchInputRef.current?.focus();
      return;
    }
    optionRefs.current[activeIndex]?.focus();
  }, [open, searchable]);

  useEffect(() => {
    if (
      !open ||
      searchable && document.activeElement === searchInputRef.current
    ) {
      return;
    }
    optionRefs.current[activeIndex]?.focus();
  }, [activeIndex, open, searchable]);

  useEffect(() => {
    setActiveIndex((current) => Math.min(current, Math.max(0, options.length - 1)));
  }, [options.length]);

  useEffect(() => {
    if (!open || !hasMore || loading || !onLoadMore) return;
    const frame = window.requestAnimationFrame(() => {
      const node = optionsRef.current;
      if (node && node.scrollHeight <= node.clientHeight + 1) onLoadMore();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [hasMore, loading, onLoadMore, open, options.length]);

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
    closeMenu();
    triggerRef.current?.focus();
  };

  return (
    <div
      className="pp-deployment-select"
      ref={rootRef}
      onKeyDown={(event) => {
        const inSearch = event.target === searchInputRef.current;
        if (event.key === "Escape" && open) {
          event.preventDefault();
          closeMenu();
          triggerRef.current?.focus();
          return;
        }
        if (event.key === "Tab") {
          closeMenu();
          return;
        }
        if (inSearch) {
          if (event.key === "ArrowDown" && options.length > 0) {
            event.preventDefault();
            setActiveIndex(0);
            optionRefs.current[0]?.focus();
          }
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
        disabled={disabled}
        onClick={() => {
          if (open) closeMenu();
          else openMenu();
        }}
      >
        <span className={!selectedLabel ? "is-placeholder" : undefined}>
          {selectedLabel ?? placeholder}
        </span>
        <SelectChevronIcon
          className={`pp-deployment-select-chevron${open ? " is-open" : ""}`}
        />
      </button>
      {open && (
        <div
          className="pp-deployment-select-menu"
        >
          {searchable && (
            <div className="pp-deployment-select-search">
              <input
                ref={searchInputRef}
                type="search"
                value={searchValue}
                aria-label={`搜索${ariaLabel}`}
                placeholder={searchPlaceholder}
                autoComplete="off"
                onChange={(event) => onSearchChange?.(event.currentTarget.value)}
              />
            </div>
          )}
          <div
            id={listboxId}
            ref={optionsRef}
            className="pp-deployment-select-options"
            role="listbox"
            aria-label={ariaLabel}
            aria-busy={loading || undefined}
            onScroll={(event) => {
              if (!hasMore || loading || !onLoadMore) return;
              const node = event.currentTarget;
              const remaining = node.scrollHeight - node.scrollTop - node.clientHeight;
              if (remaining <= 24) onLoadMore();
            }}
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
          {loading && (
            <div className="pp-deployment-select-state" aria-live="polite">
              正在加载更多资源…
            </div>
          )}
          {!loading && options.length === 0 && (
            <div className="pp-deployment-select-state">{emptyMessage}</div>
          )}
        </div>
      )}
    </div>
  );
}
