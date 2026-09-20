import { useId, useState, type ReactNode, type CSSProperties } from "react";
import { Divider } from "../Divider";
import "./Dropdown.css";

export interface DropdownProps {
  label: ReactNode;
  children?: ReactNode;
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  disabled?: boolean;
  /** 填满父容器，较长标题自动换行 */
  fullWidth?: boolean;
  className?: string;
  style?: CSSProperties;
}

export function Dropdown({ label, children, open, defaultOpen = false, onOpenChange, disabled = false, fullWidth = false, className = "", style }: DropdownProps) {
  const id = useId();
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const expanded = open ?? internalOpen;
  function toggle() {
    if (open === undefined) setInternalOpen(!expanded);
    onOpenChange?.(!expanded);
  }
  return <div className={`studio-dropdown ${className}`} style={style} data-open={expanded} data-full-width={fullWidth || undefined}>
    <button id={`${id}-trigger`} type="button" className="studio-dropdown__trigger" aria-expanded={expanded} aria-controls={`${id}-content`} onClick={toggle} disabled={disabled}>
      <span>{label}</span>
      <svg className="studio-dropdown__arrow" width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
        <path d="M1.33748 4.49581C1.56529 4.26801 1.93463 4.26801 2.16244 4.49581L6.99996 9.33333L11.8375 4.49581C12.0653 4.26801 12.4346 4.26801 12.6624 4.49581C12.8902 4.72362 12.8902 5.09296 12.6624 5.32077L7.82492 10.1583C7.36931 10.6139 6.63061 10.6139 6.175 10.1583L1.33748 5.32077C1.10967 5.09296 1.10967 4.72362 1.33748 4.49581Z" fill="currentColor" />
      </svg>
    </button>
    <div id={`${id}-content`} role="region" aria-labelledby={`${id}-trigger`} aria-hidden={!expanded} inert={!expanded || undefined} className="studio-dropdown__content">
      <div className="studio-dropdown__inner">
        <div className="studio-dropdown__divider">
          <Divider style={{ width: "100%" }} />
        </div>
        {children}
      </div>
    </div>
  </div>;
}
