import type { HTMLAttributes, ReactNode } from "react";
import nodeGlow from "./assets/node-glow.svg";
import "./BasicNode.css";

export interface BasicNodeProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title?: string;
  icon?: ReactNode;
}

function RequestIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M9 2.06667C8.66667 2.06667 8.33333 2 8 2C7.66667 2 7.33333 2.06667 7 2.06667M12.8666 4.5333C12.469 4.00236 11.9976 3.53094 11.4666 3.1333M13.9333 9C13.9999 8.66667 13.9999 8.33333 13.9999 8C13.9999 7.66667 13.9333 7.33333 13.9333 7M11.4666 12.8666C11.9976 12.469 12.469 11.9976 12.8666 11.4666M7 13.9333C7.33333 13.9999 7.66667 13.9999 8 13.9999C8.33333 13.9999 8.66667 13.9333 9 13.9333M2.33333 11.6667L1.33333 14.6667L4.33333 13.6667M2.06667 7C2.06667 7.33333 2 7.66667 2 8C2 8.33333 2.06667 8.66667 2.06667 9M4.5333 3.1333C4.00236 3.53094 3.53094 4.00236 3.1333 4.5333" stroke="white" strokeOpacity="0.5" strokeWidth="1.33333" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Request node from Figma 740:291164 */
export function BasicNode({ title = "Request", icon = <RequestIcon />, className, ...props }: BasicNodeProps) {
  return (
    <div {...props} className={["studio-basic-node", className].filter(Boolean).join(" ")}>
      <img className="studio-basic-node__glow" src={nodeGlow} alt="" aria-hidden="true" />
      <div className="studio-basic-node__surface">
        <div className="studio-basic-node__row">
          <span className="studio-basic-node__icon" aria-hidden="true">{icon}</span>
          <span className="studio-basic-node__title">{title}</span>
        </div>
      </div>
    </div>
  );
}
