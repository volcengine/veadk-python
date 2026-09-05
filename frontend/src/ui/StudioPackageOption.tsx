import type { ReactNode } from "react";
import { Minus, PlusSm12px } from "@openai/apps-sdk-ui/components/Icon";
import "./StudioPackageOption.css";

export interface StudioPackageOptionProps {
  name: string;
  description?: string;
  icon: ReactNode;
  selected: boolean;
  disabled?: boolean;
  onChange: (selected: boolean) => void;
  className?: string;
}

export function StudioPackageOption({
  name,
  description,
  icon,
  selected,
  disabled = false,
  onChange,
  className = "",
}: StudioPackageOptionProps) {
  return (
    <button
      type="button"
      className={`studio-package-option${selected ? " is-selected" : ""}${className ? ` ${className}` : ""}`}
      aria-pressed={selected}
      disabled={disabled}
      onClick={() => onChange(!selected)}
    >
      <span className="studio-package-option__icon" aria-hidden="true">
        {icon}
      </span>
      <span className="studio-package-option__content">
        <strong>{name}</strong>
        {description ? <span>{description}</span> : null}
      </span>
      <span
        className="studio-package-option__action"
        aria-hidden="true"
      >
        {selected ? <Minus /> : <PlusSm12px />}
      </span>
    </button>
  );
}
