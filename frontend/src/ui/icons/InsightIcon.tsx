import type { SVGProps } from "react";

export function InsightIcon(props: SVGProps<SVGSVGElement>) {
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
      <path d="M12 3.5c.35 3.05 1.62 5.32 4.9 6.1-3.28.78-4.55 3.05-4.9 6.1-.35-3.05-1.62-5.32-4.9-6.1 3.28-.78 4.55-3.05 4.9-6.1Z" />
      <path d="M18.5 14.5c.18 1.55.84 2.7 2.5 3.1-1.66.4-2.32 1.55-2.5 3.1-.18-1.55-.84-2.7-2.5-3.1 1.66-.4 2.32-1.55 2.5-3.1Z" />
      <path d="M5.3 14.2c.14 1.15.62 2 1.85 2.3-1.23.3-1.71 1.15-1.85 2.3-.14-1.15-.62-2-1.85-2.3 1.23-.3 1.71-1.15 1.85-2.3Z" />
    </svg>
  );
}
