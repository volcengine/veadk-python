import { useTranslation } from "react-i18next";
import "./i18n";
import { formatRelativeTimeLabel } from "../ui/relativeTime";
import { WorkspaceCollectionLayout } from "../ui/WorkspaceCollectionLayout";
import { useEffect, useRef, useState } from "react";
import { createWorkspaceProject, getWorkspaceState, listWorkspaceProjects, openWorkspaceProject, type WorkspaceProject, type WorkspacePreview } from "../adk/workspacePreview";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { PageBackButton } from "../ui/PageBackButton";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
import { LibraryResourceCard } from "../ui/LibraryResourceCard";
import { ResourceSearch, ResourceResults, ResourceGrid, ResourceCreateCard, ResourceLoadingState } from "../ui/ResourceCollection";
import "./WorkspaceCreate.css";

export function WorkspaceCreateIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 8h18M9 8v12m4-9 3 3-3 3" />
    </svg>
  );
}

export function WorkspaceCreate({ active, onBack, onReturnToProjects, createRequest = 0 }: { active: boolean; createRequest?: number; onReturnToProjects?: () => void; onBack: (section?: "workspaces" | "environments") => void }) {
  const { t, i18n } = useTranslation("create");
  const [preview, setPreview] = useState<(WorkspacePreview & WorkspaceProject) | null>(null);
  const [projects, setProjects] = useState<WorkspaceProject[]>([]);
  const [creating, setCreating] = useState(false);
  const [query, setQuery] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [listError, setListError] = useState("");
  const [busy, setBusy] = useState(false);
  const [openingProject, setOpeningProject] = useState<string | null>(null);
  const [listing, setListing] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [managing, setManaging] = useState(true);
  const [recovering, setRecovering] = useState(false);
  const [recoveryError, setRecoveryError] = useState("");
  const [retryRecovery, setRetryRecovery] = useState(0);
  const [editorGeneration, setEditorGeneration] = useState(0);
  const container = useRef<HTMLElement>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setFullscreen(false); };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, []);
  useEffect(() => {
    if (!active) setFullscreen(false);
    if (!active || managing) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active, managing]);
  const secondsLeft = preview?.expireAt ? Math.max(0, Math.ceil((Date.parse(preview.expireAt) - now) / 1000)) : null;
  const countdown = secondsLeft === null || !Number.isFinite(secondsLeft) ? t("workspace.checkingExpiry") : secondsLeft === 0 ? t("workspace.waitingRecovery") :
    `${String(Math.floor(secondsLeft / 3600)).padStart(2, "0")}:${String(Math.floor(secondsLeft / 60) % 60).padStart(2, "0")}:${String(secondsLeft % 60).padStart(2, "0")}`;
  const operation = useRef<AbortController | null>(null);
  const composing = useRef(false);
  const handledCreateRequest = useRef(0);
  useEffect(() => {
    if (!active || !createRequest || createRequest === handledCreateRequest.current) return;
    handledCreateRequest.current = createRequest;
    setManaging(true); setName(""); setError(""); setCreating(true);
  }, [active, createRequest]);

  useEffect(() => () => operation.current?.abort(), []);
  useEffect(() => { if (active) setManaging(true); else setCreating(false); }, [active]);
  useEffect(() => {
    if (!active || !managing) return;
    const controller = new AbortController();
    setListing(true);
    setListError("");
    void listWorkspaceProjects(controller.signal).then(setProjects).catch((cause: unknown) => {
      if (!controller.signal.aborted) setListError(cause instanceof Error ? cause.message : t("workspace.listFailed"));
    }).finally(() => { if (!controller.signal.aborted) setListing(false); });
    return () => controller.abort();
  }, [active, managing, refresh]);

  useEffect(() => {
    if (!active || managing || !preview) return;
    const controller = new AbortController();
    let checking = false;
    let failed = false;
    async function checkWorkspace() {
      if (checking || failed || operation.current || document.visibilityState === "hidden") return;
      checking = true;
      try {
        const state = await getWorkspaceState(controller.signal);
        if (controller.signal.aborted) return;
        const remaining = state.expireAt ? Date.parse(state.expireAt) - Date.now() : 0;
        if (state.status === "ready" && state.sessionId === preview!.sessionId && remaining >= 3_600_000) {
          if (state.expireAt !== preview!.expireAt) setPreview(current => current ? { ...current, expireAt: state.expireAt } : current);
          return;
        }
        setRecovering(true);
        setRecoveryError("");
        const next = await openWorkspaceProject(preview!.name, controller.signal);
        if (controller.signal.aborted) return;
        setPreview(next);
        if (next.sessionId !== preview!.sessionId) setEditorGeneration(value => value + 1);
        setRefresh(value => value + 1);
      } catch (cause) {
        if (!controller.signal.aborted) {
          failed = true;
          setRecoveryError(cause instanceof Error ? cause.message : t("workspace.recoveryFailed"));
        }
      } finally {
        checking = false;
        if (!controller.signal.aborted) setRecovering(false);
      }
    }
    setRecoveryError("");
    void checkWorkspace();
    const timer = window.setInterval(() => { void checkWorkspace(); }, 30_000);
    const onVisible = () => { if (document.visibilityState === "visible") void checkWorkspace(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      controller.abort();
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [active, managing, preview, retryRecovery]);

  // VS Code owns unsaved-file prompts. An unconditional outer beforeunload
  // handler can cancel navigation after the iframe has disposed its connection.

  async function launch(project?: WorkspaceProject) {
    if (operation.current) return;
    const controller = new AbortController();
    operation.current = controller;
    setBusy(true);
    setOpeningProject(project?.name ?? null);
    setError("");
    try {
      const next = project ? await openWorkspaceProject(project.name, controller.signal)
        : await createWorkspaceProject(name.trim(), controller.signal);
      if (controller.signal.aborted) return;
      setPreview(next);
      setRecoveryError("");
      setRecovering(false);
      setManaging(false);
      setCreating(false);
      setName("");
      setRefresh(value => value + 1);
    } catch (cause) {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : t("workspace.operationFailed"));
    } finally {
      operation.current = null;
      if (!controller.signal.aborted) { setBusy(false); setOpeningProject(null); }
    }
  }

  return (
    <section ref={container} className={managing ? "workspace-project-host" : `workspace-create${fullscreen ? " is-fullscreen" : ""}`} hidden={!active} aria-label={t("workspace.title")}>
      {!managing && <header className="workspace-create__header">
        <PageBackButton label={t("workspace.back")} onClick={() => { setManaging(true); setFullscreen(false); setCreating(false); setError(""); onReturnToProjects?.(); }} />
        <div className="workspace-create__heading"><h1>{preview?.name}</h1></div>
        {!managing && preview && <span className="workspace-create__countdown" role="timer" aria-label={t("workspace.restart", { countdown })} title={preview.expireAt ? t("workspace.expiresAt", { date: new Date(preview.expireAt).toLocaleString(i18n.language) }) : undefined}>{t("workspace.restart", { countdown })}</span>}
        {!managing && <button className="workspace-create__fullscreen" type="button" onClick={() => setFullscreen(value => !value)} aria-label={fullscreen ? t("workspace.exitFullscreen") : t("workspace.fullscreen")} title={fullscreen ? t("workspace.exitFullscreenHint") : t("workspace.fullscreen")}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d={fullscreen ? "M4 9h5V4m6 0v5h5M4 15h5v5m6 0v-5h5" : "M9 4H4v5m11-5h5v5M4 15v5h5m6 0h5v-5"} />
          </svg>
        </button>}
      </header>}
      <div className="workspace-create__surface" hidden={managing}>
        {preview && <iframe key={`${preview.sessionId}:${preview.name}:${editorGeneration}`} src={`${preview.url}${preview.url.includes("?") ? "&" : "?"}studio-entry-version=7`} title={`${preview.name} VS Code`}
          referrerPolicy="no-referrer" allow="clipboard-read; clipboard-write; fullscreen"
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads allow-modals allow-pointer-lock" />}
        {(recovering || recoveryError) && <div className="workspace-create__recovery" role={recoveryError ? "alert" : "status"}>
          {recovering ? <TextShimmer>{t("workspace.recovering")}</TextShimmer> : <>
            <p>{recoveryError}</p>
            <Button color="secondary" variant="soft" size="sm" onClick={() => setRetryRecovery(value => value + 1)}>{t("workspace.retry")}</Button>
          </>}
        </div>}
      </div>
      {managing && <WorkspaceCollectionLayout section="projects" onWorkspace={() => onBack("workspaces")} onEnvironment={() => onBack("environments")} onProjects={() => {}} actions={<>
            <ResourceSearch aria-label={t("workspace.search")} placeholder={t("workspace.search")} value={query} onChange={event => setQuery(event.target.value)} />
      </>}>
        <ResourceResults>
          {listError && <p className="workspace-create__error" role="alert">{listError}</p>}
          {error && !creating && <p className="workspace-create__error" role="alert">{error}</p>}
          {listing ? <ResourceLoadingState /> : <ResourceGrid>
            {!query.trim() && <ResourceCreateCard aria-label={t("workspace.newTitle")} disabled={busy} icon={<ProjectAddIcon />} onClick={() => { setName(""); setError(""); setCreating(true); }}>{t("workspace.new")}</ResourceCreateCard>}
            {projects.filter(project => project.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())).map(project => (
              <LibraryResourceCard key={project.name} title={project.name} description={project.fileCount === undefined ? t("workspace.readingStats") : [t("workspace.files", { count: project.fileCount }), ...(project.directoryCount ? [t("workspace.directories", { count: project.directoryCount })] : [])].join(t("workspace.separator"))}
                metadata={[{ label: t("workspace.createdAt"), value: openingProject === project.name ? t("workspace.opening") : project.createdAt ? formatRelativeTimeLabel(project.createdAt, Date.now(), i18n.language) : t("workspace.unknownCreatedAt"), title: project.createdAt ? new Date(project.createdAt).toLocaleString(i18n.language) : undefined }]}
                detailAction={{ label: t("workspace.open"), disabled: busy, onClick: () => void launch(project) }}
                action={{ label: t("workspace.open"), icon: "arrow", disabled: busy, onClick: () => void launch(project) }} />
            ))}
          </ResourceGrid>}
          {!listing && query.trim() && !projects.some(project => project.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())) && <p className="workspace-create__empty">{t("workspace.empty")}</p>}
        </ResourceResults>
      </WorkspaceCollectionLayout>}
      {creating && <ProjectNameDialog name={name} onName={setName} busy={busy} error={error}
        onCancel={() => { if (!busy) setCreating(false); }} onSubmit={() => { if (!composing.current) void launch(); }} composing={composing} />}
    </section>
  );
}

