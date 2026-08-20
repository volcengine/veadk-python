import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { Input } from "@openai/apps-sdk-ui/components/Input";
import {
  Select,
  type Option as SelectOption,
} from "@openai/apps-sdk-ui/components/Select";
import {
  listDeploymentResources,
  type DeploymentResource,
  type DeploymentResourceMode,
  type DeploymentResourceQuery,
  type DeployResources,
} from "../adk/client";
import "./DeploymentResources.css";

const RESOURCE_MODE_OPTIONS: SelectOption[] = [
  {
    value: "auto",
    label: "自动创建",
    description: "部署时自动创建所需资源",
  },
  {
    value: "create",
    label: "指定名称",
    description: "使用指定名称创建或复用资源",
  },
  {
    value: "existing",
    label: "选择已有",
    description: "从当前账号的已有资源中选择",
  },
];

export const DEFAULT_DEPLOY_RESOURCES: DeployResources = {
  tos: { mode: "auto" },
  cr: { mode: "auto" },
  codePipeline: { mode: "auto" },
};

interface ResourceListState {
  items: DeploymentResource[];
  serviceRegion: string;
  totalCount: number;
  hasMore: boolean;
  loading: boolean;
  error: string | null;
  reload: () => void;
  loadMore: () => void;
}

function useDeploymentResourceList(
  query: DeploymentResourceQuery | null,
): ResourceListState {
  const [items, setItems] = useState<DeploymentResource[]>([]);
  const [serviceRegion, setServiceRegion] = useState("");
  const [pageNumber, setPageNumber] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadedQueryKey, setLoadedQueryKey] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const loadingRef = useRef(false);
  const requestRef = useRef<AbortController | null>(null);
  const baseQueryKey = query ? JSON.stringify(query) : "";
  const queryKey = baseQueryKey;

  const loadPage = useCallback((nextPage: number, replace: boolean) => {
    if (!queryKey) return;
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    const request = JSON.parse(queryKey) as DeploymentResourceQuery;
    if (replace) setItems([]);
    loadingRef.current = true;
    setLoading(true);
    setError(null);
    listDeploymentResources(
      { ...request, pageNumber: nextPage, pageSize: 100 },
      controller.signal,
    )
      .then((result) => {
        setItems((current) => {
          if (replace) return result.items;
          const seen = new Set(current.map((item) => `${item.id}\u0000${item.name}`));
          return [
            ...current,
            ...result.items.filter(
              (item) => !seen.has(`${item.id}\u0000${item.name}`),
            ),
          ];
        });
        setServiceRegion(result.serviceRegion);
        setPageNumber(result.pageNumber);
        setTotalCount(result.totalCount);
        setHasMore(result.hasMore);
        setLoadedQueryKey(queryKey);
      })
      .catch((cause) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setLoadedQueryKey(queryKey);
        setError(cause instanceof Error ? cause.message : String(cause));
      })
      .finally(() => {
        if (requestRef.current === controller) {
          requestRef.current = null;
          loadingRef.current = false;
          setLoading(false);
        }
      });
  }, [queryKey]);

  useEffect(() => {
    if (!queryKey) {
      requestRef.current?.abort();
      requestRef.current = null;
      loadingRef.current = false;
      setItems([]);
      setServiceRegion("");
      setPageNumber(1);
      setTotalCount(0);
      setHasMore(false);
      setLoadedQueryKey("");
      setLoading(false);
      setError(null);
      return;
    }
    loadPage(1, true);
    return () => requestRef.current?.abort();
  }, [loadPage, queryKey, reloadKey]);

  const queryReady = Boolean(queryKey) && loadedQueryKey === queryKey;
  const reload = useCallback(() => {
    setLoadedQueryKey("");
    setReloadKey((key) => key + 1);
  }, []);
  const loadMore = useCallback(() => {
    if (!queryReady || loadingRef.current || !hasMore) return;
    loadPage(pageNumber + 1, false);
  }, [hasMore, loadPage, pageNumber, queryReady]);

  return {
    items,
    serviceRegion,
    totalCount,
    hasMore: queryReady ? hasMore : false,
    loading: Boolean(queryKey) && (!queryReady || loading),
    error,
    reload,
    loadMore,
  };
}

function resourceOptions(
  items: DeploymentResource[],
  valueField: "id" | "name",
): SelectOption[] {
  return items.map((item) => ({
    value: item[valueField],
    label: item.name,
    description: [item.status, item.region, item.id]
      .filter(Boolean)
      .join(" · "),
  }));
}

