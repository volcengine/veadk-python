import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import {
  CheckCircle,
  ChevronLeft,
  Plus,
  Trash,
} from "@openai/apps-sdk-ui/components/Icon";
import { Input } from "@openai/apps-sdk-ui/components/Input";
import { Select, type Option } from "@openai/apps-sdk-ui/components/Select";
import { Switch } from "@openai/apps-sdk-ui/components/Switch";
import { Textarea } from "@openai/apps-sdk-ui/components/Textarea";

import {
  listIdentityUserPools,
  listModelApiKeys,
  listModelOptions,
  type DeployAuthentication,
  type DeployResources,
  type DeployStage,
  type IdentityUserPool,
  type ModelApiKeyOption,
  type ModelOption,
} from "../adk/client";
import {
  cloudRegionOptions,
  defaultModelApiBase,
  defaultModelName,
  type CloudProvider,
} from "../adk/cloudProvider";
import { CloudEnvironmentConfigurator } from "../ui/CloudEnvironmentConfigurator";
import {
  DEFAULT_DEPLOY_RESOURCES,
  DeploymentResources,
  deploymentResourcesError,
} from "../ui/DeploymentResources";
import { DeploymentErrorMessage } from "../ui/DeploymentErrorMessage";
import { SkillSourcePicker } from "../ui/SkillSourcePicker";
import { agentNameProblem } from "./agentNameValidation";
import type { SelectedSkill } from "./skills/types";
import { resolvedModelSource, type ModelSource } from "./modelSource";
import { STM_BACKENDS, type EnvVar } from "./veadkCatalog";
import type {
  AgentDraft,
  CloudEnvironmentConfig,
  NetworkConfig,
} from "./types";
import "./NewAgentWorkbench.css";

export interface NewAgentWorkbenchProps {
  draft: AgentDraft;
  cloudProvider: CloudProvider;
  deployRegion: string;
  runtimeName: string;
  isRuntimeUpdate?: boolean;
  deploying: boolean;
  deployStage: DeployStage | null;
  deployError: string;
  deploySucceeded: boolean;
  showErrors: boolean;
  onBack: () => void;
  onDraftPatch: (patch: Partial<AgentDraft>) => void;
  onDeploymentPatch: (
    patch: Partial<NonNullable<AgentDraft["deployment"]>>,
  ) => void;
  onModelApiKeyChange: (key: ModelApiKeyOption) => void;
  customModelApiKey: string;
  onCustomModelApiKeyChange: (value: string) => void;
  onSelectedSkillsChange: (skills: SelectedSkill[]) => void;
  onCloudEnvironmentChange: (environment: CloudEnvironmentConfig) => void;
  onDeployRegionChange: (region: string) => void;
  onRuntimeNameChange: (runtimeName: string) => void;
  onNetworkChange: (network: NetworkConfig | undefined) => void;
  onDeploy: (options: NewAgentDeploymentOptions) => void;
}

type ModelSelectOption = Option & {
  model?: ModelOption;
  metadata?: string;
};
type WizardStep = "agent" | "environment" | "deployment";

const SELECT_OPTION_CLASS_NAME = "new-agent-workbench__select-option";

function ModelSelectOptionView({ label, metadata }: ModelSelectOption) {
  return (
    <span className="new-agent-workbench__model-option-view">
      <span className="new-agent-workbench__model-option-copy">
        <span className="new-agent-workbench__model-option-label">{label}</span>
        {metadata ? (
          <span className="new-agent-workbench__model-option-metadata">
            {metadata}
          </span>
        ) : null}
      </span>
    </span>
  );
}

function modelSelectSearchPredicate(
  option: ModelSelectOption,
  searchTerm: string,
) {
  const normalizedSearchTerm = searchTerm.trim().toLocaleLowerCase();
  if (!normalizedSearchTerm) return true;
  return [
    option.label,
    option.metadata,
    option.model?.name,
    option.model?.vendorName,
  ].some((candidate) =>
    candidate?.toLocaleLowerCase().includes(normalizedSearchTerm),
  );
}

export interface NewAgentDeploymentOptions {
  authentication: DeployAuthentication;
  sessionStorage: "in-memory" | "persistent";
  sessionBackend: SessionStorageBackendId;
  minInstance: number;
  maxInstance: number;
  createEvaluationSets: boolean;
  resources: DeployResources;
}

const SESSION_STORAGE_BACKEND_IDS = [
  "local",
  "sqlite",
  "mysql",
  "postgresql",
] as const;

type SessionStorageBackendId = (typeof SESSION_STORAGE_BACKEND_IDS)[number];

function isSessionStorageBackendId(
  value: string,
): value is SessionStorageBackendId {
  return SESSION_STORAGE_BACKEND_IDS.includes(value as SessionStorageBackendId);
}

function sessionStorageForBackend(
  backend: SessionStorageBackendId,
): NewAgentDeploymentOptions["sessionStorage"] {
  return backend === "local" ? "in-memory" : "persistent";
}

const WIZARD_STEPS: Array<{
  id: WizardStep;
  label: string;
  title: string;
  description: string;
}> = [
  {
    id: "agent",
    label: "智能体",
    title: "基本信息",
    description: "设置智能体的名称、用途、行为方式与能力",
  },
  {
    id: "environment",
    label: "执行环境",
    title: "配置执行环境",
    description: "选择默认环境或已构建的自定义环境",
  },
  {
    id: "deployment",
    label: "部署偏好",
    title: "部署偏好",
    description: "定义 AgentKit 云上参数",
  },
];

