import type { ComponentProps, ReactNode } from "react";
import resizer from "./assets/resizer.svg";
import "./Textarea.css";

export type TextareaProps = ComponentProps<"textarea"> & {
  counter?: ReactNode;
};

export function Textarea({ className = "", counter, ...props }: TextareaProps) {
  return (
    <div className={`studio-textarea ${className}`.trim()} data-counter={counter != null || undefined}>
      <textarea {...props} className="studio-textarea__input" />
      {counter != null && <span className="studio-textarea__counter">{counter}</span>}
      <img className="studio-textarea__resizer" src={resizer} alt="" aria-hidden="true" />
    </div>
  );
}
