import {
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type SVGProps,
} from "react";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { EmptyMessage } from "@openai/apps-sdk-ui/components/EmptyMessage";
import { Input } from "@openai/apps-sdk-ui/components/Input";
import { Textarea } from "@openai/apps-sdk-ui/components/Textarea";
import { useTranslation } from "react-i18next";

import {
  createWorkspace,
  deleteWorkspace,
  listEnvironments,
  listWorkspaces,
  updateWorkspace,
  type StudioEnvironment,
  type StudioWorkspace,
  type WorkspaceInput,
} from "../adk/client";
import { environmentLanguageLabel } from "./environmentModel";
import { LibraryResourceCard } from "./LibraryResourceCard";
import {
  ResourceCreateCard,
  ResourceDetailLayout,
  ResourceDetailSectionHeader,
  ResourceDetailSummary,
  ResourceGrid,
  ResourceLoadingState,
  ResourcePageHeader,
  ResourcePageShell,
  ResourceResults,
  ResourceSearch,
  ResourceTabs,
  ResourceToolbar,
} from "./ResourceCollection";
import { StudioConfirmDialog } from "./StudioConfirmDialog";
import {
  EnvironmentCenter,
  type EnvironmentClipboardImportRequest,
} from "./EnvironmentCenter";
import type { CloudProvider } from "../adk/cloudProvider";
import "./WorkspaceCenter.css";

type WorkspaceView =
  | { kind: "list" }
  | { kind: "detail"; workspaceId: string | null };

function AddIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true" {...props}>
      <path d="M8 3.25v9.5M3.25 8h9.5" />
    </svg>
  );
}

function WorkspaceEmptyIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <rect x="4.5" y="7" width="23" height="18" rx="3" />
      <path d="M10 7V5.5A1.5 1.5 0 0 1 11.5 4h4A1.5 1.5 0 0 1 17 5.5V7M9 13h5v5H9zM18 13h5M18 17h5M9 22h14" />
    </svg>
  );
}

function formatUpdatedAt(value: string, locale: string): string {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return value;
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(timestamp);
}

function availableEnvironmentCount(
  workspace: StudioWorkspace,
  environmentsById: Map<string, StudioEnvironment>,
): number {
  return workspace.environmentIds.reduce((count, id) => (
    environmentsById.get(id)?.latestVersion?.status === "available" ? count + 1 : count
  ), 0);
}

