import type { ComponentProps, CSSProperties, ReactNode } from "react";
import resizer from "./assets/resizer.svg";
import "./Textarea.css";

export type TextareaProps = ComponentProps<"textarea"> & {
  counter?: ReactNode;
  /** 拖动调整大小时的最大高度，数字单位为 px，建议不小于初始高度 80px */
  maxHeight?: CSSProperties["maxHeight"];
};

export function Textarea({ className = "", counter, maxHeight, ...props }: TextareaProps) {
  return (
    <div className={`studio-textarea ${className}`.trim()} data-counter={counter != null || undefined} style={{ maxHeight }}>
      <textarea {...props} className="studio-textarea__input" />
      {counter != null && <span className="studio-textarea__counter">{counter}</span>}
      <img className="studio-textarea__resizer" src={resizer} alt="" aria-hidden="true" />
    </div>
  );
}
