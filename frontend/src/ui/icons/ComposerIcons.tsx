import type { SVGProps } from "react";

type ComposerIconProps = SVGProps<SVGSVGElement>;

export function ComposerSendIcon(props: ComposerIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="m6.5 11.5 5.5-5.5 5.5 5.5M12 6v12" />
    </svg>
  );
}

export function ComposerStopIcon(props: ComposerIconProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" {...props}>
      <rect x="6" y="6" width="12" height="12" rx="1.75" fill="currentColor" />
    </svg>
  );
}