function WorkspaceEditor({
  workspace,
  environments,
  onBack,
  onSave,
  onDelete,
}: {
  workspace?: StudioWorkspace;
  environments: StudioEnvironment[];
  onBack: () => void;
  onSave: (input: WorkspaceInput) => Promise<void>;
  onDelete: (() => void) | null;
}) {
  const { t, i18n } = useTranslation("ui");
  const [name, setName] = useState(workspace?.name ?? "");
  const [description, setDescription] = useState(workspace?.description ?? "");
  const [environmentIds, setEnvironmentIds] = useState<string[]>(workspace?.environmentIds ?? []);
  const [environmentQuery, setEnvironmentQuery] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const normalizedQuery = environmentQuery.trim().toLocaleLowerCase();
  const visibleEnvironments = environments.filter((environment) => (
    `${environment.name} ${environment.description} ${environmentLanguageLabel(environment.language)}`
      .toLocaleLowerCase()
      .includes(normalizedQuery)
  ));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim() || saving) return;
    setSaving(true);
    setError("");
    try {
      await onSave({
        name: name.trim(),
        description: description.trim(),
        environmentIds,
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setSaving(false);
    }
  };

  return (
    <ResourcePageShell className="workspace-center" aria-label={workspace ? t("workspace.detail") : t("workspace.create")}>
      <ResourceDetailLayout
        title={workspace ? workspace.name : t("workspace.create")}
        description={t("workspace.editorDescription")}
        identitySeed={workspace?.name || t("workspace.create")}
        backLabel={t("workspace.backToList")}
        onBack={onBack}
        actions={(
          <>
            {onDelete ? <button type="button" className="is-danger" onClick={onDelete}>{t("common.delete")}</button> : null}
            <button type="submit" form="workspace-form" disabled={saving || !name.trim()}>
              {saving ? t("common.saving") : t("common.save")}
            </button>
          </>
        )}
      >
          {workspace ? (
            <ResourceDetailSummary>
              <div><dt>{t("common.environment")}</dt><dd>{t("workspace.environmentCount", { count: environmentIds.length })}</dd></div>
              <div><dt>{t("workspace.createdAt")}</dt><dd>{formatUpdatedAt(workspace.createdAt, i18n.resolvedLanguage ?? i18n.language)}</dd></div>
              <div><dt>{t("workspace.updatedAt")}</dt><dd>{formatUpdatedAt(workspace.updatedAt, i18n.resolvedLanguage ?? i18n.language)}</dd></div>
            </ResourceDetailSummary>
          ) : null}

          <form id="workspace-form" className="workspace-form" onSubmit={submit}>
            <section className="workspace-fields" aria-label={t("workspace.basicInfo")}>
              <label>
                <span>{t("common.name")}</span>
                <Input value={name} maxLength={128} autoFocus onChange={(event) => setName(event.target.value)} placeholder={t("workspace.namePlaceholder")} />
              </label>
              <label>
                <span>{t("common.description")}</span>
                <Textarea value={description} maxLength={2000} onChange={(event) => setDescription(event.target.value)} placeholder={t("workspace.descriptionPlaceholder")} />
              </label>
            </section>

            <section className="workspace-environments">
              <ResourceDetailSectionHeader
                title={t("common.environment")}
                description={t("workspace.selectedEnvironmentCount", { count: environmentIds.length })}
                actions={(
                  <ResourceSearch
                    aria-label={t("workspace.searchAvailableEnvironments")}
                    value={environmentQuery}
                    onChange={(event) => setEnvironmentQuery(event.target.value)}
                    placeholder={t("workspace.searchEnvironments")}
                  />
                )}
              />
              {environments.length === 0 ? (
                <div className="workspace-environment-empty">
                  <p>{t("workspace.noAvailableEnvironments")}</p>
                  <span>{t("workspace.createEnvironmentFirst")}</span>
                </div>
              ) : visibleEnvironments.length === 0 ? (
                <div className="workspace-environment-empty">
                  <p>{t("workspace.noMatchingEnvironments")}</p>
                  <span>{t("workspace.tryAnotherName")}</span>
                </div>
              ) : (
                <div className="workspace-environment-list">
                  {visibleEnvironments.map((environment) => {
                    const selected = environmentIds.includes(environment.id);
                    const status = environment.latestVersion?.status === "available"
                      ? t("workspace.environmentStatus.available")
                      : environment.latestVersion
                        ? t("workspace.environmentStatus.building")
                        : t("workspace.environmentStatus.notBuilt");
                    return (
                      <label key={environment.id} className={`workspace-environment-option${selected ? " is-selected" : ""}`}>
                        <input
                          type="checkbox"
                          checked={selected}
                          onChange={() => setEnvironmentIds((current) => selected
                            ? current.filter((id) => id !== environment.id)
                            : [...current, environment.id])}
                        />
                        <span className="workspace-environment-option__copy">
                          <strong title={environment.name}>{environment.name}</strong>
                          <span>{environmentLanguageLabel(environment.language)} · {status}</span>
                        </span>
                        <span className="workspace-environment-option__action">{selected ? t("workspace.added") : t("common.add")}</span>
                      </label>
                    );
                  })}
                </div>
              )}
            </section>
            {error ? <p className="workspace-form-error" role="alert">{error}</p> : null}
          </form>
      </ResourceDetailLayout>
    </ResourcePageShell>
  );
}

