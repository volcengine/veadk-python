import { useId, useRef, useState, type KeyboardEvent } from "react";
import "./UnderlineTabs.css";
import { useTabIndicator } from "../useTabIndicator";

export type UnderlineTabItem = {
  value: string;
  label: string;
  id?: string;
  panelId?: string;
};

export type UnderlineTabsProps = {
  items: readonly UnderlineTabItem[];
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  "aria-label": string;
  className?: string;
};

export function UnderlineTabs({
  items,
  value,
  defaultValue,
  onValueChange,
  "aria-label": ariaLabel,
  className = "",
}: UnderlineTabsProps) {
  const id = useId();
  const indicatorRef = useTabIndicator();
  const [internalValue, setInternalValue] = useState(defaultValue ?? items[0]?.value);
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const requestedValue = value ?? internalValue;
  const selectedValue = items.some((item) => item.value === requestedValue)
    ? requestedValue
    : items[0]?.value;

  function select(nextValue: string) {
    if (value === undefined) setInternalValue(nextValue);
    onValueChange?.(nextValue);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number;
    switch (event.key) {
      case "ArrowRight": nextIndex = (index + 1) % items.length; break;
      case "ArrowLeft": nextIndex = (index - 1 + items.length) % items.length; break;
      case "Home": nextIndex = 0; break;
      case "End": nextIndex = items.length - 1; break;
      default: return;
    }
    event.preventDefault();
    select(items[nextIndex].value);
    buttons.current[nextIndex]?.focus();
  }

  return (
    <div ref={indicatorRef} role="tablist" aria-label={ariaLabel} className={`studio-underline-tabs ${className}`.trim()}>
      {items.map((item, index) => (
        <button
          key={item.value}
          ref={(element) => { buttons.current[index] = element; }}
          type="button"
          role="tab"
          id={item.id ?? `${id}-${item.value}`}
          aria-controls={item.panelId}
          aria-selected={item.value === selectedValue}
          tabIndex={item.value === selectedValue ? 0 : -1}
          className="studio-underline-tabs__tab"
          onClick={() => select(item.value)}
          onKeyDown={(event) => handleKeyDown(event, index)}
        >
          <span className="studio-underline-tabs__label">{item.label}</span>
        </button>
      ))}
    </div>
  );
}
