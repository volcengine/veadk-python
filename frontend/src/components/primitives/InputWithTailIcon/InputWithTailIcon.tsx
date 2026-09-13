import type { ComponentProps, ReactNode } from "react";
import "./InputWithTailIcon.css";

export type InputWithTailIconProps = ComponentProps<"input"> & {
  tailIcon?: ReactNode;
  tailIconLabel?: string;
  onTailIconClick?: () => void;
};

function CopyIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M10.3333 6.5C10.3333 6.03976 9.96025 5.66667 9.5 5.66667H3.83333C3.3731 5.66667 3 6.03976 3 6.5V12.1667C3 12.6269 3.37309 13 3.83333 13H9.5C9.96026 13 10.3333 12.6269 10.3333 12.1667V6.5ZM11.3333 10.3398H12.1667C12.6269 10.3398 13 9.96677 13 9.50651V3.83333C13 3.37309 12.6269 3 12.1667 3H6.5C6.03976 3 5.66667 3.3731 5.66667 3.83333V4.66667H9.5C10.5125 4.66667 11.3333 5.48748 11.3333 6.5V10.3398ZM14 9.50651C14 10.5191 13.1792 11.3398 12.1667 11.3398H11.3333V12.1667C11.3333 13.1792 10.5125 14 9.5 14H3.83333C2.82082 14 2 13.1792 2 12.1667V6.5C2 5.48748 2.82081 4.66667 3.83333 4.66667H4.66667V3.83333C4.66667 2.82081 5.48748 2 6.5 2H12.1667C13.1792 2 14 2.82082 14 3.83333V9.50651Z" fill="currentColor" />
    </svg>
  );
}

export function InputWithTailIcon({
  className = "",
  tailIcon = <CopyIcon />,
  tailIconLabel = "Copy",
  onTailIconClick,
  disabled,
  ...props
}: InputWithTailIconProps) {
  return (
    <div className={`studio-input-with-tail-icon ${className}`.trim()}>
      <input {...props} disabled={disabled} className="studio-input-with-tail-icon__input" />
      {onTailIconClick ? (
        <button
          className="studio-input-with-tail-icon__icon"
          type="button"
          aria-label={tailIconLabel}
          disabled={disabled}
          onClick={onTailIconClick}
        >
          {tailIcon}
        </button>
      ) : (
        <span className="studio-input-with-tail-icon__icon" aria-hidden="true">{tailIcon}</span>
      )}
    </div>
  );
}
