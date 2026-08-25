import type { ReactNode } from "react";
import { Button } from "@openai/apps-sdk-ui/components/Button";
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
    <div
      className={`studio-package-option${selected ? " is-selected" : ""}${className ? ` ${className}` : ""}`}
    >
      <span className="studio-package-option__icon" aria-hidden="true">
        {icon}
      </span>
      <span className="studio-package-option__content">
        <strong>{name}</strong>
        {description ? <span>{description}</span> : null}
      </span>
      <Button
        type="button"
        className="studio-package-option__action"
        color="secondary"
        variant="ghost"
        size="sm"
        iconSize="sm"
        uniform
        aria-label={selected ? `移除 ${name}` : `安装 ${name}`}
        aria-pressed={selected}
        disabled={disabled}
        onClick={() => onChange(!selected)}
      >
        {selected ? <Minus /> : <PlusSm12px />}
      </Button>
    </div>
  );
}