function NativeModelPicker({
  cloudProvider,
  source,
  value,
  apiKeyId,
  apiKeyName,
  provider,
  apiBase,
  customApiKey,
  onSourceChange,
  onApiKeyChange,
  onModelNameChange,
  onProviderChange,
  onApiBaseChange,
  onCustomApiKeyChange,
  onLoadingChange,
}: {
  cloudProvider: CloudProvider;
  source: ModelSource;
  value: string;
  apiKeyId?: string;
  apiKeyName?: string;
  provider: string;
  apiBase: string;
  customApiKey: string;
  onSourceChange: (source: ModelSource) => void;
  onApiKeyChange: (key: ModelApiKeyOption) => void;
  onModelNameChange: (modelName: string) => void;
  onProviderChange: (provider: string) => void;
  onApiBaseChange: (apiBase: string) => void;
  onCustomApiKeyChange: (value: string) => void;
  onLoadingChange: (loading: boolean) => void;
}) {
  const [apiKeys, setApiKeys] = useState<ModelApiKeyOption[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [loadingKeys, setLoadingKeys] = useState(true);
  const [loadingModels, setLoadingModels] = useState(false);
  const [loadedModelsForApiKeyId, setLoadedModelsForApiKeyId] = useState<
    string | null
  >(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    if (source !== "ark") return;
    setLoadingKeys(true);
    setError("");
    void listModelApiKeys(controller.signal)
      .then((response) => {
        if (controller.signal.aborted) return;
        setApiKeys(response.keys);
        const selected =
          response.keys.find((key) => key.id === apiKeyId) ??
          response.keys.find((key) => key.name === apiKeyName) ??
          response.keys.find((key) => key.id === response.defaultKeyId) ??
          response.keys[0];
        if (selected && selected.id !== apiKeyId) onApiKeyChange(selected);
      })
      .catch((cause) => {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "模型凭据加载失败");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingKeys(false);
      });
    return () => controller.abort();
  }, [apiKeyId, apiKeyName, cloudProvider, onApiKeyChange, source]);

  useEffect(() => {
    if (source !== "ark" || !apiKeyId) {
      setModels([]);
      setLoadingModels(false);
      setLoadedModelsForApiKeyId(null);
      return;
    }
    const controller = new AbortController();
    setLoadingModels(true);
    setLoadedModelsForApiKeyId(null);
    setError("");
    void listModelOptions({ apiKeyId, signal: controller.signal })
      .then((response) => {
        if (!controller.signal.aborted) setModels(response.models);
      })
      .catch((cause) => {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : "模型列表加载失败");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoadingModels(false);
          setLoadedModelsForApiKeyId(apiKeyId);
        }
      });
    return () => controller.abort();
  }, [apiKeyId, cloudProvider, source]);

  useEffect(() => {
    onLoadingChange(
      source === "ark" &&
        (loadingKeys ||
          (!!apiKeyId &&
            (loadingModels || loadedModelsForApiKeyId !== apiKeyId))),
    );
  }, [
    apiKeyId,
    loadedModelsForApiKeyId,
    loadingKeys,
    loadingModels,
    onLoadingChange,
    source,
  ]);

  const sourceOptions: Option[] = [
    {
      value: "ark",
      label: cloudProvider === "byteplus" ? "BytePlus ModelArk" : "火山方舟",
    },
    { value: "custom", label: "自定义" },
    {
      value: "gateway",
      label: "模型网关",
      description: "待上线",
      disabled: true,
    },
  ];
  const apiKeyOptions: Option[] = apiKeys.map((key) => ({
    value: key.id,
    label: key.name,
  }));
  if (apiKeyId && !apiKeyOptions.some((option) => option.value === apiKeyId)) {
    apiKeyOptions.unshift({
      value: apiKeyId,
      label: apiKeyName || "当前 API Key",
    });
  }

  const modelOptions = useMemo<ModelSelectOption[]>(() => {
    const available: ModelSelectOption[] = models
      .filter(
        (model) => model.available || model.lifecycleStatus === "Retiring",
      )
      .map((model) => ({
        value: model.id,
        label: model.displayName || model.name || model.id,
        metadata: model.vendorName
          ? `${model.id} | ${model.vendorName}`
          : model.id,
        model,
      }));
    if (value && !available.some((option) => option.value === value)) {
      available.unshift({ value, label: value, metadata: value });
    }
    return available;
  }, [models, value]);

  return (
    <div className="new-agent-workbench__model-group">
      <span className="new-agent-workbench__model-group-label">模型</span>
      <div className="new-agent-workbench__model-fields">
        <label className="new-agent-workbench__field new-agent-workbench__model-field">
          <span className="new-agent-workbench__model-field-label">
            模型来源
          </span>
          <Select
            value={source}
            options={sourceOptions}
            size="xl"
            triggerClassName="new-agent-workbench__select-trigger"
            optionClassName={SELECT_OPTION_CLASS_NAME}
            pill={false}
            onChange={(option) => onSourceChange(option.value as ModelSource)}
          />
        </label>
        {source === "ark" ? (
          <>
            <label className="new-agent-workbench__field new-agent-workbench__model-field">
              <span className="new-agent-workbench__model-field-label">
                API Key<span className="new-agent-workbench__required">*</span>
              </span>
              <Select
                value={apiKeyId ?? ""}
                options={apiKeyOptions}
                loading={loadingKeys}
                loadingPlaceholder="正在加载 API Key"
                placeholder="选择 API Key"
                searchPlaceholder="搜索 API Key 名称"
                searchEmptyMessage="暂无可用 API Key"
                size="xl"
                triggerClassName="new-agent-workbench__select-trigger"
                optionClassName={SELECT_OPTION_CLASS_NAME}
                pill={false}
                onChange={(option) => {
                  const key = apiKeys.find((item) => item.id === option.value);
                  if (key) {
                    onLoadingChange(true);
                    onApiKeyChange(key);
                  }
                }}
              />
            </label>
            <label className="new-agent-workbench__field new-agent-workbench__model-field">
              <span className="new-agent-workbench__model-field-label">
                模型<span className="new-agent-workbench__required">*</span>
              </span>
              <Select
                value={value}
                options={modelOptions}
                loading={loadingModels}
                loadingPlaceholder="正在加载模型"
                placeholder="选择模型"
                searchPlaceholder="搜索名称、Model ID 或服务商"
                searchEmptyMessage="没有可用的模型"
                size="xl"
                triggerClassName="new-agent-workbench__select-trigger"
                optionClassName={`${SELECT_OPTION_CLASS_NAME} new-agent-workbench__model-option`}
                OptionView={ModelSelectOptionView}
                searchPredicate={modelSelectSearchPredicate}
                pill={false}
                disabled={!apiKeyId}
                onChange={(option) => onModelNameChange(option.value)}
              />
            </label>
          </>
        ) : (
          <>
            <label className="new-agent-workbench__field new-agent-workbench__model-field">
              <span className="new-agent-workbench__model-field-label">
                模型名称<span className="new-agent-workbench__required">*</span>
              </span>
              <Input
                value={value}
                size="xl"
                gutterSize="md"
                pill={false}
                onChange={(event) =>
                  onModelNameChange(event.currentTarget.value)
                }
              />
            </label>
            <label className="new-agent-workbench__field new-agent-workbench__model-field">
              <span className="new-agent-workbench__model-field-label">
                服务商 Provider
              </span>
              <Input
                value={provider}
                placeholder="openai"
                size="xl"
                gutterSize="md"
                pill={false}
                onChange={(event) =>
                  onProviderChange(event.currentTarget.value)
                }
              />
            </label>
            <label className="new-agent-workbench__field new-agent-workbench__model-field">
              <span className="new-agent-workbench__model-field-label">
                API Base
              </span>
              <Input
                value={apiBase}
                placeholder={defaultModelApiBase(cloudProvider)}
                size="xl"
                gutterSize="md"
                pill={false}
                onChange={(event) => onApiBaseChange(event.currentTarget.value)}
              />
            </label>
            <label className="new-agent-workbench__field new-agent-workbench__model-field">
              <span className="new-agent-workbench__model-field-label">
                API Key<span className="new-agent-workbench__required">*</span>
              </span>
              <Input
                type="password"
                value={customApiKey}
                placeholder="请输入模型 API Key"
                autoComplete="new-password"
                size="xl"
                gutterSize="md"
                pill={false}
                onChange={(event) =>
                  onCustomApiKeyChange(event.currentTarget.value)
                }
              />
            </label>
          </>
        )}
        {error ? (
          <p className="new-agent-workbench__error" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function IdentityUserPoolField({
  value,
  disabled,
  onChange,
}: {
  value: string;
  disabled: boolean;
  onChange: (uid: string) => void;
}) {
  const [pools, setPools] = useState<IdentityUserPool[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void listIdentityUserPools(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setPools(items);
      })
      .catch((cause) => {
        if (
          !controller.signal.aborted &&
          (cause as Error)?.name !== "AbortError"
        ) {
          setPools([]);
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [reloadKey]);

  const options = useMemo<Option[]>(
    () =>
      [...pools]
        .sort((left, right) => Number(right.isCurrent) - Number(left.isCurrent))
        .map((pool) => ({
          value: pool.uid,
          label: pool.name.trim() || "未命名用户池",
          description: pool.isCurrent
            ? `${pool.domain || pool.uid}（当前用户池）`
            : pool.domain || pool.uid,
        })),
    [pools],
  );
  const selectedPool = pools.find((pool) => pool.uid === value);

  return (
    <div className="new-agent-workbench__field">
      <span>
        用户池<span className="new-agent-workbench__required">*</span>
      </span>
      <Select
        value={value}
        options={options}
        loading={loading}
        loadingPlaceholder="正在加载用户池"
        placeholder="请选择用户池"
        searchPlaceholder="搜索用户池"
        searchEmptyMessage="当前账号下暂无 Identity 用户池"
        size="xl"
        pill={false}
        disabled={disabled || Boolean(error)}
        triggerClassName="new-agent-workbench__select-trigger"
        optionClassName={SELECT_OPTION_CLASS_NAME}
        onChange={(option) => onChange(option.value)}
      />
      {error ? (
        <div className="new-agent-workbench__inline-error" role="alert">
          <span>{error}</span>
          <Button
            color="secondary"
            variant="ghost"
            size="sm"
            pill={false}
            onClick={() => setReloadKey((key) => key + 1)}
          >
            重试
          </Button>
        </div>
      ) : selectedPool?.isCurrent ? (
        <small className="new-agent-workbench__helper-text">
          当前 Studio 的登录 JWT 将透传访问此 Runtime
        </small>
      ) : selectedPool ? (
        <small className="new-agent-workbench__error">
          所选用户池不是当前 Studio 使用的用户池，部署后无法从 Studio 调用此
          Runtime
        </small>
      ) : (
        <small className="new-agent-workbench__helper-text">
          当前 Studio 使用的用户池已在列表中标注
        </small>
      )}
    </div>
  );
}

function EnvironmentVariableRow({
  name,
  value,
  required = false,
  placeholder,
  locked = false,
  onRename,
  onValueChange,
  onRemove,
}: {
  name: string;
  value: string;
  required?: boolean;
  placeholder?: string;
  locked?: boolean;
  onRename: (previousName: string, nextName: string) => void;
  onValueChange: (value: string) => void;
  onRemove: () => void;
}) {
  const [draftName, setDraftName] = useState(name);

  useEffect(() => setDraftName(name), [name]);

  const commitName = () => {
    const nextName = draftName.trim().toUpperCase();
    if (!nextName) {
      setDraftName(name);
      return;
    }
    setDraftName(nextName);
    if (nextName !== name) onRename(name, nextName);
  };

  return (
    <div
      className={`new-agent-workbench__env-row${locked ? " is-locked" : ""}`}
      role="row"
    >
      <div className="new-agent-workbench__env-cell" role="cell">
        <Input
          aria-label="环境变量名称"
          value={draftName}
          title={locked ? name : undefined}
          size="xl"
          gutterSize="md"
          pill={false}
          disabled={locked}
          onChange={(event) => setDraftName(event.currentTarget.value)}
          onBlur={commitName}
          onKeyDown={(event) => {
            if (event.key === "Enter") event.currentTarget.blur();
          }}
        />
      </div>
      <div className="new-agent-workbench__env-cell" role="cell">
        <Input
          aria-label={`${name} 的值`}
          value={value}
          size="xl"
          gutterSize="md"
          pill={false}
          type={/(SECRET|PASSWORD|KEY|TOKEN)$/.test(name) ? "password" : "text"}
          placeholder={placeholder}
          required={required}
          onChange={(event) => onValueChange(event.currentTarget.value)}
        />
      </div>
      <div className="new-agent-workbench__env-action" role="cell">
        {locked ? (
          required ? (
            <span className="new-agent-workbench__required" aria-label="必填">
              *
            </span>
          ) : null
        ) : (
          <Button
            color="secondary"
            variant="ghost"
            size="lg"
            uniform
            pill={false}
            aria-label={`删除 ${name}`}
            onClick={onRemove}
          >
            <Trash aria-hidden />
          </Button>
        )}
      </div>
    </div>
  );
}

export function NewAgentWorkbench({
  draft,
  cloudProvider,
  deployRegion,
  runtimeName,
  isRuntimeUpdate = false,
  deploying,
  deployStage,
  deployError,
  deploySucceeded,
  showErrors,
  onBack,
  onDraftPatch,
  onDeploymentPatch,
  onModelApiKeyChange,
  customModelApiKey,
  onCustomModelApiKeyChange,
  onSelectedSkillsChange,
  onCloudEnvironmentChange,
  onDeployRegionChange,
  onRuntimeNameChange,
  onNetworkChange,
  onDeploy,
}: NewAgentWorkbenchProps) {
  const reduceMotion = useReducedMotion();
  const [step, setStep] = useState<WizardStep>("agent");
  const [isLeaving, setIsLeaving] = useState(false);
  const pendingBackRef = useRef<(() => void) | null>(null);
  const [agentValidationVisible, setAgentValidationVisible] = useState(false);
  const [modelDataLoading, setModelDataLoading] = useState(true);
  const [authenticationType, setAuthenticationType] =
    useState<DeployAuthentication["type"]>("api_key");
  const [userPoolUid, setUserPoolUid] = useState("");
  const [sessionBackend, setSessionBackend] = useState<SessionStorageBackendId>(
    () => {
      const backend = draft.shortTermBackend || "local";
      return draft.memory.shortTerm && isSessionStorageBackendId(backend)
        ? backend
        : "local";
    },
  );
  const sessionStorage = sessionStorageForBackend(sessionBackend);
  const [minInstance, setMinInstance] = useState("1");
  const [maxInstance, setMaxInstance] = useState(
    sessionStorage === "in-memory" ? "1" : "5",
  );
  const [createEvaluationSets, setCreateEvaluationSets] = useState(true);
  const [deployResources, setDeployResources] = useState<DeployResources>(
    DEFAULT_DEPLOY_RESOURCES,
  );
  const [deploymentValidationError, setDeploymentValidationError] =
    useState("");
  const [resourceValidationError, setResourceValidationError] = useState<
    string | null
  >(null);
  const [panelFades, setPanelFades] = useState({ top: false, bottom: false });
  const panelRef = useRef<HTMLDivElement>(null);
  const stepIndex = WIZARD_STEPS.findIndex((item) => item.id === step);
  const stepMeta = WIZARD_STEPS[stepIndex];
  const nameProblem = agentNameProblem(draft.name);
  const nameInvalid = nameProblem !== null;
  const descriptionMissing = !draft.description.trim();
  const instructionMissing = !draft.instruction.trim();
  const modelSource = resolvedModelSource(draft, cloudProvider);
  const modelMissing = !draft.modelName?.trim();
  const modelApiKeyMissing =
    modelSource === "ark" && !draft.deployment?.modelApiKeyId?.trim();
  const agentHasErrors =
    nameInvalid ||
    descriptionMissing ||
    instructionMissing ||
    modelMissing ||
    modelApiKeyMissing;
  const networkMode = draft.deployment?.network?.mode ?? "public";
  const network = draft.deployment?.network;
  const regionOptions: Option[] = cloudRegionOptions(cloudProvider);
  const envValues = draft.deployment?.envValues ?? {};
  const sessionBackendOption =
    STM_BACKENDS.find((option) => option.id === sessionBackend) ??
    STM_BACKENDS[0];
  const sessionEnvSpecs = (sessionBackendOption?.env ?? []).filter(
    (item) => !item.hidden,
  );
  const sessionEnvKeys = new Set(sessionEnvSpecs.map((item) => item.key));
  const customEnvEntries = Object.entries(envValues).filter(
    ([key]) =>
      key !== "FEISHU_APP_ID" &&
      key !== "FEISHU_APP_SECRET" &&
      !sessionEnvKeys.has(key),
  );
  const patchEnv = (key: string, value: string) => {
    onDeploymentPatch({ envValues: { ...envValues, [key]: value } });
  };
  const renameEnv = (previousKey: string, nextKey: string) => {
    const next = Object.fromEntries(
      Object.entries(envValues).map(([key, value]) =>
        key === previousKey ? [nextKey, value] : [key, value],
      ),
    );
    onDeploymentPatch({ envValues: next });
  };
  const removeEnv = (key: string) => {
    const next = { ...envValues };
    delete next[key];
    onDeploymentPatch({ envValues: next });
  };
  const addEnv = () => {
    let index = customEnvEntries.length + 1;
    let key = `CUSTOM_ENV_${index}`;
    while (key in envValues) key = `CUSTOM_ENV_${++index}`;
    patchEnv(key, "");
  };

  useEffect(() => {
    const panel = panelRef.current;
    if (!panel) return;

    const updatePanelFades = () => {
      const next = {
        top: panel.scrollTop > 1,
        bottom: panel.scrollTop + panel.clientHeight < panel.scrollHeight - 1,
      };
      setPanelFades((current) =>
        current.top === next.top && current.bottom === next.bottom
          ? current
          : next,
      );
    };

    panel.scrollTo({ top: 0, behavior: "auto" });
    panel.addEventListener("scroll", updatePanelFades, { passive: true });
    const resizeObserver = new ResizeObserver(updatePanelFades);
    resizeObserver.observe(panel);
    const mutationObserver = new MutationObserver(updatePanelFades);
    mutationObserver.observe(panel, { childList: true, subtree: true });
    const frame = window.requestAnimationFrame(updatePanelFades);

    return () => {
      window.cancelAnimationFrame(frame);
      panel.removeEventListener("scroll", updatePanelFades);
      resizeObserver.disconnect();
      mutationObserver.disconnect();
    };
  }, [step]);

  useEffect(() => {
    setMinInstance("1");
    setMaxInstance(sessionStorage === "in-memory" ? "1" : "5");
  }, [sessionStorage]);

  const goBack = () => {
    if (stepIndex === 0) {
      if (isLeaving) return;
      if (reduceMotion) {
        onBack();
        return;
      }
      pendingBackRef.current = onBack;
      setIsLeaving(true);
      return;
    }
    setStep(WIZARD_STEPS[stepIndex - 1].id);
  };

  const finishPageTransition = () => {
    if (!isLeaving) return;
    const pendingBack = pendingBackRef.current;
    pendingBackRef.current = null;
    pendingBack?.();
  };

  const continueWizard = () => {
    if (step === "agent") {
      setAgentValidationVisible(true);
      if (agentHasErrors) return;
      setStep("environment");
      return;
    }
    if (step === "environment") {
      setStep("deployment");
      return;
    }
    const min = Number(minInstance);
    const max = Number(maxInstance);
    if (
      !Number.isSafeInteger(min) ||
      min < 1 ||
      !Number.isSafeInteger(max) ||
      max < 1
    ) {
      setDeploymentValidationError("实例数必须为大于 0 的整数");
      return;
    }
    if (min > max) {
      setDeploymentValidationError("最小实例数不能大于最大实例数");
      return;
    }
    if (authenticationType === "user_pool" && !userPoolUid) {
      setDeploymentValidationError("请选择用于 Runtime 鉴权的用户池");
      return;
    }
    const resourcesError = deploymentResourcesError(deployResources);
    if (resourcesError) {
      setResourceValidationError(resourcesError);
      setDeploymentValidationError(resourcesError);
      return;
    }
    setResourceValidationError(null);
    setDeploymentValidationError("");
    onDeploy({
      authentication:
        authenticationType === "user_pool"
          ? { type: "user_pool", userPoolUid }
          : { type: "api_key" },
      sessionStorage,
      sessionBackend,
      minInstance: min,
      maxInstance: max,
      createEvaluationSets:
        cloudProvider === "byteplus" ? false : createEvaluationSets,
      resources: deployResources,
    });
  };

  const showAgentErrors = showErrors || agentValidationVisible;

  return (
    <motion.div
      className={`new-agent-workbench${isLeaving ? " is-leaving" : ""}`}
      initial={reduceMotion ? false : { opacity: 0 }}
      animate={{ opacity: isLeaving ? 0 : 1 }}
      transition={{
        duration: isLeaving ? 0.12 : 0.18,
        ease: [0.16, 1, 0.3, 1],
      }}
      onAnimationComplete={finishPageTransition}
    >
      <main className="new-agent-workbench__main" aria-label="快速模式创建">
        <section
          className="new-agent-workbench__form"
          aria-labelledby="new-agent-workbench-title"
        >
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={`heading-${step}`}
              className="new-agent-workbench__heading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.16, ease: "easeOut" }}
            >
              <h1 id="new-agent-workbench-title">{stepMeta.title}</h1>
              <p>{stepMeta.description}</p>
            </motion.div>
          </AnimatePresence>

          <div className="new-agent-workbench__panel-frame">
            <div ref={panelRef} className="new-agent-workbench__panel">
              <AnimatePresence mode="wait" initial={false}>
                {step === "agent" ? (
                  <motion.div
                    key="agent"
                    className="new-agent-workbench__fields"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.16, ease: "easeOut" }}
                  >
                    <label
                      className="new-agent-workbench__field"
                      data-validation-field="name"
                    >
                      <span className="new-agent-workbench__field-heading">
                        <span>
                          名称
                          <span className="new-agent-workbench__required">
                            *
                          </span>
                        </span>
                        <small>{draft.name.length}/50</small>
                      </span>
                      <Input
                        value={draft.name}
                        maxLength={50}
                        size="xl"
                        gutterSize="md"
                        pill={false}
                        invalid={showAgentErrors && nameInvalid}
                        placeholder="输入智能体名称"
                        onChange={(event) =>
                          onDraftPatch({ name: event.currentTarget.value })
                        }
                      />
                      {showAgentErrors && nameProblem ? (
                        <small
                          className="new-agent-workbench__error"
                          role="alert"
                        >
                          {nameProblem}
                        </small>
                      ) : null}
                    </label>
                    <label
                      className="new-agent-workbench__field"
                      data-validation-field="description"
                    >
                      <span>
                        描述
                        <span className="new-agent-workbench__required">*</span>
                      </span>
                      <Textarea
                        value={draft.description}
                        rows={4}
                        maxRows={8}
                        autoResize
                        size="xl"
                        gutterSize="md"
                        invalid={showAgentErrors && descriptionMissing}
                        placeholder="说明这个智能体可以做什么"
                        onChange={(event) =>
                          onDraftPatch({
                            description: event.currentTarget.value,
                          })
                        }
                      />
                      {showAgentErrors && descriptionMissing ? (
                        <small className="new-agent-workbench__error">
                          请输入描述
                        </small>
                      ) : null}
                    </label>
                    <label
                      className="new-agent-workbench__field"
                      data-validation-field="instruction"
                    >
                      <span>
                        提示词
                        <span className="new-agent-workbench__required">*</span>
                      </span>
                      <Textarea
                        value={draft.instruction}
                        rows={10}
                        maxRows={18}
                        autoResize
                        size="xl"
                        gutterSize="md"
                        invalid={showAgentErrors && instructionMissing}
                        placeholder="定义角色、目标和行为边界"
                        onChange={(event) =>
                          onDraftPatch({
                            instruction: event.currentTarget.value,
                          })
                        }
                      />
                      {showAgentErrors && instructionMissing ? (
                        <small className="new-agent-workbench__error">
                          请输入提示词
                        </small>
                      ) : null}
                    </label>
                    <NativeModelPicker
                      cloudProvider={cloudProvider}
                      source={modelSource}
                      value={draft.modelName ?? ""}
                      apiKeyId={draft.deployment?.modelApiKeyId}
                      apiKeyName={draft.deployment?.modelApiKeyName}
                      provider={draft.modelProvider ?? ""}
                      apiBase={draft.modelApiBase ?? ""}
                      customApiKey={customModelApiKey}
                      onSourceChange={(source) => {
                        setModelDataLoading(source === "ark");
                        onDraftPatch({
                          modelSource: source,
                          modelName:
                            source === "custom" && modelSource === "ark"
                              ? ""
                              : source === "ark" && !draft.modelName?.trim()
                                ? defaultModelName(cloudProvider)
                                : draft.modelName,
                        });
                      }}
                      onApiKeyChange={onModelApiKeyChange}
                      onModelNameChange={(modelName) =>
                        onDraftPatch({ modelName })
                      }
                      onProviderChange={(modelProvider) =>
                        onDraftPatch({ modelProvider })
                      }
                      onApiBaseChange={(modelApiBase) =>
                        onDraftPatch({ modelApiBase })
                      }
                      onCustomApiKeyChange={onCustomModelApiKeyChange}
                      onLoadingChange={setModelDataLoading}
                    />
                    {showAgentErrors && modelMissing ? (
                      <p className="new-agent-workbench__error" role="alert">
                        请选择模型
                      </p>
                    ) : null}
                    <div className="new-agent-workbench__field">
                      <span>技能</span>
                      <SkillSourcePicker
                        selected={draft.selectedSkills ?? []}
                        onChange={onSelectedSkillsChange}
                        cloudProvider={cloudProvider}
                        disabled={deploying}
                        addLabel="添加技能"
                        showSelectedCount={false}
                      />
                    </div>
                  </motion.div>
                ) : null}

                {step === "environment" ? (
                  <motion.div
                    key="environment"
                    className="new-agent-workbench__fields"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.16, ease: "easeOut" }}
                  >
                    <div className="new-agent-workbench__environment">
                      <CloudEnvironmentConfigurator
                        value={
                          draft.cloudEnvironment ?? {
                            environmentId: "",
                            environmentVersionId: "",
                          }
                        }
                        onChange={onCloudEnvironmentChange}
                        disabled={deploying}
                        controlSize="xl"
                        controlClassName="new-agent-workbench__select-trigger"
                        optionClassName={SELECT_OPTION_CLASS_NAME}
                      />
                    </div>
                  </motion.div>
                ) : null}

                {step === "deployment" ? (
                  <motion.div
                    key="deployment"
                    className="new-agent-workbench__fields"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.16, ease: "easeOut" }}
                  >
                    <label className="new-agent-workbench__field">
                      <span>
                        Runtime 名称
                        <span className="new-agent-workbench__required">*</span>
                      </span>
                      <Input
                        value={runtimeName}
                        disabled={deploying || isRuntimeUpdate}
                        size="xl"
                        gutterSize="md"
                        pill={false}
                        placeholder="agent-runtime"
                        onChange={(event) =>
                          onRuntimeNameChange(event.currentTarget.value)
                        }
                      />
                      <small className="new-agent-workbench__helper-text">
                        {isRuntimeUpdate
                          ? "更新时保持现有 Runtime 名称不变"
                          : "仅支持英文字母、数字、下划线和连字符"}
                      </small>
                    </label>
                    <label className="new-agent-workbench__field">
                      <span>
                        发布区域
                        <span className="new-agent-workbench__required">*</span>
                      </span>
                      <Select
                        value={deployRegion}
                        options={regionOptions}
                        size="xl"
                        triggerClassName="new-agent-workbench__select-trigger"
                        optionClassName={SELECT_OPTION_CLASS_NAME}
                        pill={false}
                        disabled={deploying || isRuntimeUpdate}
                        onChange={(option) =>
                          onDeployRegionChange(option.value)
                        }
                      />
                    </label>

                    <div className="new-agent-workbench__deployment-section">
                      <label className="new-agent-workbench__field">
                        <span>鉴权方式</span>
                        <Select
                          value={authenticationType}
                          options={[
                            {
                              value: "api_key",
                              label: "API Key",
                              description:
                                "默认方式，使用 Runtime API Key 访问",
                            },
                            {
                              value: "user_pool",
                              label: "用户池",
                              description: "使用 Identity 用户池签发的 JWT",
                            },
                          ]}
                          size="xl"
                          triggerClassName="new-agent-workbench__select-trigger"
                          optionClassName={SELECT_OPTION_CLASS_NAME}
                          pill={false}
                          disabled={deploying}
                          onChange={(option) => {
                            setAuthenticationType(
                              option.value as DeployAuthentication["type"],
                            );
                            setDeploymentValidationError("");
                          }}
                        />
                      </label>
                      {authenticationType === "user_pool" ? (
                        <IdentityUserPoolField
                          value={userPoolUid}
                          disabled={deploying}
                          onChange={(uid) => {
                            setUserPoolUid(uid);
                            setDeploymentValidationError("");
                          }}
                        />
                      ) : null}
                    </div>

                    <div className="new-agent-workbench__deployment-section">
                      <label className="new-agent-workbench__field">
                        <span>会话存储</span>
                        <Select
                          value={sessionBackend}
                          options={STM_BACKENDS.map((option) => ({
                            value: option.id,
                            label:
                              option.id === "local"
                                ? "In-memory 临时存储"
                                : option.label,
                          }))}
                          size="xl"
                          triggerClassName="new-agent-workbench__select-trigger"
                          optionClassName={SELECT_OPTION_CLASS_NAME}
                          pill={false}
                          disabled={deploying}
                          onChange={(option) => {
                            if (!isSessionStorageBackendId(option.value))
                              return;
                            setSessionBackend(option.value);
                            onDraftPatch({
                              memory: {
                                ...draft.memory,
                                shortTerm: option.value !== "local",
                              },
                              shortTermBackend: option.value,
                            });
                            setDeploymentValidationError("");
                          }}
                        />
                      </label>
                    </div>

                    <div className="new-agent-workbench__deployment-section">
                      <strong className="new-agent-workbench__section-title">
                        实例设置
                      </strong>
                      <div className="new-agent-workbench__instance-fields">
                        <label className="new-agent-workbench__field">
                          <span className="new-agent-workbench__model-field-label">
                            最小实例数
                          </span>
                          <Input
                            type="number"
                            min={1}
                            step={1}
                            value={minInstance}
                            size="xl"
                            gutterSize="md"
                            pill={false}
                            disabled={deploying}
                            onChange={(event) => {
                              setMinInstance(event.currentTarget.value);
                              setDeploymentValidationError("");
                            }}
                          />
                        </label>
                        <label className="new-agent-workbench__field">
                          <span className="new-agent-workbench__model-field-label">
                            最大实例数
                          </span>
                          <Input
                            type="number"
                            min={1}
                            step={1}
                            value={maxInstance}
                            size="xl"
                            gutterSize="md"
                            pill={false}
                            disabled={deploying}
                            onChange={(event) => {
                              setMaxInstance(event.currentTarget.value);
                              setDeploymentValidationError("");
                            }}
                          />
                        </label>
                      </div>
                      {sessionStorage === "in-memory" ? (
                        <small className="new-agent-workbench__helper-text">
                          为避免多实例间会话丢失，推荐将 Runtime 固定为 1～1
                        </small>
                      ) : null}
                    </div>

                    <div className="new-agent-workbench__deployment-section">
                      <label className="new-agent-workbench__field">
                        <span>网络模式</span>
                        <Select
                          value={networkMode}
                          options={[
                            { value: "public", label: "公网" },
                            { value: "private", label: "私网" },
                            { value: "both", label: "公网与私网" },
                          ]}
                          size="xl"
                          triggerClassName="new-agent-workbench__select-trigger"
                          optionClassName={SELECT_OPTION_CLASS_NAME}
                          pill={false}
                          onChange={(option) =>
                            onNetworkChange(
                              option.value === "public"
                                ? undefined
                                : {
                                    ...(network ?? {}),
                                    mode: option.value as NetworkConfig["mode"],
                                  },
                            )
                          }
                        />
                      </label>
                      {networkMode !== "public" ? (
                        <>
                          <div className="new-agent-workbench__field-row">
                            <label className="new-agent-workbench__field">
                              <span>
                                VPC ID
                                <span className="new-agent-workbench__required">
                                  *
                                </span>
                              </span>
                              <Input
                                value={network?.vpcId ?? ""}
                                size="xl"
                                gutterSize="md"
                                pill={false}
                                placeholder="vpc-xxx"
                                onChange={(event) =>
                                  onNetworkChange({
                                    ...(network ?? { mode: networkMode }),
                                    vpcId: event.currentTarget.value,
                                  })
                                }
                              />
                            </label>
                            <label className="new-agent-workbench__field">
                              <span>子网 ID（可选，多个用逗号分隔）</span>
                              <Input
                                value={network?.subnetIds ?? ""}
                                size="xl"
                                gutterSize="md"
                                pill={false}
                                placeholder="subnet-xxx"
                                onChange={(event) =>
                                  onNetworkChange({
                                    ...(network ?? { mode: networkMode }),
                                    subnetIds: event.currentTarget.value,
                                  })
                                }
                              />
                            </label>
                          </div>
                          <div className="new-agent-workbench__switch-row">
                            <div>
                              <strong>VPC 内共享公网出口</strong>
                              <span>允许私网 Runtime 通过共享出口访问公网</span>
                            </div>
                            <Switch
                              checked={!!network?.enableSharedInternetAccess}
                              onCheckedChange={(enableSharedInternetAccess) =>
                                onNetworkChange({
                                  ...(network ?? { mode: networkMode }),
                                  enableSharedInternetAccess,
                                })
                              }
                              aria-label="VPC 内共享公网出口"
                            />
                          </div>
                        </>
                      ) : null}
                    </div>

                    {cloudProvider !== "byteplus" ? (
                      <div className="new-agent-workbench__deployment-section">
                        <strong className="new-agent-workbench__section-title">
                          评测集
                        </strong>
                        <div className="new-agent-workbench__switch-row">
                          <div>
                            <strong>自动创建评测集</strong>
                            <span>
                              部署成功后自动创建 Good Case 和 Bad Case 评测集
                            </span>
                          </div>
                          <Switch
                            checked={createEvaluationSets}
                            onCheckedChange={setCreateEvaluationSets}
                            aria-label="自动创建评测集"
                          />
                        </div>
                      </div>
                    ) : null}

                    <div className="new-agent-workbench__deployment-section">
                      <strong className="new-agent-workbench__section-title">
                        资源配置
                      </strong>
                      <DeploymentResources
                        value={deployResources}
                        agentName={draft.name || "agentkit-app"}
                        runtimeName={runtimeName}
                        region={deployRegion}
                        disabled={deploying}
                        validationError={resourceValidationError}
                        onChange={(resources) => {
                          setDeployResources(resources);
                          setResourceValidationError(null);
                          setDeploymentValidationError("");
                        }}
                      />
                    </div>

                    <div className="new-agent-workbench__deployment-section">
                      <div className="new-agent-workbench__env-head">
                        <strong className="new-agent-workbench__section-title">
                          环境变量
                        </strong>
                        <Button
                          color="secondary"
                          variant="ghost"
                          size="sm"
                          pill={false}
                          onClick={addEnv}
                        >
                          <Plus aria-hidden />
                          添加变量
                        </Button>
                      </div>
                      <div
                        className="new-agent-workbench__env-table"
                        role="table"
                        aria-label="环境变量"
                      >
                        <div
                          className="new-agent-workbench__env-table-head"
                          role="row"
                        >
                          <span role="columnheader">名称</span>
                          <span role="columnheader">值</span>
                          <span role="columnheader">操作</span>
                        </div>
                        <div
                          className="new-agent-workbench__env-table-body"
                          role="rowgroup"
                        >
                          {sessionEnvSpecs.map((item: EnvVar) => (
                            <EnvironmentVariableRow
                              key={item.key}
                              name={item.key}
                              value={
                                envValues[item.key] ?? item.defaultValue ?? ""
                              }
                              required={item.required}
                              placeholder={item.placeholder}
                              locked
                              onRename={() => undefined}
                              onValueChange={(nextValue) =>
                                patchEnv(item.key, nextValue)
                              }
                              onRemove={() => undefined}
                            />
                          ))}
                          {customEnvEntries.map(([key, value]) => (
                            <EnvironmentVariableRow
                              key={key}
                              name={key}
                              value={value}
                              onRename={renameEnv}
                              onValueChange={(nextValue) =>
                                patchEnv(key, nextValue)
                              }
                              onRemove={() => removeEnv(key)}
                            />
                          ))}
                          {!sessionEnvSpecs.length &&
                          !customEnvEntries.length ? (
                            <div
                              className="new-agent-workbench__empty-row new-agent-workbench__env-table-empty"
                              role="row"
                            >
                              <span role="cell">无</span>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    </div>

                    {deploymentValidationError ? (
                      <DeploymentErrorMessage
                        message={deploymentValidationError}
                        defaultExpanded
                      />
                    ) : deployError ? (
                      <DeploymentErrorMessage
                        message={deployError}
                        defaultExpanded
                      />
                    ) : deployStage || deploySucceeded ? (
                      <div
                        className="new-agent-workbench__deploy-status"
                        role="status"
                      >
                        {deploySucceeded ? <CheckCircle aria-hidden /> : null}
                        <span>
                          {deployStage?.message ||
                            (deploySucceeded ? "部署已完成" : "正在准备部署…")}
                        </span>
                        {typeof deployStage?.pct === "number" ? (
                          <strong>{Math.round(deployStage.pct)}%</strong>
                        ) : null}
                      </div>
                    ) : null}
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </div>
            <span
              className={`new-agent-workbench__scroll-fade is-top${panelFades.top ? " is-visible" : ""}`}
              aria-hidden="true"
            />
            <span
              className={`new-agent-workbench__scroll-fade is-bottom${panelFades.bottom ? " is-visible" : ""}`}
              aria-hidden="true"
            />
          </div>

          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={`actions-${step}`}
              className="new-agent-workbench__actions"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.16, ease: "easeOut" }}
            >
              <Button
                color="secondary"
                variant="outline"
                size="lg"
                pill={false}
                disabled={deploying}
                onClick={goBack}
              >
                <ChevronLeft aria-hidden />
                {stepIndex === 0 ? "返回" : "上一步"}
              </Button>

              <Button
                color="primary"
                size="lg"
                pill={false}
                loading={deploying}
                disabled={
                  deploying || (step === "agent" && modelDataLoading)
                }
                onClick={continueWizard}
              >
                {step === "deployment"
                  ? deploySucceeded
                    ? isRuntimeUpdate
                      ? "再次更新"
                      : "重新部署"
                    : isRuntimeUpdate
                      ? "更新并发布"
                      : "部署"
                  : "下一步"}
              </Button>
            </motion.div>
          </AnimatePresence>
        </section>
      </main>

      <footer className="new-agent-workbench__footer">
        <div className="new-agent-workbench__footer-inner">
          <nav aria-label="快速模式创建进度">
            <ol className="new-agent-workbench__progress">
              {WIZARD_STEPS.map((item, index) => (
                <li
                  key={item.id}
                  className={index === stepIndex ? "is-active" : ""}
                  aria-current={index === stepIndex ? "step" : undefined}
                  aria-label={item.label}
                  title={item.label}
                >
                  <span aria-hidden="true" />
                </li>
              ))}
            </ol>
          </nav>
        </div>
      </footer>
    </motion.div>
  );
}
