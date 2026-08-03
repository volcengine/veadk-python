import type { SVGProps } from "react";

export type SandboxAgentIconKind = "codex" | "openclaw" | "hermes";

export function CodexAgentIcon(props: SVGProps<SVGSVGElement>) {
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
      <path d="M8.4 18.4H7.2a4.2 4.2 0 0 1-.65-8.35A5.7 5.7 0 0 1 17.3 8.2a4.6 4.6 0 0 1-.4 9.2h-3.2" />
      <path d="m7.8 12.3 2 2-2 2M12.2 16.3h3.2" />
    </svg>
  );
}

export function OpenClawAgentIcon(props: SVGProps<SVGSVGElement>) {
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
      <path d="M18.9 6.25A8.4 8.4 0 1 0 19.6 16" />
      <path d="M19 6.2c.1 2.1-.65 3.75-2.25 4.95-1.2.9-2.75 1.25-4.2.9" />
      <circle cx="10.6" cy="12.8" r="2.45" />
      <path d="m5.25 18.6 3.65-3.9M14.8 17.9c1.9-.45 3.55-1.65 4.65-3.35" />
    </svg>
  );
}

export function HermesAgentIcon(props: SVGProps<SVGSVGElement>) {
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
      <path d="M6.2 20c.55-2.15.75-4.1.75-6.7V9.8A5.35 5.35 0 0 1 12.35 4c3.35 0 5.65 2.35 5.65 5.65v4.6c0 2.35.35 4.25 1.15 5.75" />
      <path d="M8.05 10.2c1.35-.6 2.2-1.65 2.55-3.15.45 1.55 1.35 2.55 2.7 3.05.1-1 .4-1.95.85-2.75.45 1.25 1.2 2.2 2.15 2.75" />
      <path d="M9.3 12.65h.01M14.9 12.65h.01M10.8 15.55c.8.5 1.65.5 2.45 0" />
      <path d="M8.45 19.85c.95-.85 1.45-1.95 1.5-3.25M15.1 16.65c.05 1.2.55 2.3 1.55 3.2" />
    </svg>
  );
}

export function SandboxAgentIcon({
  kind,
  ...props
}: SVGProps<SVGSVGElement> & { kind: SandboxAgentIconKind }) {
  if (kind === "codex") return <CodexAgentIcon {...props} />;
  if (kind === "openclaw") return <OpenClawAgentIcon {...props} />;
  return <HermesAgentIcon {...props} />;
}
