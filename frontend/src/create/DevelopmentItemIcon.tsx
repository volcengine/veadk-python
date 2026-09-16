import type { SVGProps } from "react";
import { AgentKitLogoIcon } from "../ui/icons/AgentKitLogoIcon";

/** Native development items share the same 18px, repository-drawn icon geometry. */
export function DevelopmentItemIcon({kind, ...props}: SVGProps<SVGSVGElement> & {kind: "tool" | "plan" | "diff" | "thinking"}) {
  if (kind === "thinking") return <AgentKitLogoIcon {...props} />;
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
    {kind === "tool" ? <><rect x="3" y="4" width="18" height="16" rx="3" /><path d="m7 9 3 3-3 3m6 0h4" /></>
      : kind === "plan" ? <><path d="m4 7 1.5 1.5L8 6m-4 7 1.5 1.5L8 12M11 7h9m-9 6h9m-9 6h9" /><circle cx="6" cy="19" r="1" /></>
      : <><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8m-4-3v6M8 18h8" /></>}
  </svg>;
}
