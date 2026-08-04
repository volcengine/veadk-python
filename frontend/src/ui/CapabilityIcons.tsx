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
