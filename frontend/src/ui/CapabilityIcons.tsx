interface CapabilityIconProps {
  className?: string;
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

/** A folded mastery crest: a compact mark for learned skills. */
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
      <path d="m4.7 7.2 7.3-3 7.3 3-7.3 3.1Z" />
      <path d="M7.2 9.2v4.2c0 1.7 2.15 3.05 4.8 3.05s4.8-1.35 4.8-3.05V9.2" />
      <path d="M19.3 7.2v5.25" />
      <circle cx="19.3" cy="14.4" r="1.15" fill="currentColor" stroke="none" />
    </svg>
  );
}
