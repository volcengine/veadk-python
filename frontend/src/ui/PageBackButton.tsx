import type { MouseEventHandler } from "react";
import "./PageBackButton.css";

export interface PageBackButtonProps {
  label: string;
  onClick: MouseEventHandler<HTMLButtonElement>;
}

export function PageBackButton({ label, onClick }: PageBackButtonProps) {
  return (
    <button
      type="button"
      className="page-back-button"
      aria-label={label}
      title={label}
      onClick={onClick}
    >
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="m14.5 6-6 6 6 6" />
      </svg>
    </button>
  );
}
