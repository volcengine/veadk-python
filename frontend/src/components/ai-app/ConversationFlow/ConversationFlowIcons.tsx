import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function Icon({ children, ...props }: IconProps) {
  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{children}</svg>;
}

export function ConversationUserIcon(props: IconProps) {
  return <Icon {...props}><circle cx="8" cy="5" r="2.5" /><path d="M3 13v-1c0-2.1 2.1-3.5 5-3.5s5 1.4 5 3.5v1" /></Icon>;
}

export function ConversationSystemIcon(props: IconProps) {
  return <Icon {...props}><circle cx="8" cy="8" r="5.5" /><path d="M8 7v4m0-6v.1" /></Icon>;
}

export function ConversationAssistantIcon(props: IconProps) {
  return <Icon {...props}><rect x="3.5" y="3.5" width="9" height="9" rx="2" /><path d="M6 1.5v2m4-2v2m-4 9v2m4-2v2M1.5 6h2m-2 4h2m9-4h2m-2 4h2M6.5 6.5h3v3h-3z" /></Icon>;
}

export function ConversationReasoningIcon(props: IconProps) {
  return <Icon {...props}><path d="M2.5 3.5h11m-11 4h8m-8 4h6" /><circle cx="12" cy="11.5" r="1.5" /></Icon>;
}

export function ConversationToolIcon(props: IconProps) {
  return <Icon {...props}><path d="M9 2.4a3.5 3.5 0 0 0-4.5 4.5L1.9 9.5a1.7 1.7 0 0 0 2.4 2.4l2.6-2.6A3.5 3.5 0 0 0 11.4 4.8L9.1 7.1 6.9 4.9 9 2.4Z" transform="translate(1 1)" /></Icon>;
}

export function ConversationCopyIcon(props: IconProps) {
  return <Icon {...props}><rect x="5" y="5" width="8" height="8" rx="1.5" /><path d="M9.5 5V3.5A1.5 1.5 0 0 0 8 2H3.5A1.5 1.5 0 0 0 2 3.5V8A1.5 1.5 0 0 0 3.5 9.5H5" /></Icon>;
}

export function ConversationCheckIcon(props: IconProps) {
  return <Icon {...props}><path d="m3 8 3.2 3.2L13 4.5" /></Icon>;
}

export function ConversationRetryIcon(props: IconProps) {
  return <Icon {...props}><path d="M3.5 5.5A5 5 0 1 1 3 9M3.5 2.5v3.2h3.2" /></Icon>;
}

export function ConversationLikeIcon(props: IconProps) {
  return <Icon {...props}><path d="M5.5 7 8 2.5c.3-.5 1.1-.4 1.3.2.4 1.1.3 2.2-.1 3.3h3.2c1 0 1.6.8 1.4 1.7l-.8 4.2a1.6 1.6 0 0 1-1.6 1.3H5.5V7ZM2 7h3.5v6H2z" /></Icon>;
}

export function ConversationDislikeIcon(props: IconProps) {
  return <Icon {...props}><g transform="translate(16 16) rotate(180)"><path d="M5.5 7 8 2.5c.3-.5 1.1-.4 1.3.2.4 1.1.3 2.2-.1 3.3h3.2c1 0 1.6.8 1.4 1.7l-.8 4.2a1.6 1.6 0 0 1-1.6 1.3H5.5V7ZM2 7h3.5v6H2z" /></g></Icon>;
}

export function ConversationErrorIcon(props: IconProps) {
  return <Icon {...props}><circle cx="8" cy="8" r="5.5" /><path d="M8 4.5v4M8 11v.1" /></Icon>;
}

export function ConversationPendingIcon(props: IconProps) {
  return <Icon {...props}><circle cx="8" cy="8" r="3" /></Icon>;
}

export function ConversationCancelIcon(props: IconProps) {
  return <Icon {...props}><circle cx="8" cy="8" r="5.5" /><path d="m6 6 4 4m0-4-4 4" /></Icon>;
}

export function ConversationStopIcon(props: IconProps) {
  return <Icon {...props}><rect x="4" y="4" width="8" height="8" rx="1.5" fill="currentColor" stroke="none" /></Icon>;
}

export function ConversationHandoffIcon(props: IconProps) {
  return <Icon {...props}><path d="M2.5 5h10M10 2.5 12.5 5 10 7.5m3.5 3.5h-10M6 8.5 3.5 11 6 13.5" /></Icon>;
}

export function ConversationFileIcon(props: IconProps) {
  return <Icon {...props}><path d="M9.5 1.5h-6A1 1 0 0 0 2.5 2.5v11a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1V5.5l-4-4ZM9.5 1.5v4h4M5.5 8h5m-5 3h3" /></Icon>;
}

export function ConversationPreviewIcon(props: IconProps) {
  return <Icon {...props}><path d="M1.5 8S3.7 3.5 8 3.5 14.5 8 14.5 8 12.3 12.5 8 12.5 1.5 8 1.5 8Z" /><circle cx="8" cy="8" r="2" /></Icon>;
}

export function ConversationDownloadIcon(props: IconProps) {
  return <Icon {...props}><path d="M8 1.5v8m-3-3 3 3 3-3M2.5 10v3.5h11V10" /></Icon>;
}

export function ConversationAuthorizationIcon(props: IconProps) {
  return <Icon {...props}><path d="m8 1.5 5 2v4c0 3-2.1 5.4-5 7-2.9-1.6-5-4-5-7v-4l5-2Z" /><path d="m5.5 7.5 1.8 1.8 3.2-3.1" /></Icon>;
}