function ProjectNameDialog({ name, onName, busy, error, onCancel, onSubmit, composing }: {
  name: string; onName: (value: string) => void; busy: boolean; error: string;
  onCancel: () => void; onSubmit: () => void; composing: { current: boolean };
}) {
  const { t } = useTranslation("create");
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.current?.showModal();
    return () => { if (previousFocus?.isConnected) previousFocus.focus(); };
  }, []);
  return <dialog ref={dialog} className="workspace-project-dialog" aria-labelledby="project-dialog-title"
    onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}>
    <form onSubmit={event => { event.preventDefault(); onSubmit(); }}>
      <header><h2 id="project-dialog-title">{t("workspace.newTitle")}</h2>
        <button type="button" className="workspace-create__fullscreen" aria-label={t("workspace.close")} disabled={busy} onClick={onCancel}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
        </button>
      </header>
      <div className="workspace-project-dialog__body">
        <label htmlFor="workspace-project-name">{t("workspace.name")}</label>
        <input id="workspace-project-name" value={name} onChange={event => onName(event.target.value)} autoFocus
          placeholder={t("workspace.placeholder")} pattern={"[A-Za-z][A-Za-z0-9_\\-]{0,63}"} maxLength={64} required disabled={busy} aria-describedby="workspace-name-help"
          onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }}
          onKeyDown={event => { if (event.key === "Enter" && (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229)) event.preventDefault(); }} />
        <p id="workspace-name-help">{t("workspace.nameHelp")}</p>
        {error && <p className="workspace-create__error" role="alert">{error}</p>}
      </div>
      <footer>
        <Button color="secondary" variant="soft" size="sm" type="button" disabled={busy} onClick={onCancel}>{t("workspace.cancel")}</Button>
        <Button color="primary" variant="solid" size="sm" type="submit" loading={busy} disabled={busy || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(name.trim())}>{t("workspace.create")}</Button>
      </footer>
    </form>
  </dialog>;
}

function ProjectAddIcon() {
  return <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true"><path d="M8 3.25v9.5M3.25 8h9.5" /></svg>;
}
