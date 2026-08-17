import type { SVGProps } from "react";

const sharedProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export function EditCloudEnvironmentIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...sharedProps} {...props}>
      <path d="M5 19h3.2L18.6 8.6a1.7 1.7 0 0 0 0-2.4l-.8-.8a1.7 1.7 0 0 0-2.4 0L5 15.8V19Z" />
      <path d="m13.9 6.9 3.2 3.2M5 15.8 8.2 19" />
    </svg>
  );
}

export function CloseCloudEnvironmentIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg {...sharedProps} {...props}>
      <path d="m6.5 6.5 11 11M17.5 6.5l-11 11" />
    </svg>
  );
}
