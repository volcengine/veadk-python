interface AgentIdentityIconProps {
  className?: string;
}

/** Quiet geometric aperture: a model core held by an open six-part frame. */
export function AgentIdentityIcon({ className = "icon" }: AgentIdentityIconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="m10.05 3.7 1.95-1.12 1.95 1.12" />
      <path d="m16.25 5.03 3.9 2.25v4.5" />
      <path d="M20.15 15.08v1.64l-3.9 2.25" />
      <path d="m13.95 20.3-1.95 1.12-1.95-1.12" />
      <path d="m7.75 18.97-3.9-2.25v-4.5" />
      <path d="M3.85 8.92V7.28l3.9-2.25" />
      <path
        d="m12 7.55 1.28 3.17L16.45 12l-3.17 1.28L12 16.45l-1.28-3.17L7.55 12l3.17-1.28L12 7.55Z"
        fill="currentColor"
        stroke="none"
      />
    </svg>
  );
}
