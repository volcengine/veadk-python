import type { ComponentProps } from "react";
import requiredIcon from "./assets/required.svg";
import "./FormLabel.css";

export type FormLabelProps = ComponentProps<"label"> & {
  /** 显示原设计的 6px 必填星号；控件的原生 required 需单独设置 */
  required?: boolean;
  /** default 为 13px 次级文字；field 为 14px 主文字，支持换行 */
  variant?: "default" | "field";
};

export function FormLabel({ required = false, variant = "default", children, className = "", ...props }: FormLabelProps) {
  return <label {...props} className={`studio-form-label studio-form-label--${variant} ${className}`.trim()}>
    <span>{children}</span>
    {required && <img className="studio-form-label__required" src={requiredIcon} alt="必填" />}
  </label>;
}
