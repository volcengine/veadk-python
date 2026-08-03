import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

export function SandboxTerminalIcon(props: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
      <path d="m7.5 9 2.7 2.5L7.5 14M12.7 14h3.8" />
      <path d="M3.8 7.5h16.4" opacity=".55" />
    </svg>
  );
}

export function SandboxBrowserIcon(props: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
      <path d="M3.8 8h16.4" />
      <circle cx="6.5" cy="6.3" r=".65" fill="currentColor" stroke="none" />
      <circle cx="8.8" cy="6.3" r=".65" fill="currentColor" stroke="none" />
      <path d="m9 15 2.2-4 1.6 2.4 1.1-1.2L16 15H9Z" />
    </svg>
  );
}

export function SandboxPermissionsIcon(props: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M12 3.4 19 6v5.3c0 4.3-2.7 7.6-7 9.3-4.3-1.7-7-5-7-9.3V6l7-2.6Z" />
      <path d="m8.8 12 2 2 4.4-4.4" />
    </svg>
  );
}

export function SandboxWorkspaceIcon(props: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M3.5 7.7h6.1l1.7 2h9.2v7.5a2.3 2.3 0 0 1-2.3 2.3H5.8a2.3 2.3 0 0 1-2.3-2.3V7.7Z" />
      <path d="M3.8 7.7V6.8a2.3 2.3 0 0 1 2.3-2.3h3l1.8 2h6.9a2.3 2.3 0 0 1 2.3 2.3v.9" />
      <path d="M12 13v3M10.5 14.5h3" />
    </svg>
  );
}

export function SandboxAddIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true" {...props}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function SandboxSendIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="m6.5 11.5 5.5-5.5 5.5 5.5M12 6v12" />
    </svg>
  );
}

export function SandboxImageIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
      <circle cx="8.5" cy="9" r="1.4" />
      <path d="m5.5 17 4.2-4.2 2.6 2.4 2.1-2.1 4.1 3.9" />
    </svg>
  );
}

export function SandboxFileIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M6 3.5h7l5 5v12H6z" />
      <path d="M13 3.5v5h5M9 13h6M9 16h5" />
    </svg>
  );
}

export function SandboxVideoIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="3.5" y="5" width="13.5" height="14" rx="2.5" />
      <path d="m17 10 3.5-2v8L17 14zM7 8.5h4.5" />
    </svg>
  );
}

export function SandboxSparkIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="m12 3 1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5zM18.5 15.5l.7 2.1 2.1.7-2.1.7-.7 2.1-.7-2.1-2.1-.7 2.1-.7z" />
    </svg>
  );
}

export function SandboxCloseIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true" {...props}>
      <path d="m6.5 6.5 11 11M17.5 6.5l-11 11" />
    </svg>
  );
}

export function SandboxChevronIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="m9 6 6 6-6 6" />
    </svg>
  );
}

export function SandboxHistoryIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M4.8 8.2A8 8 0 1 1 4 12M4.8 8.2V4.5M4.8 8.2h3.7" />
      <path d="M12 8v4.5l3 1.8" />
    </svg>
  );
}

export function SandboxSpinnerIcon(props: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true" {...props}>
      <path d="M20 12a8 8 0 1 1-2.35-5.65" />
    </svg>
  );
}
