import type { SVGProps } from "react";

type StudioRoleIconProps = Omit<SVGProps<SVGSVGElement>, "role"> & {
  role: "admin" | "developer" | "user";
};

const sharedIconProps = {
  viewBox: "0 0 16 16",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.35,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
} as const;

export function StudioRoleIcon({ role, ...props }: StudioRoleIconProps) {
  switch (role) {
    case "admin":
      return (
        <svg {...props} {...sharedIconProps}>
          <path d="M8 1.75 13 3.7v3.75c0 3.05-1.78 5.6-5 6.8-3.22-1.2-5-3.75-5-6.8V3.7L8 1.75Z" />
          <path d="m5.75 7.9 1.45 1.45 3.05-3.05" />
        </svg>
      );
    case "developer":
      return (
        <svg {...props} {...sharedIconProps}>
          <path d="m5.3 4.25-3.25 3.5 3.25 3.5M10.7 4.25l3.25 3.5-3.25 3.5M9.25 2.75l-2.5 10" />
        </svg>
      );
    default:
      return (
        <svg {...props} {...sharedIconProps}>
          <circle cx="8" cy="5.25" r="2.5" />
          <path d="M3.25 13.75c.35-2.45 2.1-4 4.75-4s4.4 1.55 4.75 4" />
        </svg>
      );
  }
}
