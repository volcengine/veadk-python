import { useId, useRef, type KeyboardEvent } from "react";
import type { PillTabsProps } from "../PillTabs";
import { useTabIndicator } from "../useTabIndicator";
import "./GlassTabs.css";

export type GlassTabsProps = PillTabsProps;

export function GlassTabs({ items, value, onValueChange, className = "", id, "aria-label": label }: GlassTabsProps) {
  const generatedId = useId();
  const tabListId = id ?? generatedId;
  const indicatorRef = useTabIndicator();
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const selectedIndex = items.findIndex(item => item.value === value);

  function navigate(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next: number;
    switch (event.key) {
      case "ArrowRight": next = (index + 1) % items.length; break;
      case "ArrowLeft": next = (index - 1 + items.length) % items.length; break;
      case "Home": next = 0; break;
      case "End": next = items.length - 1; break;
      default: return;
    }
    event.preventDefault();
    onValueChange(items[next].value);
    tabRefs.current[next]?.focus();
  }

  return <div ref={indicatorRef} className={`studio-glass-tabs ${className}`} role="tablist" aria-label={label} id={tabListId}>
    {items.map((item, index) => <button
      key={item.value}
      ref={element => { tabRefs.current[index] = element; }}
      id={`${tabListId}-tab-${index}`}
      type="button"
      role="tab"
      className="studio-glass-tabs__tab"
      aria-selected={value === item.value}
      aria-controls={item.panelId}
      tabIndex={index === (selectedIndex < 0 ? 0 : selectedIndex) ? 0 : -1}
      onClick={() => onValueChange(item.value)}
      onKeyDown={event => navigate(event, index)}
    ><span>{item.label}</span></button>)}
  </div>;
}
