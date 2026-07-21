import type { SVGProps } from "react";

/** A packaged app descending into its runtime target. */
export function DeployIcon({ className, ...props }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="m12 2.75 4.25 2.45v4.9L12 12.55 7.75 10.1V5.2L12 2.75Z" />
      <path d="m7.75 5.2 4.25 2.45 4.25-2.45M12 7.65v4.9" />
      <path d="M12 12.55v4.7m-2.25-2.2L12 17.3l2.25-2.25" />
      <path d="M5.5 17.25v2.25a1.75 1.75 0 0 0 1.75 1.75h9.5a1.75 1.75 0 0 0 1.75-1.75v-2.25" />
    </svg>
  );
}
