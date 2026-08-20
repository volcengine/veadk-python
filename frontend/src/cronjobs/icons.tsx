import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function IconFrame({ children, ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export function CronClockIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <circle cx="12" cy="12" r="8.25" />
      <path d="M12 7.6v4.7l3.1 1.8" />
      <path d="M7.2 2.9 5.3 4.8M16.8 2.9l1.9 1.9" />
    </IconFrame>
  );
}

export function CronPlusIcon(props: IconProps) {
  return <IconFrame {...props}><path d="M12 5v14M5 12h14" /></IconFrame>;
}

export function CronBackIcon(props: IconProps) {
  return <IconFrame {...props}><path d="m14.8 5.8-6.2 6.2 6.2 6.2" /></IconFrame>;
}

export function CronEditIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="M13.8 5.2 18.8 10.2 9.2 19.8 4.3 19.8 4.3 14.9Z" />
      <path d="m11.9 7.1 5 5" />
    </IconFrame>
  );
}

export function CronRunIcon(props: IconProps) {
  return <IconFrame {...props}><path d="m9 6.5 8.5 5.5L9 17.5Z" /></IconFrame>;
}

export function CronPauseIcon(props: IconProps) {
  return <IconFrame {...props}><path d="M9 6.5v11M15 6.5v11" /></IconFrame>;
}

export function CronDeleteIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="M5.5 7.2h13M9 7.2V4.8h6v2.4M7.2 7.2l.7 12h8.2l.7-12M10 10.5v5.4M14 10.5v5.4" />
    </IconFrame>
  );
}

export function CronCloseIcon(props: IconProps) {
  return <IconFrame {...props}><path d="m6.5 6.5 11 11M17.5 6.5l-11 11" /></IconFrame>;
}

export function CronRefreshIcon(props: IconProps) {
  return (
    <IconFrame {...props}>
      <path d="M18.6 9a7.2 7.2 0 1 0 .1 5.7" />
      <path d="M18.6 4.8V9h-4.2" />
    </IconFrame>
  );
}
