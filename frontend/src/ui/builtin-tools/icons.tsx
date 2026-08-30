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
      <path
        d="m19.4 2.75.48 1.37 1.37.48-1.37.48-.48 1.37-.48-1.37-1.37-.48 1.37-.48.48-1.37Z"
        fill="currentColor"
        stroke="none"
      />
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
      <path
        className="video-generate-icon__body"
        d="M3.25 9h17.5v7.35a2.4 2.4 0 0 1-2.4 2.4H5.65a2.4 2.4 0 0 1-2.4-2.4V9Z"
      />
      <g className="video-generate-icon__clapper">
        <path d="M3.25 9V7.65a2.4 2.4 0 0 1 2.4-2.4h12.7a2.4 2.4 0 0 1 2.4 2.4V9H3.25Z" />
        <path d="M6.75 5.25 9.3 9M12 5.25 14.55 9M17.25 5.25 19.8 9" />
      </g>
      <path d="m10.25 11.45 4 2.55-4 2.55v-5.1Z" />
    </svg>
  );
}

export function PresentationGenerateIcon(props: ToolIconProps) {
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
      <path d="M4.25 5.25h15.5v10.5H4.25zM8.25 19.75h7.5M12 15.75v4" />
      <path d="m7.25 12.75 2.35-2.4 2.15 1.65 3.4-3.6 1.6 1.55" />
      <circle cx="7.25" cy="8.4" r=".7" fill="currentColor" stroke="none" />
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

/** An open skill card with a small activation spark. */
export function LoadSkillIcon(props: ToolIconProps) {
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
      <path d="M4.25 6.25h6.25c1 0 1.5.55 1.5 1.45v11.05c0-.9-.5-1.45-1.5-1.45H4.25V6.25Z" />
      <path d="M19.75 9.1v8.2H13.5c-1 0-1.5.55-1.5 1.45V7.7c0-.9.5-1.45 1.5-1.45h2.15" />
      <path
        d="m19 3.2.58 1.62 1.62.58-1.62.58L19 7.6l-.58-1.62-1.62-.58 1.62-.58L19 3.2Z"
        fill="currentColor"
        stroke="none"
      />
    </svg>
  );
}

/** A hand-drawn sandbox with a small code prompt inside. */
export function RunCodeIcon(props: ToolIconProps) {
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
      <path d="m4.2 8.4 1.15 10.2h13.3L19.8 8.4" />
      <path d="M4.2 8.4h15.6L17.9 5H6.1L4.2 8.4Z" />
      <path d="M7.2 12.2c1.1-1 2.25 1.25 3.4.25 1.05-.9 2.15 1.3 3.3.25" />
      <path d="m8.2 15.1 1.45 1.35 1.45-1.35M13.55 16.45h2.35" />
    </svg>
  );
}

export function CollectResourcesIcon(props: ToolIconProps) {
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
      <circle cx="6" cy="6.25" r="2.25" />
      <circle cx="18" cy="6.25" r="2.25" />
      <circle cx="12" cy="17.75" r="2.25" />
      <path d="m7.7 7.75 2.7 7.55M16.3 7.75l-2.7 7.55M8.25 6.25h7.5" />
    </svg>
  );
}

export function CreateAgentsIcon(props: ToolIconProps) {
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
      <circle cx="9" cy="8" r="3" />
      <path d="M3.75 18.75c.45-3.05 2.2-4.65 5.25-4.65s4.8 1.6 5.25 4.65" />
      <path d="M17.75 4.25v5.5M15 7h5.5M16 13.25h4.25M18.125 11.125v4.25" />
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
