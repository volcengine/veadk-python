import type { SVGProps } from "react";

type SidebarIconProps = SVGProps<SVGSVGElement>;

function SidebarPanelGlyph({ mirrored = false }: { mirrored?: boolean }) {
  return (
    <g
      opacity="0.5"
      transform={mirrored ? "translate(20 0) scale(-1 1)" : undefined}
    >
      <path
        className="sidebar-panel-glyph__divider"
        d="M5.938 6.833c.11 0 .249.102.249.292v6.042c0 .19-.14.291-.249.291s-.248-.101-.248-.291V7.125c0-.19.139-.292.248-.292Z"
        strokeWidth="1.167"
      />
      <path
        className="sidebar-panel-glyph__frame"
        d="M14.5 3.75h-9a3 3 0 0 0-3 3v6.857a3 3 0 0 0 3 3h9a3 3 0 0 0 3-3V6.75a3 3 0 0 0-3-3Z"
        strokeWidth="1.667"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </g>
  );
}

export function SidebarCollapseIcon(props: SidebarIconProps) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <SidebarPanelGlyph />
    </svg>
  );
}

export function SidebarExpandIcon(props: SidebarIconProps) {
  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true" {...props}>
      <SidebarPanelGlyph mirrored />
    </svg>
  );
}

export function NewChatIcon(props: SidebarIconProps) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path
        d="M12 8.333c.368 0 .667.299.667.667v2h2a.667.667 0 0 1 0 1.333h-2v2a.667.667 0 0 1-1.334 0v-2h-2a.667.667 0 0 1 0-1.333h2V9c0-.368.299-.667.667-.667ZM7.667 1c3.49 0 6.383 2.554 6.913 5.896a.667.667 0 0 1-1.317.208 5.667 5.667 0 1 0-9.708 4.424.67.67 0 0 1 .07.12.667.667 0 0 1-.13.834l-.95.853 4.788-.002a.667.667 0 0 1 0 1.334l-5.657.002c-.917 0-1.35-1.131-.67-1.744l1.163-1.045A6.97 6.97 0 0 1 .667 8c0-3.866 3.134-7 7-7Z"
        fill="currentColor"
      />
    </svg>
  );
}

export function SidebarSearchIcon(props: SidebarIconProps) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.333"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <circle cx="7.333" cy="7.333" r="5.333" />
      <path d="m11.133 11.133 2.867 2.867" />
    </svg>
  );
}

export function SidebarAgentIcon(props: SidebarIconProps) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path
        d="M8 0.667c4.05 0 7.334 3.283 7.334 7.333 0 4.05-3.284 7.334-7.334 7.334S0.667 12.05 0.667 8 3.95 0.667 8 0.667Zm0 1.333a6 6 0 1 0 0 12A6 6 0 0 0 8 2ZM6.167 6c.368 0 .667.299.667.667v2a.667.667 0 0 1-1.334 0v-2c0-.368.299-.667.667-.667Zm3.666 0c.368 0 .667.299.667.667v2a.667.667 0 0 1-1.333 0v-2c0-.368.298-.667.666-.667Z"
        fill="currentColor"
      />
    </svg>
  );
}

export function ResourceLibraryIcon(props: SidebarIconProps) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path
        d="M7.58 2.6a.667.667 0 0 0-.667-.667h-.666a.667.667 0 0 0-.667.667v10.667c0 .368.299.666.667.666h.666a.667.667 0 0 0 .667-.666V2.6Zm1.333 10.667A2 2 0 0 1 6.913 15.267h-.666a2 2 0 0 1-2-2V2.6a2 2 0 0 1 2-2h.666a2 2 0 0 1 2 2v10.667Z"
        fill="currentColor"
      />
      <path
        d="M11.88 5.045a.667.667 0 0 0-.801-.514l-.653.136a.667.667 0 0 0-.504.786l1.85 8.092c.081.358.44.589.8.514l.653-.137a.667.667 0 0 0 .504-.786L11.88 5.045Zm3.155 7.82a2 2 0 0 1-1.512 2.358l-.653.136a2 2 0 0 1-2.403-1.541L8.617 5.726a2 2 0 0 1 1.513-2.358l.652-.136a2 2 0 0 1 2.404 1.541l1.849 8.092Z"
        fill="currentColor"
      />
      <path
        d="M4.247 2.6a.667.667 0 0 0-.667-.667h-.667a.667.667 0 0 0-.666.667v10.667c0 .368.298.666.666.666h.667a.667.667 0 0 0 .667-.666V2.6ZM5.58 13.267a2 2 0 0 1-2 2h-.667a2 2 0 0 1-2-2V2.6a2 2 0 0 1 2-2h.667a2 2 0 0 1 2 2v10.667Z"
        fill="currentColor"
      />
    </svg>
  );
}
