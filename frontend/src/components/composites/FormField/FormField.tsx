import type { ComponentProps, ReactNode } from "react";
import { FormLabel } from "../../primitives/FormLabel";
import "./FormField.css";

export type FormFieldProps = ComponentProps<"div"> & {
  label: ReactNode;
  htmlFor: string;
  required?: boolean;
};

export function FormField({ label, htmlFor, required = false, children, className = "", ...props }: FormFieldProps) {
  return (
    <div {...props} className={`studio-form-field ${className}`.trim()}>
      {required ? <FormLabel htmlFor={htmlFor} required>{label}</FormLabel> : <label className="studio-form-field__label" htmlFor={htmlFor}>{label}</label>}
      {children}
    </div>
  );
}
