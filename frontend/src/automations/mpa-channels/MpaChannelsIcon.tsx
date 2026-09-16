import type { SVGProps } from "react";

export function MpaChannelsIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <rect x="8" y="3" width="8" height="6" rx="2" />
      <path d="M12 9v4M5 16v-1a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v1M12 13v3" />
      <rect x="2" y="16" width="6" height="5" rx="1.5" />
      <rect x="9" y="16" width="6" height="5" rx="1.5" />
      <rect x="16" y="16" width="6" height="5" rx="1.5" />
    </svg>
  );
}
