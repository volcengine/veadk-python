import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type {
  SessionEnvironmentMountSelection,
  StudioEnvironment,
  StudioWorkspace,
} from "../adk/client";
import { environmentLanguageLabel } from "./environmentModel";

function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m7 7 10 10M17 7 7 17" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="10.8" cy="10.8" r="5.8" stroke="currentColor" strokeWidth="1.7" />
      <path d="m15.2 15.2 4 4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function EnvironmentIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 7.25A2.25 2.25 0 0 1 7.25 5h9.5A2.25 2.25 0 0 1 19 7.25v9.5A2.25 2.25 0 0 1 16.75 19h-9.5A2.25 2.25 0 0 1 5 16.75v-9.5Z" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8.5 9.25 11 12l-2.5 2.75M12.75 14.75h2.75" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function WorkspaceIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4.75 7.25A2.25 2.25 0 0 1 7 5h3l1.5 2h5.5a2.25 2.25 0 0 1 2.25 2.25v7.5A2.25 2.25 0 0 1 17 19H7a2.25 2.25 0 0 1-2.25-2.25v-9.5Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
      <path d="M8 11.25h8M8 14.75h5.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function AddIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 6.5v11M6.5 12h11" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function RemoveIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="m7 7 10 10M17 7 7 17" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="m3.5 8.25 2.75 2.75 6.25-6.25" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function mountKey(value: SessionEnvironmentMountSelection): string {
  return `${value.environment_id}\u0000${value.environment_version_id}`;
}

function environmentMount(environment: StudioEnvironment): SessionEnvironmentMountSelection | null {
  return environment.latestVersion
    ? {
        environment_id: environment.id,
        environment_version_id: environment.latestVersion.versionId,
      }
    : null;
}

function workspaceEnvironmentMounts(
  workspace: StudioWorkspace,
  environmentsById: ReadonlyMap<string, StudioEnvironment>,
): SessionEnvironmentMountSelection[] {
  return workspace.environmentIds.flatMap((environmentId) => {
    const environment = environmentsById.get(environmentId);
    const mount = environment ? environmentMount(environment) : null;
    return mount ? [mount] : [];
  });
}

