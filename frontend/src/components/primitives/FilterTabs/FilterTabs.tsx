import { useRef, type KeyboardEvent } from "react";
import "./FilterTabs.css";

export type FilterTabOption = { value: string; label: string };
export type FilterTabsProps = {
  options: readonly FilterTabOption[];
  value: string;
  onValueChange: (value: string) => void;
  "aria-label": string;
  className?: string;
};

export function FilterTabs({ options, value, onValueChange, className = "", "aria-label": label }: FilterTabsProps) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const selected = Math.max(0, options.findIndex((option) => option.value === value));
  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next: number;
    switch (event.key) {
      case "ArrowLeft": next = (index - 1 + options.length) % options.length; break;
      case "ArrowRight": next = (index + 1) % options.length; break;
      case "Home": next = 0; break;
      case "End": next = options.length - 1; break;
      default: return;
    }
    event.preventDefault();
    onValueChange(options[next].value);
    refs.current[next]?.focus();
  }
  return (
    <div className={`studio-filter-tabs ${className}`.trim()} role="radiogroup" aria-label={label}>
      {options.map((option, index) => (
        <button key={option.value} ref={(element) => { refs.current[index] = element; }}
          type="button" role="radio" aria-checked={index === selected} tabIndex={index === selected ? 0 : -1}
          onClick={() => onValueChange(option.value)} onKeyDown={(event) => onKeyDown(event, index)}>
          {option.label}
        </button>
      ))}
    </div>
  );
}