function WorkspaceList({ onEnvironment }: { onEnvironment: () => void }) {
  const { t, i18n } = useTranslation("ui");
  const [workspaces, setWorkspaces] = useState<StudioWorkspace[]>([]);
  const [environments, setEnvironments] = useState<StudioEnvironment[]>([]);
  const [view, setView] = useState<WorkspaceView>({ kind: "list" });
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [statusError, setStatusError] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<StudioWorkspace | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const deferredQuery = useDeferredValue(query);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setLoadError("");
    void Promise.all([
      listWorkspaces(controller.signal),
      listEnvironments(controller.signal),
    ]).then(([nextWorkspaces, nextEnvironments]) => {
      setWorkspaces(nextWorkspaces);
      setEnvironments(nextEnvironments);
    }).catch((cause) => {
      if ((cause as Error)?.name !== "AbortError") {
        console.warn("Unable to load Studio workspaces", cause);
        setLoadError(t("workspace.loadFailed"));
      }
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [reloadKey, t]);

  useEffect(() => {
    if (!statusMessage || statusError) return;
    const timer = window.setTimeout(() => setStatusMessage(""), 2800);
    return () => window.clearTimeout(timer);
  }, [statusError, statusMessage]);

  const environmentsById = useMemo(
    () => new Map(environments.map((environment) => [environment.id, environment])),
    [environments],
  );
  const visibleWorkspaces = useMemo(() => {
    const normalized = deferredQuery.trim().toLocaleLowerCase();
    if (!normalized) return workspaces;
    return workspaces.filter((workspace) => {
      const environmentNames = workspace.environmentIds
        .map((id) => environmentsById.get(id)?.name ?? "")
        .join(" ");
      return `${workspace.name} ${workspace.description} ${environmentNames}`
        .toLocaleLowerCase()
        .includes(normalized);
    });
  }, [deferredQuery, environmentsById, workspaces]);

  const editingWorkspace = view.kind === "detail" && view.workspaceId
    ? workspaces.find((workspace) => workspace.id === view.workspaceId)
    : undefined;

  if (view.kind === "detail") {
    return (
      <WorkspaceEditor
        key={view.workspaceId ?? "new"}
        workspace={editingWorkspace}
        environments={environments}
        onBack={() => setView({ kind: "list" })}
        onDelete={editingWorkspace ? () => setDeleteTarget(editingWorkspace) : null}
        onSave={async (input) => {
          const saved = editingWorkspace
            ? await updateWorkspace(editingWorkspace.id, input)
            : await createWorkspace(input);
          setWorkspaces((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
          setStatusError(false);
          setStatusMessage(t("workspace.saved", { name: saved.name }));
          setView({ kind: "list" });
        }}
      />
    );
  }

  return (
    <ResourcePageShell className="workspace-center" aria-label={t("workspace.title")}>
      <ResourcePageHeader title={t("workspace.title")} />
      <ResourceToolbar>
        <ResourceTabs
          items={[
            { id: "workspaces", label: t("workspace.title") },
            { id: "environments", label: t("common.environment") },
          ]}
          value="workspaces"
          onChange={(value) => {
            if (value === "environments") onEnvironment();
          }}
          ariaLabel={t("workspace.resourceType")}
          idPrefix="workspace-center"
        />
        <div className="resource-toolbar__actions">
          {statusMessage ? (
            <span className={`workspace-status${statusError ? " is-error" : ""}`} role={statusError ? "alert" : "status"} aria-live="polite">
              {statusMessage}
            </span>
          ) : null}
          <ResourceSearch aria-label={t("workspace.searchWorkspaces")} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("workspace.searchWorkspaces")} />
        </div>
      </ResourceToolbar>
      <ResourceResults aria-live="polite">
        {loading ? (
          <ResourceLoadingState />
        ) : loadError ? (
          <div className="workspace-load-error" role="alert">
            <p>{loadError}</p>
            <Button color="secondary" variant="soft" size="sm" onClick={() => setReloadKey((key) => key + 1)}>{t("common.reload")}</Button>
          </div>
        ) : visibleWorkspaces.length === 0 && query.trim() ? (
          <div className="workspace-empty">
            <EmptyMessage fill="none">
              <EmptyMessage.Icon><WorkspaceEmptyIcon /></EmptyMessage.Icon>
              <EmptyMessage.Title>{t("workspace.noMatchingWorkspaces")}</EmptyMessage.Title>
              <EmptyMessage.Description>{t("workspace.tryAnotherNameOrEnvironment")}</EmptyMessage.Description>
            </EmptyMessage>
          </div>
        ) : (
          <ResourceGrid>
            {!query.trim() ? (
              <ResourceCreateCard aria-label={t("workspace.create")} icon={<AddIcon />} onClick={() => setView({ kind: "detail", workspaceId: null })}>
                {t("workspace.create")}
              </ResourceCreateCard>
            ) : null}
            {visibleWorkspaces.map((workspace) => {
              const available = availableEnvironmentCount(workspace, environmentsById);
              const missing = workspace.environmentIds.filter((id) => !environmentsById.has(id)).length;
              return (
                <LibraryResourceCard
                  key={workspace.id}
                  className="workspace-card"
                  title={workspace.name}
                  status={<Badge color={missing ? "danger" : available === workspace.environmentIds.length && available > 0 ? "success" : "secondary"} size="sm">
                    {workspace.environmentIds.length === 0
                      ? t("workspace.noEnvironmentAdded")
                      : missing
                        ? t("workspace.environmentMissing")
                        : t("workspace.availableFraction", { available, total: workspace.environmentIds.length })}
                  </Badge>}
                  description={workspace.description || t("common.noDescription")}
                  metadata={[
                    { label: t("common.environment"), value: t("workspace.environmentCount", { count: workspace.environmentIds.length }) },
                    { label: t("workspace.available"), value: t("workspace.availableCount", { count: available }) },
                    { label: t("workspace.updated"), value: formatUpdatedAt(workspace.updatedAt, i18n.resolvedLanguage ?? i18n.language) },
                  ]}
                  detailAction={{ label: t("common.manage"), onClick: () => setView({ kind: "detail", workspaceId: workspace.id }) }}
                  action={{ label: t("workspace.addEnvironment"), icon: "plus", onClick: () => setView({ kind: "detail", workspaceId: workspace.id }) }}
                />
              );
            })}
          </ResourceGrid>
        )}
      </ResourceResults>

      {deleteTarget ? (
        <StudioConfirmDialog
          title={t("workspace.deleteTitle")}
          description={t("workspace.deleteDescription", { name: deleteTarget.name })}
          confirmLabel={t("common.delete")}
          variant="danger"
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => {
            const target = deleteTarget;
            setDeleteTarget(null);
            void deleteWorkspace(target.id).then(() => {
              setWorkspaces((current) => current.filter((workspace) => workspace.id !== target.id));
              setStatusError(false);
              setStatusMessage(t("workspace.deleted", { name: target.name }));
              setView({ kind: "list" });
            }).catch((cause) => {
              setStatusError(true);
              setStatusMessage(cause instanceof Error ? cause.message : String(cause));
            });
          }}
        />
      ) : null}
    </ResourcePageShell>
  );
}

export function WorkspaceCenter({ cloudProvider }: { cloudProvider: CloudProvider }) {
  const { t } = useTranslation("ui");
  const [section, setSection] = useState<"workspaces" | "environments">("workspaces");
  const [clipboardImport, setClipboardImport] = useState<EnvironmentClipboardImportRequest | null>(null);
  const [clipboardReadError, setClipboardReadError] = useState("");
  const clipboardRequestKeyRef = useRef(0);

  const openEnvironments = () => {
    clipboardRequestKeyRef.current += 1;
    const key = clipboardRequestKeyRef.current;
    setClipboardReadError("");

    let clipboardRead: Promise<string> | null = null;
    if (typeof navigator !== "undefined" && navigator.clipboard?.readText) {
      try {
        // Start while the tab click still has a user activation.
        clipboardRead = navigator.clipboard.readText();
      } catch {
        setClipboardReadError(t("workspace.clipboardPermissionError"));
      }
    } else {
      setClipboardReadError(t("workspace.clipboardUnsupported"));
    }

    setSection("environments");
    if (!clipboardRead) return;
    void clipboardRead.then(async (text) => {
      if (clipboardRequestKeyRef.current !== key) return;
      if (text.trim()) {
        setClipboardImport({ key, text });
        return;
      }
      try {
        const permission = await navigator.permissions?.query({ name: "clipboard-read" as PermissionName });
        if (clipboardRequestKeyRef.current === key && permission?.state === "denied") {
          setClipboardReadError(t("workspace.clipboardPermissionError"));
        }
      } catch {
        // Some browsers expose clipboard access without the Permissions API.
      }
    }).catch(() => {
      if (clipboardRequestKeyRef.current !== key) return;
      setClipboardReadError(t("workspace.clipboardPermissionError"));
    });
  };

  if (section === "environments") {
    return (
      <EnvironmentCenter
        cloudProvider={cloudProvider}
        onWorkspace={() => setSection("workspaces")}
        clipboardImport={clipboardImport}
        clipboardReadError={clipboardReadError}
      />
    );
  }
  return <WorkspaceList onEnvironment={openEnvironments} />;
}