function EnvironmentPickerDialog({
  environments,
  workspaces,
  value,
  selectedWorkspaceIds,
  loading,
  error,
  onConfirm,
  onClose,
}: {
  environments: StudioEnvironment[];
  workspaces: StudioWorkspace[];
  value: readonly SessionEnvironmentMountSelection[];
  selectedWorkspaceIds: readonly string[];
  loading: boolean;
  error: string;
  onConfirm: (
    value: SessionEnvironmentMountSelection[],
    workspaceIds: string[],
  ) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const titleId = useId();
  const environmentsById = useMemo(
    () => new Map(environments.map((environment) => [environment.id, environment])),
    [environments],
  );
  const [draftWorkspaceIds, setDraftWorkspaceIds] = useState(
    () => new Set(selectedWorkspaceIds),
  );
  const [draftEnvironmentKeys, setDraftEnvironmentKeys] = useState(() => {
    const coveredEnvironmentIds = new Set(
      workspaces
        .filter((workspace) => selectedWorkspaceIds.includes(workspace.id))
        .flatMap((workspace) => workspace.environmentIds),
    );
    return new Set(value
      .filter((mount) => !coveredEnvironmentIds.has(mount.environment_id))
      .map(mountKey));
  });
  const coveredEnvironmentIds = useMemo(() => new Set(
    workspaces
      .filter((workspace) => draftWorkspaceIds.has(workspace.id))
      .flatMap((workspace) => workspace.environmentIds),
  ), [draftWorkspaceIds, workspaces]);
  const selectedKeys = useMemo(() => {
    const keys = new Set(draftEnvironmentKeys);
    for (const workspace of workspaces) {
      if (!draftWorkspaceIds.has(workspace.id)) continue;
      for (const mount of workspaceEnvironmentMounts(workspace, environmentsById)) {
        keys.add(mountKey(mount));
      }
    }
    return keys;
  }, [draftEnvironmentKeys, draftWorkspaceIds, environmentsById, workspaces]);
  const filteredEnvironments = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return environments;
    return environments.filter((environment) => (
      `${environment.name} ${environment.description} ${environmentLanguageLabel(environment.language)}`
        .toLocaleLowerCase()
        .includes(normalized)
    ));
  }, [environments, query]);
  const filteredWorkspaces = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return workspaces;
    return workspaces.filter((workspace) => {
      const environmentNames = workspace.environmentIds
        .map((id) => environmentsById.get(id)?.name ?? "")
        .join(" ");
      return `${workspace.name} ${workspace.description} ${environmentNames}`
        .toLocaleLowerCase()
        .includes(normalized);
    });
  }, [environmentsById, query, workspaces]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  const toggle = (environment: StudioEnvironment) => {
    const mount = environmentMount(environment);
    if (!mount) return;
    const key = mountKey(mount);
    if (coveredEnvironmentIds.has(environment.id)) return;
    setDraftEnvironmentKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const toggleWorkspace = (workspace: StudioWorkspace) => {
    const mounts = workspaceEnvironmentMounts(workspace, environmentsById);
    if (mounts.length === 0) return;
    setDraftWorkspaceIds((current) => {
      const next = new Set(current);
      if (next.has(workspace.id)) next.delete(workspace.id);
      else next.add(workspace.id);
      return next;
    });
    setDraftEnvironmentKeys((current) => {
      const next = new Set(current);
      for (const mount of mounts) next.delete(mountKey(mount));
      return next;
    });
  };

  const confirm = () => {
    const existingMounts = new Map(value.map((mount) => [mountKey(mount), mount]));
    onConfirm(environments.flatMap((environment) => {
      const mount = environmentMount(environment);
      if (!mount || !selectedKeys.has(mountKey(mount))) return [];
      const existing = existingMounts.get(mountKey(mount));
      return [{
        ...mount,
        mount_instance_id: existing?.mount_instance_id || crypto.randomUUID(),
      }];
    }), [...draftWorkspaceIds]);
    onClose();
  };

  return createPortal(
    <div className="studio-tool-dialog-layer">
      <button
        type="button"
        className="studio-tool-dialog-scrim"
        aria-label="关闭环境弹窗"
        onClick={onClose}
      />
      <section
        className="studio-tool-dialog session-environment-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header className="studio-tool-dialog-head">
          <span className="studio-tool-dialog-mark"><EnvironmentIcon /></span>
          <div>
            <h2 id={titleId}>添加环境</h2>
            <p>选择当前会话允许 Agent 使用的 Sandbox 环境</p>
          </div>
          <button
            type="button"
            className="studio-tool-dialog-close"
            aria-label="关闭添加环境"
            onClick={onClose}
          >
            <CloseIcon />
          </button>
        </header>
        <div className="studio-tool-dialog-body">
          <label className="studio-tool-search">
            <SearchIcon />
            <input
              value={query}
              aria-label="搜索环境"
              placeholder="搜索环境名称或能力"
              autoFocus
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <div className="studio-tool-picker session-environment-picker" role="group" aria-label="可用环境与工作区">
            {loading ? (
              <div className="studio-tool-empty">正在读取可用环境…</div>
            ) : error ? (
              <div className="studio-tool-empty">{error}</div>
            ) : filteredEnvironments.length === 0 && filteredWorkspaces.length === 0 ? (
              <div className="studio-tool-empty">没有匹配的环境或工作区</div>
            ) : (
              <>
                {filteredWorkspaces.length > 0 && (
                  <section className="session-environment-picker__group" aria-labelledby={`${titleId}-workspaces`}>
                    <h3 id={`${titleId}-workspaces`}>工作区</h3>
                    {filteredWorkspaces.map((workspace) => {
                      const mounts = workspaceEnvironmentMounts(workspace, environmentsById);
                      const active = draftWorkspaceIds.has(workspace.id);
                      const disabled = mounts.length === 0;
                      return (
                        <label key={workspace.id} className={`studio-tool-option session-environment-option is-workspace${active ? " is-selected" : ""}${disabled ? " is-disabled" : ""}`}>
                          <span className="studio-tool-option-icon"><WorkspaceIcon /></span>
                          <span className="studio-tool-option-copy">
                            <strong>{workspace.name}</strong>
                            <span>{workspace.description || "复用工作区中的全部可用环境"}</span>
                            <small>{mounts.length} 个可用环境</small>
                          </span>
                          <input
                            type="checkbox"
                            checked={active}
                            disabled={disabled}
                            aria-label={`选择工作区 ${workspace.name}`}
                            onChange={() => toggleWorkspace(workspace)}
                          />
                          <span className="session-environment-check" aria-hidden="true"><CheckIcon /></span>
                        </label>
                      );
                    })}
                  </section>
                )}
                {filteredEnvironments.length > 0 && (
                  <section className="session-environment-picker__group" aria-labelledby={`${titleId}-environments`}>
                    <h3 id={`${titleId}-environments`}>环境</h3>
                    {filteredEnvironments.map((environment) => {
                      const mount = environmentMount(environment);
                      if (!mount) return null;
                      const coveringWorkspaces = workspaces.filter((workspace) =>
                        draftWorkspaceIds.has(workspace.id) &&
                        workspace.environmentIds.includes(environment.id)
                      );
                      const covered = coveringWorkspaces.length > 0;
                      const active = selectedKeys.has(mountKey(mount));
                      return (
                        <label key={mountKey(mount)} className={`studio-tool-option session-environment-option${active ? " is-selected" : ""}${covered ? " is-covered" : ""}`}>
                          <span className="studio-tool-option-icon"><EnvironmentIcon /></span>
                          <span className="studio-tool-option-copy">
                            <strong>{environment.name}</strong>
                            <span>{covered
                              ? `已由工作区 ${coveringWorkspaces.map((workspace) => workspace.name).join("、")} 包含`
                              : environment.description || environmentLanguageLabel(environment.language)}</span>
                            <small>{environmentLanguageLabel(environment.language)} · {mount.environment_version_id}</small>
                          </span>
                          <input
                            type="checkbox"
                            checked={active}
                            disabled={covered}
                            aria-label={`选择环境 ${environment.name}`}
                            onChange={() => toggle(environment)}
                          />
                          <span className="session-environment-check" aria-hidden="true"><CheckIcon /></span>
                        </label>
                      );
                    })}
                  </section>
                )}
              </>
            )}
          </div>
        </div>
        <footer className="session-environment-dialog__footer">
          <span>已选择 {draftWorkspaceIds.size} 个工作区，覆盖 {selectedKeys.size} 个环境</span>
          <div>
            <button type="button" onClick={onClose}>取消</button>
            <button type="button" className="is-primary" disabled={loading || Boolean(error)} onClick={confirm}>
              确认添加
            </button>
          </div>
        </footer>
      </section>
    </div>,
    document.body,
  );
}

