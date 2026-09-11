import type { ComponentProps, ReactNode } from "react";
import "./Radio.css";

export type RadioProps = Omit<ComponentProps<"input">, "type" | "children"> & {
  /** 可选标签；不显示标签时请设置 aria-label 或 aria-labelledby */
  label?: ReactNode;
};

export function Radio({ label, className = "", ...props }: RadioProps) {
  return (
    <label className={`studio-radio ${className}`.trim()}>
      <span className="studio-radio__control">
        <input {...props} className="studio-radio__input" type="radio" />
        <span className="studio-radio__box" aria-hidden="true">
          <span className="studio-radio__dot" />
        </span>
      </span>
      {label != null && <span className="studio-radio__label">{label}</span>}
    </label>
  );
}
