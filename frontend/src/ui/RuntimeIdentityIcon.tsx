interface RuntimeIdentityIconProps {
  className?: string;
}

/** A live execution orbit wrapped around a compact activity pulse. */
export function RuntimeIdentityIcon({ className = "icon" }: RuntimeIdentityIconProps) {
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
      <path d="M18.7 8.15A7.55 7.55 0 0 0 5.35 7.1" />
      <path d="m18.7 8.15-.2-3.05-3.02.3" />
      <path d="M5.3 15.85A7.55 7.55 0 0 0 18.65 16.9" />
      <path d="m5.3 15.85.2 3.05 3.02-.3" />
      <path d="M6.85 12h2.8l1.4-2.9 1.9 5.8 1.42-2.9h2.78" />
    </svg>
  );
}
