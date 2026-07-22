import type { SVGProps } from "react";

type ToolIconProps = SVGProps<SVGSVGElement>;

export function WebSearchIcon(props: ToolIconProps) {
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
      <circle cx="10.25" cy="10.25" r="6.25" />
      <path d="M4.15 10.25h12.2M10.25 4c1.65 1.72 2.5 3.8 2.5 6.25s-.85 4.53-2.5 6.25M10.25 4c-1.65 1.72-2.5 3.8-2.5 6.25s.85 4.53 2.5 6.25M14.8 14.8 20 20" />
    </svg>
  );
}

export function ImageGenerateIcon(props: ToolIconProps) {
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
      <rect x="3.25" y="5.25" width="15.5" height="13.5" rx="2.25" />
      <circle cx="8.1" cy="9.3" r="1.35" />
      <path d="m4.7 16.5 3.65-3.7 2.45 2.25 2.2-2.2 4.35 4.1" />
      <path d="m19.4 2.75.48 1.37 1.37.48-1.37.48-.48 1.37-.48-1.37-1.37-.48 1.37-.48.48-1.37Z" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function VideoGenerateIcon(props: ToolIconProps) {
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
      <rect x="3.25" y="5.5" width="16.25" height="13" rx="2.4" />
      <path d="m10.2 9.2 4.4 2.8-4.4 2.8V9.2Z" />
      <path d="m19.25 2.5.42 1.2 1.2.42-1.2.42-.42 1.2-.42-1.2-1.2-.42 1.2-.42.42-1.2Z" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function LoadMemoryIcon(props: ToolIconProps) {
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
      <path d="M5 7.4c0-1.55 3.13-2.8 7-2.8s7 1.25 7 2.8-3.13 2.8-7 2.8-7-1.25-7-2.8Z" />
      <path d="M5 7.4v4.55c0 1.55 3.13 2.8 7 2.8s7-1.25 7-2.8V7.4M5 11.95v4.55c0 1.55 3.13 2.8 7 2.8s7-1.25 7-2.8v-4.55" />
      <path d="M8.2 12.25h.01M8.2 16.8h.01" />
    </svg>
  );
}

export function LoadKnowledgebaseIcon(props: ToolIconProps) {
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
      <path d="M4.25 4.25h4.5v15.5h-4.5zM8.75 5.75h5v14h-5zM13.75 4.25h4.1v10.25h-4.1z" />
      <path d="M5.75 7h1.5M10.25 8.25h2M10.25 11h2M15.15 7h1.3" />
      <circle cx="17.45" cy="17.35" r="2.45" />
      <path d="m19.25 19.15 1.55 1.55" />
    </svg>
  );
}

export function ToolDisclosureIcon(props: ToolIconProps) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="m6 3.25 4.5 4.75L6 12.75" />
    </svg>
  );
}
