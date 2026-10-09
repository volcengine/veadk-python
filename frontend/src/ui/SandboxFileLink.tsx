import { createContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { fetchSessionFile } from "../adk/client";

export const SandboxFileContext = createContext<{ appName: string; sessionId: string } | null>(null);

export function sandboxFilePath(href: string | undefined): string | null {
  if (!href || /[?#]/.test(href)) return null;
  try {
    const path = decodeURIComponent(href);
    if (!/^\/data\/(output|workspace)\/.+/.test(path) || path.endsWith("/")) return null;
    if (/[\\\u0000-\u001f\u007f]/.test(path) || path.split("/").some((part) => part === "." || part === "..")) return null;
    return path;
  } catch {
    return null;
  }
}

export function SandboxFileLink({ appName, sessionId, path, children }: {
  appName: string; sessionId: string; path: string; children: ReactNode;
}) {
  const { t } = useTranslation("conversation");
  const pending = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setBusy(false);
    setFailed(false);
    return () => { pending.current?.abort(); pending.current = null; };
  }, [appName, sessionId, path]);
  async function download() {
    if (pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setFailed(false);
    try {
      const blob = await fetchSessionFile(appName, sessionId, path, controller.signal);
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      try {
        anchor.href = url;
        anchor.download = path.slice(path.lastIndexOf("/") + 1);
        document.body.appendChild(anchor);
        anchor.click();
      } finally {
        anchor.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 0);
      }
    } catch {
      if (!controller.signal.aborted) setFailed(true);
    } finally {
      if (pending.current === controller) { pending.current = null; setBusy(false); }
    }
  }
  return <>
    <a className="sandbox-file-download" href={encodeURI(path)} aria-disabled={busy} aria-busy={busy}
      onClick={(event) => { event.preventDefault(); void download(); }}>
      <span aria-hidden="true">↓</span>
      <span>{busy ? t("markdown.downloading") : t("markdown.downloadFile")} · {children}</span>
    </a>
    {failed && <span role="alert"> {t("markdown.downloadFailed")}</span>}
  </>;
}
