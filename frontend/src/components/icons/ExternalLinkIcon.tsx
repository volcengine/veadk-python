import type { SVGProps } from "react";

export function ExternalLinkIcon(props: SVGProps<SVGSVGElement>) {
  return <svg width="1em" height="1em" viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
    <path
      d="M7.25 2.25H6.25C3.25 2.25 2.25 3.25 2.25 6.25V9.75C2.25 12.75 3.25 13.75 6.25 13.75H9.75C12.75 13.75 13.75 12.75 13.75 9.75V8.5M8.5 7.5 13.75 2.25M11 2.25h2.75V5"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>;
}
