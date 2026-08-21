import {
  type CSSProperties,
  type ComponentType,
  Fragment,
  lazy,
  type ReactNode,
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  AnimatePresence,
  motion,
  useReducedMotion,
  type Variants,
} from "motion/react";
import { Checkbox } from "@openai/apps-sdk-ui/components/Checkbox";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { Input } from "@openai/apps-sdk-ui/components/Input";
import { RadioGroup } from "@openai/apps-sdk-ui/components/RadioGroup";
import {
  Select,
  type Option as SelectOption,
} from "@openai/apps-sdk-ui/components/Select";
import { Textarea } from "@openai/apps-sdk-ui/components/Textarea";
import {
  ArrowUp,
  Bot,
  Boxes,
  ChevronRight,
  Cpu,
  Database,
  ExternalLink,
  FolderUp,
  Globe,
  Info,
  Layers,
  Loader2,
  Plus,
  Rocket,
  Shapes,
  Sparkles,
  Trash2,
  Wrench,
  X,
} from "lucide-react";
import {
  type CreateModeProps,
  type AgentDraft,
  type CloudEnvironmentConfig,
  MAX_CLOUD_DOCKERFILE_LENGTH,
  type McpTool,
  type SelectedSkill,
  emptyDraft,
} from "./types";
import {
  harnessSidecarProviderNotice,
  harnessSidecarOptionLabel,
  harnessSidecarProfileLabel,
  releaseDraftFromDebugVariant,
  selectedHarnessModelProxyOptimizations,
  selectedHarnessProfile,
  selectedHarnessOptimizations,
} from "./harnessSidecarOptions";
import {
  A2A_REGISTRY_DEFAULTS,
  A2A_REGISTRY_ENV,
  BUILTIN_TOOLS,
  createBuiltinToolsForProvider,
  STM_BACKENDS,
  LTM_BACKENDS,
  KB_BACKENDS,
  DEFAULT_KB_BACKEND,
  TRACING_EXPORTERS,
  type BackendOption,
  type EnvVar,
} from "./veadkCatalog";
import {
  firstInvalidRuntimeEnv,
  runtimeEnvConfiguration,
  runtimeEnvJsonError,
  runtimeEnvVars,
  type RuntimeEnvConfiguration,
  type RuntimeEnvSelection,
} from "./deploymentEnv";
import { agentNameProblem, duplicateAgentNames } from "./agentNameValidation";
import {
  AGENT_TYPES,
  agentTypeMeta,
  isA2aType,
  isOrchestratorType,
} from "./agentTypeMeta";
import { displayDescription } from "./displayText";
import { localPickerMatches } from "./localPickerSearch";
import {
  mcpAuthTokenInputValue,
  mcpUrlNeedsPathWarning,
  prepareMcpAuth,
  updateMcpAuthTokenInput,
} from "./mcpAuth";
import {
  normalizeDraft,
  sanitizeGeneratedDraftCapabilities,
} from "./normalizeDraft";
import {
  activeModelConfiguration,
  resolvedModelSource,
  type ModelSource,
} from "./modelSource";
import { resolveRuntimeName } from "./runtimeName";
import type { AgentProject } from "./project";
import { AgentBuildCanvas } from "./AgentBuildCanvas";
import {
  AgentBuilderChatPanel,
  type AgentBuilderChatMessage,
} from "./AgentBuilderChatPanel";
import {
  loadAgentBuilderConversation,
  writeAgentBuilderConversation,
  type StoredAgentBuilderConversation,
} from "./agentBuilderConversationStorage";
import { CreateAgentHeader } from "../ui/CreateAgentHeader";
import {
  AgentFaceSquareIcon,
  CreateCloseIcon,
  DebugSettingsIcon,
  MessageSmileSquareIcon,
} from "../ui/icons/CreateAgentIcons";
import type { SkillSource } from "./skills/types";
import { SkillHubPicker } from "./SkillHubPicker";
import { LocalPicker } from "./LocalPicker";
import { SkillSpacePicker } from "./SkillSpacePicker";
import {
  CloudEnvironmentAdvancedTrigger,
  CloudEnvironmentConfigurator,
} from "../ui/CloudEnvironmentConfigurator";
import { listA2aSpaces, type A2aSpaceRef } from "./a2aSpaces";
import {
  listVikingKnowledgebases,
  type VikingKnowledgebaseRef,
} from "./vikingKnowledgebases";
import { listVikingMemories, type VikingMemoryRef } from "./vikingMemories";
import {
  ProjectPreview,
  type DeployResult,
  type DeploymentTaskUpdate,
} from "../ui/ProjectPreview";
import { Blocks, ThinkingPlaceholder } from "../ui/Blocks";
import { DeploymentErrorMessage } from "../ui/DeploymentErrorMessage";
import { StudioConfirmDialog } from "../ui/StudioConfirmDialog";
import { TraceDrawer } from "../ui/TraceDrawer";
import { isImeCompositionEvent } from "../ui/composerKeyboard";
import {
  createGeneratedAgentTestRun,
  createGeneratedAgentTestSession,
  createGeneratedAgentConversation,
  deleteGeneratedAgentTestRun,
  deployAgentkitProject,
  generateAgentDraftFromRequirement,
  generateAgentProject,
  listModelApiKeys,
  listModelOptions,
  type ModelApiKeyOption,
  runGeneratedAgentTestSSE,
  runGeneratedAgentConversationSSE,
  type AdkEvent,
  type GeneratedAgentConversationEvent,
  type ModelOption,
} from "../adk/client";
import {
  beginAgentDebug,
  classifyTelemetryError,
  type AgentDebugFailedProps,
} from "../telemetry";
import type {
  DeployStage,
  GeneratedAgentTestRun,
  UiFeatures,
} from "../adk/client";
import {
  defaultCloudRegion,
  defaultEmbeddingModelName,
  defaultImageEditModelName,
  defaultImageModelName,
  defaultModelApiBase,
  defaultModelName,
  defaultVideoModelName,
  modelActivationConsoleUrl,
  plannerModelName,
  type CloudProvider,
} from "../adk/cloudProvider";
import { applyEvent, emptyAcc, type Block } from "../blocks";
import {
  customModelCredentialRequirements,
  customModelEnvironmentBindings,
} from "./customModelCredentials";
import "./CustomCreate.css";

const MarkdownPromptEditor = lazy(() => import("./MarkdownPromptEditor"));

const DEBUG_TEST_RUN_STORAGE_KEY = "veadk.generatedAgentTestRuns";
const GENERATED_AGENT_REQUIREMENT_MIN_LENGTH = 4;
const AGENT_BUILDER_PERSIST_DEBOUNCE_MS = 200;

function readStoredDebugTestRunIds(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(
      window.sessionStorage.getItem(DEBUG_TEST_RUN_STORAGE_KEY) ?? "[]",
    );
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (item): item is string => typeof item === "string" && item.length > 0,
    );
  } catch {
    return [];
  }
}

function writeStoredDebugTestRunIds(runIds: string[]) {
  if (typeof window === "undefined") return;
  const uniqueRunIds = Array.from(new Set(runIds)).slice(-20);
  try {
    if (uniqueRunIds.length) {
      window.sessionStorage.setItem(
        DEBUG_TEST_RUN_STORAGE_KEY,
        JSON.stringify(uniqueRunIds),
      );
    } else {
      window.sessionStorage.removeItem(DEBUG_TEST_RUN_STORAGE_KEY);
    }
  } catch {
    // Best-effort cleanup bookkeeping only.
  }
}

function rememberDebugTestRun(runId: string) {
  writeStoredDebugTestRunIds([...readStoredDebugTestRunIds(), runId]);
}

function forgetDebugTestRun(runId: string) {
  writeStoredDebugTestRunIds(
    readStoredDebugTestRunIds().filter((item) => item !== runId),
  );
}

/* ---------------------------------------------------------------- *
 * Step metadata. Each step renders its own form panel on the right;
 * the left rail shows progress + per-step completion checkmarks.
 * ---------------------------------------------------------------- */
type StepId =
  | "type"
  | "basic"
  | "model"
  | "tools"
  | "skills"
  | "knowledge"
  | "memory"
  | "subagents"
  | "review";

interface StepMeta {
  id: StepId;
  label: string;
  hint: string;
  icon: typeof Bot;
  required?: boolean;
}

const STEPS: StepMeta[] = [
  {
    id: "type",
    label: "Agent 类型",
    hint: "选择 Agent 类型",
    icon: Shapes,
    required: true,
  },
  {
    id: "basic",
    label: "基本信息",
    hint: "名称、描述与系统提示词",
    icon: Info,
    required: true,
  },
  { id: "model", label: "模型配置", hint: "模型与服务（可选）", icon: Cpu },
  { id: "tools", label: "工具", hint: "可调用的能力", icon: Wrench },
  { id: "skills", label: "技能", hint: "声明式技能", icon: Sparkles },
  { id: "knowledge", label: "知识库", hint: "外部知识检索", icon: Database },
  { id: "memory", label: "记忆", hint: "短期与长期记忆", icon: Layers },
  { id: "subagents", label: "子 Agent", hint: "嵌套协作", icon: Boxes },
  { id: "review", label: "完成", hint: "预览并创建", icon: Rocket },
];

/** Root-only reset mark: a tilted eraser clearing the current draft. */
function ClearAgentIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="m7.2 15.8 7.9-7.9a2 2 0 0 1 2.8 0l1.2 1.2a2 2 0 0 1 0 2.8l-7 7H8.7l-1.5-1.5a1.15 1.15 0 0 1 0-1.6Z" />
      <path d="m12.7 10.3 4 4" />
      <path d="M6.3 19h12.4" />
      <path d="m5.5 8.2.5-1.4 1.4-.5L6 5.8l-.5-1.4L5 5.8l-1.4.5 1.4.5.5 1.4Z" />
    </svg>
  );
}

function DebugVariantDeleteIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M4.75 7.25h14.5" />
      <path d="M9.1 4.75h5.8l.75 2.5h-7.3l.75-2.5Z" />
      <path d="m6.75 7.25.75 12h9l.75-12" />
      <path d="M10 10.25v5.75M14 10.25v5.75" />
    </svg>
  );
}

function A2aRefreshIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M18.25 8.2A7.1 7.1 0 0 0 6.1 6.65L4.5 8.25" />
      <path d="M4.5 4.75v3.5H8" />
      <path d="M5.75 15.8A7.1 7.1 0 0 0 17.9 17.35l1.6-1.6" />
      <path d="M19.5 19.25v-3.5H16" />
    </svg>
  );
}

type AgentType = NonNullable<AgentDraft["agentType"]>;

const AGENT_TYPE_BAR_LABELS: Record<AgentType, string> = {
  llm: "智能体",
  sequential: "分步协作",
  parallel: "同时处理",
  loop: "循环执行",
  a2a: "远程智能体",
};

const A2A_REGISTRY_ENV_TO_FIELD = {
  REGISTRY_SPACE_ID: "registrySpaceId",
  REGISTRY_TOP_K: "registryTopK",
  REGISTRY_REGION: "registryRegion",
  REGISTRY_ENDPOINT: "registryEndpoint",
} as const;

type A2aRegistryEnvKey = keyof typeof A2A_REGISTRY_ENV_TO_FIELD;
const A2A_REGISTRY_SPACE_ENV_KEY = "REGISTRY_SPACE_ID";
const A2A_REGISTRY_RUNTIME_ENV = A2A_REGISTRY_ENV.filter(
  (item) => item.key !== A2A_REGISTRY_SPACE_ENV_KEY,
);

function a2aRegistryEnvValues(
  registry: AgentDraft["a2aRegistry"] | undefined,
  options: { includeDefaults: boolean },
): Record<string, string> {
  if (!registry?.enabled) return {};
  const values: Record<string, string> = {
    REGISTRY_SPACE_ID: registry.registrySpaceId ?? "",
  };
  if (options.includeDefaults) {
    values.REGISTRY_TOP_K =
      registry.registryTopK?.trim() || A2A_REGISTRY_DEFAULTS.topK;
    values.REGISTRY_REGION =
      registry.registryRegion?.trim() || A2A_REGISTRY_DEFAULTS.region;
    values.REGISTRY_ENDPOINT =
      registry.registryEndpoint?.trim() || A2A_REGISTRY_DEFAULTS.endpoint;
  } else {
    values.REGISTRY_TOP_K = registry.registryTopK ?? "";
    values.REGISTRY_REGION = registry.registryRegion ?? "";
    values.REGISTRY_ENDPOINT = registry.registryEndpoint ?? "";
  }
  return values;
}

function providerRuntimeEnv(
  env: EnvVar[],
  cloudProvider: CloudProvider,
): EnvVar[] {
  if (cloudProvider !== "byteplus") return env;
  return env.map((item) => {
    if (item.key === "MODEL_EMBEDDING_NAME") {
      return { ...item, placeholder: defaultEmbeddingModelName(cloudProvider) };
    }
    if (item.key === "MODEL_EMBEDDING_API_BASE") {
      return { ...item, placeholder: defaultModelApiBase(cloudProvider) };
    }
    if (item.key === "MODEL_IMAGE_NAME") {
      return { ...item, placeholder: defaultImageModelName(cloudProvider) };
    }
    if (item.key === "MODEL_EDIT_NAME") {
      return { ...item, placeholder: defaultImageEditModelName(cloudProvider) };
    }
    if (item.key === "MODEL_VIDEO_NAME") {
      return { ...item, placeholder: defaultVideoModelName(cloudProvider) };
    }
    if (
      item.key === "MODEL_IMAGE_API_BASE" ||
      item.key === "MODEL_EDIT_API_BASE" ||
      item.key === "MODEL_VIDEO_API_BASE"
    ) {
      return { ...item, placeholder: defaultModelApiBase(cloudProvider) };
    }
    return item;
  });
}

/* ---------------------------------------------------------------- *
 * Multi-select checklist. Each row = label + desc, toggling the id in
 * `selected`. Used for built-in tools and tracing exporters.
 * ---------------------------------------------------------------- */
interface ChecklistItem {
  id: string;
  label: string;
  desc: string;
}

function Checklist({
  items,
  selected,
  onToggle,
  scrollRows,
}: {
  items: ChecklistItem[];
  selected: string[];
  onToggle: (id: string) => void;
  scrollRows?: number;
}) {
  return (
    <div
      className={`cw-checklist ${scrollRows ? "cw-checklist-tools" : ""}`}
      style={
        scrollRows
          ? ({
              "--cw-checklist-max-height": `${scrollRows * 40 + (scrollRows - 1) * 8}px`,
            } as CSSProperties)
          : undefined
      }
    >
      {items.map((it) => {
        const on = selected.includes(it.id);
        return (
          <Checkbox
            key={it.id}
            id={`cw-check-${it.id}`}
            className={`cw-check ${on ? "is-on" : ""}`}
            checked={on}
            onCheckedChange={(next) => {
              if (next !== on) onToggle(it.id);
            }}
            label={
              <span className="cw-check-text">
                <span className="cw-check-title">{it.label}</span>
              </span>
            }
          />
        );
      })}
    </div>
  );
}

/* ---------------------------------------------------------------- *
 * Segmented backend picker. Renders BackendOption[] as a wrapping row
 * of selectable cards; one active at a time.
 * ---------------------------------------------------------------- */
function BackendSelect({
  id,
  options,
  value,
  onChange,
}: {
  id: string;
  options: BackendOption[];
  value: string | undefined;
  onChange: (id: string) => void;
}) {
  const selectOptions: SelectOption[] = options.map((option) => ({
    value: option.id,
    label: option.label,
  }));
  return (
    <Select
      id={id}
      options={selectOptions}
      value={value ?? options[0]?.id ?? ""}
      placeholder="请选择后端"
      size="md"
      pill={false}
      align="start"
      triggerClassName="cw-agent-config-select-trigger"
      optionClassName="cw-agent-config-select-option"
      onChange={(option) => onChange(option.value)}
    />
  );
}

function isSensitiveEnv(key: string): boolean {
  return /(SECRET|PASSWORD|KEY|TOKEN)$/.test(key);
}

/** Feature-specific settings stay readable in their own configuration area,
 * while their VeADK environment-variable names remain visible and exact. */