export function SessionEnvironmentPicker({
  environments,
  workspaces,
  value,
  selectedWorkspaceIds,
  loading,
  disabled = false,
  error = "",
  onChange,
  onRefresh,
}: {
  environments: StudioEnvironment[];
  workspaces: StudioWorkspace[];
  value: readonly SessionEnvironmentMountSelection[];
  selectedWorkspaceIds: readonly string[];
  loading: boolean;
  disabled?: boolean;
  error?: string;
  onChange?: (
    value: SessionEnvironmentMountSelection[],
    workspaceIds?: string[],
  ) => void;
  onRefresh?: () => void | Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const addButtonRef = useRef<HTMLButtonElement>(null);
  const environmentsByKey = useMemo(() => new Map(
    environments.flatMap((environment) => {
      const mount = environmentMount(environment);
      return mount ? [[mountKey(mount), environment] as const] : [];
    }),
  ), [environments]);
  const environmentsById = useMemo(
    () => new Map(environments.map((environment) => [environment.id, environment])),
    [environments],
  );
  const selectedWorkspaces = workspaces.filter((workspace) =>
    selectedWorkspaceIds.includes(workspace.id)
  );
  const workspaceEnvironmentIds = new Set(
    selectedWorkspaces.flatMap((workspace) => workspace.environmentIds),
  );
  const directlySelectedMounts = value.filter((mount) =>
    !workspaceEnvironmentIds.has(mount.environment_id)
  );
  const closeDialog = () => {
    setOpen(false);
    requestAnimationFrame(() => addButtonRef.current?.focus());
  };

  return (
    <div className="session-environment-select">
      {value.length > 0 && (
        <div className="session-environment-list" role="list" aria-label="已挂载环境">
          {selectedWorkspaces.map((workspace) => {
            const workspaceMountIds = new Set(
              workspaceEnvironmentMounts(workspace, environmentsById)
                .map((mount) => mount.environment_id),
            );
            return (
              <div key={`workspace:${workspace.id}`} className="session-environment-item is-workspace" role="listitem">
                <span className="session-environment-item__icon"><WorkspaceIcon /></span>
                <span className="session-environment-item__copy">
                  <strong>{workspace.name}</strong>
                  <small>{workspaceMountIds.size} 个环境</small>
                </span>
                {onChange && (
                  <button
                    type="button"
                    className="topo-remove-capability"
                    aria-label={`移除工作区 ${workspace.name}`}
                    title="移除"
                    disabled={disabled}
                    onClick={() => {
                      const otherWorkspaceIds = selectedWorkspaceIds.filter((id) => id !== workspace.id);
                      const preservedEnvironmentIds = new Set(workspaces
                        .filter((item) => otherWorkspaceIds.includes(item.id))
                        .flatMap((item) => item.environmentIds));
                      onChange(
                        value.filter((mount) =>
                          !workspaceMountIds.has(mount.environment_id) ||
                          preservedEnvironmentIds.has(mount.environment_id)
                        ),
                        otherWorkspaceIds,
                      );
                    }}
                  >
                    <RemoveIcon />
                  </button>
                )}
              </div>
            );
          })}
          {directlySelectedMounts.map((mount) => {
            const environment = environmentsByKey.get(mountKey(mount));
            return (
              <div key={mountKey(mount)} className="session-environment-item" role="listitem">
                <span className="session-environment-item__icon"><EnvironmentIcon /></span>
                <span className="session-environment-item__copy">
                  <strong>{environment?.name ?? mount.environment_id}</strong>
                  <small>{environment
                    ? environmentLanguageLabel(environment.language)
                    : mount.environment_version_id}</small>
                </span>
                {onChange && (
                  <button
                    type="button"
                    className="topo-remove-capability"
                    aria-label={`移除环境 ${environment?.name ?? mount.environment_id}`}
                    title="移除"
                    disabled={disabled}
                    onClick={() => onChange(
                      value.filter((item) => mountKey(item) !== mountKey(mount)),
                      [...selectedWorkspaceIds],
                    )}
                  >
                    <RemoveIcon />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
      {onChange && (
        <button
          ref={addButtonRef}
          type="button"
          className="topo-capability-add-slot"
          aria-label="添加环境"
          disabled={disabled || loading}
          onClick={() => {
            setOpen(true);
            void onRefresh?.();
          }}
        >
          <AddIcon />
          <span>{value.length > 0 ? "添加更多环境" : "为当前 Session 添加环境"}</span>
        </button>
      )}
      {(loading || error || environments.length === 0) && (
        <p className={error ? "is-error" : undefined} role={error ? "alert" : undefined}>
          {loading
            ? "正在加载可用环境…"
            : error || "暂无可用的 AIO Sandbox 环境。"}
        </p>
      )}
      {open && (
        <EnvironmentPickerDialog
          environments={environments}
          workspaces={workspaces}
          value={value}
          selectedWorkspaceIds={selectedWorkspaceIds}
          loading={loading}
          error={error}
          onConfirm={(next, workspaceIds) => onChange?.(next, workspaceIds)}
          onClose={closeDialog}
        />
      )}
    </div>
  );
}
