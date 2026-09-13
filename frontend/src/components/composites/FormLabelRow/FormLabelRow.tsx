import type { HTMLAttributes, ReactNode } from "react";
import { FormLabel } from "../../primitives/FormLabel";
import { Button } from "../../primitives/Button";
import plus from "./assets/plus.svg";
import "./FormLabelRow.css";

export interface FormLabelRowProps extends HTMLAttributes<HTMLDivElement> {
  label: ReactNode;
  htmlFor?: string;
  required?: boolean;
  actionLabel?: ReactNode;
  actionIcon?: ReactNode;
  onAction?: () => void;
  actionDisabled?: boolean;
}

export function FormLabelRow({ label, htmlFor, required, actionLabel = "Add", actionIcon, onAction, actionDisabled, className = "", ...props }: FormLabelRowProps) {
  return <div {...props} className={`studio-form-label-row ${className}`.trim()}>
    <FormLabel htmlFor={htmlFor} required={required}>{label}</FormLabel>
    <Button variant="ghost" className="studio-form-label-row__action" startIcon={actionIcon ?? <img src={plus} alt="" />} onClick={onAction} disabled={actionDisabled}>{actionLabel}</Button>
  </div>;
}
