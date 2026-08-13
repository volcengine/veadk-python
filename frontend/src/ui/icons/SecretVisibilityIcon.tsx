import type { SVGProps } from "react";

export function SecretVisibilityIcon({
  visible,
  ...props
}: SVGProps<SVGSVGElement> & { visible: boolean }) {
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
      <path d="M2.8 12s3.3-5.4 9.2-5.4 9.2 5.4 9.2 5.4-3.3 5.4-9.2 5.4S2.8 12 2.8 12Z" />
      <circle cx="12" cy="12" r="2.4" />
      {!visible && <path d="m4.2 4.2 15.6 15.6" />}
    </svg>
  );
}
