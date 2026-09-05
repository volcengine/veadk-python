import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const outlineProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export function FeishuQrCodeIcon(props: IconProps) {
  return (
    <svg {...outlineProps} {...props}>
      <rect x="3.5" y="3.5" width="6" height="6" rx="1" />
      <rect x="14.5" y="3.5" width="6" height="6" rx="1" />
      <rect x="3.5" y="14.5" width="6" height="6" rx="1" />
      <path d="M14.5 14.5h2.5v2.5h-2.5zM18 18h2.5v2.5H18zM18 14.5h2.5M14.5 18v2.5" />
    </svg>
  );
}

export function FeishuSpinnerIcon(props: IconProps) {
  return (
    <svg {...outlineProps} strokeWidth="2" {...props}>
      <path d="M20 12a8 8 0 1 1-2.35-5.65" />
    </svg>
  );
}

export function FeishuRefreshIcon(props: IconProps) {
  return (
    <svg {...outlineProps} {...props}>
      <path d="M19.5 8.5V4.8l-2.2 2.1A8 8 0 1 0 20 13" />
    </svg>
  );
}

export function FeishuCheckIcon(props: IconProps) {
  return (
    <svg {...outlineProps} {...props}>
      <path d="m5 12.5 4.2 4.2L19 7" />
    </svg>
  );
}

export function FeishuEyeIcon(props: IconProps) {
  return (
    <svg {...outlineProps} {...props}>
      <path d="M3.5 12s3.2-5 8.5-5 8.5 5 8.5 5-3.2 5-8.5 5-8.5-5-8.5-5Z" />
      <circle cx="12" cy="12" r="2.2" />
    </svg>
  );
}

export function FeishuEyeOffIcon(props: IconProps) {
  return (
    <svg {...outlineProps} {...props}>
      <path d="m4 4 16 16M9.4 7.4A8.8 8.8 0 0 1 12 7c5.3 0 8.5 5 8.5 5a13 13 0 0 1-2 2.5M6.2 8.3A14.2 14.2 0 0 0 3.5 12s3.2 5 8.5 5c1 0 2-.2 2.8-.5" />
      <path d="M10.4 10.4a2.2 2.2 0 0 0 3.2 3.2" />
    </svg>
  );
}