function ResourcePicker({
  ariaLabel,
  value,
  valueLabel,
  state,
  disabled,
  valueField = "id",
  onChange,
}: {
  ariaLabel: string;
  value: string;
  valueLabel?: string;
  state: ResourceListState;
  disabled: boolean;
  valueField?: "id" | "name";
  onChange: (resource: DeploymentResource) => void;
}) {
  const options = useMemo(
    () => {
      const available = resourceOptions(state.items, valueField);
      if (!value || available.some((option) => option.value === value)) {
        return available;
      }
      return [
        {
          value,
          label: valueLabel || value,
          description: "当前选择",
        },
        ...available,
      ];
    },
    [state.items, value, valueField, valueLabel],
  );
  const selectId = useId();
  return (
    <div className="pp-resource-picker">
      <Select
        id={selectId}
        name={ariaLabel}
        value={value}
        placeholder="请选择已有资源"
        loadingPlaceholder="正在加载…"
        loading={state.loading}
        options={options}
        size="md"
        pill={false}
        align="start"
        triggerClassName="pp-app-select-trigger"
        optionClassName="pp-app-select-option"
        disabled={disabled || Boolean(state.error)}
        searchPlaceholder="搜索资源名称"
        searchEmptyMessage="未找到匹配资源"
        actions={
          state.hasMore
            ? [
                {
                  id: "load-more",
                  label: state.loading ? "正在加载…" : "加载更多",
                  onSelect: state.loadMore,
                },
              ]
            : []
        }
        onChange={(option) => {
          const resource = state.items.find(
            (item) => item[valueField] === option.value,
          );
          if (resource) onChange(resource);
        }}
      />
      {state.error ? (
        <div className="pp-resource-error" role="alert">
          <span>{state.error}</span>
          <Button
            type="button"
            color="secondary"
            variant="ghost"
            size="sm"
            pill={false}
            onClick={state.reload}
          >重试</Button>
        </div>
      ) : state.loading && state.items.length === 0 ? (
        <span className="pp-resource-status" aria-live="polite">正在加载云资源…</span>
      ) : state.items.length === 0 ? (
        <span className="pp-resource-status">暂无可用资源。</span>
      ) : state.serviceRegion ? (
        <span className="pp-resource-status">
          实际服务区域：{state.serviceRegion} · 已加载 {state.items.length}
          {state.totalCount > 0 ? `/${state.totalCount}` : ""}
        </span>
      ) : null}
    </div>
  );
}

function ModeField({
  resource,
  value,
  disabled,
  onChange,
}: {
  resource: string;
  value: DeploymentResourceMode;
  disabled: boolean;
  onChange: (mode: DeploymentResourceMode) => void;
}) {
  return (
    <div className="pp-resource-field pp-resource-mode">
      <label htmlFor={`pp-resource-mode-${resource}`}>配置方式</label>
      <Select
        id={`pp-resource-mode-${resource}`}
        value={value}
        placeholder="请选择配置方式"
        options={RESOURCE_MODE_OPTIONS}
        size="md"
        pill={false}
        align="start"
        triggerClassName="pp-app-select-trigger"
        optionClassName="pp-app-select-option"
        disabled={disabled}
        onChange={(option) =>
          onChange(option.value as DeploymentResourceMode)
        }
      />
    </div>
  );
}

function TextField({
  label,
  value,
  placeholder,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  placeholder: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <div className="pp-resource-field">
      <label>{label}</label>
      <Input
        size="md"
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        autoComplete="off"
        onChange={(event) => onChange(event.currentTarget.value)}
      />
    </div>
  );
}

function AutomaticResourceNames({
  items,
  note,
}: {
  items: { label: string; name: string }[];
  note?: string;
}) {
  return (
    <div className="pp-resource-auto-names">
      <span>自动创建名称</span>
      <dl>
        {items.map((item) => (
          <div key={item.label}>
            <dt>{item.label}</dt>
            <dd title={item.name}>{item.name}</dd>
          </div>
        ))}
      </dl>
      {note && <small>{note}</small>}
    </div>
  );
}

export function deploymentResourcesError(resources: DeployResources): string | null {
  if (resources.tos.mode !== "auto" && !resources.tos.bucket?.trim()) {
    return "请填写或选择 TOS 存储桶。";
  }
  if (
    resources.cr.mode !== "auto" &&
    (!resources.cr.instance?.trim() ||
      !resources.cr.namespace?.trim() ||
      !resources.cr.repository?.trim())
  ) {
    return "请完整填写或选择 CR 实例、命名空间和镜像仓库。";
  }
  if (
    resources.codePipeline.mode !== "auto" &&
    (!resources.codePipeline.workspaceName?.trim() ||
      !resources.codePipeline.pipelineName?.trim())
  ) {
    return "请完整填写或选择 CodePipeline Workspace 和 Pipeline。";
  }
  if (
    resources.codePipeline.mode === "existing" &&
    (!resources.codePipeline.workspaceId?.trim() ||
      !resources.codePipeline.pipelineId?.trim())
  ) {
    return "请选择已有的 CodePipeline Workspace 和兼容 Pipeline。";
  }
  return null;
}