function RuntimeEnvFields({
  env,
  values,
  onChange,
  renderAfterField,
}: {
  env: EnvVar[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  renderAfterField?: (item: EnvVar) => ReactNode;
}) {
  const visibleEnv = env.filter((item) => !item.hidden);
  if (visibleEnv.length === 0) {
    return <p className="cw-env-empty">此后端无需额外运行参数。</p>;
  }
  return (
    <div className="cw-env-fields">
      {visibleEnv.map((item) => {
        const value = values[item.key] ?? item.defaultValue ?? "";
        const jsonError = runtimeEnvJsonError(item, values);
        const controlId = `cw-env-${item.key}`;
        return (
          <Fragment key={item.key}>
            <label className="cw-env-field" htmlFor={controlId}>
              <span className="cw-env-field-head">
                <span className="cw-env-field-title">
                  <span className="cw-env-field-label">
                    {item.comment || item.key}
                    {item.required && <span className="cw-req">*</span>}
                  </span>
                  {item.help && (
                    <span
                      className="cw-env-help"
                      tabIndex={0}
                      data-help={item.help}
                      aria-label={`${item.comment || item.key}说明：${item.help}`}
                    >
                      ?
                      <span className="cw-env-help-popover" role="tooltip">
                        {item.help}
                      </span>
                    </span>
                  )}
                  {item.link && (
                    <a
                      className="cw-env-link"
                      href={item.link.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={`打开 OpenViking ${item.link.label}`}
                      aria-label={`打开 OpenViking ${item.link.label}`}
                      onClick={(event) => event.stopPropagation()}
                    >
                      <ExternalLink aria-hidden="true" />
                    </a>
                  )}
                </span>
                {item.comment && <code title={item.key}>{item.key}</code>}
              </span>
              {item.multiline || item.format === "json" ? (
                <Textarea
                  id={controlId}
                  size="md"
                  rows={4}
                  value={value}
                  placeholder={item.placeholder || "请输入参数值"}
                  autoComplete="off"
                  spellCheck={false}
                  invalid={!!jsonError}
                  aria-invalid={!!jsonError}
                  onChange={(event) =>
                    onChange(item.key, event.currentTarget.value)
                  }
                />
              ) : (
                <Input
                  id={controlId}
                  size="md"
                  type={isSensitiveEnv(item.key) ? "password" : "text"}
                  value={value}
                  placeholder={item.placeholder || "请输入参数值"}
                  autoComplete="off"
                  invalid={!!jsonError}
                  aria-invalid={!!jsonError}
                  onChange={(event) =>
                    onChange(item.key, event.currentTarget.value)
                  }
                />
              )}
              {jsonError && <span className="cw-env-error">{jsonError}</span>}
            </label>
            {renderAfterField?.(item)}
          </Fragment>
        );
      })}
    </div>
  );
}

const OPENVIKING_KNOWLEDGE_INDEX_HELP =
  "默认值：留空；生成项目时使用 Agent 名自动生成，例如 my_agent_kb。未配置 DATABASE_OPENVIKING_TARGET_URI 时，默认 URI 拼接为 viking://user/{知识库归属 ID，未填则 default}/resources/{资源索引}/；如果填写了 DATABASE_OPENVIKING_TARGET_URI，则直接使用该完整 URI。";

function OpenVikingKnowledgeIndexField({
  value,
  onChange,
}: {
  value: string;
  onChange: (index: string) => void;
}) {
  const controlId = "cw-openviking-knowledge-index";
  return (
    <label className="cw-env-field" htmlFor={controlId}>
      <span className="cw-env-field-head">
        <span className="cw-env-field-title">
          <span className="cw-env-field-label">OpenViking 资源索引</span>
          <span
            className="cw-env-help"
            tabIndex={0}
            data-help={OPENVIKING_KNOWLEDGE_INDEX_HELP}
            aria-label={`OpenViking 资源索引说明：${OPENVIKING_KNOWLEDGE_INDEX_HELP}`}
          >
            ?
            <span className="cw-env-help-popover" role="tooltip">
              {OPENVIKING_KNOWLEDGE_INDEX_HELP}
            </span>
          </span>
        </span>
      </span>
      <Input
        id={controlId}
        size="md"
        value={value}
        placeholder=""
        autoComplete="off"
        onChange={(event) => onChange(event.currentTarget.value)}
      />
    </label>
  );
}

function a2aSpaceDisplayName(space: A2aSpaceRef): string {
  return space.name.trim() || "未命名智能体中心";
}

function vikingKnowledgebaseDisplayName(item: VikingKnowledgebaseRef): string {
  const name = item.name.trim() || item.id || "未命名知识库";
  const details = [item.sourceLabel, item.projectName].filter(Boolean);
  return details.length ? `${name} · ${details.join(" · ")}` : name;
}

function vikingMemoryDisplayName(item: VikingMemoryRef): string {
  return item.name.trim() || item.id || "未命名记忆库";
}

function modelAvailabilityLabel(model: ModelOption): string {
  if (model.available) return "已开通";
  if (model.lifecycleStatus === "Retiring") return "即将下线";
  if (model.activationState && model.activationState !== "Available") {
    return "未开通";
  }
  return "暂不可用";
}

function isModelSelectable(model: ModelOption): boolean {
  return model.available || model.lifecycleStatus === "Retiring";
}

type ModelCatalogOption = SelectOption & {
  kind: "model" | "unknown" | "activation";
  model?: ModelOption;
  searchTerms: string[];
};

type ModelApiKeyCatalogOption = SelectOption & {
  apiKey: ModelApiKeyOption;
  searchTerms: string[];
};

type A2aSpaceCatalogOption = SelectOption & {
  searchTerms: string[];
};

function catalogSearchPredicate(
  option: SelectOption & { searchTerms?: string[] },
  searchTerm: string,
): boolean {
  return localPickerMatches(searchTerm, [
    option.label,
    ...(option.searchTerms ?? []),
  ]);
}

function ModelCatalogOptionView(option: ModelCatalogOption) {
  const model = option.model;
  if (!model) {
    return (
      <>
        <span className="cw-model-option-copy">
          <strong>当前配置</strong>
          <small>{option.value}</small>
        </span>
        <span className="cw-model-status is-unknown">状态未知</span>
      </>
    );
  }
  return (
    <>
      <span className="cw-model-option-copy">
        <strong>{model.displayName}</strong>
        <small>
          {model.id}
          {model.vendorName ? ` · ${model.vendorName}` : ""}
        </small>
      </span>
      <span
        className={`cw-model-status ${
          option.kind === "activation"
            ? "is-unavailable"
            : model.available
              ? "is-available"
              : model.lifecycleStatus === "Retiring"
                ? "is-retiring"
                : "is-unavailable"
        }`}
      >
        {option.kind === "activation"
          ? "未开通，去开通"
          : modelAvailabilityLabel(model)}
      </span>
    </>
  );
}

function ModelOptionSelect({
  value,
  cloudProvider,
  apiKeyId,
  apiKeyName,
  onApiKeyChange,
  onChange,
}: {
  value: string;
  cloudProvider: CloudProvider;
  apiKeyId?: string;
  apiKeyName?: string;
  onApiKeyChange: (key: ModelApiKeyOption) => void;
  onChange: (modelId: string) => void;
}) {
  const [apiKeys, setApiKeys] = useState<ModelApiKeyOption[]>([]);
  const [keysLoading, setKeysLoading] = useState(false);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [modelsApiKeyId, setModelsApiKeyId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [keySelectionRevision, setKeySelectionRevision] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setKeysLoading(true);
    setError(null);
    listModelApiKeys(controller.signal)
      .then((response) => {
        if (controller.signal.aborted) return;
        setApiKeys(response.keys);
        const selected =
          response.keys.find((key) => key.id === apiKeyId) ??
          response.keys.find((key) => key.name === apiKeyName) ??
          response.keys.find((key) => key.id === response.defaultKeyId) ??
          response.keys[0];
        if (selected) onApiKeyChange(selected);
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setError(
            err instanceof Error ? err.message : "加载 Ark API Key 失败",
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setKeysLoading(false);
      });
    return () => controller.abort();
  }, [cloudProvider]);

  useEffect(() => {
    if (!apiKeyId) {
      setModels([]);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setModelsApiKeyId(null);
    listModelOptions({
      signal: controller.signal,
      apiKeyId,
      refresh: keySelectionRevision > 0,
    })
      .then((response) => {
        if (!controller.signal.aborted) {
          setModels(response.models);
          setModelsApiKeyId(apiKeyId);
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : "加载模型列表失败");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [apiKeyId, cloudProvider, keySelectionRevision]);

  const normalizedValue = value.trim();
  const modelsAreCurrent = modelsApiKeyId === apiKeyId;
  const visibleModels = modelsAreCurrent ? models : [];
  const selectedApiKey = apiKeys.find((key) => key.id === apiKeyId);
  const selectedApiKeyLabel = selectedApiKey
    ? selectedApiKey.name
    : apiKeyId
      ? "当前 API Key"
      : keysLoading
        ? "正在加载 API Key…"
        : apiKeys.length === 0
          ? "暂无可用 API Key"
          : "请选择 API Key";
  const selectedModel = visibleModels.find(
    (model) => model.id === normalizedValue,
  );
  const selectedLabel =
    loading && !modelsAreCurrent
      ? "正在刷新模型列表…"
      : selectedModel
        ? selectedModel.displayName
        : normalizedValue || "请选择模型";
  const apiKeyOptions = useMemo<ModelApiKeyCatalogOption[]>(
    () =>
      apiKeys.map((key) => ({
        value: key.id,
        label: key.name,
        searchTerms: [key.name],
        apiKey: key,
      })),
    [apiKeys],
  );
  const modelOptions = useMemo<ModelCatalogOption[]>(() => {
    const options: ModelCatalogOption[] = visibleModels.map((model) => {
      const selectable = isModelSelectable(model);
      const activationRequired =
        !selectable && model.activationState !== "Available";
      return {
        value: model.id,
        label: model.displayName,
        disabled: !selectable && !activationRequired,
        kind: activationRequired ? "activation" : "model",
        model,
        searchTerms: [
          model.displayName,
          model.id,
          model.name,
          model.vendorName,
          model.activationState,
          model.lifecycleStatus,
        ].filter((term): term is string => Boolean(term)),
      } satisfies ModelCatalogOption;
    });
    if (normalizedValue && !selectedModel) {
      options.unshift({
        value: normalizedValue,
        label: normalizedValue,
        kind: "unknown",
        searchTerms: [normalizedValue],
      });
    }
    return options;
  }, [normalizedValue, selectedModel, visibleModels]);
  const availableCount = visibleModels.filter(
    (model) => model.available,
  ).length;
  const activationConsoleUrl = modelActivationConsoleUrl(cloudProvider);

  return (
    <div className="cw-a2a-space-picker cw-model-picker">
      <div className="cw-model-picker-stack">
        <div className="cw-model-picker-field">
          <label className="cw-model-picker-label" htmlFor="cw-model-api-key">
            API Key
          </label>
          <Select
            id="cw-model-api-key"
            options={apiKeyOptions}
            value={apiKeyId ?? ""}
            loading={keysLoading}
            loadingPlaceholder="正在加载 API Key…"
            placeholder={selectedApiKeyLabel}
            size="lg"
            pill={false}
            align="start"
            triggerClassName="cw-agent-config-select-trigger"
            optionClassName="cw-agent-config-select-option"
            searchPlaceholder="搜索 API Key 名称"
            searchEmptyMessage="未找到匹配的 API Key"
            searchPredicate={catalogSearchPredicate}
            onChange={(option) => {
              setKeySelectionRevision((revision) => revision + 1);
              onApiKeyChange(option.apiKey);
            }}
          />
        </div>
        <div className="cw-model-picker-field">
          <label className="cw-model-picker-label" htmlFor="cw-model-name-select">
            模型名称
          </label>
          <div className="cw-a2a-space-select-wrap">
            <Select
              id="cw-model-name-select"
              options={modelOptions}
              value={normalizedValue}
              loading={loading}
              loadingPlaceholder="正在刷新模型列表…"
              placeholder={selectedLabel}
              size="lg"
              pill={false}
              align="start"
              triggerClassName="cw-agent-config-select-trigger"
              optionClassName="cw-agent-config-select-option"
              OptionView={ModelCatalogOptionView}
              searchPlaceholder="搜索名称、Model ID 或服务商"
              searchEmptyMessage="未找到匹配的模型"
              searchPredicate={catalogSearchPredicate}
              onChange={(option) => {
                if (option.kind === "activation") {
                  window.open(
                    activationConsoleUrl,
                    "_blank",
                    "noopener,noreferrer",
                  );
                  return;
                }
                onChange(option.value);
              }}
            />
          </div>
        </div>
      </div>
      {error ? (
        <div className="cw-banner cw-a2a-space-error" role="alert">
          <Info className="cw-i" />
          <span>{error}</span>
        </div>
      ) : !loading && visibleModels.length === 0 ? (
        <span className="cw-help">当前账号下暂无可配置模型。</span>
      ) : !loading ? (
        <span className="cw-help">
          已加载 {visibleModels.length} 个模型，其中 {availableCount} 个已开通。
        </span>
      ) : null}
    </div>
  );
}

function A2aSpaceSelect({
  value,
  region,
  invalid,
  onChange,
}: {
  value: string;
  region: string;
  invalid: boolean;
  onChange: (spaceId: string) => void;
}) {
  const normalizedRegion = region.trim() || A2A_REGISTRY_DEFAULTS.region;
  const [spaces, setSpaces] = useState<A2aSpaceRef[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listA2aSpaces({ region: normalizedRegion })
      .then((items) => {
        if (!cancelled) setSpaces(items);
      })
      .catch((err) => {
        if (!cancelled) {
          setSpaces([]);
          setError(err instanceof Error ? err.message : "加载失败");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [normalizedRegion, reloadKey]);

  const selectedKnown =
    !value || spaces.some((space) => space.id === value.trim());
  const selectedSpace = spaces.find((space) => space.id === value.trim());
  const selectedLabel = selectedSpace
    ? a2aSpaceDisplayName(selectedSpace)
    : value && !selectedKnown
      ? "已选择的智能体中心"
      : "请选择智能体中心";
  const disabled = loading && spaces.length === 0;
  const spaceOptions = useMemo<A2aSpaceCatalogOption[]>(() => {
    const options: A2aSpaceCatalogOption[] = spaces.map((space) => ({
      value: space.id,
      label: a2aSpaceDisplayName(space),
      searchTerms: [
        a2aSpaceDisplayName(space),
        space.id,
        space.projectName,
      ].filter((term): term is string => Boolean(term)),
    }));
    if (value && !selectedKnown) {
      options.unshift({
        value,
        label: "已选择的智能体中心",
        searchTerms: ["已选择的智能体中心", value],
      });
    }
    return options;
  }, [selectedKnown, spaces, value]);

  return (
    <div className="cw-a2a-space-picker">
      <div className="cw-a2a-space-row">
        <div
          className="cw-a2a-space-select-wrap"
          aria-invalid={invalid || undefined}
        >
          <Select
            id="cw-a2a-space"
            options={spaceOptions}
            value={value}
            placeholder={selectedLabel}
            loadingPlaceholder="正在加载智能体中心…"
            loading={loading}
            disabled={disabled}
            size="lg"
            pill={false}
            align="start"
            triggerClassName="cw-agent-config-select-trigger"
            optionClassName="cw-agent-config-select-option"
            searchPlaceholder="搜索名称或 ID"
            searchEmptyMessage="未找到匹配的智能体中心"
            searchPredicate={catalogSearchPredicate}
            onChange={(option) => onChange(option.value)}
          />
        </div>
        <button
          type="button"
          className="cw-icon-btn cw-a2a-space-refresh"
          title="刷新智能体中心列表"
          aria-label="刷新智能体中心列表"
          disabled={loading}
          onClick={() => setReloadKey((key) => key + 1)}
        >
          {loading ? (
            <Loader2 className="cw-i cw-i-sm cw-spin" />
          ) : (
            <A2aRefreshIcon className="cw-i cw-i-sm" />
          )}
        </button>
      </div>
      {error ? (
        <div className="cw-banner cw-a2a-space-error" role="alert">
          <Info className="cw-i" />
          <span>{error}</span>
        </div>
      ) : loading ? (
        <span className="cw-help cw-a2a-space-status">
          <Loader2 className="cw-i cw-i-sm cw-spin" />
          正在加载 AgentKit 智能体中心…
        </span>
      ) : spaces.length === 0 ? (
        <span className="cw-help">此账号下暂无 AgentKit 智能体中心。</span>
      ) : (
        <span className="cw-help">
          已加载 {spaces.length} 个智能体中心，列表仅展示中心名称。
        </span>
      )}
    </div>
  );
}

type ResourcePickerItem = { id: string };

type ResourceCatalogOption<T extends ResourcePickerItem> = SelectOption & {
  item: T;
  searchTerms: string[];
};

function ResourcePicker<T extends ResourcePickerItem>({
  value,
  items,
  loading,
  error,
  pickerClassName,
  placeholder,
  emptyMessage,
  loadedMessage,
  refreshLabel,
  noMatchesMessage,
  getLabel,
  getSearchFields,
  makeUnknownItem,
  onChange,
  onRefresh,
}: {
  value: string;
  items: T[];
  loading: boolean;
  error: string | null;
  pickerClassName: string;
  selectLabel: string;
  searchLabel: string;
  listLabel: string;
  placeholder: string;
  emptyMessage: ReactNode;
  loadedMessage: (count: number) => ReactNode;
  refreshLabel: string;
  noMatchesMessage: string;
  getLabel: (item: T) => string;
  getSearchFields: (item: T) => Array<string | undefined>;
  getKey: (item: T) => string;
  getOptionIds: (item: T) => Array<string | undefined>;
  makeUnknownItem: (id: string) => T;
  onChange: (item: T) => void;
  onRefresh: () => void;
}) {
  const selectedKnown =
    !value || items.some((item) => item.id === value.trim());
  const selectedItem = items.find((item) => item.id === value.trim());
  const selectedLabel = selectedItem
    ? getLabel(selectedItem)
    : value && !selectedKnown
      ? value
      : placeholder;
  const disabled = loading && items.length === 0;
  const options = useMemo<ResourceCatalogOption<T>[]>(() => {
    const nextOptions: ResourceCatalogOption<T>[] = items.map((item) => ({
      value: item.id,
      label: getLabel(item),
      item,
      searchTerms: getSearchFields(item).filter(
        (term): term is string => Boolean(term),
      ),
    }));
    if (value && !selectedKnown) {
      const item = makeUnknownItem(value);
      nextOptions.unshift({
        value,
        label: value,
        item,
        searchTerms: [value],
      });
    }
    return nextOptions;
  }, [getLabel, getSearchFields, items, makeUnknownItem, selectedKnown, value]);

  if (loading && items.length === 0) {
    return (
      <span className="cw-viking-kb-inline-status" role="status">
        <Loader2 className="cw-i cw-i-sm cw-spin" />
        正在加载…
      </span>
    );
  }

  return (
    <div className={`cw-a2a-space-picker ${pickerClassName}`}>
      <div className="cw-a2a-space-row">
        <div className="cw-a2a-space-select-wrap">
          <Select
            id={`cw-resource-picker-${pickerClassName.replace(/[^a-z0-9-]/gi, "-")}`}
            options={options}
            value={value}
            placeholder={selectedLabel}
            loading={loading}
            loadingPlaceholder="正在加载…"
            disabled={disabled}
            size="lg"
            pill={false}
            align="start"
            triggerClassName="cw-agent-config-select-trigger"
            optionClassName="cw-agent-config-select-option"
            searchPlaceholder="搜索名称或 ID"
            searchEmptyMessage={noMatchesMessage}
            searchPredicate={catalogSearchPredicate}
            onChange={(option) => onChange(option.item)}
          />
        </div>
        <button
          type="button"
          className="cw-icon-btn cw-a2a-space-refresh cw-viking-kb-refresh"
          title={refreshLabel}
          aria-label={refreshLabel}
          disabled={loading}
          onClick={onRefresh}
        >
          {loading ? (
            <Loader2 className="cw-i cw-i-sm cw-spin" />
          ) : (
            <A2aRefreshIcon className="cw-i cw-i-sm" />
          )}
        </button>
      </div>
      {error ? (
        <div className="cw-banner cw-a2a-space-error" role="alert">
          <Info className="cw-i" />
          <span>{error}</span>
        </div>
      ) : items.length === 0 ? (
        <span className="cw-help">{emptyMessage}</span>
      ) : (
        <span className="cw-help">{loadedMessage(items.length)}</span>
      )}
    </div>
  );
}

function VikingKnowledgebaseSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (item: VikingKnowledgebaseRef) => void;
}) {
  const [items, setItems] = useState<VikingKnowledgebaseRef[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listVikingKnowledgebases()
      .then((next) => {
        if (!cancelled) setItems(next);
      })
      .catch((err) => {
        if (!cancelled) {
          setItems([]);
          setError(err instanceof Error ? err.message : "加载失败");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  return (
    <ResourcePicker
      value={value}
      items={items}
      loading={loading}
      error={error}
      pickerClassName="cw-viking-kb-picker"
      selectLabel="选择 VikingDB 知识库"
      searchLabel="搜索 VikingDB 知识库"
      listLabel="VikingDB 知识库"
      placeholder="请选择 VikingDB 知识库"
      emptyMessage="此账号下暂无 VikingDB 知识库。"
      loadedMessage={(count) =>
        `已加载 ${count} 个知识库，选择的知识库会用于当前 Agent。`
      }
      refreshLabel="刷新知识库列表"
      noMatchesMessage="未找到匹配的知识库"
      getLabel={vikingKnowledgebaseDisplayName}
      getSearchFields={(item) => [
        vikingKnowledgebaseDisplayName(item),
        item.id,
        item.description,
        item.projectName,
        item.resourceId,
        item.agentkitKnowledgeId,
        item.providerKnowledgeId,
        item.sourceLabel,
      ]}
      getKey={(item) => item.id}
      getOptionIds={(item) => [
        item.id,
        item.resourceId,
        item.agentkitKnowledgeId,
        item.providerKnowledgeId,
      ]}
      makeUnknownItem={(id) => ({
        id,
        name: id,
        description: "",
        projectName: "",
        region: "",
        sourceKind: "knowledge" as const,
        sourceLabel: "Knowledge Engine",
        resourceId: "",
      })}
      onChange={onChange}
      onRefresh={() => setReloadKey((key) => key + 1)}
    />
  );
}

function VikingMemorySelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (item: VikingMemoryRef) => void;
}) {
  const [items, setItems] = useState<VikingMemoryRef[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listVikingMemories()
      .then((next) => {
        if (!cancelled) setItems(next);
      })
      .catch((err) => {
        if (!cancelled) {
          setItems([]);
          setError(err instanceof Error ? err.message : "加载失败");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  return (
    <ResourcePicker
      value={value}
      items={items}
      loading={loading}
      error={error}
      pickerClassName="cw-viking-memory-picker"
      selectLabel="选择 VikingDB 记忆库"
      searchLabel="搜索 VikingDB 记忆库"
      listLabel="VikingDB 记忆库"
      placeholder="请选择 VikingDB 记忆库，不选择则自动创建"
      emptyMessage="此账号下暂无 VikingDB 记忆库，未选择时会自动创建。"
      loadedMessage={(count) => `已加载 ${count} 个记忆库；不选择时会自动创建。`}
      refreshLabel="刷新记忆库列表"
      noMatchesMessage="未找到匹配的记忆库"
      getLabel={vikingMemoryDisplayName}
      getSearchFields={(item) => [
        vikingMemoryDisplayName(item),
        item.id,
        item.description,
        item.projectName,
        item.region,
        item.resourceId,
        ...(item.memoryTypes ?? []),
      ]}
      getKey={(item) => `${item.projectName}:${item.region}:${item.id}`}
      getOptionIds={(item) => [item.id, item.resourceId]}
      makeUnknownItem={(id) => ({
        id,
        name: id,
        description: "",
        projectName: "",
        region: "",
        resourceId: "",
        memoryTypes: [],
      })}
      onChange={onChange}
      onRefresh={() => setReloadKey((key) => key + 1)}
    />
  );
}

/* ---------------------------------------------------------------- *
 * MCP tool editor: edits draft.mcpTools. Each row picks a transport
 * (http / stdio) and shows the matching fields. http -> url + optional
 * bearer token; stdio -> command + space-separated args. Optional name.
 * ---------------------------------------------------------------- */
function McpToolEditor({
  tools,
  onChange,
}: {
  tools: McpTool[];
  onChange: (next: McpTool[]) => void;
}) {
  const update = (i: number, p: Partial<McpTool>) =>
    onChange(tools.map((t, idx) => (idx === i ? { ...t, ...p } : t)));

  const remove = (i: number) => onChange(tools.filter((_, idx) => idx !== i));

  const add = () =>
    onChange([...tools, { name: "", transport: "http", url: "" }]);

  return (
    <div className="cw-mcp">
      {tools.length > 0 && (
        <div className="cw-mcp-list">
          <AnimatePresence initial={false}>
            {tools.map((t, i) => (
              <motion.div
                key={i}
                className="cw-mcp-row"
                layout
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.16 }}
              >
                <div className="cw-mcp-rowhead">
                  <RadioGroup<McpTool["transport"]>
                    className="cw-mcp-transport"
                    aria-label={`MCP 工具 ${i + 1} 传输方式`}
                    value={t.transport}
                    onChange={(transport) => update(i, { transport })}
                  >
                    <RadioGroup.Item
                      value="http"
                      className={`cw-seg cw-seg-sm ${
                        t.transport === "http" ? "is-on" : ""
                      }`}
                    >
                      <span className="cw-seg-title">HTTP</span>
                    </RadioGroup.Item>
                    <RadioGroup.Item
                      value="stdio"
                      className={`cw-seg cw-seg-sm ${
                        t.transport === "stdio" ? "is-on" : ""
                      }`}
                    >
                      <span className="cw-seg-title">stdio</span>
                    </RadioGroup.Item>
                  </RadioGroup>
                  <button
                    type="button"
                    className="cw-icon-btn cw-icon-danger"
                    onClick={() => remove(i)}
                    aria-label="移除 MCP 工具"
                  >
                    <Trash2 className="cw-i cw-i-sm" />
                  </button>
                </div>

                <Input
                  size="md"
                  value={t.name}
                  placeholder="名称（用于命名，可留空）"
                  aria-label={`MCP 工具 ${i + 1} 名称`}
                  onChange={(e) => update(i, { name: e.target.value })}
                />

                {t.transport === "http" ? (
                  <>
                    <Input
                      size="md"
                      value={t.url ?? ""}
                      placeholder="MCP 服务地址（StreamableHTTP）"
                      aria-label={`MCP 工具 ${i + 1} 服务地址`}
                      onChange={(e) => update(i, { url: e.target.value })}
                    />
                    {mcpUrlNeedsPathWarning(t.url ?? "") && (
                      <p className="cw-mcp-warning">
                        <Info aria-hidden="true" />
                        <span>
                          当前地址不是以 /mcp 结尾，请确认它是实际的 MCP
                          Endpoint。Studio 会保留该地址，不会自动补充路径。
                        </span>
                      </p>
                    )}
                    <Input
                      size="md"
                      value={mcpAuthTokenInputValue(t)}
                      placeholder="Bearer Token（可选）"
                      aria-label={`MCP 工具 ${i + 1} Bearer Token`}
                      onChange={(e) =>
                        onChange(
                          tools.map((tool, index) =>
                            index === i
                              ? updateMcpAuthTokenInput(tool, e.target.value)
                              : tool,
                          ),
                        )
                      }
                    />
                  </>
                ) : (
                  <>
                    <Input
                      size="md"
                      value={t.command ?? ""}
                      placeholder="启动命令，例如 npx"
                      aria-label={`MCP 工具 ${i + 1} 启动命令`}
                      onChange={(e) => update(i, { command: e.target.value })}
                    />
                    <Input
                      size="md"
                      value={(t.args ?? []).join(" ")}
                      placeholder="参数（用空格分隔），例如 -y @playwright/mcp@latest"
                      aria-label={`MCP 工具 ${i + 1} 启动参数`}
                      onChange={(e) =>
                        update(i, {
                          args: e.target.value.split(/\s+/).filter(Boolean),
                        })
                      }
                    />
                    <p className="cw-mcp-note">
                      stdio MCP
                      暂不参与调试运行；点击“去部署”时会完整保留这项配置并生成对应代码。
                    </p>
                  </>
                )}
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      <button type="button" className="cw-add-sub" onClick={add}>
        <Plus className="cw-i" />
        添加 MCP 工具
      </button>
    </div>
  );
}

/* ---------------------------------------------------------------- *
 * Multi-source skill picker: tab bar switching between Skill Hub
 * (public marketplace), local folder/.zip upload, and account-scoped
 * AgentKit SkillSpaces. Selected skills from all sources share one
 * list rendered below the tabs.
 * ---------------------------------------------------------------- */
function AgentKitSkillsIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M5.5 7.5h10.75a2 2 0 0 1 2 2v7.75a2 2 0 0 1-2 2H5.5a2 2 0 0 1-2-2V9.5a2 2 0 0 1 2-2Z" />
      <path d="M7 4.75h9.5a2 2 0 0 1 2 2" opacity=".58" />
      <path d="m11 10.25.72 1.48 1.63.24-1.18 1.15.28 1.62-1.45-.77-1.45.77.28-1.62-1.18-1.15 1.63-.24.72-1.48Z" />
      <path d="M19.25 11.25h1.5M20 10.5V12" opacity=".72" />
    </svg>
  );
}

function SelectedSkillRow({
  s,
  onRemove,
}: {
  s: SelectedSkill;
  onRemove: () => void;
}) {
  let Icon: ComponentType<{ className?: string }> = Sparkles;
  let label = "火山 Find Skill 技能广场";
  if (s.source === "local") {
    Icon = FolderUp;
    label = "本地";
  } else if (s.source === "skillspace") {
    Icon = AgentKitSkillsIcon;
    label = "AgentKit Skills 中心";
  }
  return (
    <motion.div
      key={`${s.source}:${s.folder}:${s.skillId || s.slug || ""}:${s.version || ""}`}
      className="cw-selected-skill-row"
      layout
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.16 }}
    >
      <span className="cw-selected-skill-icon" aria-hidden>
        <Icon className="cw-i cw-i-sm" />
      </span>
      <span className="cw-selected-skill-meta">
        <span className="cw-selected-skill-name">{s.name}</span>
        <span className="cw-selected-skill-detail">
          {label}
          {s.description ? ` · ${displayDescription(s.description)}` : ""}
        </span>
      </span>
      <button
        type="button"
        className="cw-selected-skill-remove"
        onClick={onRemove}
        aria-label={`移除 ${s.name}`}
        title={`移除 ${s.name}`}
      >
        <X className="cw-i cw-i-sm" />
      </button>
    </motion.div>
  );
}

const SKILL_SOURCES: {
  id: SkillSource;
  label: string;
  icon: ComponentType<{ className?: string }>;
}[] = [
  { id: "local", label: "本地文件", icon: FolderUp },
  { id: "skillspace", label: "AgentKit Skills 中心", icon: AgentKitSkillsIcon },
  { id: "skillhub", label: "火山 Find Skill 技能广场", icon: Globe },
];

function SkillsSourceTabs({
  selected,
  onChange,
  cloudProvider,
}: {
  selected: SelectedSkill[];
  onChange: (next: SelectedSkill[]) => void;
  cloudProvider: CloudProvider;
}) {
  const [active, setActive] = useState<SkillSource>("local");
  const [open, setOpen] = useState(false);
  const activeIndex = SKILL_SOURCES.findIndex((source) => source.id === active);
  const remove = (key: string) =>
    onChange(selected.filter((s) => skillKey(s) !== key));

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  return (
    <div className="cw-skillspane">
      <button
        type="button"
        className="cw-skill-add"
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
      >
        <span className="cw-skill-add-icon" aria-hidden>
          <Plus className="cw-i" />
        </span>
        <span>添加 Skill</span>
      </button>

      {selected.length > 0 && (
        <div className="cw-skill-selected">
          <span className="cw-skill-selected-label">
            已加入技能 · {selected.length}
          </span>
          <div className="cw-selected-skill-list">
            <AnimatePresence initial={false}>
              {selected.map((s) => (
                <SelectedSkillRow
                  key={skillKey(s)}
                  s={s}
                  onRemove={() => remove(skillKey(s))}
                />
              ))}
            </AnimatePresence>
          </div>
        </div>
      )}

      <AnimatePresence>
        {open && (
          <motion.div
            className="cw-skill-dialog-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.16 }}
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) setOpen(false);
            }}
          >
            <motion.div
              className="cw-skill-dialog"
              role="dialog"
              aria-modal="true"
              aria-labelledby="cw-skill-dialog-title"
              initial={{ opacity: 0, y: 10, scale: 0.985 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 6, scale: 0.99 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
            >
              <div className="cw-skill-dialog-head">
                <h3 id="cw-skill-dialog-title">添加 Skill</h3>
                <button
                  type="button"
                  className="cw-skill-dialog-close"
                  aria-label="关闭添加 Skill"
                  onClick={() => setOpen(false)}
                >
                  <X className="cw-i" />
                </button>
              </div>
              <div className="cw-skill-dialog-body">
                <div
                  className="cw-skill-sourcetabs"
                  role="tablist"
                  style={
                    {
                      "--cw-skill-tab-slider-width": `calc((100% - 16px) / ${SKILL_SOURCES.length})`,
                      "--cw-active-skill-tab-offset": `calc(${activeIndex * 100}% + ${
                        activeIndex * 4
                      }px)`,
                    } as CSSProperties
                  }
                >
                  <span className="cw-skill-tab-slider" aria-hidden />
                  {SKILL_SOURCES.map(({ id, label, icon: Icon }) => (
                    <button
                      key={id}
                      type="button"
                      role="tab"
                      id={`cw-skill-tab-${id}`}
                      aria-controls="cw-skill-tabpanel"
                      aria-selected={active === id}
                      className={`cw-skill-pickertab ${active === id ? "is-on" : ""}`}
                      onClick={() => setActive(id)}
                    >
                      <Icon className="cw-i cw-i-sm" />
                      {label}
                    </button>
                  ))}
                </div>

                <div
                  id="cw-skill-tabpanel"
                  className="cw-skill-tabbody"
                  role="tabpanel"
                  aria-labelledby={`cw-skill-tab-${active}`}
                >
                  {active === "skillhub" && (
                    <SkillHubPicker selected={selected} onChange={onChange} />
                  )}
                  {active === "local" && (
                    <LocalPicker selected={selected} onChange={onChange} />
                  )}
                  {active === "skillspace" && (
                    <SkillSpacePicker
                      selected={selected}
                      onChange={onChange}
                      cloudProvider={cloudProvider}
                    />
                  )}
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function skillKey(s: SelectedSkill): string {
  if (s.source === "skillhub") return `hub:${s.namespace}/${s.slug}`;
  if (s.source === "local") return `local:${s.folder}`;
  return `ss:${s.skillSpaceId}/${s.skillId}/${s.version || ""}`;
}

/* ---------------------------------------------------------------- *
 * Toggle switch row.
 * ---------------------------------------------------------------- */
function Toggle({
  checked,
  onChange,
  title,
  desc,
  showDescription = false,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  title: string;
  desc: string;
  showDescription?: boolean;
  icon: typeof Bot;
}) {
  return (
    <button
      type="button"
      className={`cw-toggle ${checked ? "is-on" : ""}`}
      onClick={() => onChange(!checked)}
      aria-pressed={checked}
    >
      <span className="cw-toggle-text">
        <span className="cw-toggle-title">{title}</span>
        {showDescription && <span className="cw-toggle-help">{desc}</span>}
      </span>
      <span className="cw-switch" aria-hidden>
        <motion.span
          className="cw-switch-knob"
          layout
          transition={{ type: "spring", stiffness: 520, damping: 34 }}
        />
      </span>
    </button>
  );
}

/* ================================================================ *
 * Tree addressing — the draft is a recursive AgentDraft. A node is
 * addressed by an array of child indices; [] is the root.
 * ================================================================ */
type NodePath = number[];

const samePath = (a: NodePath, b: NodePath) =>
  a.length === b.length && a.every((v, i) => v === b[i]);

function pathExists(root: AgentDraft, path: NodePath): boolean {
  let node: AgentDraft | undefined = root;
  for (const i of path) {
    node = node.subAgents?.[i];
    if (!node) return false;
  }
  return true;
}

function getNode(root: AgentDraft, path: NodePath): AgentDraft {
  let node = root;
  for (const i of path) node = node.subAgents[i];
  return node;
}

/** Immutably replace the node at `path` by applying `fn` (copies each level). */
function updateNode(
  root: AgentDraft,
  path: NodePath,
  fn: (n: AgentDraft) => AgentDraft,
): AgentDraft {
  if (path.length === 0) return fn(root);
  const [i, ...rest] = path;
  const subAgents = root.subAgents.slice();
  subAgents[i] = updateNode(subAgents[i], rest, fn);
  return { ...root, subAgents };
}

function addChild(
  root: AgentDraft,
  path: NodePath,
  cloudProvider: CloudProvider = "volcengine",
): AgentDraft {
  return updateNode(root, path, (n) => ({
    ...n,
    subAgents: [...n.subAgents, emptyDraft(cloudProvider)],
  }));
}

function insertChild(
  root: AgentDraft,
  parentPath: NodePath,
  index: number,
  cloudProvider: CloudProvider = "volcengine",
): AgentDraft {
  return updateNode(root, parentPath, (n) => {
    const subAgents = n.subAgents.slice();
    subAgents.splice(index, 0, emptyDraft(cloudProvider));
    return { ...n, subAgents };
  });
}

function removeNode(root: AgentDraft, path: NodePath): AgentDraft {
  if (path.length === 0) return root; // the root is never removable
  const parentPath = path.slice(0, -1);
  const idx = path[path.length - 1];
  return updateNode(root, parentPath, (n) => ({
    ...n,
    subAgents: n.subAgents.filter((_, i) => i !== idx),
  }));
}

/** Move a child within its parent's list from index `from` to `to`. The moved
 *  node carries its whole subtree with it. */
function reorderSiblings(
  root: AgentDraft,
  parentPath: NodePath,
  from: number,
  to: number,
): AgentDraft {
  return updateNode(root, parentPath, (n) => {
    const subAgents = n.subAgents.slice();
    const [moved] = subAgents.splice(from, 1);
    subAgents.splice(to, 0, moved);
    return { ...n, subAgents };
  });
}

/** Reordering only matters where child order drives execution: Sequential and
 *  Loop orchestrators. Parallel / LLM sub-agents are order-independent. */
const orderedChildrenType = (t: AgentDraft["agentType"]) =>
  t === "sequential" || t === "loop";

/** A node holds children only when it's an LLM or an orchestrator (not A2A). */
const nodeAcceptsChildren = (n: AgentDraft) => !isA2aType(n.agentType);

/** Max nesting depth below the root (root = depth 0). Keeps the tree readable
 *  within the fixed-width panel instead of needing horizontal scroll. */
const MAX_TREE_DEPTH = 3;

/** Per-node required-field problem, or null when the node is valid. */
function nodeProblem(
  n: AgentDraft,
  duplicateNames: ReadonlySet<string>,
  isRoot = false,
): string | null {
  if (isA2aType(n.agentType)) {
    if (isRoot) return "远程 Agent 只能作为子 Agent";
    return n.a2aRegistry?.registrySpaceId.trim()
      ? null
      : "缺少 AgentKit 智能体中心";
  }
  const nameProblem = agentNameProblem(n.name);
  if (nameProblem) return nameProblem;
  if (duplicateNames.has(n.name)) return "Agent 名称在当前结构中必须唯一";
  if (n.description.trim().length === 0) return "缺少描述";
  if (isOrchestratorType(n.agentType))
    return n.subAgents.length === 0 ? "缺少子 Agent" : null;
  return n.instruction.trim().length === 0 ? "缺少系统提示词" : null;
}

interface TreeProblem {
  path: NodePath;
  name: string;
  typeLabel: string;
  problem: string;
}

/** Collect required-field problems across the whole tree, in render order. */
function treeProblems(
  root: AgentDraft,
  duplicateNames: ReadonlySet<string>,
  path: NodePath = [],
): TreeProblem[] {
  const out: TreeProblem[] = [];
  const remote = isA2aType(root.agentType);
  const p = nodeProblem(root, duplicateNames, path.length === 0);
  if (p) {
    out.push({
      path,
      name: remote ? "远程 Agent" : root.name.trim() || "未命名",
      typeLabel: agentTypeMeta(root.agentType).label,
      problem: p,
    });
  }
  if (nodeAcceptsChildren(root)) {
    root.subAgents.forEach((c, i) =>
      out.push(...treeProblems(c, duplicateNames, [...path, i])),
    );
  }
  return out;
}

function validationProblemMessage(problem: TreeProblem): string {
  if (problem.problem === "缺少子 Agent") {
    return `${problem.typeLabel}至少需要添加一个子 Agent 后才能调试或发布。`;
  }
  return `${problem.name}：${problem.problem}`;
}

/** Count the root Agent and every nested sub-Agent in the draft. */
function countDraftAgents(root: AgentDraft): number {
  return (
    1 +
    root.subAgents.reduce((total, child) => total + countDraftAgents(child), 0)
  );
}

/** Collect only settings used by active components across the Agent tree. */
function collectDeploymentEnv(root: AgentDraft): RuntimeEnvConfiguration {
  const prepared = prepareMcpAuth(root);
  const selections: RuntimeEnvSelection[] = [];
  const fixedValues: Record<string, string> = { ...prepared.envValues };
  const cloudProvider = prepared.draft.cloudProvider ?? "volcengine";
  const modelProxyHarnessOptimizationLabels =
    selectedHarnessModelProxyOptimizations(prepared.draft).map(
      harnessSidecarOptionLabel,
    );
  let usesArkModel = false;
  let arkModelName = "";
  for (const binding of customModelEnvironmentBindings(
    prepared.draft,
    defaultModelApiBase(cloudProvider),
  )) {
    const env: EnvVar[] = [
      {
        key: binding.apiKeyKey,
        required: true,
        comment: binding.label,
      },
    ];
    if (binding.providerKey) {
      env.push({ key: binding.providerKey, required: true });
      fixedValues[binding.providerKey] = binding.provider;
    }
    if (binding.apiBaseKey) {
      env.push({ key: binding.apiBaseKey, required: true });
      fixedValues[binding.apiBaseKey] = binding.apiBase;
    }
    selections.push({ env });
  }
  const visit = (node: AgentDraft) => {
    if (
      node.agentType === "llm" &&
      resolvedModelSource(node, cloudProvider) === "ark"
    ) {
      usesArkModel = true;
      if (!arkModelName) {
        arkModelName = (node.modelName ?? "").trim();
      }
    }
    for (const toolId of node.builtinTools ?? []) {
      const tool = BUILTIN_TOOLS.find((item) => item.id === toolId);
      if (tool)
        selections.push({ env: providerRuntimeEnv(tool.env, cloudProvider) });
    }
    for (const mcpTool of node.mcpTools ?? []) {
      if (mcpTool.authTokenEnv) {
        selections.push({
          env: [
            {
              key: mcpTool.authTokenEnv,
              required: false,
              comment: `${mcpTool.name.trim() || "MCP"} Bearer Token`,
            },
          ],
        });
      }
    }
    if (node.a2aRegistry?.enabled) {
      selections.push({ env: A2A_REGISTRY_ENV });
      Object.assign(
        fixedValues,
        a2aRegistryEnvValues(node.a2aRegistry, { includeDefaults: true }),
      );
    }
    if (node.memory.shortTerm) {
      selections.push({
        env: providerRuntimeEnv(
          STM_BACKENDS.find(
            (item) => item.id === (node.shortTermBackend ?? "local"),
          )?.env ?? [],
          cloudProvider,
        ),
      });
    }
    if (node.memory.longTerm) {
      selections.push({
        env: providerRuntimeEnv(
          LTM_BACKENDS.find(
            (item) => item.id === (node.longTermBackend ?? "local"),
          )?.env ?? [],
          cloudProvider,
        ),
      });
    }
    if (node.knowledgebase) {
      selections.push({
        env: providerRuntimeEnv(
          KB_BACKENDS.find(
            (item) =>
              item.id === (node.knowledgebaseBackend ?? DEFAULT_KB_BACKEND),
          )?.env ?? [],
          cloudProvider,
        ),
      });
    }
    if (node.tracing) {
      for (const exporterId of node.tracingExporters ?? []) {
        const exporter = TRACING_EXPORTERS.find(
          (item) => item.id === exporterId,
        );
        if (exporter) {
          selections.push({
            env: exporter.env,
            enableFlag: exporter.enableFlag,
          });
        }
      }
    }
    node.subAgents.forEach(visit);
  };
  visit(prepared.draft);
  if (usesArkModel) {
    selections.push({
      env: [
        { key: "MODEL_AGENT_PROVIDER", required: true },
        { key: "MODEL_AGENT_API_BASE", required: true },
        {
          key: "MODEL_AGENT_API_KEY",
          required: true,
          comment: "Ark API Key",
          placeholder: "由所选 API Key 注入",
          secret: true,
          readOnly: true,
          serverManaged: true,
          requiredBy: modelProxyHarnessOptimizationLabels,
        },
      ],
    });
    fixedValues.MODEL_AGENT_PROVIDER = "openai";
    fixedValues.MODEL_AGENT_API_BASE = defaultModelApiBase(cloudProvider);
    const selectedModelName = arkModelName || defaultModelName(cloudProvider);
    fixedValues.MODEL_AGENT_NAME = selectedModelName;
    fixedValues.MODEL_NAME = selectedModelName;
  }
  if (
    selectedHarnessOptimizations(prepared.draft).includes("mcp_resilience")
  ) {
    selections.push({
      env: [
        {
          key: "MCP_URLS",
          required: true,
          comment: "MCP 统一网关地址",
          placeholder: "https://example.com/mcp",
          requiredBy: [harnessSidecarOptionLabel("mcp_resilience")],
        },
        {
          key: "MCP_API_KEY",
          required: true,
          comment: "MCP 统一网关 API Key",
          secret: true,
          requiredBy: [harnessSidecarOptionLabel("mcp_resilience")],
        },
      ],
    });
  }
  const config = runtimeEnvConfiguration(selections);
  return {
    specs: config.specs,
    fixedValues: { ...config.fixedValues, ...fixedValues },
  };
}

/* ---------------------------------------------------------------- *
 * Left structure tree: one selectable, editable node (recursive).
 * ---------------------------------------------------------------- */
export function TreeNode({
  root,
  path,
  selectedPath,
  duplicateNames,
  showErrors,
  validationPulse,
  onSelect,
  onChange,
  onClearRoot,
}: {
  root: AgentDraft;
  path: NodePath;
  selectedPath: NodePath;
  duplicateNames: ReadonlySet<string>;
  showErrors: boolean;
  validationPulse: number;
  onSelect: (p: NodePath) => void;
  /** Replace the whole tree; optionally move the selection. */
  onChange: (nextRoot: AgentDraft, select?: NodePath) => void;
  onClearRoot: () => void;
}) {
  const node = getNode(root, path);
  const meta = agentTypeMeta(node.agentType);
  const Icon = meta.icon;
  const isRoot = path.length === 0;
  const selected = samePath(path, selectedPath);
  const acceptsChildren = nodeAcceptsChildren(node);
  const canAddChild = acceptsChildren && path.length < MAX_TREE_DEPTH;

  const add = () => {
    const next = addChild(root, path);
    const childIndex = getNode(next, path).subAgents.length - 1;
    onChange(next, [...path, childIndex]);
  };
  const del = () => onChange(removeNode(root, path), path.slice(0, -1));

  // Drag-to-reorder is enabled only when this node's PARENT is a Sequential or
  // Loop orchestrator (order = execution order). Dragging carries the subtree.
  const parentPath = path.slice(0, -1);
  const draggable =
    !isRoot && orderedChildrenType(getNode(root, parentPath).agentType);
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    const raw = e.dataTransfer.getData("application/x-agent-path");
    if (!raw) return;
    let src: NodePath;
    try {
      src = JSON.parse(raw) as NodePath;
    } catch {
      return;
    }
    // Reorder among siblings only (same parent).
    if (!samePath(src.slice(0, -1), parentPath)) return;
    const from = src[src.length - 1];
    const to = path[path.length - 1];
    if (from === to) return;
    onChange(reorderSiblings(root, parentPath, from, to), [...parentPath, to]);
  };

  return (
    <div className="cw-tree-branch">
      <div
        className={`cw-tree-node cw-tree-type-${node.agentType ?? "llm"} ${
          selected ? "is-selected" : ""
        } ${draggable ? "is-draggable" : ""} ${dragOver ? "is-dragover" : ""} ${
          showErrors && nodeProblem(node, duplicateNames, isRoot)
            ? `is-invalid cw-error-shake-${validationPulse % 2}`
            : ""
        }`}
        role="button"
        tabIndex={0}
        draggable={draggable}
        onDragStart={
          draggable
            ? (e) => {
                e.dataTransfer.setData(
                  "application/x-agent-path",
                  JSON.stringify(path),
                );
                e.dataTransfer.effectAllowed = "move";
                e.stopPropagation();
              }
            : undefined
        }
        onDragOver={
          draggable
            ? (e) => {
                e.preventDefault();
                setDragOver(true);
              }
            : undefined
        }
        onDragLeave={draggable ? () => setDragOver(false) : undefined}
        onDrop={draggable ? handleDrop : undefined}
        onClick={() => onSelect(path)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelect(path);
          }
        }}
      >
        <Icon className="cw-tree-icon" />
        <span className="cw-tree-main">
          <span className="cw-tree-name">
            {isA2aType(node.agentType)
              ? "远程 Agent"
              : node.name.trim() || "未命名"}
          </span>
          <span className="cw-tree-type">{meta.label}</span>
        </span>
        <span className="cw-tree-actions">
          {isRoot && (
            <button
              type="button"
              className="cw-icon-btn cw-tree-clear"
              title="清空根 Agent"
              aria-label="清空根 Agent"
              onClick={(e) => {
                e.stopPropagation();
                onClearRoot();
              }}
            >
              <ClearAgentIcon className="cw-i cw-i-sm" />
            </button>
          )}
          {canAddChild && (
            <button
              type="button"
              className="cw-icon-btn"
              title="添加子 Agent"
              onClick={(e) => {
                e.stopPropagation();
                add();
              }}
            >
              <Plus className="cw-i cw-i-sm" />
            </button>
          )}
          {!isRoot && (
            <button
              type="button"
              className="cw-icon-btn cw-icon-danger"
              title="删除"
              onClick={(e) => {
                e.stopPropagation();
                del();
              }}
            >
              <Trash2 className="cw-i cw-i-sm" />
            </button>
          )}
        </span>
      </div>
      {acceptsChildren && node.subAgents.length > 0 && (
        <div className="cw-tree-children">
          {node.subAgents.map((_, i) => (
            <TreeNode
              key={i}
              root={root}
              path={[...path, i]}
              selectedPath={selectedPath}
              duplicateNames={duplicateNames}
              showErrors={showErrors}
              validationPulse={validationPulse}
              onSelect={onSelect}
              onChange={onChange}
              onClearRoot={onClearRoot}
            />
          ))}
        </div>
      )}
    </div>
  );
}

type DebugPhase = "idle" | "starting" | "ready" | "sending" | "error";

type WorkspaceMode = "build" | "validate" | "publish";
interface DebugMessage {
  role: "user" | "assistant";
  content: string;
  blocks?: Block[];
  error?: string;
}

interface DebugVariant {
  id: string;
  name: string;
  modelName: string;
  description: string;
  instruction: string;
  configOpen: boolean;
  phase: DebugPhase;
  runtimeSnapshot: string;
  messages: DebugMessage[];
  error: string | null;
}

interface DebugTraceTarget {
  runId: string;
  sessionId: string;
  variantName: string;
}

function sameBaseUrl(a: string | undefined, b: string): boolean {
  const normalize = (value: string | undefined) =>
    (value ?? "").trim().replace(/\/+$/, "");
  return normalize(a) === normalize(b);
}

function shouldUseProviderDefaultModel(
  modelName: string | undefined,
  previousProvider: CloudProvider,
  nextProvider: CloudProvider,
): boolean {
  const trimmed = (modelName ?? "").trim();
  if (!trimmed) return true;
  if (trimmed === defaultModelName(previousProvider)) return true;
  if (trimmed === defaultModelName(nextProvider)) return false;
  return nextProvider === "byteplus" && trimmed.includes("doubao-");
}

function draftForCloudProvider(
  draft: AgentDraft,
  cloudProvider: CloudProvider,
): AgentDraft {
  const previousProvider = draft.cloudProvider ?? "volcengine";
  const modelSource = resolvedModelSource(draft, previousProvider);
  const nextSubAgents = draft.subAgents.map((child) =>
    draftForCloudProvider(child, cloudProvider),
  );
  const nextModelName =
    modelSource === "ark" &&
    shouldUseProviderDefaultModel(
      draft.modelName,
      previousProvider,
      cloudProvider,
    )
      ? defaultModelName(cloudProvider)
      : draft.modelName;
  const shouldUseProviderDefaultBase =
    sameBaseUrl(draft.modelApiBase, defaultModelApiBase(previousProvider)) ||
    (cloudProvider === "byteplus" &&
      (draft.modelApiBase ?? "").includes("volces.com"));
  const nextModelApiBase = shouldUseProviderDefaultBase
    ? defaultModelApiBase(cloudProvider)
    : draft.modelApiBase;
  const changed =
    draft.cloudProvider !== cloudProvider ||
    nextModelName !== draft.modelName ||
    nextModelApiBase !== draft.modelApiBase ||
    nextSubAgents.some((child, index) => child !== draft.subAgents[index]);
  if (!changed) return draft;
  return {
    ...draft,
    cloudProvider,
    modelName: nextModelName,
    modelApiBase: nextModelApiBase,
    subAgents: nextSubAgents,
  };
}

interface CustomCreateInitialState {
  draft: AgentDraft;
  customModelSecretValues: Record<string, string>;
}

function customCreateInitialState(
  initialDraft: AgentDraft,
  cloudProvider: CloudProvider,
): CustomCreateInitialState {
  const draft = draftForCloudProvider(initialDraft, cloudProvider);
  const requirements = customModelCredentialRequirements(
    draft,
    defaultModelApiBase(cloudProvider),
  );
  const secretKeys = new Set(requirements.map(({ key }) => key));
  const initialEnvValues = draft.deployment?.envValues ?? {};
  const customModelSecretValues = Object.fromEntries(
    Object.entries(initialEnvValues).filter(
      ([key, value]) => secretKeys.has(key) && Boolean(value.trim()),
    ),
  );
  if (Object.keys(customModelSecretValues).length === 0) {
    return { draft, customModelSecretValues };
  }
  return {
    draft: {
      ...draft,
      deployment: {
        ...(draft.deployment ?? { feishuEnabled: false }),
        envValues: Object.fromEntries(
          Object.entries(initialEnvValues).filter(([key]) => !secretKeys.has(key)),
        ),
      },
    },
    customModelSecretValues,
  };
}

function codegenDraft(draft: AgentDraft): AgentDraft {
  const prepared = prepareMcpAuth(draft).draft;
  const activeModelDraft = activeModelConfiguration(
    prepared,
    prepared.cloudProvider ?? "volcengine",
  );
  return {
    ...activeModelDraft,
    deployment: {
      feishuEnabled: !!draft.deployment?.feishuEnabled,
      modelApiKeyId: draft.deployment?.modelApiKeyId ?? "",
      modelApiKeyName: draft.deployment?.modelApiKeyName ?? "",
    },
  };
}

function defaultDebugModelName(draft: AgentDraft): string {
  const modelName = draft.modelName?.trim();
  if (modelName) return modelName;
  for (const child of draft.subAgents) {
    const childModelName = defaultDebugModelName(child);
    if (childModelName) return childModelName;
  }
  return "";
}

function debugRuntimeDraft(
  draft: AgentDraft,
  transientEnvValues: Record<string, string> = {},
): AgentDraft {
  const runtimeEnv = collectDeploymentEnv(draft);
  const values = {
    ...(draft.deployment?.envValues ?? {}),
    ...transientEnvValues,
    ...runtimeEnv.fixedValues,
  };
  return {
    ...codegenDraft(draft),
    deployment: {
      feishuEnabled: !!draft.deployment?.feishuEnabled,
      modelApiKeyId: draft.deployment?.modelApiKeyId ?? "",
      modelApiKeyName: draft.deployment?.modelApiKeyName ?? "",
      envValues: Object.fromEntries(
        runtimeEnvVars(runtimeEnv.specs, values).map(({ key, value }) => [
          key,
          value,
        ]),
      ),
    },
  };
}

function debugSnapshotKey(
  draft: AgentDraft,
  transientEnvValues: Record<string, string> = {},
): string {
  return JSON.stringify(debugRuntimeDraft(draft, transientEnvValues));
}

function debugVariantSnapshot(
  draftSnapshot: string,
  variant: Pick<DebugVariant, "modelName" | "description" | "instruction">,
): string {
  return JSON.stringify({
    draftSnapshot,
    modelName: variant.modelName,
    description: variant.description,
    instruction: variant.instruction,
  });
}

function debugVariantConfigurationKey(
  variant: Pick<DebugVariant, "modelName" | "description" | "instruction">,
): string {
  return JSON.stringify({
    modelName: variant.modelName.trim(),
    description: variant.description.trim(),
    instruction: variant.instruction.trim(),
  });
}

type DebugWorkspaceView = "intro" | "config" | "results";

const DEBUG_VIEW_ENTER_SECONDS = 0.22;
const DEBUG_VIEW_EXIT_SECONDS = 0.13;
const DEBUG_COLUMN_ENTER_SECONDS = 0.18;
const DEBUG_COLUMN_EXIT_SECONDS = 0.1;
const DEBUG_COLUMN_STAGGER_SECONDS = 0.035;
const DEBUG_MOTION_EASE = [0.22, 1, 0.36, 1] as const;
const WORKSPACE_VIEW_ENTER_SECONDS = 0.22;
const WORKSPACE_VIEW_EXIT_SECONDS = 0.14;
const BUILDER_PANEL_SECONDS = 0.24;
const BUILDER_PANEL_EASE = [0.4, 0, 0.2, 1] as const;
const DEBUG_SUGGESTED_QUESTIONS = [
  "请用一句话介绍你能帮我完成哪些任务",
  "帮我处理一个典型任务，并说明关键步骤",
  "如果信息不足，请先向我提问再继续",
] as const;

function debugWorkspaceView(variants: DebugVariant[]): DebugWorkspaceView {
  if (variants.some((variant) => variant.configOpen)) return "config";
  if (
    variants.length > 1 ||
    variants.some(
      (variant) => variant.phase === "error" || variant.messages.length > 0,
    )
  )
    return "results";
  return "intro";
}

function debugVariantChangeLabel(
  variant: Pick<DebugVariant, "modelName" | "description" | "instruction">,
  baseline?: Pick<DebugVariant, "modelName" | "description" | "instruction">,
): string {
  if (!baseline) return "";
  const changes = [
    variant.instruction.trim() !== baseline.instruction.trim() && "提示词",
    variant.modelName.trim() !== baseline.modelName.trim() && "模型",
    variant.description.trim() !== baseline.description.trim() && "描述",
  ].filter((item): item is string => Boolean(item));
  return changes.length > 0
    ? `${changes.join("、")} ${changes.length} 处改动`
    : "0 处改动";
}

function DebugComparisonWorkspace({
  enabled,
  disabledReason,
  variants,
  draftSnapshot,
  siteLogoUrl,
  input,
  onInput,
  onSend,
  onStartVariant,
  onRemoveVariant,
  onCompleteConfig,
  onCancelConfig,
  onOpenSettings,
  onConfigChange,
  onOpenTrace,
}: {
  enabled: boolean;
  disabledReason: string;
  variants: DebugVariant[];
  draftSnapshot: string;
  siteLogoUrl: string;
  input: string;
  onInput: (v: string) => void;
  onSend: () => void;
  onStartVariant: (id: string) => void;
  onRemoveVariant: (id: string) => void;
  onCompleteConfig: (id: string) => void;
  onCancelConfig: (id: string) => void;
  onOpenSettings: (id: string) => void;
  onConfigChange: (
    id: string,
    field: "modelName" | "description" | "instruction",
    value: string,
  ) => void;
  onOpenTrace: (id: string) => void;
}) {
  const view = debugWorkspaceView(variants);
  const reduceMotion = useReducedMotion();
  const previousViewRef = useRef<DebugWorkspaceView>(view);
  const viewOrder: Record<DebugWorkspaceView, number> = {
    intro: 0,
    config: 1,
    results: 2,
  };
  const viewDirection =
    viewOrder[view] >= viewOrder[previousViewRef.current] ? 1 : -1;
  useEffect(() => {
    previousViewRef.current = view;
  }, [view]);
  const viewMotion: Variants = {
    initial: (direction: number) => ({
      opacity: 0,
      x: reduceMotion ? 0 : direction * 18,
    }),
    visible: {
      opacity: 1,
      x: 0,
      transition: {
        duration: reduceMotion ? 0 : DEBUG_VIEW_ENTER_SECONDS,
        ease: DEBUG_MOTION_EASE,
      },
    },
    exit: (direction: number) => ({
      opacity: 0,
      x: reduceMotion ? 0 : direction * -10,
      transition: {
        duration: reduceMotion ? 0 : DEBUG_VIEW_EXIT_SECONDS,
        ease: DEBUG_MOTION_EASE,
      },
    }),
  };
  const stateGridRows =
    view === "intro"
      ? "minmax(0, 1fr) auto"
      : view === "config"
        ? "minmax(0, 1fr) 44px"
        : "minmax(0, 1fr) 136px";
  const columnMotion = (index: number) => ({
    layout: reduceMotion ? false : true,
    initial: reduceMotion ? { opacity: 0 } : { opacity: 0, x: 12 },
    animate: {
      opacity: 1,
      x: 0,
      scale: 1,
      transition: {
        duration: reduceMotion ? 0 : DEBUG_COLUMN_ENTER_SECONDS,
        delay: reduceMotion ? 0 : index * DEBUG_COLUMN_STAGGER_SECONDS,
        ease: DEBUG_MOTION_EASE,
      },
    },
    exit: {
      opacity: 0,
      x: reduceMotion ? 0 : 8,
      scale: reduceMotion ? 1 : 0.985,
      transition: {
        duration: reduceMotion ? 0 : DEBUG_COLUMN_EXIT_SECONDS,
        ease: DEBUG_MOTION_EASE,
      },
    },
  });
  const configVariant = variants.find((variant) => variant.configOpen);
  const runningVariants = variants.filter((variant) => {
    if (variant.phase !== "ready") return false;
    return (
      variant.runtimeSnapshot === debugVariantSnapshot(draftSnapshot, variant)
    );
  });
  const sending = variants.some((variant) => variant.phase === "sending");
  const canSend = runningVariants.length > 0 && !sending;
  const traceableVariants = variants.filter((variant) =>
    variant.messages.some(
      (message) => message.role === "assistant" && !message.error,
    ),
  );

  const renderComposer = (compact: boolean) => (
    <div className={`cw-ab-composer${compact ? " is-compact" : ""}`}>
      {compact && <span className="cw-ab-sample-label">线上样本</span>}
      <Textarea
        className="cw-debug-input"
        size="md"
        variant="soft"
        rows={compact ? 1 : 2}
        value={input}
        placeholder={canSend ? "输入你的问题" : "正在准备调试环境"}
        disabled={!canSend}
        onChange={(event) => onInput(event.target.value)}
        onKeyDown={(event) => {
          if (isImeCompositionEvent(event.nativeEvent)) return;
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            onSend();
          }
        }}
      />
      <button
        type="button"
        className="cw-debug-send"
        aria-label="发送测试消息"
        disabled={!canSend || !input.trim()}
        onClick={onSend}
      >
        {sending ? (
          <Loader2 className="cw-i cw-spin" />
        ) : (
          <ArrowUp className="cw-i" />
        )}
      </button>
    </div>
  );

  const baseline = variants[0];

  return (
    <section
      className={`cw-ab-workspace is-${view}`}
      aria-label="A/B 调试工作台"
    >
      <AnimatePresence initial={false} mode="popLayout" custom={viewDirection}>
        <motion.div
          key={enabled ? view : "disabled"}
          custom={viewDirection}
          variants={viewMotion}
          initial="initial"
          animate="visible"
          exit="exit"
          style={{
            gridRow: "1 / -1",
            gridColumn: "1",
            minWidth: 0,
            minHeight: 0,
            display: "grid",
            gridTemplateRows: enabled ? stateGridRows : "minmax(0, 1fr)",
            overflow: "hidden",
          }}
        >
          {!enabled ? (
            <div className="cw-debug-empty">{disabledReason}</div>
          ) : view === "intro" ? (
            <>
          <div className="cw-debug-intro">
            <div className="cw-debug-intro-content">
              <div className="cw-debug-intro-title">
                <span aria-hidden="true">
                  <img src={siteLogoUrl} alt="" />
                </span>
                <h2>调试你的 Agent</h2>
              </div>
              <div className="cw-debug-suggestions" aria-label="推荐问题">
                {DEBUG_SUGGESTED_QUESTIONS.map((question) => (
                  <button
                    key={question}
                    type="button"
                    onClick={() => onInput(question)}
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="cw-debug-intro-composer">{renderComposer(false)}</div>
            </>
          ) : view === "config" ? (
            <>
          <div
            className="cw-ab-config-grid"
            style={
              {
                "--cw-ab-column-count": variants.length,
              } as CSSProperties
            }
          >
            <AnimatePresence mode="popLayout">
              {variants.map((variant, variantIndex) => {
              const modelName = variant.modelName.trim();
              const description = variant.description.trim();
              const instruction = variant.instruction.trim();
              const configurationKey = debugVariantConfigurationKey(variant);
              const duplicateConfiguration = Boolean(
                modelName &&
                description &&
                instruction &&
                variants.findIndex(
                  (item) =>
                    debugVariantConfigurationKey(item) === configurationKey,
                ) !== variantIndex,
              );
              const configurationUnavailable =
                !modelName ||
                !description ||
                !instruction ||
                duplicateConfiguration;
              const disabledReason = !modelName
                ? "请先选择模型"
                : !description
                  ? "请填写描述"
                  : !instruction
                    ? "请填写系统提示词"
                    : duplicateConfiguration
                      ? "该配置与已有测试组相同"
                      : "";
              const changedDescription =
                variantIndex > 0 && variant.description !== baseline?.description;
              const changedModel =
                variantIndex > 0 && variant.modelName !== baseline?.modelName;
              const changedInstruction =
                variantIndex > 0 && variant.instruction !== baseline?.instruction;
              const changeLabel = debugVariantChangeLabel(variant, baseline);
                return (
                  <motion.section
                    key={variant.id}
                    className="cw-ab-config-column"
                    layoutDependency={variants.length}
                    {...columnMotion(variantIndex)}
                  >
                  <header className="cw-ab-column-label">
                    <span className="cw-ab-group-chip">
                      {variantIndex === 0 ? "基准组 A" : "对照组 B"}
                    </span>
                    <span className="cw-ab-change-summary">
                      {variantIndex > 0 ? changeLabel : null}
                    </span>
                    <button
                      type="button"
                      className="cw-ab-group-config-toggle"
                      aria-label={variant.configOpen ? "关闭当前组设置" : "配置当前组"}
                      title={variant.configOpen ? "关闭当前组设置" : "配置当前组"}
                      onClick={() => {
                        if (variant.configOpen) {
                          onCancelConfig(variant.id);
                          return;
                        }
                        onOpenSettings(variant.id);
                      }}
                    >
                      {variant.configOpen ? <CreateCloseIcon /> : <DebugSettingsIcon />}
                    </button>
                  </header>
                  <div className="cw-ab-agent-heading">
                    <span aria-hidden="true"><AgentFaceSquareIcon /></span>
                    <strong>{variant.name || "Meeting Assistant"}</strong>
                    {variant.id !== "baseline" && (
                      <button
                        type="button"
                        className="cw-ab-remove"
                        aria-label={`删除${variant.name}`}
                        onClick={() => onRemoveVariant(variant.id)}
                      >
                        <DebugVariantDeleteIcon />
                      </button>
                    )}
                  </div>
                  <div className="cw-ab-config">
                    <label>
                      <span>描述 <b>*</b>{changedDescription && <em>Change</em>}</span>
                      <Textarea
                        className="cw-ab-config-control"
                        size="md"
                        rows={3}
                        maxLength={50}
                        value={variant.description}
                        onChange={(event) =>
                          onConfigChange(variant.id, "description", event.target.value)
                        }
                      />
                      <small>{variant.description.length}/50</small>
                    </label>
                    <label>
                      <span>模型 <b>*</b>{changedModel && <em>Change</em>}</span>
                      <Input
                        className="cw-ab-config-control"
                        size="md"
                        value={variant.modelName}
                        placeholder="使用 Agent 当前模型"
                        onChange={(event) =>
                          onConfigChange(variant.id, "modelName", event.target.value)
                        }
                      />
                    </label>
                    <label>
                      <span>系统提示词 <b>*</b>{changedInstruction && <em>Change</em>}</span>
                      <Textarea
                        className="cw-ab-config-control"
                        size="md"
                        rows={7}
                        value={variant.instruction}
                        onChange={(event) =>
                          onConfigChange(variant.id, "instruction", event.target.value)
                        }
                      />
                    </label>
                  </div>
                  {configurationUnavailable && (
                    <span className="cw-ab-config-error">{disabledReason}</span>
                  )}
                  </motion.section>
                );
              })}
            </AnimatePresence>
          </div>
          <div className="cw-ab-config-actions">
            <button
              type="button"
              className="is-primary"
              disabled={!configVariant}
              onClick={() => configVariant && onCompleteConfig(configVariant.id)}
            >
              确定
            </button>
          </div>
            </>
          ) : (
            <>
          <div
            className="cw-ab-results-grid"
            style={
              {
                "--cw-ab-column-count": variants.length,
              } as CSSProperties
            }
          >
            <AnimatePresence mode="popLayout">
              {variants.map((variant, variantIndex) => {
              const assistantAvailable = variant.messages.some(
                (message) => message.role === "assistant",
              );
              const changeLabel = debugVariantChangeLabel(variant, baseline);
              const stale = Boolean(
                variant.phase === "ready" &&
                variant.runtimeSnapshot &&
                variant.runtimeSnapshot !==
                  debugVariantSnapshot(draftSnapshot, variant),
              );
                return (
                  <motion.section
                    key={variant.id}
                    className="cw-ab-result-column"
                    layoutDependency={variants.length}
                    {...columnMotion(variantIndex)}
                  >
                  <header className="cw-ab-column-label">
                    <span className="cw-ab-group-chip">
                      {variantIndex === 0 ? "基准组 A" : "对照组 B"}
                    </span>
                    <span className="cw-ab-change-summary">
                      {variantIndex > 0 ? changeLabel : null}
                    </span>
                    <button
                      type="button"
                      className="cw-ab-group-config-toggle"
                      aria-label={variant.configOpen ? "关闭当前组设置" : "配置当前组"}
                      title={variant.configOpen ? "关闭当前组设置" : "配置当前组"}
                      onClick={() => {
                        if (variant.configOpen) {
                          onCancelConfig(variant.id);
                          return;
                        }
                        onOpenSettings(variant.id);
                      }}
                    >
                      {variant.configOpen ? <CreateCloseIcon /> : <DebugSettingsIcon />}
                    </button>
                  </header>
                  <motion.div
                    className="cw-ab-conversation"
                    initial={{ opacity: 0, y: reduceMotion ? 0 : 4 }}
                    animate={{
                      opacity: 1,
                      y: 0,
                      transition: {
                        duration: reduceMotion
                          ? 0
                          : DEBUG_COLUMN_ENTER_SECONDS,
                        delay: reduceMotion
                          ? 0
                          : variantIndex * DEBUG_COLUMN_STAGGER_SECONDS,
                        ease: DEBUG_MOTION_EASE,
                      },
                    }}
                  >
                    {stale ? (
                      <div className="cw-ab-empty">
                        <button
                          type="button"
                          onClick={() => onStartVariant(variant.id)}
                        >
                          配置已变更，请重新启动此环境
                        </button>
                      </div>
                    ) : variant.error ? (
                      <DeploymentErrorMessage
                        message={variant.error}
                        className="cw-debug-error-detail"
                        defaultExpanded
                      />
                    ) : variant.phase === "starting" ? (
                      <div className="cw-ab-empty cw-ab-starting">
                        <Loader2 className="cw-i cw-spin" />
                        <span>正在创建独立测试环境</span>
                      </div>
                    ) : variant.messages.length === 0 ? (
                      <div className="cw-ab-empty">
                        {variant.phase === "ready" ? (
                          <span>等待测试问题</span>
                        ) : (
                          <button type="button" onClick={() => onStartVariant(variant.id)}>
                            启动环境
                          </button>
                        )}
                      </div>
                    ) : (
                      variant.messages.map((message, index) => (
                        <div
                          key={index}
                          className={`cw-debug-msg cw-debug-msg-${message.role}`}
                        >
                          <div className="cw-debug-content">
                            {message.role === "user" ? (
                              message.content
                            ) : message.error ? (
                              <DeploymentErrorMessage
                                message={message.error}
                                className="cw-debug-msg-error"
                                defaultExpanded
                              />
                            ) : message.blocks && message.blocks.length > 0 ? (
                              <Blocks blocks={message.blocks} onAction={() => {}} />
                            ) : message.content ? (
                              message.content
                            ) : index === variant.messages.length - 1 &&
                              variant.phase === "sending" ? (
                              <ThinkingPlaceholder />
                            ) : null}
                          </div>
                        </div>
                      ))
                    )}
                    {!assistantAvailable &&
                      variant.phase === "ready" &&
                      variant.messages.length > 0 && (
                        <span className="cw-ab-waiting">等待测试问题</span>
                      )}
                  </motion.div>
                  </motion.section>
                );
              })}
            </AnimatePresence>
          </div>
          <div className="cw-ab-results-footer">
            {traceableVariants.length > 0 && (
              <div className="cw-ab-verdict">
                <span>真实运行结果已生成，可查看调用链路</span>
                <AnimatePresence mode="popLayout">
                  {traceableVariants.map((variant, index) => (
                    <motion.button
                      key={variant.id}
                      type="button"
                      layout={reduceMotion ? false : "position"}
                      initial={{ opacity: 0, x: reduceMotion ? 0 : 6 }}
                      animate={{
                        opacity: 1,
                        x: 0,
                        transition: {
                          duration: reduceMotion
                            ? 0
                            : DEBUG_COLUMN_ENTER_SECONDS,
                          delay: reduceMotion
                            ? 0
                            : index * DEBUG_COLUMN_STAGGER_SECONDS,
                          ease: DEBUG_MOTION_EASE,
                        },
                      }}
                      exit={{
                        opacity: 0,
                        x: reduceMotion ? 0 : 4,
                        transition: {
                          duration: reduceMotion
                            ? 0
                            : DEBUG_COLUMN_EXIT_SECONDS,
                          ease: DEBUG_MOTION_EASE,
                        },
                      }}
                      onClick={() => onOpenTrace(variant.id)}
                    >
                      查看{index === 0 ? "A" : "B"}组调用链路
                    </motion.button>
                  ))}
                </AnimatePresence>
              </div>
            )}
            {renderComposer(true)}
          </div>
            </>
          )}
        </motion.div>
      </AnimatePresence>
    </section>
  );
}

function WorkspaceHeader({
  onBack,
  onDebug,
  onDeploy,
  debugMode,
  showDebugPreview,
  comparisonDisabled,
  onAddComparison,
  onExitDebug,
}: {
  onBack: () => void;
  onDebug: () => void;
  onDeploy: () => void;
  debugMode: boolean;
  showDebugPreview: boolean;
  comparisonDisabled: boolean;
  onAddComparison: () => void;
  onExitDebug: () => void;
}) {
  return (
    <CreateAgentHeader
      onBack={onBack}
      onDebug={onDebug}
      onDeploy={onDeploy}
      debugMode={debugMode}
      showDebugPreview={showDebugPreview}
      comparisonDisabled={comparisonDisabled}
      onAddComparison={onAddComparison}
      onExitDebug={onExitDebug}
    />
  );
}

function conversationDraftContext(agent: AgentDraft): Record<string, unknown> {
  return {
    name: agent.name,
    description: agent.description,
    instruction: agent.instruction,
    agentType: agent.agentType ?? "llm",
    modelSource: agent.modelSource,
    modelName: agent.modelName,
    maxIterations: agent.maxIterations,
    tools: agent.tools,
    skills: agent.skills,
    memory: agent.memory,
    knowledgebase: agent.knowledgebase,
    tracing: agent.tracing,
    builtinTools: agent.builtinTools ?? [],
    customTools: agent.customTools ?? [],
    mcpTools: (agent.mcpTools ?? []).map((tool) => ({
      name: tool.name,
      transport: tool.transport,
      url: tool.url,
      command: tool.command,
      args: tool.args,
      authTokenEnv: tool.authTokenEnv,
    })),
    subAgents: agent.subAgents.map(conversationDraftContext),
  };
}

function conversationUpdateRequirement(
  requirement: string,
  currentDraft: AgentDraft,
): string {
  return [
    "请根据用户的新要求更新当前 Agent 配置。保留用户没有要求修改的现有配置。",
    `用户的新要求：${requirement}`,
    "当前 Agent 配置：",
    JSON.stringify(conversationDraftContext(currentDraft), null, 2),
  ].join("\n");
}

/* ================================================================ *
 * Main component
 * ================================================================ */
interface CustomCreateProps extends CreateModeProps {
  /** Current Studio brand mark, shared with the site shell. */
  siteLogoUrl: string;
  /** Requirement entered on the create-agent entry screen. */
  initialGoal?: string;
  /** User-and-draft-scoped key for restoring the visible builder transcript. */
  agentBuilderStorageKey?: string;
  /** Pre-fill the wizard (used when importing an agent-structure YAML). */
  initialDraft?: AgentDraft;
  /** Global UI feature gates loaded from the backend. */
  features?: UiFeatures;
  /** Publish deploy progress into the persistent app header. */
  onDeploymentTaskChange?: (task: DeploymentTaskUpdate) => void;
  /** Specific creation path inside the scratch flow. */
  createMode?: "custom" | "yaml_import";
  /** Existing Runtime target when editing an Agent from the library. */
  deploymentTarget?: {
    runtimeId: string;
    name: string;
    region: string;
    appName?: string;
    currentVersion?: number | null;
  };
  /** Region selected before entering the create flow. */
  initialDeployRegion?: string;
  /** Cloud provider selected by the Studio shell. */
  cloudProvider?: CloudProvider;
  /** Called after an existing Runtime has been updated and released. */
  onDeploymentComplete?: (result: DeployResult) => void | Promise<void>;
  /** Called once the persistent deployment task has been created. */
  onDeploymentStarted?: (task: DeploymentTaskUpdate) => void;
  /** Persists the live builder state as a resumable library draft. */
  onDraftChange?: (draft: AgentDraft, dirty: boolean) => void;
  /** Restores the draft state from before this editing session and exits. */
  onDiscard?: () => void;
}

export function CustomCreate({
  onBack,
  onCreate,
  onAgentAdded,
  initialDraft,
  features,
  onDeploymentTaskChange,
  createMode = "custom",
  deploymentTarget,
  siteLogoUrl,
  cloudProvider = "volcengine",
  initialDeployRegion = defaultCloudRegion(cloudProvider),
  onDeploymentComplete,
  onDeploymentStarted,
  onDraftChange,
  onDiscard,
  initialGoal = "",
  agentBuilderStorageKey,
}: CustomCreateProps) {
  void onCreate; // outcome is the in-pane project preview, not a navigation
  void onDiscard; // the discard action is intentionally hidden in this flow
  const reduceMotion = useReducedMotion();
  const workspaceViewMotion = {
    initial: {
      opacity: 0,
      x: reduceMotion ? 0 : 12,
    },
    animate: {
      opacity: 1,
      x: 0,
      transition: {
        duration: reduceMotion ? 0 : WORKSPACE_VIEW_ENTER_SECONDS,
        ease: DEBUG_MOTION_EASE,
      },
    },
    exit: {
      opacity: 0,
      x: reduceMotion ? 0 : -8,
      transition: {
        duration: reduceMotion ? 0 : WORKSPACE_VIEW_EXIT_SECONDS,
        ease: DEBUG_MOTION_EASE,
      },
    },
  };
  const [initialState] = useState<CustomCreateInitialState>(() =>
    customCreateInitialState(
      initialDraft ?? emptyDraft(cloudProvider),
      cloudProvider,
    ),
  );
  const [draft, setDraft] = useState<AgentDraft>(initialState.draft);
  const [customModelSecretValues, setCustomModelSecretValues] = useState<
    Record<string, string>
  >(initialState.customModelSecretValues);
  const configuredRuntimeName = draft.deployment?.runtimeName ?? "";
  const deploymentRuntimeName = deploymentTarget
    ? deploymentTarget.name
    : resolveRuntimeName(
        draft.name,
        configuredRuntimeName,
        draft.deployment?.runtimeNameCustomized,
      );
  const transientModelSecretValues = customModelSecretValues;
  useEffect(() => {
    setDraft((current) => draftForCloudProvider(current, cloudProvider));
  }, [cloudProvider]);
  const [storedAgentBuilderConversation] = useState<StoredAgentBuilderConversation>(() =>
    agentBuilderStorageKey && typeof window !== "undefined"
      ? loadAgentBuilderConversation(localStorage, agentBuilderStorageKey)
      : { messages: [] },
  );
  const [aiRequirement, setAiRequirement] = useState(initialGoal);
  const [aiGenerating, setAiGenerating] = useState(false);
  const [aiGenerated, setAiGenerated] = useState(false);
  const [agentBuilderMessages, setAgentBuilderMessages] = useState<
    AgentBuilderChatMessage[]
  >(storedAgentBuilderConversation.messages);
  const [agentBuilderConversation, setAgentBuilderConversation] = useState<{
    conversationId: string;
    expiresAt: number;
  } | null>(() =>
    storedAgentBuilderConversation.conversationId &&
    storedAgentBuilderConversation.expiresAt
      ? {
          conversationId: storedAgentBuilderConversation.conversationId,
          expiresAt: storedAgentBuilderConversation.expiresAt,
        }
      : null,
  );
  const agentBuilderAbortRef = useRef<AbortController | null>(null);
  const agentBuilderMountedRef = useRef(false);
  const [usedAiGeneration, setUsedAiGeneration] = useState(false);
  const [aiErrorDialog, setAiErrorDialog] = useState<string | null>(null);
  const trimmedAiRequirement = aiRequirement.trim();
  const aiRequirementError =
    trimmedAiRequirement.length > 0 &&
    trimmedAiRequirement.length < GENERATED_AGENT_REQUIREMENT_MIN_LENGTH
      ? "请至少输入 4 个字符。"
      : "";
  const initialDraftSnapshotRef = useRef(JSON.stringify(draft));
  const lastNotifiedDraftSnapshotRef = useRef(initialDraftSnapshotRef.current);
  const draftSnapshot = JSON.stringify(draft);
  const draftDirty = draftSnapshot !== initialDraftSnapshotRef.current;
  const onDraftChangeRef = useRef(onDraftChange);
  useEffect(() => {
    onDraftChangeRef.current = onDraftChange;
  }, [onDraftChange]);
  useEffect(() => {
    if (draftSnapshot === lastNotifiedDraftSnapshotRef.current) return;
    lastNotifiedDraftSnapshotRef.current = draftSnapshot;
    onDraftChangeRef.current?.(
      draftForCloudProvider(draft, cloudProvider),
      draftDirty,
    );
  }, [cloudProvider, draft, draftDirty, draftSnapshot]);
  useEffect(() => {
    agentBuilderMountedRef.current = true;
    return () => {
      agentBuilderMountedRef.current = false;
      queueMicrotask(() => {
        if (!agentBuilderMountedRef.current) {
          agentBuilderAbortRef.current?.abort();
        }
      });
    };
  }, []);
  useEffect(() => {
    if (!agentBuilderStorageKey || typeof window === "undefined") return;
    const timer = window.setTimeout(() => {
      try {
        writeAgentBuilderConversation(localStorage, agentBuilderStorageKey, {
          messages: agentBuilderMessages,
          conversationId: agentBuilderConversation?.conversationId,
          expiresAt: agentBuilderConversation?.expiresAt,
        });
      } catch (error) {
        setAiErrorDialog(
          error instanceof Error
            ? error.message
            : "浏览器拒绝保存智能创建对话。",
        );
      }
    }, AGENT_BUILDER_PERSIST_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [agentBuilderConversation, agentBuilderMessages, agentBuilderStorageKey]);
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("build");
  const [builderPanel, setBuilderPanel] = useState<"chat" | "config" | "none">("chat");
  const [configTab, setConfigTab] = useState<"basic" | "capabilities">("basic");
  const [showErrors, setShowErrors] = useState(false);
  const [project, setProject] = useState<AgentProject | null>(null);
  const [building, setBuilding] = useState(false);
  const [cloudEnvironmentEditorOpen, setCloudEnvironmentEditorOpen] =
    useState(false);
  const [deployRegion, setDeployRegion] = useState<string>(
    deploymentTarget?.region ?? initialDeployRegion,
  );
  const debugEnabled = features?.generatedAgentTestRun === true;
  const debugDisabledReason =
    features?.generatedAgentTestRunDisabledReason ||
    "当前后端暂不支持生成 Agent 调试运行。";
  const [debugVariants, setDebugVariants] = useState<DebugVariant[]>(() => {
    const initialProviderDraft = draftForCloudProvider(
      initialDraft ?? emptyDraft(cloudProvider),
      cloudProvider,
    );
    return [
      {
        id: "baseline",
        name: "基准组",
        modelName: defaultDebugModelName(initialProviderDraft),
        description: initialProviderDraft.description,
        instruction: initialProviderDraft.instruction,
        configOpen: false,
        phase: "idle",
        runtimeSnapshot: "",
        messages: [],
        error: null,
      },
    ];
  });
  const [selectedVariantId, setSelectedVariantId] = useState("baseline");
  const debugVariantSequenceRef = useRef(1);
  const baselineModelEditedRef = useRef(false);
  const debugRunsRef = useRef(
    new Map<string, { run: GeneratedAgentTestRun; sessionId: string }>(),
  );
  const debugRunGenerationRef = useRef(0);
  const startDebugVariantRef = useRef<
    ((id: string) => Promise<void>) | null
  >(null);
  const [activeDebugRunCount, setActiveDebugRunCount] = useState(0);
  const [debugInput, setDebugInput] = useState("");
  const [debugTraceTarget, setDebugTraceTarget] =
    useState<DebugTraceTarget | null>(null);
  const [debugLeaveConfirmOpen, setDebugLeaveConfirmOpen] = useState(false);
  const [debugLeaveCleaning, setDebugLeaveCleaning] = useState(false);
  const debugLeaveConfirmResolverRef = useRef<
    ((confirmed: boolean) => void) | null
  >(null);
  const [buildErr, setBuildErr] = useState("");
  const [a2aRegistryAdvancedOpen, setA2aRegistryAdvancedOpen] = useState(false);

  // Which tree node is being edited ([] = root). The detail pane and per-node
  // inline errors are driven by this selection.
  const [selectedPath, setSelectedPath] = useState<NodePath>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const sectionRefs = useRef<Partial<Record<StepId, HTMLElement | null>>>({});

  async function cleanupStoredDebugRuns() {
    const activeRunIds = new Set(
      [...debugRunsRef.current.values()].map(({ run }) => run.runId),
    );
    const staleRunIds = readStoredDebugTestRunIds().filter(
      (runId) => !activeRunIds.has(runId),
    );
    if (!staleRunIds.length) return;
    await Promise.all(
      staleRunIds.map(async (runId) => {
        try {
          await deleteGeneratedAgentTestRun(runId);
          forgetDebugTestRun(runId);
        } catch (err) {
          console.warn("清理遗留调试运行失败", err);
        }
      }),
    );
  }

  useEffect(() => {
    void cleanupStoredDebugRuns();
    return () => {
      debugRunGenerationRef.current += 1;
      for (const { run } of debugRunsRef.current.values()) {
        deleteGeneratedAgentTestRun(run.runId)
          .then(() => forgetDebugTestRun(run.runId))
          .catch((err) => console.warn("清理调试运行失败", err));
      }
      debugRunsRef.current.clear();
    };
  }, []);

  useEffect(() => {
    if (workspaceMode !== "validate" || !debugEnabled) return;
    void startDebugVariantRef.current?.("baseline");
  }, [debugEnabled, workspaceMode]);

  useEffect(() => {
    return () => {
      debugLeaveConfirmResolverRef.current?.(false);
      debugLeaveConfirmResolverRef.current = null;
    };
  }, []);

  // Section wrapper: registers a ref for scroll-spy + renders the heading.
  // IMPORTANT: keep a STABLE identity (stored in a ref). If this were declared
  // as a fresh function each render, React would remount every section on every
  // keystroke — replacing the nodes the scroll-spy reads and dropping input
  // focus.
  // NOTE: Must be declared before any conditional returns to satisfy React hooks rules.
  const sectionImpl = useRef<
    | ((p: { meta: StepMeta; children: React.ReactNode }) => React.ReactElement)
    | null
  >(null);
  if (!sectionImpl.current) {
    sectionImpl.current = ({ meta, children }) => (
      <section
        ref={(el) => {
          sectionRefs.current[meta.id] = el;
        }}
        id={`cw-sec-${meta.id}`}
        data-step-id={meta.id}
        className={`cw-section cw-section-${meta.id}`}
      >
        <header className="cw-sec-head">
          <h2 className="cw-sec-title">{meta.label}</h2>
        </header>
        <div className="cw-sec-body">{children}</div>
      </section>
    );
  }

  // The selection is clamped to a path that still exists (a deletion may have
  // removed the previously-selected node). `patch` always edits this node.
  const safePath = pathExists(draft, selectedPath) ? selectedPath : [];
  const node = getNode(draft, safePath);
  const isRootAgent = safePath.length === 0;
  const a2aRegistryAdvancedId = `cw-a2a-registry-advanced-${
    safePath.join("-") || "root"
  }`;
  const patch = (p: Partial<AgentDraft>) =>
    setDraft((d) => updateNode(d, safePath, (n) => ({ ...n, ...p })));

  const patchDeploymentEnv = (key: string, value: string) =>
    setDraft((current) => ({
      ...current,
      deployment: {
        ...(current.deployment ?? { feishuEnabled: false }),
        envValues: {
          ...(current.deployment?.envValues ?? {}),
          [key]: value,
        },
      },
    }));

  const patchA2aRegistry = (
    updates: Partial<NonNullable<AgentDraft["a2aRegistry"]>>,
  ) =>
    patch({
      a2aRegistry: {
        ...(node.a2aRegistry ?? {
          enabled: false,
          registrySpaceId: "",
          registryTopK: "",
          registryRegion: "",
          registryEndpoint: "",
        }),
        ...updates,
      },
    });

  const patchA2aRegistryEnv = (key: string, value: string) => {
    if (!(key in A2A_REGISTRY_ENV_TO_FIELD)) return;
    const field = A2A_REGISTRY_ENV_TO_FIELD[key as A2aRegistryEnvKey];
    patchA2aRegistry({ [field]: value });
    patchDeploymentEnv(key, value);
  };

  const selectAgentType = (agentType: NonNullable<AgentDraft["agentType"]>) => {
    if (isRootAgent && agentType === "a2a") return;
    if (agentType === "a2a") {
      patch({
        agentType,
        a2aRegistry: {
          ...(node.a2aRegistry ?? {
            registrySpaceId: "",
            registryTopK: "",
            registryRegion: "",
            registryEndpoint: "",
          }),
          enabled: true,
        },
      });
      return;
    }
    patch({
      agentType,
      a2aRegistry: node.a2aRegistry
        ? { ...node.a2aRegistry, enabled: false }
        : undefined,
    });
  };

  // Replace the whole tree (structural edits from the left tree), optionally
  // moving the selection to a new node.
  const applyTree = (nextRoot: AgentDraft, select?: NodePath) => {
    setDraft(nextRoot);
    if (select) setSelectedPath(select);
  };

  const applyGeneratedAgentDraft = (generatedDraft: AgentDraft) => {
    setDraft(
      draftForCloudProvider(
        sanitizeGeneratedDraftCapabilities(
          normalizeDraft(generatedDraft),
          cloudProvider,
        ),
        cloudProvider,
      ),
    );
    setSelectedPath([]);
    setProject(null);
    setShowErrors(false);
    setBuildErr("");
    setAiGenerated(true);
    setUsedAiGeneration(true);
  };

  const handleGenerateDraft = async (
    requirementOverride?: string,
    options?: { preserveCurrentDraft?: boolean },
  ) => {
    const requirement = (requirementOverride ?? aiRequirement).trim();
    if (!requirement || aiGenerating) return;
    if (
      !options?.preserveCurrentDraft &&
      requirement.length < GENERATED_AGENT_REQUIREMENT_MIN_LENGTH
    ) return;
    if (
      !options?.preserveCurrentDraft &&
      draftDirty &&
      !window.confirm("生成的新配置会替换当前画布和属性，确定继续吗？")
    ) {
      return;
    }

    setAiGenerating(true);
    setAiGenerated(false);
    setAiErrorDialog(null);
    setBuildErr("");
    try {
      const generationRequirement = options?.preserveCurrentDraft
        ? conversationUpdateRequirement(requirement, draft)
        : requirement;
      const result = await generateAgentDraftFromRequirement(generationRequirement);
      applyGeneratedAgentDraft(result.draft);
    } catch (error) {
      setAiErrorDialog(error instanceof Error ? error.message : String(error));
    } finally {
      setAiGenerating(false);
    }
  };

  const runAgentBuilderConversation = async (rawMessage: string) => {
    const message = rawMessage.trim();
    if (!message || aiGenerating) return;

    const userMessageId = crypto.randomUUID();
    const assistantMessageId = crypto.randomUUID();
    const controller = new AbortController();
    agentBuilderAbortRef.current?.abort();
    agentBuilderAbortRef.current = controller;
    setAiRequirement(message);
    setAiGenerating(true);
    setAiGenerated(false);
    setBuildErr("");
    setAgentBuilderMessages((current) => [
      ...current,
      { id: userMessageId, role: "user", text: message },
      {
        id: assistantMessageId,
        role: "assistant",
        blocks: [],
        streaming: true,
      },
    ]);

    const updateAssistantMessage = (
      update: (current: AgentBuilderChatMessage) => AgentBuilderChatMessage,
    ) => {
      setAgentBuilderMessages((current) =>
        current.map((item) =>
          item.id === assistantMessageId ? update(item) : item,
        ),
      );
    };

    try {
      let conversationId =
        agentBuilderConversation &&
        agentBuilderConversation.expiresAt > Date.now() / 1000
          ? agentBuilderConversation.conversationId
          : null;
      if (!conversationId) {
        const conversation = await createGeneratedAgentConversation(controller.signal);
        conversationId = conversation.conversationId;
        setAgentBuilderConversation(conversation);
      }

      let acc = emptyAcc();
      for await (const event of runGeneratedAgentConversationSSE({
        conversationId,
        message,
        signal: controller.signal,
      })) {
        const eventType = (event as { type?: unknown }).type;
        if (eventType === "done") break;
        if (eventType === "error") {
          const detail = (event as { message?: unknown }).message;
          throw new Error(
            typeof detail === "string" ? detail : "智能创建对话失败",
          );
        }
        if (eventType === "agent_draft") {
          applyGeneratedAgentDraft(
            (event as Extract<
              GeneratedAgentConversationEvent,
              { type: "agent_draft" }
            >).draft,
          );
          continue;
        }

        const adkEvent = event as AdkEvent;
        const eventError =
          adkEvent.error || adkEvent.errorMessage || adkEvent.error_message;
        if (eventError) throw new Error(String(eventError));
        acc = applyEvent(acc, adkEvent);
        updateAssistantMessage((current) => ({
          ...current,
          blocks: acc.blocks,
        }));
      }
      setAgentBuilderConversation({
        conversationId,
        expiresAt: Date.now() / 1000 + 30 * 60,
      });
    } catch (error) {
      const aborted = controller.signal.aborted;
      const messageText = error instanceof Error ? error.message : String(error);
      if (messageText.includes("HTTP 404")) {
        setAgentBuilderConversation(null);
      }
      updateAssistantMessage((current) => ({
        ...current,
        error: aborted ? undefined : messageText,
        blocks:
          aborted &&
          (!current.blocks ||
            current.blocks.length === 0 ||
            current.blocks.every(
              (block) => block.kind === "thinking" && !block.done,
            ))
            ? [{ kind: "text", text: "已停止。你可以继续补充需求。" }]
            : current.blocks,
      }));
    } finally {
      if (agentBuilderAbortRef.current === controller) {
        agentBuilderAbortRef.current = null;
      }
      updateAssistantMessage((current) => ({
        ...current,
        streaming: false,
        blocks: current.blocks?.map((block) =>
          block.kind === "thinking" ? { ...block, done: true } : block,
        ),
      }));
      setAiGenerating(false);
    }
  };

  const stopAgentBuilderConversation = () => {
    agentBuilderAbortRef.current?.abort();
  };

  const initialGoalGenerationRef = useRef(false);
  useEffect(() => {
    const goal = initialGoal.trim();
    if (!goal || initialGoalGenerationRef.current) return;
    initialGoalGenerationRef.current = true;
    void runAgentBuilderConversation(goal);
  }, [initialGoal]);

  const addCanvasStep = (path: NodePath) => {
    const parent = getNode(draft, path);
    if (!nodeAcceptsChildren(parent) || path.length >= MAX_TREE_DEPTH) return;
    const next = addChild(draft, path, cloudProvider);
    const childIndex = getNode(next, path).subAgents.length - 1;
    applyTree(next, [...path, childIndex]);
  };

  const insertCanvasStep = (parentPath: NodePath, index: number) => {
    const parent = getNode(draft, parentPath);
    if (!nodeAcceptsChildren(parent) || parentPath.length >= MAX_TREE_DEPTH) {
      return;
    }
    const safeIndex = Math.max(0, Math.min(index, parent.subAgents.length));
    const next = insertChild(draft, parentPath, safeIndex, cloudProvider);
    applyTree(next, [...parentPath, safeIndex]);
  };

  const clearRootAgent = () => {
    if (
      !window.confirm("清空根 Agent 的全部配置和子 Agent？此操作无法撤销。")
    ) {
      return;
    }
    setDraft(emptyDraft(cloudProvider));
    setSelectedPath([]);
    setShowErrors(false);
  };

  const deleteCanvasStep = (path: NodePath) => {
    if (path.length === 0) {
      clearRootAgent();
      return;
    }
    applyTree(removeNode(draft, path), path.slice(0, -1));
  };

  // Root-only rich sections read these off the root draft directly.
  const builtinTools = node.builtinTools ?? [];
  const createBuiltinTools = useMemo(
    () => createBuiltinToolsForProvider(cloudProvider),
    [cloudProvider],
  );
  const createBuiltinToolIds = useMemo(
    () => new Set(createBuiltinTools.map((tool) => tool.id)),
    [createBuiltinTools],
  );
  const mcpTools = node.mcpTools ?? [];
  const selectedSkills = node.selectedSkills ?? [];
  const toggleBuiltin = (id: string) => {
    if (!createBuiltinToolIds.has(id)) return;
    patch({
      builtinTools: builtinTools.includes(id)
        ? builtinTools.filter((x) => x !== id)
        : [...builtinTools, id],
    });
  };

  // Detail-pane branching is driven by the SELECTED node's type.
  const orchestrator = isOrchestratorType(node.agentType);
  const a2a = isA2aType(node.agentType);
  useEffect(() => {
    if (orchestrator && configTab === "capabilities") {
      setConfigTab("basic");
    }
  }, [configTab, orchestrator]);
  const modelSource = resolvedModelSource(node, cloudProvider);
  const modelSourceOptions = useMemo<
    SelectOption<ModelSource | "gateway">[]
  >(
    () => [
      {
        value: "ark",
        label:
          cloudProvider === "byteplus" ? "BytePlus ModelArk" : "火山方舟",
      },
      { value: "custom", label: "自定义" },
      {
        value: "gateway",
        label: "模型网关（待上线）",
        disabled: true,
      },
    ],
    [cloudProvider],
  );
  const selectModelSource = (source: ModelSource) => {
    const nextModelName =
      source === "custom" && modelSource === "ark"
        ? ""
        : source === "ark" && !node.modelName?.trim()
          ? defaultModelName(cloudProvider)
          : node.modelName;
    patch({
      modelSource: source,
      modelName: nextModelName,
    });
  };

  // Inline error flags for the selected node.
  const duplicateNames = useMemo(() => duplicateAgentNames(draft), [draft]);
  const nameProblem = a2a
    ? null
    : (agentNameProblem(node.name) ??
      (duplicateNames.has(node.name)
        ? "Agent 名称在当前结构中必须唯一"
        : null));
  const nameInvalid = nameProblem !== null;
  const descriptionMissing = !a2a && node.description.trim().length === 0;
  const instructionMissing = node.instruction.trim().length === 0;
  const a2aRegistrySpaceMissing =
    a2a && !node.a2aRegistry?.registrySpaceId.trim();
  // Whole-tree validation: every node must satisfy its type's requirements.
  const problems = useMemo(
    () => treeProblems(draft, duplicateNames),
    [draft, duplicateNames],
  );
  const canFinish = problems.length === 0;
  const providerDraft = useMemo(
    () => draftForCloudProvider(draft, cloudProvider),
    [cloudProvider, draft],
  );
  const harnessOptimizationProfile = selectedHarnessProfile(draft);
  const harnessOptimizations = selectedHarnessOptimizations(draft);
  const harnessProviderNotice = harnessSidecarProviderNotice(cloudProvider);
  const currentDebugSnapshot = useMemo(
    () => debugSnapshotKey(providerDraft, transientModelSecretValues),
    [providerDraft, transientModelSecretValues],
  );
  const selectedDebugVariant =
    debugVariants.find((variant) => variant.id === selectedVariantId) ??
    debugVariants[0];
  const deploymentEnv = useMemo(
    () => collectDeploymentEnv(providerDraft),
    [providerDraft],
  );
  const customModelCredentials = useMemo(
    () =>
      customModelCredentialRequirements(
        providerDraft,
        defaultModelApiBase(cloudProvider),
      ),
    [cloudProvider, providerDraft],
  );
  const selectedCustomModelCredential = customModelCredentials.find(
    (requirement) =>
      requirement.label === `${node.name.trim() || "自定义模型"} 模型 API Key`,
  );

  function focusValidationProblem(problem: TreeProblem) {
    const sectionId = problem.problem === "缺少子 Agent" ? "type" : "basic";
    const section = sectionRefs.current[sectionId];
    section?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });

    const field =
      problem.problem === "缺少描述"
        ? "description"
        : problem.problem === "缺少系统提示词"
          ? "instruction"
          : problem.problem === "缺少 AgentKit 智能体中心"
            ? "a2a-registry"
            : problem.problem === "缺少子 Agent" ||
                problem.problem === "远程 Agent 只能作为子 Agent"
              ? null
              : "name";
    const fieldRoot = field
      ? section?.querySelector<HTMLElement>(
          `[data-validation-field="${field}"]`,
        )
      : section;
    const focusTarget = fieldRoot?.matches(
      'input, textarea, button:not([disabled]), [contenteditable="true"], [tabindex]:not([tabindex="-1"])',
    )
      ? fieldRoot
      : fieldRoot?.querySelector<HTMLElement>(
          'input, textarea, button:not([disabled]), [contenteditable="true"], [tabindex]:not([tabindex="-1"])',
        );
    focusTarget?.focus({ preventScroll: true });
  }

  const requireCompleteDraft = () => {
    if (canFinish) return true;
    setShowErrors(true);
    if (problems[0]) {
      setSelectedPath(problems[0].path);
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() =>
          focusValidationProblem(problems[0]),
        );
      });
    }
    return false;
  };

  const cleanupDebugRuns = async () => {
    debugRunGenerationRef.current += 1;
    setDebugTraceTarget(null);
    const runs = [...debugRunsRef.current.values()];
    debugRunsRef.current.clear();
    setActiveDebugRunCount(0);
    setDebugVariants((current) =>
      current.map((variant) => ({
        ...variant,
        phase: "idle",
        runtimeSnapshot: "",
        messages: [],
        error: null,
      })),
    );
    await Promise.all(
      runs.map(async ({ run }) => {
        try {
          await deleteGeneratedAgentTestRun(run.runId);
          forgetDebugTestRun(run.runId);
        } catch (err) {
          console.warn("清理调试运行失败", err);
        }
      }),
    );
  };

  const cleanupDebugVariantRun = async (id: string) => {
    const runtime = debugRunsRef.current.get(id);
    if (!runtime) return;
    debugRunsRef.current.delete(id);
    setActiveDebugRunCount(debugRunsRef.current.size);
    try {
      await deleteGeneratedAgentTestRun(runtime.run.runId);
      forgetDebugTestRun(runtime.run.runId);
    } catch (err) {
      console.warn("清理调试运行失败", err);
    }
  };

  const openDebugTrace = (id: string) => {
    const runtime = debugRunsRef.current.get(id);
    const variant = debugVariants.find((item) => item.id === id);
    if (!runtime || !variant) return;
    setDebugTraceTarget({
      runId: runtime.run.runId,
      sessionId: runtime.sessionId,
      variantName: variant.name,
    });
  };

  const resolveDebugLeaveConfirm = (confirmed: boolean) => {
    const resolve = debugLeaveConfirmResolverRef.current;
    debugLeaveConfirmResolverRef.current = null;
    resolve?.(confirmed);
  };

  const cancelDebugLeaveConfirm = () => {
    if (debugLeaveCleaning) return;
    setDebugLeaveConfirmOpen(false);
    resolveDebugLeaveConfirm(false);
  };

  const acceptDebugLeaveConfirm = async () => {
    if (debugLeaveCleaning) return;
    setDebugLeaveCleaning(true);
    try {
      await cleanupDebugRuns();
      setDebugLeaveConfirmOpen(false);
      resolveDebugLeaveConfirm(true);
    } finally {
      setDebugLeaveCleaning(false);
    }
  };

  const confirmLeaveDebug = async () => {
    const debugRunPending = debugVariants.some(
      (variant) =>
        variant.phase === "starting" || variant.phase === "sending",
    );
    if (
      workspaceMode !== "validate" ||
      (activeDebugRunCount === 0 && !debugRunPending)
    )
      return true;
    if (debugLeaveConfirmResolverRef.current) return false;
    return new Promise<boolean>((resolve) => {
      debugLeaveConfirmResolverRef.current = resolve;
      setDebugLeaveConfirmOpen(true);
    });
  };

  const openPublishPreview = async (
    variantId?: string,
    draftOverride?: AgentDraft,
  ) => {
    if (!(await confirmLeaveDebug())) return;
    setBuildErr("");
    if (!requireCompleteDraft()) {
      setWorkspaceMode("build");
      return;
    }
    const releaseProviderDraft = draftForCloudProvider(
      draftOverride ?? draft,
      cloudProvider,
    );
    if (
      releaseProviderDraft.harnessSidecar?.enabled &&
      harnessProviderNotice
    ) {
      setBuildErr(harnessProviderNotice);
      return;
    }
    if (
      releaseProviderDraft.cloudEnvironment?.dockerfile !== undefined &&
      !releaseProviderDraft.cloudEnvironment.dockerfile.trim()
    ) {
      setBuildErr("Dockerfile 不能为空。请输入有效内容，或恢复自动生成。");
      return;
    }
    if (
      (releaseProviderDraft.cloudEnvironment?.dockerfile?.length ?? 0) >
      MAX_CLOUD_DOCKERFILE_LENGTH
    ) {
      setBuildErr("Dockerfile 不能超过 64 KiB。请精简内容后重试。");
      return;
    }
    const releaseDeploymentEnv = collectDeploymentEnv(releaseProviderDraft);
    const invalidEnv = firstInvalidRuntimeEnv(
      releaseDeploymentEnv.specs,
      releaseProviderDraft.deployment?.envValues ?? {},
    );
    if (invalidEnv) {
      setBuildErr(
        `${invalidEnv.spec.comment || invalidEnv.spec.key}：${invalidEnv.error}`,
      );
      return;
    }
    setBuilding(true);
    try {
      const releaseVariant = variantId
        ? debugVariants.find((variant) => variant.id === variantId)
        : selectedDebugVariant;
      if (releaseVariant) setSelectedVariantId(releaseVariant.id);
      const releaseDraft = releaseVariant
        ? releaseDraftFromDebugVariant(releaseProviderDraft, releaseVariant)
        : releaseProviderDraft;
      const generated = await generateAgentProject(codegenDraft(releaseDraft));
      setDraft(releaseDraft);
      setProject(generated);
      setWorkspaceMode("publish");
    } catch (error) {
      setBuildErr(error instanceof Error ? error.message : String(error));
    } finally {
      setBuilding(false);
    }
  };

  const startDebugVariant = async (id: string) => {
    if (!debugEnabled || building) return;
    if (!requireCompleteDraft()) return;
    const variant = debugVariants.find((item) => item.id === id);
    if (
      !variant ||
      variant.phase === "starting" ||
      variant.phase === "sending" ||
      (variant.phase === "ready" &&
        variant.runtimeSnapshot ===
          debugVariantSnapshot(currentDebugSnapshot, variant) &&
        debugRunsRef.current.has(id))
    ) {
      return;
    }
    const modelName = variant.modelName.trim();
    const description = variant.description.trim();
    const instruction = variant.instruction.trim();
    const configurationKey = debugVariantConfigurationKey(variant);
    const variantIndex = debugVariants.findIndex((item) => item.id === id);
    const firstMatchingIndex = debugVariants.findIndex(
      (item) => debugVariantConfigurationKey(item) === configurationKey,
    );
    if (
      !modelName ||
      !description ||
      !instruction ||
      firstMatchingIndex !== variantIndex
    )
      return;

    const snapshot = debugVariantSnapshot(currentDebugSnapshot, variant);
    setDebugVariants((current) =>
      current.map((item) =>
        item.id === id
          ? {
              ...item,
              configOpen: false,
              phase: "starting",
              messages: [],
              error: null,
            }
          : item,
      ),
    );
    setDebugInput("");

    let createdRun: GeneratedAgentTestRun | null = null;
    const runGeneration = debugRunGenerationRef.current;
    let failedPhase: AgentDebugFailedProps["failedPhase"] = "unknown";
    const variantType = id === "baseline" ? "baseline" : "comparison";
    const operation = beginAgentDebug({
      agentId: String(providerDraft.name || "unknown"),
      variantType,
    });
    try {
      await cleanupDebugVariantRun(id);
      await cleanupStoredDebugRuns();
      if (runGeneration !== debugRunGenerationRef.current) return;
      const variantDraft: AgentDraft = {
        ...providerDraft,
        modelName: variant.modelName || providerDraft.modelName,
        description: variant.description,
        instruction: variant.instruction,
      };
      failedPhase = "create_test_run";
      createdRun = await createGeneratedAgentTestRun(
        debugRuntimeDraft(variantDraft, transientModelSecretValues),
        deploymentTarget
          ? {
              runtimeId: deploymentTarget.runtimeId,
              region: deploymentTarget.region,
            }
          : undefined,
      );
      rememberDebugTestRun(createdRun.runId);
      failedPhase = "create_test_session";
      const sessionId = await createGeneratedAgentTestSession(
        createdRun.runId,
        "test_user",
      );
      if (runGeneration !== debugRunGenerationRef.current) {
        try {
          await deleteGeneratedAgentTestRun(createdRun.runId);
          forgetDebugTestRun(createdRun.runId);
        } catch (cleanupError) {
          console.warn("清理调试运行失败", cleanupError);
        }
        return;
      }
      debugRunsRef.current.set(id, { run: createdRun, sessionId });
      setActiveDebugRunCount(debugRunsRef.current.size);
      setDebugVariants((current) =>
        current.map((item) =>
          item.id === id
            ? { ...item, phase: "ready", runtimeSnapshot: snapshot }
            : item,
        ),
      );
      operation.succeed({ debugRunId: String(createdRun.runId) });
    } catch (err) {
      if (createdRun) {
        try {
          await deleteGeneratedAgentTestRun(createdRun.runId);
          forgetDebugTestRun(createdRun.runId);
        } catch (cleanupError) {
          console.warn("清理调试运行失败", cleanupError);
        }
      }
      setDebugVariants((current) =>
        current.map((item) =>
          item.id === id
            ? {
                ...item,
                phase: "error",
                runtimeSnapshot: "",
                error: err instanceof Error ? err.message : String(err),
              }
            : item,
        ),
      );
      operation.fail({
        failedPhase,
        ...classifyTelemetryError(err, { phase: failedPhase }),
      });
    }
  };
  startDebugVariantRef.current = startDebugVariant;

  const sendDebugMessage = async () => {
    const text = debugInput.trim();
    const targets = debugVariants.filter(
      (variant) =>
        variant.phase === "ready" &&
        variant.runtimeSnapshot ===
          debugVariantSnapshot(currentDebugSnapshot, variant) &&
        debugRunsRef.current.has(variant.id),
    );
    if (!text || targets.length === 0) return;

    setDebugInput("");
    const targetIds = new Set(targets.map((variant) => variant.id));
    setDebugVariants((current) =>
      current.map((variant) =>
        targetIds.has(variant.id)
          ? {
              ...variant,
              phase: "sending",
              messages: [
                ...variant.messages,
                { role: "user", content: text },
                { role: "assistant", content: "", blocks: [] },
              ],
            }
          : variant,
      ),
    );

    await Promise.all(
      targets.map(async (variant) => {
        const runtime = debugRunsRef.current.get(variant.id);
        if (!runtime) return;
        try {
          let acc = emptyAcc();
          for await (const event of runGeneratedAgentTestSSE({
            runId: runtime.run.runId,
            userId: "test_user",
            sessionId: runtime.sessionId,
            text,
          })) {
            const eventError =
              event.error || event.errorMessage || event.error_message;
            if (!eventError) acc = applyEvent(acc, event);
            setDebugVariants((current) =>
              current.map((item) => {
                if (item.id !== variant.id) return item;
                const messages = [...item.messages];
                const last = { ...messages[messages.length - 1] };
                if (eventError) {
                  last.error = String(eventError);
                } else {
                  last.content = acc.blocks
                    .filter((block) => block.kind === "text")
                    .map((block) => (block as { text: string }).text)
                    .join("");
                  last.blocks = acc.blocks;
                }
                messages[messages.length - 1] = last;
                return { ...item, messages };
              }),
            );
            if (eventError) break;
          }
        } catch (err) {
          setDebugVariants((current) =>
            current.map((item) => {
              if (item.id !== variant.id) return item;
              const messages = [...item.messages];
              const last = { ...messages[messages.length - 1] };
              last.error = err instanceof Error ? err.message : String(err);
              messages[messages.length - 1] = last;
              return { ...item, messages };
            }),
          );
        } finally {
          setDebugVariants((current) =>
            current.map((item) =>
              item.id === variant.id ? { ...item, phase: "ready" } : item,
            ),
          );
        }
      }),
    );
  };

  const addDebugVariant = () => {
    setDebugVariants((current) => {
      if (current.length >= 2) return current;
      const sequence = debugVariantSequenceRef.current++;
      const id = `variant-${sequence}`;
      return [
        ...current.map((variant) => ({ ...variant, configOpen: false })),
        {
          id,
          name: `对照组 ${sequence}`,
          modelName: draft.modelName ?? "",
          description: draft.description,
          instruction: draft.instruction,
          configOpen: true,
          phase: "idle",
          runtimeSnapshot: "",
          messages: [],
          error: null,
        },
      ];
    });
  };

  const removeDebugVariant = async (id: string) => {
    if (id === "baseline") return;
    await cleanupDebugVariantRun(id);
    setDebugVariants((current) =>
      current.filter((variant) => variant.id !== id),
    );
    if (selectedVariantId === id) setSelectedVariantId("baseline");
  };

  const patchDebugVariant = (id: string, patch: Partial<DebugVariant>) =>
    setDebugVariants((current) =>
      current.map((variant) =>
        variant.id === id ? { ...variant, ...patch } : variant,
      ),
    );

  const updateDebugVariantConfig = (
    id: string,
    field: "modelName" | "description" | "instruction",
    value: string,
  ) => {
    if (id === "baseline" && field === "modelName") {
      baselineModelEditedRef.current = true;
    }
    patchDebugVariant(id, { [field]: value });
    if (selectedVariantId !== id || id === "baseline") return;
    setSelectedVariantId("baseline");
  };

  const completeDebugVariantConfig = (id: string) => {
    const variant = debugVariants.find((item) => item.id === id);
    if (!variant) return;
    const modelName = variant.modelName.trim();
    const description = variant.description.trim();
    const instruction = variant.instruction.trim();
    const configurationKey = debugVariantConfigurationKey(variant);
    const variantIndex = debugVariants.findIndex((item) => item.id === id);
    const firstMatchingIndex = debugVariants.findIndex(
      (item) => debugVariantConfigurationKey(item) === configurationKey,
    );
    if (
      !modelName ||
      !description ||
      !instruction ||
      firstMatchingIndex !== variantIndex
    )
      return;
    void startDebugVariant(id);
  };

  const handleDeploy = async (
    proj: AgentProject,
    onStage?: (s: DeployStage) => void,
    options?: Parameters<typeof deployAgentkitProject>[3],
  ) => {
    const net = draft.deployment?.network;
    const network =
      net && net.mode && net.mode !== "public"
        ? {
            mode: net.mode,
            vpc_id: net.vpcId,
            subnet_ids: net.subnetIds,
            enable_shared_internet_access: net.enableSharedInternetAccess,
          }
        : undefined;
    return deployAgentkitProject(
      proj.name,
      proj.files,
      {
        region: deploymentTarget?.region ?? deployRegion,
        projectName: "default",
        network,
      },
      {
        ...options,
        onStage,
        runtimeId: deploymentTarget?.runtimeId,
        runtimeName: options?.runtimeName ?? deploymentRuntimeName,
        appName: deploymentTarget?.appName,
        description: draft.description,
        harnessSidecar: draft.harnessSidecar,
      },
    );
  };

  const openValidation = () => {
    if (!requireCompleteDraft()) return;
    setDebugVariants((current) =>
      current.map((variant) =>
        variant.id === "baseline" && !debugRunsRef.current.has(variant.id)
          ? {
              ...variant,
              modelName: baselineModelEditedRef.current
                ? variant.modelName
                : defaultDebugModelName(providerDraft),
              description: providerDraft.description,
              instruction: providerDraft.instruction,
            }
          : variant,
      ),
    );
    setWorkspaceMode("validate");
  };

  const handleWorkspaceChange = async (nextMode: WorkspaceMode) => {
    if (nextMode === "publish") {
      await openPublishPreview();
      return;
    }
    if (nextMode === "validate") {
      openValidation();
      return;
    }
    if (!(await confirmLeaveDebug())) return;
    setWorkspaceMode(nextMode);
  };

  const updateCloudEnvironment = (cloudEnvironment: CloudEnvironmentConfig) => {
    const nextDraft = { ...draft, cloudEnvironment };
    setDraft(nextDraft);
    setBuildErr("");
    if (workspaceMode === "publish" && !cloudEnvironmentEditorOpen) {
      void openPublishPreview(undefined, nextDraft);
    } else if (workspaceMode !== "publish") {
      setProject(null);
    }
  };

  const Section = sectionImpl.current;

  const metaOf = (id: StepId) => STEPS.find((s) => s.id === id)!;

  const aiComposer = (
    <section
      className={`cw-ai-compose${aiGenerating ? " is-generating" : ""}${aiGenerated ? " is-success" : ""}`}
      aria-label="AI 自动填写 Agent 配置"
    >
      <AnimatePresence initial={false} mode="wait">
        {aiGenerated ? (
          <motion.div
            key="success"
            className="cw-ai-compose-success"
            role="status"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            <span className="cw-ai-success-check" aria-hidden />
            <strong>生成成功</strong>
            <button
              type="button"
              className="cw-ai-regenerate"
              onClick={() => setAiGenerated(false)}
            >
              重新生成
            </button>
          </motion.div>
        ) : (
          <motion.div
            key="compose"
            className="cw-ai-compose-entry"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
          >
            <form
              className="cw-ai-compose-form"
              onSubmit={(event) => {
                event.preventDefault();
                void handleGenerateDraft();
              }}
            >
              <Input
                className="cw-ai-compose-input"
                type="text"
                size="lg"
                variant="soft"
                value={aiRequirement}
                maxLength={8000}
                disabled={aiGenerating}
                placeholder={`描述目标，使用 ${plannerModelName(cloudProvider)} 模型一键生成配置`}
                aria-invalid={Boolean(aiRequirementError)}
                aria-describedby={
                  aiRequirementError ? "ai-requirement-error" : undefined
                }
                invalid={Boolean(aiRequirementError)}
                onChange={(event) => setAiRequirement(event.target.value)}
                onKeyDown={(event) => {
                  if (isImeCompositionEvent(event.nativeEvent)) return;
                  if (event.key === "Enter") {
                    event.preventDefault();
                    void handleGenerateDraft();
                  }
                }}
              />
              <button
                type="submit"
                disabled={
                  aiGenerating ||
                  !trimmedAiRequirement ||
                  Boolean(aiRequirementError)
                }
                aria-label={aiGenerating ? "正在智能生成" : "智能生成"}
              >
                {aiGenerating ? (
                  <span className="cw-ai-orb" aria-hidden>
                    <span />
                  </span>
                ) : (
                  "智能生成"
                )}
              </button>
            </form>
            {aiRequirementError && (
              <p
                className="cw-ai-requirement-error"
                id="ai-requirement-error"
                role="alert"
              >
                {aiRequirementError}
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
  void aiComposer;

  return (
    <div className={`cw-root is-${workspaceMode}`}>
      <WorkspaceHeader
        onBack={onBack}
        onDebug={() => void handleWorkspaceChange("validate")}
        onDeploy={() => void handleWorkspaceChange("publish")}
        debugMode={workspaceMode === "validate"}
        showDebugPreview={
          workspaceMode !== "validate" ||
          debugWorkspaceView(debugVariants) !== "results"
        }
        comparisonDisabled={debugVariants.length >= 2}
        onAddComparison={addDebugVariant}
        onExitDebug={() => void handleWorkspaceChange("build")}
      />
      {buildErr && (
        <DeploymentErrorMessage
          className="cw-workspace-alert"
          message={buildErr}
        />
      )}
      <main className="cw-workspace-main" id="cw-workspace-main">
        <AnimatePresence initial={false} mode="popLayout">
        {workspaceMode === "build" && (
          <motion.div
            key="build-workspace"
            className="cw-build-workspace cw-workspace-view"
            {...workspaceViewMotion}
          >
            <div className="cw-editor">
              <AnimatePresence initial={false} mode="popLayout">
                {builderPanel === "chat" ? (
                  <motion.div
                    key="builder-chat"
                    className="cw-builder-chat-motion"
                    initial={
                      reduceMotion
                        ? false
                        : {
                            opacity: 0,
                            clipPath: "inset(0 100% 0 0 round 16px)",
                          }
                    }
                    animate={{
                      opacity: 1,
                      clipPath: "inset(0 0% 0 0 round 16px)",
                    }}
                    exit={{
                      opacity: 0,
                      clipPath: reduceMotion
                        ? "inset(0 0% 0 0 round 16px)"
                        : "inset(0 100% 0 0 round 16px)",
                      pointerEvents: "none",
                    }}
                    transition={{
                      duration: reduceMotion ? 0 : BUILDER_PANEL_SECONDS,
                      ease: BUILDER_PANEL_EASE,
                    }}
                  >
                    <AgentBuilderChatPanel
                      messages={agentBuilderMessages}
                      busy={aiGenerating}
                      onCollapse={() => setBuilderPanel("none")}
                      onStop={stopAgentBuilderConversation}
                      onSubmit={(goal) => void runAgentBuilderConversation(goal)}
                    />
                  </motion.div>
                ) : (
                  <motion.div
                    key="builder-chat-trigger"
                    className="cw-open-chat-motion"
                    initial={reduceMotion ? false : { opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{
                      duration: reduceMotion ? 0 : 0.16,
                      ease: [0.22, 1, 0.36, 1],
                    }}
                  >
                    <Button
                      type="button"
                      color="secondary"
                      variant="ghost"
                      size="sm"
                      uniform
                      pill={false}
                      className="cw-open-chat"
                      aria-label="展开智能创建对话"
                      onClick={() => setBuilderPanel("chat")}
                    >
                      <MessageSmileSquareIcon />
                    </Button>
                  </motion.div>
                )}
              </AnimatePresence>
              <motion.div
                className="cw-canvas-motion"
                layout={reduceMotion ? false : "position"}
                transition={{
                  layout: {
                    duration: reduceMotion ? 0 : BUILDER_PANEL_SECONDS,
                    ease: BUILDER_PANEL_EASE,
                  },
                }}
              >
                <AgentBuildCanvas
                  draft={draft}
                  direction="vertical"
                  selectedPath={safePath}
                  onSelect={(path) => {
                    setSelectedPath(path);
                    setBuilderPanel("config");
                  }}
                  onAdd={addCanvasStep}
                  onInsert={insertCanvasStep}
                  onDelete={deleteCanvasStep}
                />
              </motion.div>
              {/* Right: the form for the currently-selected node. */}
              <AnimatePresence initial={false} mode="popLayout">
                {builderPanel === "config" && (
              <motion.div
                key="builder-config"
                className={`cw-detail is-${configTab}`}
                initial={
                  reduceMotion
                    ? false
                    : {
                        opacity: 0,
                        clipPath: "inset(0 0 0 100% round 16px)",
                      }
                }
                animate={{
                  opacity: 1,
                  clipPath: "inset(0 0 0 0% round 16px)",
                }}
                exit={{
                  opacity: 0,
                  clipPath: reduceMotion
                    ? "inset(0 0 0 0% round 16px)"
                    : "inset(0 0 0 100% round 16px)",
                  pointerEvents: "none",
                }}
                transition={{
                  duration: reduceMotion ? 0 : BUILDER_PANEL_SECONDS,
                  ease: BUILDER_PANEL_EASE,
                }}
              >
                <header className="cw-detail-header">
                  <span className="cw-detail-agent-icon" aria-hidden="true"><AgentFaceSquareIcon /></span>
                  <strong className={node.name.trim() ? undefined : "is-name-missing"}>
                    {node.name.trim() || "名称未配置"}
                  </strong>
                  <Button
                    type="button"
                    color="secondary"
                    variant="ghost"
                    size="sm"
                    uniform
                    pill={false}
                    className="cw-detail-close"
                    aria-label="关闭 Agent 配置"
                    onClick={() => setBuilderPanel("none")}
                  >
                    <X />
                  </Button>
                </header>
                <div className="cw-detail-tabs" role="tablist" aria-label="Agent 配置分类">
                  <button
                    type="button"
                    role="tab"
                    aria-selected={configTab === "basic"}
                    className={configTab === "basic" ? "is-active" : ""}
                    onClick={() => setConfigTab("basic")}
                  >基本信息</button>
                  {!orchestrator && (
                    <button
                      type="button"
                      role="tab"
                      aria-selected={configTab === "capabilities"}
                      className={configTab === "capabilities" ? "is-active" : ""}
                      onClick={() => setConfigTab("capabilities")}
                    >能力扩展</button>
                  )}
                </div>
                {/* Scroll area: form on the left, step nav on the right. */}
                <div className="cw-detail-scroll" ref={scrollRef}>
                  <div className="cw-detail-inner">
                    <div className="cw-lower">
                      <div className="cw-form-col">
                        <Section meta={metaOf("type")}>
                          <RadioGroup<AgentType>
                            className="cw-agent-type-options"
                            aria-label="Agent 类型"
                            value={node.agentType ?? "llm"}
                            onChange={selectAgentType}
                          >
                            {AGENT_TYPES.map((t) => {
                              const on = (node.agentType ?? "llm") === t.id;
                              const remoteTypeDisabled =
                                isRootAgent && t.id === "a2a";
                              const disabledHintId = remoteTypeDisabled
                                ? "cw-remote-agent-disabled-hint"
                                : undefined;
                              return (
                                <div
                                  key={t.id}
                                  data-agent-type={t.id}
                                  className={`cw-agent-type-option ${on ? "is-on" : ""} ${
                                    remoteTypeDisabled ? "is-disabled" : ""
                                  }`}
                                  tabIndex={remoteTypeDisabled ? 0 : undefined}
                                  aria-describedby={disabledHintId}
                                >
                                  <RadioGroup.Item
                                    value={t.id}
                                    disabled={remoteTypeDisabled}
                                    block
                                    className="cw-agent-type-control"
                                  >
                                    <span className="cw-agent-type-copy">
                                      <strong>
                                        {AGENT_TYPE_BAR_LABELS[t.id]}
                                      </strong>
                                    </span>
                                  </RadioGroup.Item>
                                  {remoteTypeDisabled && (
                                    <span
                                      id={disabledHintId}
                                      className="cw-agent-type-disabled-hint"
                                      role="tooltip"
                                    >
                                      远程智能体只能作为子步骤使用
                                    </span>
                                  )}
                                </div>
                              );
                            })}
                          </RadioGroup>
                          {showErrors &&
                            orchestrator &&
                            node.subAgents.length === 0 && (
                              <span className="cw-error-text">
                                {validationProblemMessage({
                                  path: safePath,
                                  name: node.name.trim() || "未命名",
                                  typeLabel: agentTypeMeta(node.agentType)
                                    .label,
                                  problem: "缺少子 Agent",
                                })}
                              </span>
                            )}
                        </Section>
                        <Section meta={metaOf("basic")}>
                          <div className="cw-form">
                            {!a2a && (
                              <>
                                <div className="cw-field cw-model-config-row cw-basic-name-field">
                                  <label
                                    className="cw-label cw-form-section-title"
                                    htmlFor="cw-agent-name"
                                  >
                                    名称
                                    <span className="cw-req">*</span>
                                  </label>
                                  <Input
                                    id="cw-agent-name"
                                    size="md"
                                    invalid={nameInvalid}
                                    data-validation-field="name"
                                    value={node.name}
                                    placeholder="assistant"
                                    aria-invalid={showErrors && nameInvalid}
                                    aria-describedby={
                                      showErrors && nameProblem
                                        ? "cw-agent-name-error"
                                        : undefined
                                    }
                                    onChange={(e) =>
                                      patch({ name: e.target.value })
                                    }
                                  />
                                  {showErrors && nameProblem ? (
                                    <span
                                      id="cw-agent-name-error"
                                      role="alert"
                                      className="cw-error-text"
                                    >
                                      {nameProblem}
                                    </span>
                                  ) : (
                                    <span className="cw-help">
                                      遵循 Google ADK
                                      命名规则，且在执行流程中保持唯一。
                                    </span>
                                  )}
                                </div>
                                <div className="cw-field cw-model-config-row cw-basic-description-field">
                                  <label
                                    className="cw-label cw-form-section-title"
                                    htmlFor="cw-agent-description"
                                  >
                                    {isRootAgent ? "描述" : "智能体描述"}
                                    <span className="cw-req">*</span>
                                  </label>
                                  <Textarea
                                    id="cw-agent-description"
                                    size="md"
                                    rows={3}
                                    invalid={descriptionMissing}
                                    data-validation-field="description"
                                    value={node.description}
                                    placeholder="简要描述这个 Agent 的用途，便于团队识别…"
                                    aria-invalid={
                                      showErrors && descriptionMissing
                                    }
                                    aria-describedby={
                                      showErrors && descriptionMissing
                                        ? "cw-agent-description-error"
                                        : undefined
                                    }
                                    onChange={(e) =>
                                      patch({ description: e.target.value })
                                    }
                                  />
                                  {showErrors && descriptionMissing ? (
                                    <span
                                      id="cw-agent-description-error"
                                      role="alert"
                                      className="cw-error-text"
                                    >
                                      描述为必填项
                                    </span>
                                  ) : (
                                    <span className="cw-help">
                                      {isRootAgent
                                        ? "完整描述会保留；部署时会自动整理为符合 Runtime 规范的单行描述。"
                                        : "描述会显示在 Agent 列表与选择器中。"}
                                    </span>
                                  )}
                                </div>
                              </>
                            )}
                            {orchestrator ? (
                              <>
                                {node.agentType === "loop" && (
                                  <div className="cw-field">
                                    <label
                                      className="cw-label"
                                      htmlFor="cw-agent-max-iterations"
                                    >
                                      最大轮次
                                    </label>
                                    <Input
                                      id="cw-agent-max-iterations"
                                      size="md"
                                      type="number"
                                      min={1}
                                      value={node.maxIterations ?? 3}
                                      onChange={(e) =>
                                        patch({
                                          maxIterations: Math.max(
                                            1,
                                            Number(e.target.value) || 1,
                                          ),
                                        })
                                      }
                                    />
                                    <span className="cw-help">
                                      循环编排反复执行子
                                      Agent，直到满足条件或达到该轮次上限。
                                    </span>
                                  </div>
                                )}
                              </>
                            ) : a2a ? (
                              <div
                                className="cw-field cw-remote-center-fields"
                                data-validation-field="a2a-registry"
                              >
                                <div className="cw-remote-center-head">
                                  <label
                                    className="cw-label"
                                    htmlFor="cw-a2a-space"
                                  >
                                    AgentKit 智能体中心
                                    <span className="cw-req">*</span>
                                  </label>
                                  <p className="cw-help cw-remote-center-description">
                                    远程 Agent 的名称、描述和能力来自中心返回的
                                    Agent Card。
                                    系统会根据每轮任务动态发现并挂载匹配的
                                    Agent。
                                  </p>
                                </div>
                                <A2aSpaceSelect
                                  value={
                                    node.a2aRegistry?.registrySpaceId ?? ""
                                  }
                                  region={
                                    node.a2aRegistry?.registryRegion ||
                                    A2A_REGISTRY_DEFAULTS.region
                                  }
                                  invalid={
                                    showErrors && a2aRegistrySpaceMissing
                                  }
                                  onChange={(spaceId) =>
                                    patchA2aRegistryEnv(
                                      A2A_REGISTRY_SPACE_ENV_KEY,
                                      spaceId,
                                    )
                                  }
                                />
                                <button
                                  type="button"
                                  className="cw-more-options"
                                  aria-expanded={a2aRegistryAdvancedOpen}
                                  aria-controls={a2aRegistryAdvancedId}
                                  onClick={() =>
                                    setA2aRegistryAdvancedOpen((open) => !open)
                                  }
                                >
                                  <span>更多选项</span>
                                  <ChevronRight
                                    className={`cw-more-options-chevron ${
                                      a2aRegistryAdvancedOpen ? "is-open" : ""
                                    }`}
                                    aria-hidden
                                  />
                                </button>
                                <AnimatePresence initial={false}>
                                  {a2aRegistryAdvancedOpen && (
                                    <motion.div
                                      id={a2aRegistryAdvancedId}
                                      className="cw-model-advanced"
                                      initial={{ height: 0, opacity: 0 }}
                                      animate={{ height: "auto", opacity: 1 }}
                                      exit={{ height: 0, opacity: 0 }}
                                      transition={{
                                        duration: 0.18,
                                        ease: "easeOut",
                                      }}
                                    >
                                      <RuntimeEnvFields
                                        env={A2A_REGISTRY_RUNTIME_ENV}
                                        values={a2aRegistryEnvValues(
                                          node.a2aRegistry,
                                          { includeDefaults: false },
                                        )}
                                        onChange={patchA2aRegistryEnv}
                                      />
                                    </motion.div>
                                  )}
                                </AnimatePresence>
                                {showErrors && a2aRegistrySpaceMissing && (
                                  <span className="cw-error-text" role="alert">
                                    请选择 AgentKit 智能体中心
                                  </span>
                                )}
                              </div>
                            ) : (
                              <div
                                className="cw-field cw-model-config-row cw-basic-prompt-field"
                                data-validation-field="instruction"
                              >
                                <label className="cw-label cw-form-section-title">
                                  系统提示词<span className="cw-req">*</span>
                                </label>
                                <Suspense
                                  fallback={
                                    <div
                                      className="cw-markdown-loading"
                                      role="status"
                                    >
                                      正在加载 Markdown 编辑器…
                                    </div>
                                  }
                                >
                                  <MarkdownPromptEditor
                                    value={node.instruction}
                                    invalid={instructionMissing}
                                    onChange={(instruction) =>
                                      patch({ instruction })
                                    }
                                  />
                                </Suspense>
                                {showErrors && instructionMissing ? (
                                  <span className="cw-error-text" role="alert">
                                    系统提示词为必填项
                                  </span>
                                ) : (
                                  <span className="cw-help">
                                    支持 Markdown 快捷输入，例如键入 ##
                                    加空格创建二级标题。
                                  </span>
                                )}
                              </div>
                            )}
                          </div>
                        </Section>

                        {/* Every LLM agent gets model, tools, skills, and knowledge.
                Root LLM agents additionally own memory and tracing. */}
                        {!orchestrator && !a2a && (
                          <>
                            <Section meta={metaOf("model")}>
                              <div className="cw-form cw-model-form">
                                <h3 className="cw-form-section-title cw-model-section-title">
                                  模型配置
                                </h3>
                                <div className="cw-field cw-model-config-row cw-model-source-field">
                                  <label
                                    className="cw-label"
                                    htmlFor="cw-model-source"
                                  >
                                    来源
                                  </label>
                                  <Select
                                    id="cw-model-source"
                                    options={modelSourceOptions}
                                    value={modelSource}
                                    size="lg"
                                    pill={false}
                                    align="start"
                                    triggerClassName="cw-agent-config-select-trigger"
                                    optionClassName="cw-agent-config-select-option"
                                    onChange={(option) => {
                                      if (option.value !== "gateway")
                                        selectModelSource(option.value);
                                    }}
                                  />
                                </div>
                                {modelSource === "ark" ? (
                                  <div className="cw-field cw-model-ark-field">
                                    <ModelOptionSelect
                                      value={node.modelName ?? ""}
                                      cloudProvider={cloudProvider}
                                      apiKeyId={draft.deployment?.modelApiKeyId}
                                      apiKeyName={draft.deployment?.modelApiKeyName}
                                      onApiKeyChange={(key) =>
                                        setDraft((current) => ({
                                          ...current,
                                          deployment: {
                                            ...(current.deployment ?? {
                                              feishuEnabled: false,
                                            }),
                                            modelApiKeyId: key.id,
                                            modelApiKeyName: key.name,
                                          },
                                        }))
                                      }
                                      onChange={(modelName) =>
                                        patch({ modelName })
                                      }
                                    />
                                  </div>
                                ) : (
                                  <>
                                    <div className="cw-field cw-model-config-row">
                                      <label
                                        className="cw-label"
                                        htmlFor="cw-custom-model-name"
                                      >
                                        模型名称
                                      </label>
                                      <Input
                                        id="cw-custom-model-name"
                                        size="md"
                                        value={node.modelName ?? ""}
                                        onChange={(e) =>
                                          patch({ modelName: e.target.value })
                                        }
                                      />
                                    </div>
                                    <div className="cw-field cw-model-config-row">
                                      <label
                                        className="cw-label"
                                        htmlFor="cw-custom-model-provider"
                                      >
                                        提供商
                                      </label>
                                      <div className="cw-model-provider-control">
                                        <Input
                                          id="cw-custom-model-provider"
                                          size="md"
                                          value={node.modelProvider ?? ""}
                                          placeholder="openai"
                                          onChange={(e) =>
                                            patch({
                                              modelProvider: e.target.value,
                                            })
                                          }
                                        />
                                        <a
                                          className="cw-model-provider-help"
                                          href="https://docs.litellm.ai/docs/providers"
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          onClick={(event) =>
                                            event.stopPropagation()
                                          }
                                        >
                                          LiteLLM 支持列表
                                          <ExternalLink aria-hidden="true" />
                                        </a>
                                      </div>
                                    </div>
                                    <div className="cw-field cw-model-config-row is-long">
                                      <label
                                        className="cw-label"
                                        htmlFor="cw-custom-model-api-base"
                                      >
                                        API Base
                                      </label>
                                      <Input
                                        id="cw-custom-model-api-base"
                                        size="md"
                                        value={node.modelApiBase ?? ""}
                                        onChange={(e) =>
                                          patch({
                                            modelApiBase: e.target.value,
                                          })
                                        }
                                      />
                                    </div>
                                    <div className="cw-field cw-model-config-row is-long">
                                      <label
                                        className="cw-label"
                                        htmlFor="cw-custom-model-api-key"
                                      >
                                        API Key
                                      </label>
                                      <Input
                                        id="cw-custom-model-api-key"
                                        size="md"
                                        type="password"
                                        value={
                                          selectedCustomModelCredential
                                            ? (customModelSecretValues[
                                                selectedCustomModelCredential
                                                  .key
                                              ] ?? "")
                                            : ""
                                        }
                                        autoComplete="new-password"
                                        onChange={(event) => {
                                          if (!selectedCustomModelCredential)
                                            return;
                                          const value =
                                            event.currentTarget.value;
                                          setCustomModelSecretValues(
                                            (current) => ({
                                              ...current,
                                              [selectedCustomModelCredential.key]:
                                                value,
                                            }),
                                          );
                                        }}
                                      />
                                    </div>
                                  </>
                                )}
                              </div>
                            </Section>

                            <Section meta={metaOf("tools")}>
                              <div className="cw-form cw-capabilities-form">
                                <div className="cw-field">
                                  <label className="cw-label">内置工具</label>
                                  <span className="cw-help">
                                    勾选 VeADK 提供的内置能力，生成时会自动补全
                                    import 与所需环境变量。
                                  </span>
                                  <div className="cw-tools-list-shell">
                                    <Checklist
                                      items={createBuiltinTools}
                                      selected={builtinTools}
                                      onToggle={toggleBuiltin}
                                      scrollRows={6}
                                    />
                                  </div>
                                  <AnimatePresence initial={false}>
                                    {builtinTools.includes("run_code") && (
                                      <motion.div
                                        className="cw-tool-config"
                                        initial={{ opacity: 0, y: -4 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        exit={{ opacity: 0, y: -4 }}
                                        transition={{
                                          duration: 0.16,
                                          ease: "easeOut",
                                        }}
                                      >
                                        <div className="cw-tool-config-head">
                                          <span className="cw-label">
                                            代码沙箱配置
                                          </span>
                                          <span className="cw-help">
                                            指定 AgentKit 代码沙箱。
                                          </span>
                                        </div>
                                        <RuntimeEnvFields
                                          env={
                                            BUILTIN_TOOLS.find(
                                              (item) => item.id === "run_code",
                                            )?.env ?? []
                                          }
                                          values={
                                            draft.deployment?.envValues ?? {}
                                          }
                                          onChange={patchDeploymentEnv}
                                        />
                                      </motion.div>
                                    )}
                                  </AnimatePresence>
                                </div>
                                <div className="cw-field cw-mcp-field">
                                  <label className="cw-label">MCP 工具</label>
                                  <McpToolEditor
                                    tools={mcpTools}
                                    onChange={(next) =>
                                      patch({ mcpTools: next })
                                    }
                                  />
                                </div>
                              </div>
                            </Section>

                            <Section meta={metaOf("skills")}>
                              <div className="cw-form cw-capabilities-form">
                                <div className="cw-field cw-skill-field">
                                  <label className="cw-label">技能</label>
                                  <SkillsSourceTabs
                                    selected={selectedSkills}
                                    onChange={(next) =>
                                      patch({ selectedSkills: next })
                                    }
                                    cloudProvider={cloudProvider}
                                  />
                                </div>
                              </div>
                            </Section>

                            <Section meta={metaOf("knowledge")}>
                              <div className="cw-form cw-toggle-stack">
                                <Toggle
                                  checked={node.knowledgebase}
                                  onChange={(v) => patch({ knowledgebase: v })}
                                  title="知识库"
                                  desc="启用外部知识检索（RAG），让 Agent 基于你的资料作答。"
                                  icon={Database}
                                />
                                {node.knowledgebase && (
                                  <div className="cw-field cw-subfield">
                                    <label
                                      className="cw-label"
                                      htmlFor="cw-knowledgebase-backend"
                                    >
                                      知识库后端
                                    </label>
                                    <BackendSelect
                                      id="cw-knowledgebase-backend"
                                      options={KB_BACKENDS}
                                      value={node.knowledgebaseBackend}
                                      onChange={(id) =>
                                        patch({
                                          knowledgebaseBackend: id,
                                          knowledgebaseIndex:
                                            id === "viking" ||
                                            id === "openviking"
                                              ? node.knowledgebaseIndex
                                              : "",
                                        })
                                      }
                                    />
                                    {(node.knowledgebaseBackend ??
                                      DEFAULT_KB_BACKEND) === "viking" && (
                                      <div className="cw-field cw-subfield">
                                        <label
                                          className="cw-label"
                                          htmlFor="cw-viking-knowledgebase"
                                        >
                                          VikingDB 知识库
                                        </label>
                                        <VikingKnowledgebaseSelect
                                          value={node.knowledgebaseIndex ?? ""}
                                          onChange={(knowledgebase) => {
                                            patch({
                                              knowledgebaseIndex:
                                                knowledgebase.id,
                                            });
                                            if (knowledgebase.projectName) {
                                              patchDeploymentEnv(
                                                "DATABASE_VIKING_PROJECT",
                                                knowledgebase.projectName,
                                              );
                                            }
                                            if (knowledgebase.region) {
                                              patchDeploymentEnv(
                                                "DATABASE_VIKING_REGION",
                                                knowledgebase.region,
                                              );
                                            }
                                            if (knowledgebase.sourceKind) {
                                              patchDeploymentEnv(
                                                "DATABASE_VIKING_COLLECTION_KIND",
                                                knowledgebase.sourceKind,
                                              );
                                            }
                                            patchDeploymentEnv(
                                              "DATABASE_VIKING_RESOURCE_ID",
                                              knowledgebase.resourceId ?? "",
                                            );
                                          }}
                                        />
                                      </div>
                                    )}
                                    <RuntimeEnvFields
                                      env={
                                        KB_BACKENDS.find(
                                          (item) =>
                                            item.id ===
                                            (node.knowledgebaseBackend ??
                                              DEFAULT_KB_BACKEND),
                                        )?.env ?? []
                                      }
                                      values={draft.deployment?.envValues ?? {}}
                                      onChange={patchDeploymentEnv}
                                      renderAfterField={
                                        (node.knowledgebaseBackend ??
                                          DEFAULT_KB_BACKEND) === "openviking"
                                          ? (item) =>
                                              item.key ===
                                              "DATABASE_OPENVIKING_USER_ID" ? (
                                                <OpenVikingKnowledgeIndexField
                                                  value={
                                                    node.knowledgebaseIndex ??
                                                    ""
                                                  }
                                                  onChange={(
                                                    knowledgebaseIndex,
                                                  ) =>
                                                    patch({
                                                      knowledgebaseIndex,
                                                    })
                                                  }
                                                />
                                              ) : null
                                          : undefined
                                      }
                                    />
                                  </div>
                                )}
                              </div>
                            </Section>

                            {isRootAgent && (
                              <Section meta={metaOf("memory")}>
                                <div className="cw-form cw-toggle-stack">
                                  <div className="cw-capability-memory-group">
                                    <Toggle
                                      checked={node.memory.shortTerm}
                                      onChange={(v) =>
                                        patch({
                                          memory: {
                                            ...node.memory,
                                            shortTerm: v,
                                          },
                                        })
                                      }
                                      title="短期记忆"
                                      desc="存储单会话上下文"
                                      showDescription
                                      icon={Layers}
                                    />
                                    {node.memory.shortTerm && (
                                      <div className="cw-field cw-subfield">
                                        <label
                                          className="cw-label"
                                          htmlFor="cw-short-term-backend"
                                        >
                                          短期记忆后端
                                        </label>
                                        <BackendSelect
                                          id="cw-short-term-backend"
                                          options={STM_BACKENDS}
                                          value={node.shortTermBackend}
                                          onChange={(id) =>
                                            patch({ shortTermBackend: id })
                                          }
                                        />
                                        <RuntimeEnvFields
                                          env={
                                            STM_BACKENDS.find(
                                              (item) =>
                                                item.id ===
                                                (node.shortTermBackend ??
                                                  "local"),
                                            )?.env ?? []
                                          }
                                          values={
                                            draft.deployment?.envValues ?? {}
                                          }
                                          onChange={patchDeploymentEnv}
                                        />
                                      </div>
                                    )}
                                  </div>
                                  <div className="cw-capability-memory-group">
                                    <Toggle
                                      checked={node.memory.longTerm}
                                      onChange={(v) =>
                                        patch({
                                          memory: {
                                            ...node.memory,
                                            longTerm: v,
                                          },
                                        })
                                      }
                                      title="长期记忆"
                                      desc="存储跨会话上下文，通常使用向量化检索"
                                      showDescription
                                      icon={Database}
                                    />
                                    {node.memory.longTerm && (
                                      <div className="cw-field cw-subfield">
                                        <label
                                          className="cw-label"
                                          htmlFor="cw-long-term-backend"
                                        >
                                          长期记忆后端
                                        </label>
                                        <BackendSelect
                                          id="cw-long-term-backend"
                                          options={LTM_BACKENDS}
                                          value={node.longTermBackend}
                                          onChange={(id) =>
                                            patch({
                                              longTermBackend: id,
                                              longTermMemoryIndex:
                                                id === "viking"
                                                  ? node.longTermMemoryIndex
                                                  : "",
                                            })
                                          }
                                        />
                                        {(node.longTermBackend ?? "local") ===
                                          "viking" && (
                                          <div className="cw-field cw-subfield">
                                            <label className="cw-label">
                                              VikingDB 记忆库
                                            </label>
                                            <VikingMemorySelect
                                              value={
                                                node.longTermMemoryIndex ?? ""
                                              }
                                              onChange={(memory) => {
                                                patch({
                                                  longTermMemoryIndex: memory.id,
                                                });
                                                patchDeploymentEnv(
                                                  "DATABASE_VIKINGMEM_PROJECT",
                                                  memory.projectName,
                                                );
                                                patchDeploymentEnv(
                                                  "DATABASE_VIKING_REGION",
                                                  memory.region,
                                                );
                                                patchDeploymentEnv(
                                                  "DATABASE_VIKINGMEM_MEMORY_TYPE",
                                                  (memory.memoryTypes ?? []).join(
                                                    ",",
                                                  ),
                                                );
                                              }}
                                            />
                                          </div>
                                        )}
                                        <RuntimeEnvFields
                                          env={
                                            LTM_BACKENDS.find(
                                              (item) =>
                                                item.id ===
                                                (node.longTermBackend ??
                                                  "local"),
                                            )?.env ?? []
                                          }
                                          values={
                                            draft.deployment?.envValues ?? {}
                                          }
                                          onChange={patchDeploymentEnv}
                                        />
                                        <Toggle
                                          checked={!!node.autoSaveSession}
                                          onChange={(v) =>
                                            patch({ autoSaveSession: v })
                                          }
                                          title="自动保存会话到长期记忆"
                                          desc="会话结束时自动把内容写入长期记忆，无需手动调用。"
                                          icon={Database}
                                        />
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </Section>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                    {/* cw-lower */}
                  </div>
                  {/* cw-detail-inner */}
                </div>
                {/* cw-detail-scroll */}
              </motion.div>
                )}
              </AnimatePresence>
              {/* cw-detail */}
            </div>
          </motion.div>
        )}

        {workspaceMode === "validate" && (
          <motion.div
            key="validate-workspace"
            className={`cw-validation-workspace cw-workspace-view is-${debugWorkspaceView(debugVariants)}`}
            {...workspaceViewMotion}
            style={
              {
                "--cw-validation-content-width": `${Math.max(
                  1,
                  debugVariants.length,
                ) * 471}px`,
              } as CSSProperties
            }
          >
            <motion.div
              className="cw-validation-canvas"
              aria-label="Agent 画布预览"
              layout={reduceMotion ? false : "position"}
              transition={{
                layout: {
                  duration: DEBUG_VIEW_ENTER_SECONDS,
                  ease: DEBUG_MOTION_EASE,
                },
              }}
            >
              <motion.div
                key={`validation-canvas-${debugVariants.length}`}
                className="cw-validation-canvas-content"
                initial={reduceMotion ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{
                  duration: reduceMotion ? 0 : DEBUG_COLUMN_ENTER_SECONDS,
                  delay: reduceMotion ? 0 : DEBUG_VIEW_EXIT_SECONDS / 2,
                  ease: DEBUG_MOTION_EASE,
                }}
              >
                <AgentBuildCanvas
                  draft={draft}
                  direction="vertical"
                  selectedPath={safePath}
                  onSelect={setSelectedPath}
                  onAdd={() => {}}
                  onInsert={() => {}}
                  onDelete={() => {}}
                  readOnly
                  interactivePreview
                />
              </motion.div>
            </motion.div>
            <motion.div
              className="cw-validation-content"
              layout={reduceMotion ? false : "position"}
              transition={{
                layout: {
                  duration: DEBUG_VIEW_ENTER_SECONDS,
                  ease: DEBUG_MOTION_EASE,
                },
              }}
            >
              <DebugComparisonWorkspace
                enabled={debugEnabled}
                disabledReason={debugDisabledReason}
                variants={debugVariants}
                draftSnapshot={currentDebugSnapshot}
                siteLogoUrl={siteLogoUrl}
                input={debugInput}
                onInput={setDebugInput}
                onSend={sendDebugMessage}
                onStartVariant={startDebugVariant}
                onRemoveVariant={removeDebugVariant}
                onCompleteConfig={completeDebugVariantConfig}
                onCancelConfig={(id) =>
                  setDebugVariants((current) =>
                    current.map((variant) => ({
                      ...variant,
                      configOpen:
                        variant.id === id ? false : variant.configOpen,
                    })),
                  )
                }
                onOpenSettings={(id) =>
                  setDebugVariants((current) =>
                    current.map((variant) => ({
                      ...variant,
                      configOpen: variant.id === id,
                    })),
                  )
                }
                onConfigChange={updateDebugVariantConfig}
                onOpenTrace={openDebugTrace}
              />
            </motion.div>
          </motion.div>
        )}

        {workspaceMode === "publish" && (
          <motion.div
            key="publish-workspace"
            className="cw-preview-body cw-workspace-view"
            {...workspaceViewMotion}
          >
            {project ? (
              <ProjectPreview
                embedded
                deploymentTitle="环境与部署"
                deploymentEnvironmentPane={
                  <section className="pp-config-section pp-cloud-environment-section">
                    <div className="pp-config-label">运行环境</div>
                    <CloudEnvironmentConfigurator
                      cloudProvider={cloudProvider}
                      value={draft.cloudEnvironment ?? { cliTools: [] }}
                      onChange={updateCloudEnvironment}
                      editorOpen={cloudEnvironmentEditorOpen}
                      onEditorOpenChange={(open) => {
                        setCloudEnvironmentEditorOpen(open);
                        if (!open) void openPublishPreview();
                      }}
                      disabled={building}
                    />
                    <CloudEnvironmentAdvancedTrigger
                      customized={
                        draft.cloudEnvironment?.dockerfile !== undefined
                      }
                      disabled={building}
                      onClick={() => setCloudEnvironmentEditorOpen(true)}
                    />
                  </section>
                }
                cloudProvider={cloudProvider}
                project={project}
                agentDraft={draft}
                agentName={draft.name || "未命名 Agent"}
                agentCount={countDraftAgents(draft)}
                releaseConfiguration={
                  selectedDebugVariant
                    ? {
                        modelName:
                          selectedDebugVariant.modelName ||
                          draft.modelName ||
                          "默认模型",
                        description: selectedDebugVariant.description,
                        instruction: selectedDebugVariant.instruction,
                        optimizations: [
                          `优化场景：${harnessSidecarProfileLabel(harnessOptimizationProfile)}`,
                          ...harnessOptimizations.map(harnessSidecarOptionLabel),
                        ],
                      }
                    : undefined
                }
                onChange={setProject}
                onDeploy={handleDeploy}
                onAgentAdded={onAgentAdded}
                onDeploymentTaskChange={onDeploymentTaskChange}
                deployDisabled={building || Boolean(buildErr)}
                deploymentRuntimeId={deploymentTarget?.runtimeId}
                deploymentRuntimeName={deploymentRuntimeName}
                deploymentRuntimeNameCustomized={
                  !!deploymentTarget || !!draft.deployment?.runtimeNameCustomized
                }
                onDeploymentRuntimeNameChange={(runtimeName) =>
                  setDraft((current) => ({
                    ...current,
                    deployment: {
                      ...(current.deployment ?? { feishuEnabled: false }),
                      runtimeName,
                      runtimeNameCustomized: true,
                    },
                  }))
                }
                onDeploymentStarted={onDeploymentStarted}
                onDeploymentComplete={onDeploymentComplete}
                feishuEnabled={!!draft.deployment?.feishuEnabled}
                onFeishuEnabledChange={(feishuEnabled) => {
                  const nextDraft: AgentDraft = {
                    ...draft,
                    deployment: {
                      ...(draft.deployment ?? { feishuEnabled: false }),
                      feishuEnabled,
                    },
                  };
                  setDraft(nextDraft);
                }}
                deploymentEnv={deploymentEnv.specs}
                requiredSecretEnv={customModelCredentials}
                requiredSecretEnvValues={customModelSecretValues}
                onRequiredSecretEnvChange={(key, value) =>
                  setCustomModelSecretValues((current) => ({
                    ...current,
                    [key]: value,
                  }))
                }
                deploymentEnvValues={{
                  ...providerDraft.deployment?.envValues,
                  ...customModelSecretValues,
                  ...deploymentEnv.fixedValues,
                }}
                onDeploymentEnvChange={patchDeploymentEnv}
                network={draft.deployment?.network}
                onNetworkChange={(network) =>
                  setDraft((current) => ({
                    ...current,
                    deployment: {
                      ...(current.deployment ?? { feishuEnabled: false }),
                      network,
                    },
                  }))
                }
                deployRegion={deployRegion}
                onDeployRegionChange={setDeployRegion}
                deploymentTelemetry={{
                  source: "scratch",
                  createMode,
                  aiAssisted: usedAiGeneration,
                }}
              />
            ) : (
              <div className="cw-publish-loading" role="status">
                <Loader2 className="cw-i cw-spin" />
                <strong>正在生成发布配置</strong>
                <span>校验 Agent 结构并准备部署快照…</span>
              </div>
            )}
          </motion.div>
        )}
        </AnimatePresence>
      </main>
      {debugTraceTarget && (
        <TraceDrawer
          testRunId={debugTraceTarget.runId}
          sessionId={debugTraceTarget.sessionId}
          title={`调用链路 · ${debugTraceTarget.variantName}`}
          onClose={() => setDebugTraceTarget(null)}
        />
      )}
      {debugLeaveConfirmOpen && (
        <StudioConfirmDialog
          variant="warning"
          title="离开调试？"
          description="离开调试页面后，当前环境将被清理。您可以通过重新启动环境进行新的测试。"
          confirmLabel={debugLeaveCleaning ? "清理中..." : "确定离开"}
          closeLabel="关闭离开调试确认"
          busy={debugLeaveCleaning}
          onCancel={cancelDebugLeaveConfirm}
          onConfirm={() => void acceptDebugLeaveConfirm()}
        />
      )}
      {aiErrorDialog && (
        <div className="confirm-scrim" onClick={() => setAiErrorDialog(null)}>
          <div
            className="confirm-box cw-ai-error-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="ai-generate-error-title"
            aria-describedby="ai-generate-error-message"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="confirm-title" id="ai-generate-error-title">
              智能生成失败
            </div>
            <div className="cw-ai-error-message" id="ai-generate-error-message">
              {aiErrorDialog}
            </div>
            <div className="confirm-actions">
              <button
                type="button"
                className="confirm-btn cw-ai-error-close"
                onClick={() => setAiErrorDialog(null)}
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
