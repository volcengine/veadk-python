import { useEffect, useId, useLayoutEffect, useRef, useState, useImperativeHandle, type ComponentProps, type ReactNode, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import downIcon from "./assets/down.svg";
import "./Select.css";

export interface SelectOption { value: string; label: string; icon?: ReactNode; disabled?: boolean }
export type SelectProps = Omit<ComponentProps<"select">, "children" | "value" | "defaultValue" | "multiple" | "size"> & {
  options: readonly SelectOption[];
  value?: string;
  defaultValue?: string;
};

export function Select({ options, value, defaultValue, onChange, className = "", style, disabled, id, ref, tabIndex, "aria-label": ariaLabel, "aria-labelledby": labelledBy, ...props }: SelectProps) {
  const uid = useId();
  const listId = `${uid}-list`;
  const trigger = useRef<HTMLButtonElement>(null);
  const native = useRef<HTMLSelectElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  useImperativeHandle(ref, () => native.current!);
  const [internalValue, setInternalValue] = useState(defaultValue ?? options.find(option => !option.disabled)?.value ?? "");
  const currentValue = value ?? internalValue;
  const selected = options.find(option => option.value === currentValue);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [position, setPosition] = useState({ left: 0, top: 0, width: 0, maxHeight: 240 });
  const search = useRef({ text: "", time: 0 });

  function show() {
    if (disabled) return;
    const index = options.findIndex(option => option.value === currentValue && !option.disabled);
    setActive(index >= 0 ? index : options.findIndex(option => !option.disabled));
    setOpen(true);
  }
  function choose(index: number) {
    const option = options[index];
    if (!option || option.disabled) return;
    if (native.current && currentValue !== option.value) {
      native.current.value = option.value;
      native.current.dispatchEvent(new Event("change", { bubbles: true }));
    }
    setOpen(false);
    trigger.current?.focus();
  }
  function keyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      if (!open) { show(); return; }
      const enabled = options.map((option, index) => option.disabled ? -1 : index).filter(index => index >= 0);
      if (!enabled.length) return;
      const at = enabled.indexOf(active);
      setActive(event.key === "Home" ? enabled[0] : event.key === "End" ? enabled[enabled.length - 1] : enabled[(at + (event.key === "ArrowDown" ? 1 : -1) + enabled.length) % enabled.length]);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (open) choose(active); else show();
    } else if (event.key === "Escape") {
      if (open) event.preventDefault();
      setOpen(false);
    } else if (event.key === "Tab") {
      setOpen(false);
    } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      const now = Date.now();
      search.current = { text: (now - search.current.time < 600 ? search.current.text : "") + event.key.toLowerCase(), time: now };
      const index = options.findIndex(option => !option.disabled && option.label.toLowerCase().startsWith(search.current.text));
      if (index >= 0) { setActive(index); setOpen(true); }
    }
  }
  useLayoutEffect(() => {
    if (!open) return;
    function place() {
      const rect = trigger.current?.getBoundingClientRect();
      if (!rect) return;
      const below = window.innerHeight - rect.bottom - 12;
      const above = rect.top - 12;
      const height = Math.min(240, options.length * 36 + 8);
      const flip = below < height && above > below;
      const maxHeight = Math.max(36, Math.min(240, flip ? above : below));
      setPosition({ left: Math.max(8, Math.min(rect.left, window.innerWidth - rect.width - 8)), top: flip ? rect.top - Math.min(height, maxHeight) - 6 : rect.bottom + 6, width: rect.width, maxHeight });
    }
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => { window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); };
  }, [open, options.length]);
  useEffect(() => {
    if (!open) return;
    function outside(event: PointerEvent) {
      if (event.target instanceof Node && !trigger.current?.contains(event.target) && !menu.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);
  useEffect(() => {
    if (open) menu.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView?.({ block: "nearest" });
  }, [active, open]);

  return <span className={`studio-select ${className}`.trim()} style={style} data-disabled={disabled || undefined}>
    <button ref={trigger} id={id} type="button" role="combobox" className="studio-select__display" disabled={disabled} tabIndex={tabIndex} aria-label={ariaLabel} aria-labelledby={labelledBy} aria-expanded={open} aria-haspopup="listbox" aria-controls={open ? listId : undefined} aria-activedescendant={open && active >= 0 ? `${uid}-option-${active}` : undefined} aria-required={props.required} onClick={() => open ? setOpen(false) : show()} onKeyDown={keyDown}>
      <span className="studio-select__content">
        {selected?.icon && <span className="studio-select__icon" aria-hidden="true">{selected.icon}</span>}
        <span className="studio-select__label">{selected?.label}</span>
      </span>
      <img className="studio-select__arrow" data-open={open} src={downIcon} alt="" />
    </button>
    <select {...props} ref={native} className="studio-select__native" aria-hidden="true" tabIndex={-1} disabled={disabled} value={currentValue} onChange={event => {
      if (value === undefined) setInternalValue(event.target.value);
      onChange?.(event);
    }}>
      {options.map(option => <option key={option.value} value={option.value} disabled={option.disabled}>{option.label}</option>)}
    </select>
    {open && createPortal(<div ref={menu} id={listId} role="listbox" aria-label={ariaLabel ?? "选项"} aria-labelledby={labelledBy} className="studio-select-menu" style={position}>
      {options.map((option, index) => <div key={option.value} id={`${uid}-option-${index}`} role="option" aria-selected={option.value === currentValue} aria-disabled={option.disabled || undefined} data-active={index === active} data-index={index} className="studio-select-menu__option" onPointerMove={() => !option.disabled && setActive(index)} onMouseDown={event => event.preventDefault()} onClick={() => choose(index)}>
        {option.icon && <span className="studio-select__icon" aria-hidden="true">{option.icon}</span>}
        <span className="studio-select__label">{option.label}</span>
        {option.value === currentValue && <svg className="studio-select-menu__check" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="m3 8 3 3 7-7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg>}
      </div>)}
    </div>, document.body)}
  </span>;
}