export function DeploymentResources({
  value,
  agentName,
  runtimeName,
  region,
  disabled,
  validationError,
  onChange,
}: {
  value: DeployResources;
  agentName: string;
  runtimeName: string;
  region: string;
  disabled: boolean;
  validationError: string | null;
  onChange: (resources: DeployResources) => void;
}) {
  const resolvedAgentName = agentName.trim() || "agentkit-app";
  const resolvedRuntimeName = runtimeName.trim() || resolvedAgentName;
  const automaticBucketName =
    region && region !== "cn-beijing"
      ? `agentkit-platform-{账号 ID}-${region.startsWith("cn-") ? region.slice(3) : region}`
      : "agentkit-platform-{账号 ID}";
  const tosList = useDeploymentResourceList(
    value.tos.mode === "existing" ? { kind: "tos-bucket", region } : null,
  );
  const registryList = useDeploymentResourceList(
    value.cr.mode === "existing" ? { kind: "cr-registry", region } : null,
  );
  const namespaceList = useDeploymentResourceList(
    value.cr.mode === "existing" && value.cr.instance
      ? { kind: "cr-namespace", region, registry: value.cr.instance }
      : null,
  );
  const repositoryList = useDeploymentResourceList(
    value.cr.mode === "existing" && value.cr.instance && value.cr.namespace
      ? {
          kind: "cr-repository",
          region,
          registry: value.cr.instance,
          namespace: value.cr.namespace,
        }
      : null,
  );
  const workspaceList = useDeploymentResourceList(
    value.codePipeline.mode === "existing"
      ? { kind: "cp-workspace", region }
      : null,
  );
  const pipelineList = useDeploymentResourceList(
    value.codePipeline.mode === "existing" && value.codePipeline.workspaceId
      ? {
          kind: "cp-pipeline",
          region,
          workspaceId: value.codePipeline.workspaceId,
        }
      : null,
  );

  const patch = (next: Partial<DeployResources>) =>
    onChange({ ...value, ...next });

  return (
    <div className="pp-resource-list">
      <div className="pp-resource-item">
        <div className="pp-resource-name">TOS 存储桶</div>
        <div className="pp-resource-grid">
          <ModeField
            resource="TOS 存储桶"
            value={value.tos.mode}
            disabled={disabled}
            onChange={(mode) => patch({ tos: { mode } })}
          />
          {value.tos.mode === "create" && (
            <TextField
              label="存储桶名称"
              value={value.tos.bucket ?? ""}
              placeholder="输入存储桶名称"
              disabled={disabled}
              onChange={(bucket) => patch({ tos: { ...value.tos, bucket } })}
            />
          )}
          {value.tos.mode === "existing" && (
            <label className="pp-resource-field">
              <span>已有存储桶</span>
              <ResourcePicker
                ariaLabel="已有 TOS 存储桶"
                value={value.tos.bucket ?? ""}
                valueLabel={value.tos.bucket}
                state={tosList}
                disabled={disabled}
                onChange={(resource) =>
                  patch({ tos: { ...value.tos, bucket: resource.name } })
                }
              />
            </label>
          )}
          {value.tos.mode === "auto" && (
            <AutomaticResourceNames
              items={[
                { label: "存储桶", name: automaticBucketName },
              ]}
              note="账号 ID 在部署时按当前云账号解析。"
            />
          )}
        </div>
      </div>

      <div className="pp-resource-item">
        <div className="pp-resource-name">容器镜像仓库（CR）</div>
        <div className="pp-resource-grid">
          <ModeField
            resource="CR"
            value={value.cr.mode}
            disabled={disabled}
            onChange={(mode) => patch({ cr: { mode } })}
          />
          {value.cr.mode === "create" && (
            <div className="pp-resource-fields pp-resource-fields-three">
              <TextField
                label="实例名称"
                value={value.cr.instance ?? ""}
                placeholder="CR 实例"
                disabled={disabled}
                onChange={(instance) => patch({ cr: { ...value.cr, instance } })}
              />
              <TextField
                label="命名空间"
                value={value.cr.namespace ?? ""}
                placeholder="命名空间"
                disabled={disabled}
                onChange={(namespace) => patch({ cr: { ...value.cr, namespace } })}
              />
              <TextField
                label="镜像仓库"
                value={value.cr.repository ?? ""}
                placeholder="镜像仓库"
                disabled={disabled}
                onChange={(repository) => patch({ cr: { ...value.cr, repository } })}
              />
            </div>
          )}
          {value.cr.mode === "existing" && (
            <div className="pp-resource-fields pp-resource-fields-three">
              <label className="pp-resource-field">
                <span>CR 实例</span>
                <ResourcePicker
                  ariaLabel="已有 CR 实例"
                  value={value.cr.instance ?? ""}
                  valueLabel={value.cr.instance}
                  state={registryList}
                  disabled={disabled}
                  valueField="name"
                  onChange={(resource) =>
                    patch({
                      cr: { mode: "existing", instance: resource.name },
                    })
                  }
                />
              </label>
              <label className="pp-resource-field">
                <span>命名空间</span>
                <ResourcePicker
                  ariaLabel="已有 CR 命名空间"
                  value={value.cr.namespace ?? ""}
                  valueLabel={value.cr.namespace}
                  state={namespaceList}
                  disabled={disabled || !value.cr.instance}
                  valueField="name"
                  onChange={(resource) =>
                    patch({
                      cr: {
                        ...value.cr,
                        namespace: resource.name,
                        repository: undefined,
                      },
                    })
                  }
                />
              </label>
              <label className="pp-resource-field">
                <span>镜像仓库</span>
                <ResourcePicker
                  ariaLabel="已有 CR 镜像仓库"
                  value={value.cr.repository ?? ""}
                  valueLabel={value.cr.repository}
                  state={repositoryList}
                  disabled={disabled || !value.cr.namespace}
                  valueField="name"
                  onChange={(resource) =>
                    patch({
                      cr: { ...value.cr, repository: resource.name },
                    })
                  }
                />
              </label>
            </div>
          )}
          {value.cr.mode === "auto" && (
            <AutomaticResourceNames
              items={[
                { label: "CR 实例", name: "agentkit-platform-{账号 ID}" },
                { label: "命名空间", name: "agentkit" },
                {
                  label: "镜像仓库",
                  name: `${resolvedAgentName}-{4 位随机字符}`,
                },
              ]}
              note="账号 ID 在部署时解析，镜像仓库的随机字符在部署时生成。"
            />
          )}
        </div>
      </div>

      <div className="pp-resource-item">
        <div className="pp-resource-name">CodePipeline</div>
        <div className="pp-resource-grid">
          <ModeField
            resource="CodePipeline"
            value={value.codePipeline.mode}
            disabled={disabled}
            onChange={(mode) => patch({ codePipeline: { mode } })}
          />
          {value.codePipeline.mode === "create" && (
            <div className="pp-resource-fields">
              <TextField
                label="Workspace 名称"
                value={value.codePipeline.workspaceName ?? ""}
                placeholder="Workspace 名称"
                disabled={disabled}
                onChange={(workspaceName) =>
                  patch({ codePipeline: { ...value.codePipeline, workspaceName } })
                }
              />
              <TextField
                label="Pipeline 名称"
                value={value.codePipeline.pipelineName ?? ""}
                placeholder="Pipeline 名称"
                disabled={disabled}
                onChange={(pipelineName) =>
                  patch({ codePipeline: { ...value.codePipeline, pipelineName } })
                }
              />
            </div>
          )}
          {value.codePipeline.mode === "existing" && (
            <div className="pp-resource-fields">
              <label className="pp-resource-field">
                <span>Workspace</span>
                <ResourcePicker
                  ariaLabel="已有 CodePipeline Workspace"
                  value={value.codePipeline.workspaceId ?? ""}
                  valueLabel={value.codePipeline.workspaceName}
                  state={workspaceList}
                  disabled={disabled}
                  onChange={(resource) =>
                    patch({
                      codePipeline: {
                        mode: "existing",
                        workspaceId: resource.id,
                        workspaceName: resource.name,
                      },
                    })
                  }
                />
              </label>
              <label className="pp-resource-field">
                <span>兼容 Pipeline</span>
                <ResourcePicker
                  ariaLabel="已有 AgentKit CodePipeline"
                  value={value.codePipeline.pipelineId ?? ""}
                  valueLabel={value.codePipeline.pipelineName}
                  state={pipelineList}
                  disabled={disabled || !value.codePipeline.workspaceId}
                  onChange={(resource) =>
                    patch({
                      codePipeline: {
                        ...value.codePipeline,
                        pipelineId: resource.id,
                        pipelineName: resource.name,
                      },
                    })
                  }
                />
              </label>
            </div>
          )}
          {value.codePipeline.mode === "auto" && (
            <AutomaticResourceNames
              items={[
                { label: "Workspace", name: "agentkit-cli-workspace" },
                {
                  label: "Pipeline",
                  name: resolvedRuntimeName,
                },
              ]}
              note="Pipeline 与 Runtime 名称一致。"
            />
          )}
        </div>
      </div>
      {validationError && (
        <p className="pp-resource-validation" role="alert">
          {validationError}
        </p>
      )}
    </div>
  );
}
