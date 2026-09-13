import { useId, type HTMLAttributes, type ReactNode } from "react";
import face from "./assets/face.svg";
import merge from "./assets/merge.svg";
import skill from "./assets/skill.svg";
import tool from "./assets/tool.svg";
import blue from "./assets/glow-blue.svg";
import indigo from "./assets/glow-indigo.svg";
import small from "./assets/glow-small.svg";
import pink from "./assets/glow-pink.svg";
import white from "./assets/glow-white.svg";
import defaultGlow from "./assets/glow-default.svg";
import "./AgentNode.css";

export interface AgentNodeProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title: string;
  description: string;
  selected?: boolean;
  icon?: ReactNode;
  iconVariant?: "agent" | "assistant";
  skillCount: number;
  toolCount: number;
}

export function AgentNode({ title, description, selected = false, icon, iconVariant = "assistant", skillCount, toolCount, className = "", ...props }: AgentNodeProps) {
  const titleId = useId();
  return <article {...props} aria-labelledby={titleId} data-selected={selected} className={`studio-agent-node ${className}`.trim()}>
    {selected && <svg className="studio-agent-node__selection-border" viewBox="-1 -1 218 149" fill="none" aria-hidden="true">
      <defs><linearGradient id={`${titleId}-border`} x1="0" y1="0.5" x2="1" y2="0.5" gradientUnits="userSpaceOnUse" gradientTransform="matrix(91.5 147 -216 130.86383857 124.50000643 -65.43192312)">
        <stop stopColor="#9dbcff" />
        <stop offset="0.5" stopColor="#4562a2" />
        <stop offset="1" stopColor="#425172" stopOpacity="0.8" />
      </linearGradient></defs>
      <rect x="-0.5" y="-0.5" width="217" height="148" rx="16.5" stroke={`url(#${titleId}-border)`} strokeOpacity="0.6" />
    </svg>}
    <div className="studio-agent-node__glow" aria-hidden="true">
      {selected ? <><img className="studio-agent-node__glow-blue" src={blue} alt="" /><img className="studio-agent-node__glow-indigo" src={indigo} alt="" /><img className="studio-agent-node__glow-small" src={small} alt="" /><img className="studio-agent-node__glow-pink" src={pink} alt="" /><img className="studio-agent-node__glow-white" src={white} alt="" /></> : <img className="studio-agent-node__glow-default" src={defaultGlow} alt="" />}
    </div>
    <div className="studio-agent-node__surface">
      <div className="studio-agent-node__content">
        <div className="studio-agent-node__heading"><span aria-hidden="true">{icon ?? <img src={iconVariant === "agent" ? face : merge} alt="" />}</span><h3 id={titleId}>{title}</h3></div>
        <div className="studio-agent-node__body">
          <p className="studio-agent-node__description" title={description}>{description}</p>
          <div className="studio-agent-node__counts"><span aria-label={`${skillCount} skills`}><img src={skill} alt="" /><span>{skillCount}</span></span><span aria-label={`${toolCount} tools`}><img src={tool} alt="" /><span>{toolCount}</span></span></div>
        </div>
      </div>
    </div>
  </article>;
}
