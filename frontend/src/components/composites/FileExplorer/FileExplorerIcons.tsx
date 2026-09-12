import type { ReactNode, SVGProps } from "react";
import { filePresentation, type FileExplorerIconKind } from "./FileExplorerFileTypes";

export function FileExplorerChevron(props: SVGProps<SVGSVGElement>) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}><path d="m9 5 7 7-7 7" /></svg>;
}

export function FileExplorerFolderIcon({ open }: { open: boolean }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {open ? <><path d="M3 18V6a2 2 0 0 1 2-2h4l3 3h6a2 2 0 0 1 2 2v1" /><path d="m3 18 3.6-7h14.3a1 1 0 0 1 .9 1.45l-3.2 6.45A2 2 0 0 1 16.8 20H5a2 2 0 0 1-2-2Z" /></> : <path d="M3 18V6a2 2 0 0 1 2-2h4l3 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />}
  </svg>;
}

const documentOutline = "M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Zm0 0v6h6";
const documentKinds = new Set<FileExplorerIconKind>(["script", "style", "text", "python", "go", "rust", "java", "pdf", "archive", "file"]);
const fileShapes: Record<FileExplorerIconKind, ReactNode> = {
  react: <><ellipse cx="12" cy="12" rx="10" ry="3.8" /><ellipse cx="12" cy="12" rx="10" ry="3.8" transform="rotate(60 12 12)" /><ellipse cx="12" cy="12" rx="10" ry="3.8" transform="rotate(120 12 12)" /><circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none" /></>,
  script: <path d="m9.5 11-2 3 2 3m5-6 2 3-2 3" />,
  style: <path d="M7.5 12h9m-10 4h9M11 10l-2 8m6-8-2 8" />,
  markup: <path d="m7 7-5 5 5 5m10-10 5 5-5 5m-3-14-4 18" />,
  json: <><path d="M8 3H6a2 2 0 0 0-2 2v4c0 1.5-1 3-2 3 1 0 2 1.5 2 3v4a2 2 0 0 0 2 2h2M16 3h2a2 2 0 0 1 2 2v4c0 1.5 1 3 2 3-1 0-2 1.5-2 3v4a2 2 0 0 1-2 2h-2" /><path d="M11 9h2m-2 6h2" /></>,
  config: <><path d="M3 6h3m4 0h11M3 12h11m4 0h3M3 18h5m4 0h9" /><circle cx="8" cy="6" r="2" /><circle cx="16" cy="12" r="2" /><circle cx="10" cy="18" r="2" /></>,
  lock: <><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2" /></>,
  markdown: <><rect x="2.5" y="5" width="19" height="14" rx="2" /><path d="M6 15V9l3 3 3-3v6m5-6v6m-2-2 2 2 2-2" /></>,
  text: <path d="M8 12h8M8 16h5" />,
  python: <path d="M9 18v-7h3a2.5 2.5 0 0 1 0 5H9" />,
  go: <path d="M15.5 12a3.5 3.5 0 1 0 0 5.5V15H12" />,
  rust: <path d="M9 18v-7h3a2 2 0 0 1 0 4H9m3 0 3 3" />,
  java: <path d="M9 11h7m-2.5 0v4.5a2.5 2.5 0 0 1-5 0" />,
  terminal: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m7 9 3 3-3 3m6 0h4" /></>,
  environment: <><path d="m10 3-.7 2.2-2 .9-2.1-.8-2 3.4 1.5 1.7-.2 2.2L3 14l2 3.5 2.2-.4 1.8 1.3.7 2.6h4.2l.7-2.6 1.8-1.3 2.2.4 2-3.5-1.5-1.4-.2-2.2 1.5-1.7-2-3.4-2.1.8-2-.9L14 3Z" /><circle cx="12" cy="12" r="3" /></>,
  image: <><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="8" cy="9" r="1.5" /><path d="m3 17 5-5 4 4 3-3 6 6" /></>,
  pdf: <path d="M7 17v-6h1a1.5 1.5 0 0 1 0 3H7m4-3v6h1a3 3 0 0 0 0-6Zm6 6v-6h2m-2 3h2" />,
  archive: <><path d="M10 7h2m0 2h2m-4 2h2m0 2h2" /><rect x="10" y="15" width="4" height="3" rx=".75" /></>,
  file: null,
};

export function FileExplorerFileIcon({ name }: { name: string }) {
  const { icon } = filePresentation(name);
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" data-file-kind={icon}>
    {documentKinds.has(icon) && <path d={documentOutline} />}
    {fileShapes[icon]}
  </svg>;
}
