import type { HTMLAttributes, MouseEventHandler } from "react";
import "./DashedZone.css";

export interface DashedZoneProps extends HTMLAttributes<HTMLDivElement> {
  label?: string;
  onAdd?: MouseEventHandler<HTMLButtonElement>;
}

/** Figma node 849:443867, including its original 2px / 2px dashed stroke */
export function DashedZone({ label = "Add", onAdd, className, ...props }: DashedZoneProps) {
  return (
    <div {...props} className={["studio-dashed-zone", className].filter(Boolean).join(" ")}>
      <svg className="studio-dashed-zone__border" aria-hidden="true" width="100%" height="100%">
        <rect x="0.5" y="0.5" rx="11.5" ry="11.5" />
      </svg>
      <button className="studio-dashed-zone__button" type="button" onClick={onAdd}>
        <svg className="studio-dashed-zone__icon" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path d="M7.5 13.3333V8.5H2.66667C2.39052 8.5 2.16667 8.27614 2.16667 8C2.16667 7.72386 2.39052 7.5 2.66667 7.5H7.5V2.66667C7.5 2.39052 7.72386 2.16667 8 2.16667C8.27614 2.16667 8.5 2.39052 8.5 2.66667V7.5H13.3333C13.6095 7.5 13.8333 7.72386 13.8333 8C13.8333 8.27614 13.6095 8.5 13.3333 8.5H8.5V13.3333C8.5 13.6095 8.27614 13.8333 8 13.8333C7.72386 13.8333 7.5 13.6095 7.5 13.3333Z" fill="currentColor" />
        </svg>
        <span>{label}</span>
      </button>
    </div>
  );
}
