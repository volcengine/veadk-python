import { useEffect, useId, useRef, useState } from "react";

export interface SkillConfigOption {
  value: string;
  label: string;
}

interface SkillConfigSelectProps {
  label: string;
  value: string;
  options: SkillConfigOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  allowCustom?: boolean;
  placeholder?: string;
  error?: string;
}

function SelectChevronIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="m7 9 5 5 5-5"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function SkillConfigSelect({
  label,
  value,
  options,
  onChange,
  disabled = false,
  allowCustom = false,
  placeholder = "请选择",
  error,
}: SkillConfigSelectProps) {
  const listboxId = useId();
  const labelId = useId();
  const errorId = useId();
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const selectedIndex = options.findIndex((option) => option.value === value);
  const normalizedQuery = value.trim().toLocaleLowerCase();
  const visibleOptions = allowCustom && normalizedQuery
    ? options.filter((option) => (
      option.value.toLocaleLowerCase().includes(normalizedQuery)
      || option.label.toLocaleLowerCase().includes(normalizedQuery)
    ))
    : options;
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(Math.max(0, selectedIndex));
  const selected = selectedIndex >= 0 ? options[selectedIndex] : undefined;
  const unavailable = disabled || (!allowCustom && options.length === 0);

  const close = (returnFocus = false) => {
    setOpen(false);
    if (returnFocus) {
      window.requestAnimationFrame(() => (
        allowCustom ? inputRef.current?.focus() : triggerRef.current?.focus()
      ));
    }
  };

  const openAt = (index: number) => {
    if (unavailable) return;
    if (visibleOptions.length === 0) return;
    setActiveIndex(Math.min(Math.max(index, 0), visibleOptions.length - 1));
    setOpen(true);
  };

  useEffect(() => {
    if (!open) return;
    const menu = menuRef.current;
    const focusTimer = allowCustom
      ? undefined
      : window.requestAnimationFrame(() => {
        optionRefs.current[activeIndex]?.focus();
      });
    const handleWheel = (event: WheelEvent) => {
      if (!menu) return;
      const atTop = menu.scrollTop <= 0;
      const atBottom = menu.scrollTop + menu.clientHeight >= menu.scrollHeight - 1;
      if (
        menu.scrollHeight <= menu.clientHeight
        || (event.deltaY < 0 && atTop)
        || (event.deltaY > 0 && atBottom)
      ) {
        event.preventDefault();
      }
      event.stopPropagation();
    };
    const handlePointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) {
        close();
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close(true);
    };
    menu?.addEventListener("wheel", handleWheel, { passive: false });
    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      if (focusTimer !== undefined) window.cancelAnimationFrame(focusTimer);
      menu?.removeEventListener("wheel", handleWheel);
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [activeIndex, allowCustom, open]);

  const moveActive = (index: number) => {
    if (visibleOptions.length === 0) return;
    const nextIndex = (index + visibleOptions.length) % visibleOptions.length;
    setActiveIndex(nextIndex);
    optionRefs.current[nextIndex]?.focus();
  };

  return (
    <div
      ref={rootRef}
      className={`skill-config-select${open ? " is-open" : ""}`}
      onBlur={(event) => {
        if (!event.relatedTarget || !rootRef.current?.contains(event.relatedTarget)) close();
      }}
    >
      <span id={labelId} className="skill-config-select__label">{label}</span>
      {allowCustom ? (
        <div className={`skill-config-select__trigger is-editable${disabled ? " is-disabled" : ""}`} aria-expanded={open}>
          <input
            ref={inputRef}
            value={value}
            disabled={disabled}
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={open}
            aria-controls={open ? listboxId : undefined}
            aria-labelledby={labelId}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? errorId : undefined}
            placeholder={placeholder}
            onChange={(event) => {
              onChange(event.target.value);
              setActiveIndex(0);
              if (options.length > 0) setOpen(true);
            }}
            onClick={() => {
              if (!open && visibleOptions.length > 0) openAt(0);
            }}
            onKeyDown={(event) => {
              if (event.nativeEvent.isComposing || event.keyCode === 229) return;
              if (event.key === "ArrowDown") {
                event.preventDefault();
                if (open) optionRefs.current[activeIndex]?.focus();
                else openAt(0);
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                if (open) optionRefs.current[visibleOptions.length - 1]?.focus();
                else openAt(visibleOptions.length - 1);
              } else if (event.key === "Enter" && open) {
                event.preventDefault();
                const option = visibleOptions[activeIndex];
                if (option) onChange(option.value);
                close();
              } else if (event.key === "Escape") {
                event.preventDefault();
                close();
              }
            }}
          />
          <button
            type="button"
            className="skill-config-select__toggle"
            disabled={disabled || options.length === 0}
            aria-label={open ? "收起模型选项" : "展开模型选项"}
            onClick={() => {
              if (open) close();
              else openAt(0);
            }}
          >
            <SelectChevronIcon />
          </button>
        </div>
      ) : (
        <button
          ref={triggerRef}
          type="button"
          className="skill-config-select__trigger"
          disabled={unavailable}
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={open ? listboxId : undefined}
          aria-labelledby={labelId}
          onClick={() => {
            if (open) close();
            else openAt(selectedIndex >= 0 ? selectedIndex : 0);
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              openAt(selectedIndex >= 0 ? selectedIndex : 0);
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              openAt(selectedIndex >= 0 ? selectedIndex : options.length - 1);
            }
          }}
        >
          <span className={selected ? undefined : "is-placeholder"} title={selected?.label}>
            {selected?.label || (options.length === 0 ? "暂无可用选项" : placeholder)}
          </span>
          <SelectChevronIcon />
        </button>
      )}
      {open ? (
        <div
          ref={menuRef}
          id={listboxId}
          className="skill-config-select__menu"
          role="listbox"
          aria-labelledby={labelId}
        >
          {visibleOptions.length === 0 ? (
            <div className="skill-config-select__empty" role="status">
              没有匹配项，可直接使用当前模型 ID
            </div>
          ) : null}
          {visibleOptions.map((option, index) => {
            const isSelected = option.value === value;
            return (
              <button
                key={option.value}
                ref={(node) => { optionRefs.current[index] = node; }}
                type="button"
                role="option"
                aria-selected={isSelected}
                tabIndex={index === activeIndex ? 0 : -1}
                className={`skill-config-select__option${isSelected ? " is-selected" : ""}`}
                title={option.label}
                onFocus={() => setActiveIndex(index)}
                onClick={() => {
                  onChange(option.value);
                  close(true);
                }}
                onKeyDown={(event) => {
                  if (event.key === "ArrowDown") {
                    event.preventDefault();
                    moveActive(index + 1);
                  } else if (event.key === "ArrowUp") {
                    event.preventDefault();
                    moveActive(index - 1);
                  } else if (event.key === "Home") {
                    event.preventDefault();
                    moveActive(0);
                  } else if (event.key === "End") {
                    event.preventDefault();
                    moveActive(options.length - 1);
                  }
                }}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      ) : null}
      {error ? <span id={errorId} className="skill-config-select__error" role="alert">{error}</span> : null}
    </div>
  );
}
