import type { SVGProps } from "react";

export function RuntimeArtifactsIcon(props: SVGProps<SVGSVGElement>) {
  return <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d="M3.5 7.5V6A2 2 0 0 1 5.5 4h4l2 3h7A2 2 0 0 1 20.5 9v9a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2V7.5Z" /><path d="M8 12h8M8 16h5" /></svg>;
}

export function ArtifactRefreshIcon() {
  return <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M19 8a8 8 0 1 0 .6 7M19 4v4h-4" /></svg>;
}

export function ArtifactDownloadIcon() {
  return <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3v12m-4-4 4 4 4-4M4 16v4h16v-4" /></svg>;
}
