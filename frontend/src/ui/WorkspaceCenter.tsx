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

function formatUpdatedAt(value: string): string {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return value;
  return new Intl.DateTimeFormat("zh-CN", {
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
    <ResourcePageShell className="workspace-center" aria-label={workspace ? "工作区详情" : "新建工作区"}>
      <ResourceDetailLayout
        title={workspace ? workspace.name : "新建工作区"}
        description="将常用环境组合在一起；同一个环境可以加入多个工作区。"
        identitySeed={workspace?.name || "新建工作区"}
        backLabel="返回工作区列表"
        onBack={onBack}
        actions={(
          <>
            {onDelete ? <button type="button" className="is-danger" onClick={onDelete}>删除</button> : null}
            <button type="submit" form="workspace-form" disabled={saving || !name.trim()}>
              {saving ? "保存中" : "保存"}
            </button>
          </>
        )}
      >
          {workspace ? (
            <ResourceDetailSummary>
              <div><dt>环境</dt><dd>{environmentIds.length} 个</dd></div>
              <div><dt>创建时间</dt><dd>{formatUpdatedAt(workspace.createdAt)}</dd></div>
              <div><dt>最近更新</dt><dd>{formatUpdatedAt(workspace.updatedAt)}</dd></div>
            </ResourceDetailSummary>
          ) : null}

          <form id="workspace-form" className="workspace-form" onSubmit={submit}>
            <section className="workspace-fields" aria-label="基本信息">
              <label>
                <span>名称</span>
                <Input value={name} maxLength={128} autoFocus onChange={(event) => setName(event.target.value)} placeholder="例如：内容生产" />
              </label>
              <label>
                <span>描述</span>
                <Textarea value={description} maxLength={2000} onChange={(event) => setDescription(event.target.value)} placeholder="说明这个工作区的用途" />
              </label>
            </section>

            <section className="workspace-environments">
              <ResourceDetailSectionHeader
                title="环境"
                description={`已选择 ${environmentIds.length} 个，可在其他工作区中继续复用`}
                actions={(
                  <ResourceSearch
                    aria-label="搜索可用环境"
                    value={environmentQuery}
                    onChange={(event) => setEnvironmentQuery(event.target.value)}
                    placeholder="搜索环境"
                  />
                )}
              />
              {environments.length === 0 ? (
                <div className="workspace-environment-empty">
                  <p>还没有可添加的环境</p>
                  <span>请先在“环境”页面创建并构建环境。</span>
                </div>
              ) : visibleEnvironments.length === 0 ? (
                <div className="workspace-environment-empty">
                  <p>没有匹配的环境</p>
                  <span>请尝试搜索其他名称。</span>
                </div>
              ) : (
                <div className="workspace-environment-list">
                  {visibleEnvironments.map((environment) => {
                    const selected = environmentIds.includes(environment.id);
                    const status = environment.latestVersion?.status === "available" ? "可用" : environment.latestVersion ? "构建中" : "未构建";
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
                        <span className="workspace-environment-option__action">{selected ? "已添加" : "添加"}</span>
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
        setLoadError(cause instanceof Error ? cause.message : String(cause));
      }
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [reloadKey]);

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
          setStatusMessage(`已保存工作区“${saved.name}”`);
          setView({ kind: "list" });
        }}
      />
    );
  }

  return (
    <ResourcePageShell className="workspace-center" aria-label="工作区">
      <ResourcePageHeader title="工作区" />
      <ResourceToolbar>
        <ResourceTabs
          items={[
            { id: "workspaces", label: "工作区" },
            { id: "environments", label: "环境" },
          ]}
          value="workspaces"
          onChange={(value) => {
            if (value === "environments") onEnvironment();
          }}
          ariaLabel="工作区资源类型"
          idPrefix="workspace-center"
        />
        <div className="resource-toolbar__actions">
          {statusMessage ? (
            <span className={`workspace-status${statusError ? " is-error" : ""}`} role={statusError ? "alert" : "status"} aria-live="polite">
              {statusMessage}
            </span>
          ) : null}
          <ResourceSearch aria-label="搜索工作区" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索工作区" />
        </div>
      </ResourceToolbar>
      <ResourceResults aria-live="polite">
        {loading ? (
          <ResourceLoadingState />
        ) : loadError ? (
          <div className="workspace-load-error" role="alert">
            <p>{loadError}</p>
            <Button color="secondary" variant="soft" size="sm" onClick={() => setReloadKey((key) => key + 1)}>重新加载</Button>
          </div>
        ) : visibleWorkspaces.length === 0 && query.trim() ? (
          <div className="workspace-empty">
            <EmptyMessage fill="none">
              <EmptyMessage.Icon><WorkspaceEmptyIcon /></EmptyMessage.Icon>
              <EmptyMessage.Title>没有匹配的工作区</EmptyMessage.Title>
              <EmptyMessage.Description>请尝试搜索其他名称或环境</EmptyMessage.Description>
            </EmptyMessage>
          </div>
        ) : (
          <ResourceGrid>
            {!query.trim() ? (
              <ResourceCreateCard aria-label="新建工作区" icon={<AddIcon />} onClick={() => setView({ kind: "detail", workspaceId: null })}>
                新建工作区
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
                    {workspace.environmentIds.length === 0 ? "未添加环境" : missing ? "环境缺失" : `${available}/${workspace.environmentIds.length} 可用`}
                  </Badge>}
                  description={workspace.description || "暂无描述"}
                  metadata={[
                    { label: "环境", value: `${workspace.environmentIds.length} 个环境` },
                    { label: "可用", value: `${available} 个可用` },
                    { label: "更新", value: formatUpdatedAt(workspace.updatedAt) },
                  ]}
                  detailAction={{ label: "管理", onClick: () => setView({ kind: "detail", workspaceId: workspace.id }) }}
                  action={{ label: "添加环境", icon: "plus", onClick: () => setView({ kind: "detail", workspaceId: workspace.id }) }}
                />
              );
            })}
          </ResourceGrid>
        )}
      </ResourceResults>

      {deleteTarget ? (
        <StudioConfirmDialog
          title="删除工作区"
          description={`确定删除工作区“${deleteTarget.name}”吗？环境本身不会被删除。`}
          confirmLabel="删除"
          variant="danger"
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => {
            const target = deleteTarget;
            setDeleteTarget(null);
            void deleteWorkspace(target.id).then(() => {
              setWorkspaces((current) => current.filter((workspace) => workspace.id !== target.id));
              setStatusError(false);
              setStatusMessage(`已删除工作区“${target.name}”`);
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
        setClipboardReadError("未能读取剪贴板。请允许剪贴板权限，或点击“导入环境”后手动粘贴分享码。");
      }
    } else {
      setClipboardReadError("当前浏览器无法自动读取剪贴板；请点击“导入环境”后手动粘贴分享码。");
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
          setClipboardReadError("未能读取剪贴板。请允许剪贴板权限，或点击“导入环境”后手动粘贴分享码。");
        }
      } catch {
        // Some browsers expose clipboard access without the Permissions API.
      }
    }).catch(() => {
      if (clipboardRequestKeyRef.current !== key) return;
      setClipboardReadError("未能读取剪贴板。请允许剪贴板权限，或点击“导入环境”后手动粘贴分享码。");
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
