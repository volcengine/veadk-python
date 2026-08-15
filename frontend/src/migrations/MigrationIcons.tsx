import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function Icon({
  children,
  ...props
}: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      {...props}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export function BackIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="m10 6-6 6 6 6M4 12h16" />
    </Icon>
  );
}

export function DownloadIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 3v12m-4-4 4 4 4-4M5 20h14" />
    </Icon>
  );
}

export function FileIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M6 3.5h8l4 4V20H6zM14 3.5v4h4M9 12h6M9 15.5h6" />
    </Icon>
  );
}

export function PlusIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 5v14M5 12h14" />
    </Icon>
  );
}

export function DeployIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M14.5 4.5c2.3-.9 4.2-.8 5-.6.2.8.3 2.7-.6 5l-5.1 5.1-3.8-3.8zM15.4 8.6h.1M10.3 10.5l-3.8.7-2.1 2.1 5.3.2M13.5 13.7l-.7 3.8-2.1 2.1-.2-5.3M7.2 16.8l-2.8 2.8" />
    </Icon>
  );
}

export function SendIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="m5 12 14-7-5.6 14-1.8-5.6zM11.6 13.4 19 5" />
    </Icon>
  );
}

export function UploadIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 16V4m-4 4 4-4 4 4M5 20h14" />
    </Icon>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="m6 6 12 12M18 6 6 18" />
    </Icon>
  );
}
