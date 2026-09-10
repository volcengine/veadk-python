import type { ComponentProps, ReactNode } from "react";
import "./Switch.css";

export type SwitchProps = Omit<ComponentProps<"input">, "type" | "children" | "role"> & {
  label: ReactNode;
  className?: string;
};

export function Switch({ label, className = "", ...props }: SwitchProps) {
  return (
    <label className={`studio-switch ${className}`.trim()}>
      <span className="studio-switch__label">{label}</span>
      <span className="studio-switch__control">
        <input {...props} className="studio-switch__input" type="checkbox" role="switch" />
        <span className="studio-switch__track" aria-hidden="true"><span className="studio-switch__thumb" /></span>
      </span>
    </label>
  );
}
