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
