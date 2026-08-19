interface CapabilityIconProps {
  className?: string;
}

export type CanvasAgentType = "llm" | "sequential" | "parallel" | "loop" | "a2a";

/** Figma `git-merge` mark used in the Agent canvas node identity strip. */
export function AgentFlowCapabilityIcon({ className = "icon" }: CapabilityIconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden
    >
      <path
        d="M10.4 12.8a2.4 2.4 0 1 0 2.4-2.4 2.4 2.4 0 0 0-2.4 2.4Zm0 0A7.2 7.2 0 0 1 3.2 5.6m0 0a2.4 2.4 0 1 0 0-4.8 2.4 2.4 0 0 0 0 4.8Zm0 0v9.6"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Type-specific identity mark used by Agent canvas cards and containers. */
export function CanvasAgentTypeIcon({
  type,
  className = "icon",
}: CapabilityIconProps & { type: CanvasAgentType }) {
  if (type === "llm") {
    return <AgentFlowCapabilityIcon className={className} />;
  }

  const commonProps = {
    className,
    viewBox: "0 0 16 16",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.45,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };

  if (type === "sequential") {
    return (
      <svg {...commonProps}>
        <circle cx="3.25" cy="3" r="1.25" />
        <circle cx="3.25" cy="8" r="1.25" />
        <circle cx="3.25" cy="13" r="1.25" />
        <path d="M6.4 3h6.35M6.4 8h6.35M6.4 13h6.35" />
      </svg>
    );
  }

  if (type === "parallel") {
    return (
      <svg {...commonProps}>
        <path d="M2 8h3.15M5.15 8c2.2 0 2.2-4.4 4.4-4.4H14M5.15 8h8.85M5.15 8c2.2 0 2.2 4.4 4.4 4.4H14" />
        <circle cx="2" cy="8" r="1" fill="currentColor" stroke="none" />
        <circle cx="14" cy="3.6" r="1" fill="currentColor" stroke="none" />
        <circle cx="14" cy="8" r="1" fill="currentColor" stroke="none" />
        <circle cx="14" cy="12.4" r="1" fill="currentColor" stroke="none" />
      </svg>
    );
  }

  if (type === "loop") {
    return (
      <svg {...commonProps}>
        <path d="M12.75 5.1A5.4 5.4 0 0 0 3.2 4.25L2 5.5" />
        <path d="M2 2.75V5.5h2.75" />
        <path d="M3.25 10.9a5.4 5.4 0 0 0 9.55.85L14 10.5" />
        <path d="M14 13.25V10.5h-2.75" />
      </svg>
    );
  }

  return (
    <svg {...commonProps}>
      <circle cx="8" cy="8" r="6" />
      <path d="M2.3 8h11.4M8 2c1.8 1.65 2.7 3.65 2.7 6S9.8 12.35 8 14M8 2C6.2 3.65 5.3 5.65 5.3 8S6.2 12.35 8 14" />
    </svg>
  );
}

/** Open-book mark used for the compact skill count on Agent canvas cards. */
export function AgentSkillCountIcon({ className = "icon" }: CapabilityIconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden
    >
      <path
        d="M10 5.2C8.62 3.84 6.62 3.2 4 3.2c-.66 0-1.2.54-1.2 1.2v9.4c0 .66.54 1.2 1.2 1.2 2.62 0 4.62.64 6 2m0-11.8c1.38-1.36 3.38-2 6-2 .66 0 1.2.54 1.2 1.2v9.4c0 .66-.54 1.2-1.2 1.2-2.62 0-4.62.64-6 2m0-11.8V17"
        stroke="currentColor"
        strokeWidth="1.55"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Puzzle-piece mark used for the compact tool count on Agent canvas cards. */
export function AgentToolCountIcon({ className = "icon" }: CapabilityIconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 20 20"
      fill="none"
      aria-hidden
    >
      <path
        d="M7.7 3.2h2.05a2.1 2.1 0 1 1 3.95 1v2.1h2.1c.55 0 1 .45 1 1v2.05a2.1 2.1 0 1 0-1 3.95h-2.1v2.5c0 .55-.45 1-1 1h-2.05a2.1 2.1 0 1 0-3.95-1v-2.5H4.2c-.55 0-1-.45-1-1v-2.05a2.1 2.1 0 1 0 1-3.95h2.5V4.2c0-.55.45-1 1-1Z"
        stroke="currentColor"
        strokeWidth="1.55"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Three tuned control tracks: a compact mark for mounted tools. */
export function ToolCapabilityIcon({ className = "icon" }: CapabilityIconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M4.5 6.7h4.2M12.3 6.7h7.2" />
      <path d="M4.5 12h8.2M16.3 12h3.2" />
      <path d="M4.5 17.3h2.7M10.8 17.3h8.7" />
      <circle cx="10.5" cy="6.7" r="1.8" fill="currentColor" stroke="none" />
      <circle cx="14.5" cy="12" r="1.8" fill="currentColor" stroke="none" />
      <circle cx="9" cy="17.3" r="1.8" fill="currentColor" stroke="none" />
    </svg>
  );
}

/** A quiet four-point spark: a compact mark for reusable skills. */
export function SkillCapabilityIcon({ className = "icon" }: CapabilityIconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <g transform="translate(0 2)">
        <path d="M11.6 3.5c.45 3.75 2.75 6.05 6.5 6.5-3.75.45-6.05 2.75-6.5 6.5-.45-3.75-2.75-6.05-6.5-6.5 3.75-.45 6.05-2.75 6.5-6.5Z" />
        <path d="M18.7 3.8v3.4M20.4 5.5H17" />
      </g>
    </svg>
  );
}
