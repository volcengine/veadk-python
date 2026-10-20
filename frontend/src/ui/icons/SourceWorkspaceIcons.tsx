import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function iconProps(props: IconProps): IconProps {
  return {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.75,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
    ...props,
  };
}

export function SourceCodeIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="m9 7-5 5 5 5M15 7l5 5-5 5M13.5 4l-3 16" /></svg>;
}

export function SourceFileIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M6.5 3.75h7l4 4V20.25h-11zM13.5 3.75v4h4M9 12h6M9 15.5h4.5" /></svg>;
}

export function SourceFolderIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M3.75 7.25h6l1.75 2h8.75v9.25H3.75zM3.75 7.25V5.5h5l1.5 1.75" /></svg>;
}

export function SourceChevronIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="m9 5 7 7-7 7" /></svg>;
}

export function SourceCloseIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="m6.5 6.5 11 11M17.5 6.5l-11 11" /></svg>;
}

export function SourceLightThemeIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <circle cx="12" cy="12" r="3.25" />
      <path d="M12 2.75v2M12 19.25v2M2.75 12h2M19.25 12h2M5.45 5.45l1.4 1.4M17.15 17.15l1.4 1.4M18.55 5.45l-1.4 1.4M6.85 17.15l-1.4 1.4" />
    </svg>
  );
}

export function SourceDarkThemeIcon(props: IconProps) {
  return <svg {...iconProps(props)}><path d="M19.25 15.25A8 8 0 0 1 8.75 4.75a8 8 0 1 0 10.5 10.5Z" /></svg>;
}

export function SourceRefreshIcon(props: IconProps) {
  return (
    <svg {...iconProps(props)}>
      <path d="M19.25 8.25V4.5l-1.8 1.8a7.5 7.5 0 1 0 1.8 7.65" />
      <path d="M19.25 4.5H15.5" />
    </svg>
  );
}
