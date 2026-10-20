import type { HTMLAttributes, ReactNode } from "react";
import { FormLabel } from "../../primitives/FormLabel";
import { Button } from "../../primitives/Button";
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

function AddIcon() {
  return <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M7.5 13.3333V8.5H2.66667C2.39052 8.5 2.16667 8.27614 2.16667 8C2.16667 7.72386 2.39052 7.5 2.66667 7.5H7.5V2.66667C7.5 2.39052 7.72386 2.16667 8 2.16667C8.27614 2.16667 8.5 2.39052 8.5 2.66667V7.5H13.3333C13.6095 7.5 13.8333 7.72386 13.8333 8C13.8333 8.27614 13.6095 8.5 13.3333 8.5H8.5V13.3333C8.5 13.6095 8.27614 13.8333 8 13.8333C7.72386 13.8333 7.5 13.6095 7.5 13.3333Z" fill="currentColor" />
  </svg>;
}

export function FormLabelRow({ label, htmlFor, required, actionLabel = "Add", actionIcon, onAction, actionDisabled, className = "", ...props }: FormLabelRowProps) {
  return <div {...props} className={`studio-form-label-row ${className}`.trim()}>
    <FormLabel htmlFor={htmlFor} required={required}>{label}</FormLabel>
    <Button variant="ghost" className="studio-form-label-row__action" startIcon={actionIcon ?? <AddIcon />} onClick={onAction} disabled={actionDisabled}>{actionLabel}</Button>
  </div>;
}
