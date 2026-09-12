import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function iconProps(props: IconProps): IconProps {
  return {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "1.75",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
    ...props,
  };
}

export function ToolCommandIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
      <path d="m7.5 9 2.7 2.5L7.5 14M12.7 14h3.8M3.8 7.5h16.4" />
    </svg>
  );
}

export function ToolReadIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="M6 3.5h7l5 5v12H6zM13 3.5v5h5M8.8 13h5.7M8.8 16h3.8" />
      <circle cx="16.8" cy="16.5" r="2.3" />
      <path d="m18.5 18.2 1.8 1.8" />
    </svg>
  );
}

export function ToolSearchIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <circle cx="10.5" cy="10.5" r="5.75" />
      <path d="m15 15 4.25 4.25" />
    </svg>
  );
}

export function ToolFileChangeIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="M5.5 3.5h7l4 4v4M12.5 3.5v4h4M10.5 20.5h-5v-17" />
      <path d="m12.5 17.5 5.6-5.6 2 2-5.6 5.6-2.8.8z" />
    </svg>
  );
}

export function ToolMcpIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="M8 8V4.5M16 8V4.5M6.5 8h11v3.5a5.5 5.5 0 0 1-11 0zM12 17v3" />
      <path d="M5.5 4.5h5M13.5 4.5h5" />
    </svg>
  );
}

export function ToolAuthorizationIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="M12 3.5 19 6v5.2c0 4.3-2.7 7.6-7 9.3-4.3-1.7-7-5-7-9.3V6z" />
      <path d="m8.8 12 2 2 4.4-4.4" />
    </svg>
  );
}

export function ToolGenericIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="M14.8 6.2a4.1 4.1 0 0 0-5.6 5.6l-5.4 5.4a2 2 0 0 0 2.8 2.8l5.4-5.4a4.1 4.1 0 0 0 5.6-5.6l-2.5 2.5-2.6-.6-.6-2.6z" />
    </svg>
  );
}

export function ToolChevronIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="m9 5 7 7-7 7" />
    </svg>
  );
}

export function ToolCheckIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="m5 12.5 4.5 4.5L19 7.5" />
    </svg>
  );
}

export function ToolErrorIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5v5.25M12 16.25h.01" />
    </svg>
  );
}

export function ToolSpinnerIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="M20 12a8 8 0 1 1-2.35-5.65" />
    </svg>
  );
}

export function ToolCopyIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <rect x="8" y="8" width="11" height="11" rx="2" />
      <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
    </svg>
  );
}
