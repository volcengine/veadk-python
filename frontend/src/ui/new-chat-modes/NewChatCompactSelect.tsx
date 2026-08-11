import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import "./new-chat-workspace.css";

export interface NewChatCompactSelectOption {
  value: string;
  label: string;
  description?: string;
}

const HOVER_OPEN_DELAY_MS = 120;
const HOVER_CLOSE_DELAY_MS = 180;

interface NewChatCompactSelectProps {
  label: string;
  hideLabel?: boolean;
  value: string;
  options: NewChatCompactSelectOption[];
  onChange: (value: string) => void;
  placeholder: string;
  loading?: boolean;
  error?: string;
  disabled?: boolean;
  searchable?: boolean;
  onRetry?: () => void;
}

function ChevronIcon() {
  return (
    <svg className="new-chat-compact-select__chevron" viewBox="0 0 16 16" aria-hidden="true">
      <path d="m4.75 6.25 3.25 3.5 3.25-3.5" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg className="new-chat-compact-select__check" viewBox="0 0 16 16" aria-hidden="true">
      <path d="m3.25 8.25 3 3 6.5-6.5" />
    </svg>
  );
}

export function NewChatCompactSelect({
  label,
  hideLabel = false,
  value,
  options,
  onChange,
  placeholder,
  loading = false,
  error = "",
  disabled = false,
  searchable = false,
  onRetry,
}: NewChatCompactSelectProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const focusSearchOnOpenRef = useRef(false);
  const hoverOpenTimerRef = useRef<number | null>(null);
  const hoverCloseTimerRef = useRef<number | null>(null);
  const selected = options.find((option) => option.value === value);
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visibleOptions = useMemo(
    () => normalizedQuery
      ? options.filter((option) =>
          `${option.label} ${option.description || ""}`.toLocaleLowerCase().includes(normalizedQuery),
        )
      : options,
    [normalizedQuery, options],
  );

  const closeMenu = useCallback((returnFocus = false) => {
    if (hoverOpenTimerRef.current !== null) {
      window.clearTimeout(hoverOpenTimerRef.current);
      hoverOpenTimerRef.current = null;
    }
    if (hoverCloseTimerRef.current !== null) {
      window.clearTimeout(hoverCloseTimerRef.current);
      hoverCloseTimerRef.current = null;
    }
    focusSearchOnOpenRef.current = false;
    setOpen(false);
    setQuery("");
    if (returnFocus) triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const onOutsideClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) closeMenu();
    };
    document.addEventListener("mousedown", onOutsideClick);
    return () => document.removeEventListener("mousedown", onOutsideClick);
  }, [closeMenu, open]);

  useEffect(() => {
    if (!open || !searchable || !focusSearchOnOpenRef.current) return;
    focusSearchOnOpenRef.current = false;
    requestAnimationFrame(() => searchRef.current?.focus());
  }, [open, searchable]);

  useEffect(() => () => {
    if (hoverOpenTimerRef.current !== null) window.clearTimeout(hoverOpenTimerRef.current);
    if (hoverCloseTimerRef.current !== null) window.clearTimeout(hoverCloseTimerRef.current);
  }, []);

  function openMenu(focusSearch: boolean) {
    if (hoverOpenTimerRef.current !== null) {
      window.clearTimeout(hoverOpenTimerRef.current);
      hoverOpenTimerRef.current = null;
    }
    if (hoverCloseTimerRef.current !== null) {
      window.clearTimeout(hoverCloseTimerRef.current);
      hoverCloseTimerRef.current = null;
    }
    focusSearchOnOpenRef.current = focusSearch;
    setQuery("");
    setActiveIndex(Math.max(0, options.findIndex((option) => option.value === value)));
    setOpen(true);
  }

  function scheduleHoverOpen() {
    if (disabled || open || hoverOpenTimerRef.current !== null) return;
    hoverOpenTimerRef.current = window.setTimeout(() => {
      hoverOpenTimerRef.current = null;
      openMenu(false);
    }, HOVER_OPEN_DELAY_MS);
  }

  function cancelHoverClose() {
    if (hoverCloseTimerRef.current === null) return;
    window.clearTimeout(hoverCloseTimerRef.current);
    hoverCloseTimerRef.current = null;
  }

  function scheduleHoverClose() {
    if (hoverOpenTimerRef.current !== null) {
      window.clearTimeout(hoverOpenTimerRef.current);
      hoverOpenTimerRef.current = null;
    }
    if (!open || hoverCloseTimerRef.current !== null) return;
    hoverCloseTimerRef.current = window.setTimeout(() => {
      hoverCloseTimerRef.current = null;
      closeMenu();
    }, HOVER_CLOSE_DELAY_MS);
  }

  function choose(index: number) {
    const option = visibleOptions[index];
    if (!option) return;
    onChange(option.value);
    closeMenu(true);
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape" && open) {
      event.preventDefault();
      closeMenu(true);
      return;
    }
    if (event.key === "Home" && open && visibleOptions.length > 0) {
      event.preventDefault();
      setActiveIndex(0);
      return;
    }
    if (event.key === "End" && open && visibleOptions.length > 0) {
      event.preventDefault();
      setActiveIndex(visibleOptions.length - 1);
      return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") {
      if (open && event.key === "Enter" && visibleOptions[activeIndex]) {
        event.preventDefault();
        choose(activeIndex);
      }
      return;
    }
    event.preventDefault();
    if (!open) {
      openMenu(true);
      return;
    }
    const delta = event.key === "ArrowDown" ? 1 : -1;
    setActiveIndex((index) =>
      (index + delta + visibleOptions.length) % Math.max(1, visibleOptions.length),
    );
  }

  const showLoading = loading && options.length === 0;
  const displayLabel = showLoading
    ? "加载中…"
    : selected?.label || placeholder;

  return (
    <div
      className="new-chat-compact-select"
      ref={rootRef}
      onKeyDown={onKeyDown}
      onPointerEnter={(event) => {
        if (event.pointerType === "mouse") cancelHoverClose();
      }}
      onPointerLeave={(event) => {
        if (event.pointerType === "mouse") scheduleHoverClose();
      }}
    >
      <button
        ref={triggerRef}
        type="button"
        className="new-chat-compact-select__trigger"
        aria-label={`${label}：${displayLabel}`}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onPointerEnter={(event) => {
          if (event.pointerType === "mouse") scheduleHoverOpen();
        }}
        onClick={() => open ? closeMenu() : openMenu(true)}
      >
        {hideLabel ? null : (
          <span className="new-chat-compact-select__label">{label}</span>
        )}
        {showLoading ? (
          <span className="new-chat-compact-select__spinner" aria-hidden="true" />
        ) : (
          <span className={`new-chat-compact-select__value${selected ? "" : " is-placeholder"}`}>
            {displayLabel}
          </span>
        )}
        {showLoading ? null : <ChevronIcon />}
      </button>

      {open ? (
        <div className="new-chat-compact-select__menu">
          {searchable && options.length > 0 ? (
            <label className="new-chat-compact-select__search">
              <span className="sr-only">搜索{label}</span>
              <input
                ref={searchRef}
                value={query}
                placeholder={`搜索${label}`}
                onChange={(event) => {
                  setQuery(event.currentTarget.value);
                  setActiveIndex(0);
                }}
              />
            </label>
          ) : null}

          <div className="new-chat-compact-select__list" role="listbox" aria-label={label}>
            {loading && options.length === 0 ? (
              <div className="new-chat-compact-select__status" role="status">正在加载…</div>
            ) : error ? (
              <div className="new-chat-compact-select__status is-error" role="alert">
                <span>{error}</span>
                {onRetry ? <button type="button" onClick={onRetry}>重试</button> : null}
              </div>
            ) : visibleOptions.length === 0 ? (
              <div className="new-chat-compact-select__status">{query ? "没有匹配项" : "暂无可选项"}</div>
            ) : visibleOptions.map((option, index) => (
              <button
                key={option.value}
                type="button"
                role="option"
                tabIndex={-1}
                aria-selected={option.value === value}
                className={`new-chat-compact-select__option${index === activeIndex ? " is-active" : ""}`}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => choose(index)}
              >
                <span className="new-chat-compact-select__option-copy">
                  <strong>{option.label}</strong>
                  {option.description ? <small>{option.description}</small> : null}
                </span>
                {option.value === value ? <CheckIcon /> : null}
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
