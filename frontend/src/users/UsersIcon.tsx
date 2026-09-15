import type { SVGProps } from "react";

export function UsersIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="9" cy="8" r="3.25" />
      <path d="M2.75 20v-1.5a6.25 6.25 0 0 1 12.5 0V20M16 5.25a3.25 3.25 0 0 1 0 6.5M18 14a5.5 5.5 0 0 1 3.25 5V20" />
    </svg>
  );
}
