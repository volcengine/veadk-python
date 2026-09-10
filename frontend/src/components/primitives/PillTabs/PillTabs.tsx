import { useId, useRef, type KeyboardEvent } from "react";
import "./PillTabs.css";
import { useTabIndicator } from "../useTabIndicator";

export interface PillTabItem {
  value: string;
  label: string;
  panelId?: string;
}

export interface PillTabsProps {
  items: readonly PillTabItem[];
  value: string;
  onValueChange: (value: string) => void;
  "aria-label": string;
  className?: string;
  id?: string;
}

/** Dark pill tabs from Figma node 849:443534 */
export function PillTabs({ items, value, onValueChange, className, id, "aria-label": label }: PillTabsProps) {
  const generatedId = useId();
  const indicatorRef = useTabIndicator();
  const tabListId = id ?? generatedId;
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const selectedIndex = items.findIndex((item) => item.value === value);

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
    onValueChange(items[nextIndex].value);
    tabRefs.current[nextIndex]?.focus();
  }

  return (
    <div ref={indicatorRef} className={["studio-pill-tabs", className].filter(Boolean).join(" ")} role="tablist" aria-label={label} id={tabListId}>
      {items.map((item, index) => (
        <button
          key={item.value}
          ref={(element) => { tabRefs.current[index] = element; }}
          id={`${tabListId}-tab-${index}`}
          className="studio-pill-tabs__tab"
          type="button"
          role="tab"
          aria-selected={item.value === value}
          aria-controls={item.panelId}
          tabIndex={index === (selectedIndex < 0 ? 0 : selectedIndex) ? 0 : -1}
          onClick={() => onValueChange(item.value)}
          onKeyDown={(event) => handleKeyDown(event, index)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
