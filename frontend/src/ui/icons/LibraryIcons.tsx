import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const sharedProps = {
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.75,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export function LibraryIcon(props: IconProps) {
  return (
    <svg {...sharedProps} {...props}>
      <path d="M4.25 6.75h5.1l1.55 1.8h8.85v8.7a2 2 0 0 1-2 2H6.25a2 2 0 0 1-2-2V6.75Z" />
      <path d="M6.5 6.75V5.9a1.15 1.15 0 0 1 1.15-1.15h3.6l1.55 1.8h4.55a1.15 1.15 0 0 1 1.15 1.15v.85" />
      <path d="M8 12.1h8M8 15.6h5.5" />
    </svg>
  );
}

export function DocumentArtifactIcon(props: IconProps) {
  return (
    <svg {...sharedProps} {...props}>
      <path d="M6.25 3.75h7.4l4.1 4.1v12.4H6.25V3.75Z" />
      <path d="M13.5 3.9v4.2h4.05M9 12h6M9 15.5h4.5" />
    </svg>
  );
}

export function ImageArtifactIcon(props: IconProps) {
  return (
    <svg {...sharedProps} {...props}>
      <rect x="3.75" y="4.5" width="16.5" height="15" rx="2" />
      <circle cx="9" cy="9.3" r="1.35" />
      <path d="m5.8 17 4.2-4.15 2.8 2.65 2.15-2.15 3.25 3.65" />
    </svg>
  );
}

export function VideoArtifactIcon(props: IconProps) {
  return (
    <svg {...sharedProps} {...props}>
      <rect x="3.75" y="5.25" width="16.5" height="13.5" rx="2" />
      <path d="m10.25 9 4.8 3-4.8 3V9Z" />
    </svg>
  );
}

export function SearchLibraryIcon(props: IconProps) {
  return (
    <svg {...sharedProps} {...props}>
      <circle cx="10.7" cy="10.7" r="6.1" />
      <path d="m15.25 15.25 4.2 4.2" />
    </svg>
  );
}

export function PreviewArtifactIcon(props: IconProps) {
  return (
    <svg {...sharedProps} {...props}>
      <path d="M3.75 12s3.05-5.25 8.25-5.25S20.25 12 20.25 12 17.2 17.25 12 17.25 3.75 12 3.75 12Z" />
      <circle cx="12" cy="12" r="2.35" />
    </svg>
  );
}

export function DownloadArtifactIcon(props: IconProps) {
  return (
    <svg {...sharedProps} {...props}>
      <path d="M12 3.75v10.5M8.4 10.8 12 14.4l3.6-3.6" />
      <path d="M5 17.25v2h14v-2" />
    </svg>
  );
}

export function CloseLibraryIcon(props: IconProps) {
  return (
    <svg {...sharedProps} {...props}>
      <path d="m6.5 6.5 11 11M17.5 6.5l-11 11" />
    </svg>
  );
}
