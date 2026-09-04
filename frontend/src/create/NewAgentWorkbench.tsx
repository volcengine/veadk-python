import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
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
}> = [
  { id: "agent" },
  { id: "environment" },
  { id: "deployment" },
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
  const { t } = useTranslation("create");
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
          setError(cause instanceof Error ? cause.message : t("workbench.model.credentialsLoadError"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoadingKeys(false);
      });
    return () => controller.abort();
  }, [apiKeyId, apiKeyName, cloudProvider, onApiKeyChange, source, t]);

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
          setError(cause instanceof Error ? cause.message : t("workbench.model.modelsLoadError"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoadingModels(false);
          setLoadedModelsForApiKeyId(apiKeyId);
        }
      });
    return () => controller.abort();
  }, [apiKeyId, cloudProvider, source, t]);

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
      label: cloudProvider === "byteplus" ? "BytePlus ModelArk" : t("workbench.model.volcengineArk"),
    },
    { value: "custom", label: t("workbench.model.custom") },
    {
      value: "gateway",
      label: t("workbench.model.gateway"),
      description: t("workbench.model.comingSoon"),
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
      label: apiKeyName || t("workbench.model.currentApiKey"),
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
      <span className="new-agent-workbench__model-group-label">{t("workbench.model.label")}</span>
      <div className="new-agent-workbench__model-fields">
        <label className="new-agent-workbench__field new-agent-workbench__model-field">
          <span className="new-agent-workbench__model-field-label">
            {t("workbench.model.source")}
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
                loadingPlaceholder={t("workbench.model.loadingApiKeys")}
                placeholder={t("workbench.model.selectApiKey")}
                searchPlaceholder={t("workbench.model.searchApiKeys")}
                searchEmptyMessage={t("workbench.model.noApiKeys")}
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
                {t("workbench.model.label")}<span className="new-agent-workbench__required">*</span>
              </span>
              <Select
                value={value}
                options={modelOptions}
                loading={loadingModels}
                loadingPlaceholder={t("workbench.model.loadingModels")}
                placeholder={t("workbench.model.selectModel")}
                searchPlaceholder={t("workbench.model.searchModels")}
                searchEmptyMessage={t("workbench.model.noModels")}
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
                {t("workbench.model.name")}<span className="new-agent-workbench__required">*</span>
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
                {t("workbench.model.provider")}
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
                placeholder={t("workbench.model.apiKeyPlaceholder")}
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
  const { t } = useTranslation("create");
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
          label: pool.name.trim() || t("workbench.identity.unnamedPool"),
          description: pool.isCurrent
            ? t("workbench.identity.currentPool", { value: pool.domain || pool.uid })
            : pool.domain || pool.uid,
        })),
    [pools, t],
  );
  const selectedPool = pools.find((pool) => pool.uid === value);

  return (
    <div className="new-agent-workbench__field">
      <span>
        {t("workbench.identity.userPool")}<span className="new-agent-workbench__required">*</span>
      </span>
      <Select
        value={value}
        options={options}
        loading={loading}
        loadingPlaceholder={t("workbench.identity.loading")}
        placeholder={t("workbench.identity.placeholder")}
        searchPlaceholder={t("workbench.identity.search")}
        searchEmptyMessage={t("workbench.identity.empty")}
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
            {t("common.retry")}
          </Button>
        </div>
      ) : selectedPool?.isCurrent ? (
        <small className="new-agent-workbench__helper-text">
          {t("workbench.identity.currentHint")}
        </small>
      ) : selectedPool ? (
        <small className="new-agent-workbench__error">
          {t("workbench.identity.mismatchHint")}
        </small>
      ) : (
        <small className="new-agent-workbench__helper-text">
          {t("workbench.identity.selectionHint")}
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
  const { t } = useTranslation("create");
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
          aria-label={t("workbench.environmentVariables.nameAriaLabel")}
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
          aria-label={t("workbench.environmentVariables.valueAriaLabel", { name })}
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
            <span className="new-agent-workbench__required" aria-label={t("common.required")}>
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
            aria-label={t("workbench.environmentVariables.deleteNamed", { name })}
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
  const { t } = useTranslation("create");
  const reduceMotion = useReducedMotion();
  const [step, setStep] = useState<WizardStep>("agent");
  const [isLeaving, setIsLeaving] = useState(false);
  const pendingBackRef = useRef<(() => void) | null>(null);
  const [agentValidationVisible, setAgentValidationVisible] = useState(false);
  const [nameValidationTouched, setNameValidationTouched] = useState(false);
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
  const stepMeta = {
    ...WIZARD_STEPS[stepIndex],
    label: t(`workbench.steps.${step}.label`),
    title: t(`workbench.steps.${step}.title`),
    description: t(`workbench.steps.${step}.description`),
  };
  const nameProblem = agentNameProblem(draft.name, (key) =>
    t(`validation.agentName.${key}`),
  );
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
      !minInstance.trim() ||
      !maxInstance.trim() ||
      !Number.isSafeInteger(min) ||
      min < 0 ||
      !Number.isSafeInteger(max) ||
      max < 1
    ) {
      setDeploymentValidationError(
        t("workbench.validation.instanceIntegers"),
      );
      return;
    }
    if (min > max) {
      setDeploymentValidationError(t("workbench.validation.instanceOrder"));
      return;
    }
    if (authenticationType === "user_pool" && !userPoolUid) {
      setDeploymentValidationError(t("workbench.validation.userPoolRequired"));
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
  const showNameError = showAgentErrors || nameValidationTouched;

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
      <main className="new-agent-workbench__main" aria-label={t("workbench.ariaLabel")}>
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
                          {t("common.name")}
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
                        invalid={showNameError && nameInvalid}
                        placeholder={t("workbench.agent.namePlaceholder")}
                        aria-describedby={
                          showNameError && nameProblem
                            ? "new-agent-workbench-name-error"
                            : undefined
                        }
                        onBlur={() => setNameValidationTouched(true)}
                        onChange={(event) => {
                          setNameValidationTouched(true);
                          onDraftPatch({ name: event.currentTarget.value });
                        }}
                      />
                      {showNameError && nameProblem ? (
                        <small
                          id="new-agent-workbench-name-error"
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
                        {t("common.description")}
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
                        placeholder={t("workbench.agent.descriptionPlaceholder")}
                        onChange={(event) =>
                          onDraftPatch({
                            description: event.currentTarget.value,
                          })
                        }
                      />
                      {showAgentErrors && descriptionMissing ? (
                        <small className="new-agent-workbench__error">
                          {t("workbench.validation.descriptionRequired")}
                        </small>
                      ) : null}
                    </label>
                    <label
                      className="new-agent-workbench__field"
                      data-validation-field="instruction"
                    >
                      <span>
                        {t("workbench.agent.prompt")}
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
                        placeholder={t("workbench.agent.promptPlaceholder")}
                        onChange={(event) =>
                          onDraftPatch({
                            instruction: event.currentTarget.value,
                          })
                        }
                      />
                      {showAgentErrors && instructionMissing ? (
                        <small className="new-agent-workbench__error">
                          {t("workbench.validation.promptRequired")}
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
                        {t("workbench.validation.modelRequired")}
                      </p>
                    ) : null}
                    <div className="new-agent-workbench__field">
                      <span>{t("workbench.agent.skills")}</span>
                      <SkillSourcePicker
                        selected={draft.selectedSkills ?? []}
                        onChange={onSelectedSkillsChange}
                        cloudProvider={cloudProvider}
                        disabled={deploying}
                        addLabel={t("workbench.agent.addSkill")}
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
                        {t("workbench.deployment.runtimeName")}
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
                          ? t("workbench.deployment.runtimeNameUpdateHint")
                          : t("workbench.deployment.runtimeNameHint")}
                      </small>
                    </label>
                    <label className="new-agent-workbench__field">
                      <span>
                        {t("workbench.deployment.region")}
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
                        <span>{t("workbench.deployment.authentication")}</span>
                        <Select
                          value={authenticationType}
                          options={[
                            {
                              value: "api_key",
                              label: "API Key",
                              description:
                                t("workbench.deployment.apiKeyDescription"),
                            },
                            {
                              value: "user_pool",
                              label: t("workbench.identity.userPool"),
                              description: t("workbench.deployment.userPoolDescription"),
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
                        <span>{t("workbench.deployment.sessionStorage")}</span>
                        <Select
                          value={sessionBackend}
                          options={STM_BACKENDS.map((option) => ({
                            value: option.id,
                            label:
                              option.id === "local"
                                ? t("workbench.deployment.inMemoryStorage")
                                : t(`workbench.deployment.backends.${option.id}`, { defaultValue: option.label }),
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
                        {t("workbench.deployment.instances")}
                      </strong>
                      <div className="new-agent-workbench__instance-fields">
                        <label className="new-agent-workbench__field">
                          <span className="new-agent-workbench__model-field-label">
                            {t("workbench.deployment.minInstances")}
                          </span>
                          <Input
                            type="number"
                            min={0}
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
                            {t("workbench.deployment.maxInstances")}
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
                          {t("workbench.deployment.inMemoryHint")}
                        </small>
                      ) : null}
                    </div>

                    <div className="new-agent-workbench__deployment-section">
                      <label className="new-agent-workbench__field">
                        <span>{t("workbench.deployment.networkMode")}</span>
                        <Select
                          value={networkMode}
                          options={[
                            { value: "public", label: t("workbench.deployment.network.public") },
                            { value: "private", label: t("workbench.deployment.network.private") },
                            { value: "both", label: t("workbench.deployment.network.both") },
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
                              <span>{t("workbench.deployment.subnetIds")}</span>
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
                              <strong>{t("workbench.deployment.sharedInternet")}</strong>
                              <span>{t("workbench.deployment.sharedInternetHint")}</span>
                            </div>
                            <Switch
                              checked={!!network?.enableSharedInternetAccess}
                              onCheckedChange={(enableSharedInternetAccess) =>
                                onNetworkChange({
                                  ...(network ?? { mode: networkMode }),
                                  enableSharedInternetAccess,
                                })
                              }
                              aria-label={t("workbench.deployment.sharedInternet")}
                            />
                          </div>
                        </>
                      ) : null}
                    </div>

                    {cloudProvider !== "byteplus" ? (
                      <div className="new-agent-workbench__deployment-section">
                        <strong className="new-agent-workbench__section-title">
                          {t("workbench.deployment.evaluationSets")}
                        </strong>
                        <div className="new-agent-workbench__switch-row">
                          <div>
                            <strong>{t("workbench.deployment.createEvaluationSets")}</strong>
                            <span>
                              {t("workbench.deployment.evaluationSetsHint")}
                            </span>
                          </div>
                          <Switch
                            checked={createEvaluationSets}
                            onCheckedChange={setCreateEvaluationSets}
                            aria-label={t("workbench.deployment.createEvaluationSets")}
                          />
                        </div>
                      </div>
                    ) : null}

                    <div className="new-agent-workbench__deployment-section">
                      <strong className="new-agent-workbench__section-title">
                        {t("workbench.deployment.resources")}
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
                          {t("workbench.environmentVariables.title")}
                        </strong>
                        <Button
                          color="secondary"
                          variant="ghost"
                          size="sm"
                          pill={false}
                          onClick={addEnv}
                        >
                          <Plus aria-hidden />
                          {t("workbench.environmentVariables.add")}
                        </Button>
                      </div>
                      <div
                        className="new-agent-workbench__env-table"
                        role="table"
                        aria-label={t("workbench.environmentVariables.title")}
                      >
                        <div
                          className="new-agent-workbench__env-table-head"
                          role="row"
                        >
                          <span role="columnheader">{t("common.name")}</span>
                          <span role="columnheader">{t("common.value")}</span>
                          <span role="columnheader">{t("common.actions")}</span>
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
                              <span role="cell">{t("common.none")}</span>
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
                            (deploySucceeded ? t("workbench.deployment.complete") : t("workbench.deployment.preparing"))}
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
                {stepIndex === 0 ? t("common.back") : t("common.previous")}
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
                      ? t("workbench.actions.updateAgain")
                      : t("workbench.actions.deployAgain")
                    : isRuntimeUpdate
                      ? t("workbench.actions.updateAndPublish")
                      : t("common.deploy")
                  : t("common.next")}
              </Button>
            </motion.div>
          </AnimatePresence>
        </section>
      </main>

      <footer className="new-agent-workbench__footer">
        <div className="new-agent-workbench__footer-inner">
          <nav aria-label={t("workbench.progress")}>
            <ol className="new-agent-workbench__progress">
              {WIZARD_STEPS.map((item, index) => (
                <li
                  key={item.id}
                  className={index === stepIndex ? "is-active" : ""}
                  aria-current={index === stepIndex ? "step" : undefined}
                  aria-label={t(`workbench.steps.${item.id}.label`)}
                  title={t(`workbench.steps.${item.id}.label`)}
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
