interface AgentFaceIconProps {
  className?: string;
}

/** The friendly Agent face shared by the Sidebar and Agent pickers. */
export function AgentFaceIcon({ className = "icon" }: AgentFaceIconProps) {
  return (
    <svg
      className={`${className} sidebar-agent-face`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="4.25" y="5.25" width="15.5" height="13.5" rx="4.75" />
      <path className="sidebar-agent-face__eye" d="M8.5 10.7v2" />
      <path className="sidebar-agent-face__eye" d="M15.5 10.7v2" />
    </svg>
  );
}
