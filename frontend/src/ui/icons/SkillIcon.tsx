import type { SVGProps } from "react";

export function SkillIcon(props: SVGProps<SVGSVGElement>) {
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
      <g className="skill-icon__rear-document">
        <path d="M9.6 4.25H7.25a2 2 0 0 0-2 2v11.5a2 2 0 0 0 2 2H9" />
      </g>
      <g className="skill-icon__front-document">
        <path d="M7.25 4.25h7.1l2.4 2.4v13.1h-9.5a2 2 0 0 1-2-2V6.25a2 2 0 0 1 2-2Z" />
        <path d="M14.25 4.25v2.9h2.5M8.5 11h5M8.5 14h5M8.5 17h3" />
      </g>
    </svg>
  );
}
