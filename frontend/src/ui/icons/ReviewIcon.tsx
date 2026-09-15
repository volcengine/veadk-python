import type { SVGProps } from "react";

export function ReviewIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M8.5 4.5H6a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-13a2 2 0 0 0-2-2h-2.5" />
      <rect x="8.5" y="2.5" width="7" height="4" rx="1.5" />
      <path d="m8 13 2.5 2.5L16 10" />
    </svg>
  );
}
