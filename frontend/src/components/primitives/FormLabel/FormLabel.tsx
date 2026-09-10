import type { ComponentProps } from "react";
import requiredIcon from "./assets/required.svg";
import "./FormLabel.css";

export type FormLabelProps = ComponentProps<"label"> & { required?: boolean };

export function FormLabel({ required = false, children, className = "", ...props }: FormLabelProps) {
  return <label {...props} className={`studio-form-label ${className}`.trim()}>
    <span>{children}</span>
    {required && <img className="studio-form-label__required" src={requiredIcon} alt="必填" />}
  </label>;
}
