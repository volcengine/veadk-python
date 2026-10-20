import { useState, type ComponentProps, type ReactNode } from "react";
import check from "./assets/check.svg";
import add from "./assets/add.svg";
import "./PillTag.css";

export type PillTagProps = Omit<ComponentProps<"button">, "aria-pressed"> & {
  icon?: ReactNode;
  selected?: boolean;
  defaultSelected?: boolean;
  onSelectedChange?: (selected: boolean) => void;
};

export function PillTag({ icon, selected, defaultSelected = false, onSelectedChange, onClick, children, className = "", type = "button", ...props }: PillTagProps) {
  const [internalSelected, setInternalSelected] = useState(defaultSelected);
  const active = selected ?? internalSelected;
  return <button {...props} type={type} aria-pressed={active} className={`studio-pill-tag ${className}`.trim()} onClick={event => {
    onClick?.(event);
    if (event.defaultPrevented) return;
    if (selected === undefined) setInternalSelected(!active);
    onSelectedChange?.(!active);
  }}>
    <svg className="studio-pill-tag__border" aria-hidden="true"><rect x=".25" y=".25" rx="17.75" /></svg>
    {icon && <span className="studio-pill-tag__icon" aria-hidden="true">{icon}</span>}
    <span className="studio-pill-tag__label">{children}</span>
    <span className="studio-pill-tag__state" aria-hidden="true"><img src={active ? check : add} alt="" /></span>
  </button>;
}
