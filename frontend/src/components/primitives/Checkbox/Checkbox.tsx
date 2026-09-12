import type { ComponentProps, ReactNode } from "react";
import "./Checkbox.css";

export type CheckboxProps = Omit<ComponentProps<"input">, "type" | "children"> & {
  label: ReactNode;
};

export function Checkbox({ label, className = "", ...props }: CheckboxProps) {
  return (
    <label className={`studio-checkbox ${className}`.trim()}>
      <span className="studio-checkbox__control">
        <input {...props} className="studio-checkbox__input" type="checkbox" />
        <span className="studio-checkbox__box" aria-hidden="true">
          <svg className="studio-checkbox__checkmark" viewBox="0 0 16 16" fill="none">
            <path d="M4.5 8.45L6.88 11L11.5 5" stroke="white" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </span>
      <span className="studio-checkbox__label">{label}</span>
    </label>
  );
}
