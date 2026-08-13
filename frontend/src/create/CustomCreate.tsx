import {
  type CSSProperties,
  type ComponentType,
  Fragment,
  lazy,
  type ReactNode,
  Suspense,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { AnimatePresence, motion } from "motion/react";
import { Checkbox } from "@openai/apps-sdk-ui/components/Checkbox";
import { RadioGroup } from "@openai/apps-sdk-ui/components/RadioGroup";
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
  Eye,
  EyeOff,
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
  type McpTool,
  type SelectedSkill,
  emptyDraft,
} from "./types";
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
import { draftToYaml } from "./configYaml";
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
import type { AgentProject } from "./project";
import { AgentBuildCanvas } from "./AgentBuildCanvas";
import type { SkillSource } from "./skills/types";
import { SkillHubPicker } from "./SkillHubPicker";
import { LocalPicker } from "./LocalPicker";
import { SkillSpacePicker } from "./SkillSpacePicker";
import {
  listA2aSpaces,
  type A2aSpaceRef,
} from "./a2aSpaces";
import {
  listVikingKnowledgebases,
  type VikingKnowledgebaseRef,
} from "./vikingKnowledgebases";
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
import type { A2uiAction, A2uiComponent } from "../a2ui/types";
import {
  createGeneratedAgentTestRun,
  createGeneratedAgentTestSession,
  deleteGeneratedAgentTestRun,
  deployAgentkitProject,
  generateAgentDraftFromRequirement,
  generateAgentProject,
  runGeneratedAgentTestSSE,
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
  plannerModelName,
  type CloudProvider,
} from "../adk/cloudProvider";
import { applyEvent, emptyAcc, type Block } from "../blocks";
import { customModelCredentialRequirements } from "./customModelCredentials";
import { validateModelConnection } from "./comparison/modelCredentials";
import {
  previewDebugChangeSummary,
  removeDebugChange,
  summarizeDebugChanges,
  switchPrimaryDebugChange,
  updateDebugVariantConfiguration as preserveDebugVariantEvidence,
} from "./comparison/debugVariantState";
import {
  buildCandidateDraft,
  applyCandidateAtomically,
  effectiveComparisonOverrides,
  fingerprintDraft,
  firstConfigurableAgent,
  listConfigurableAgents,
  type AgentComparisonOverride,
  type ComparisonDimension,
} from "./comparison/draftComparison";
import {
  persistComparisonRecord,
  readComparisonRecords,
  type ComparisonHistoryRecord,
} from "./comparison/comparisonHistory";
import {
  ComparisonTraceDrawer,
  type ComparisonTraceTarget,
} from "./comparison/ComparisonTraceDrawer";
import { ComparisonDrawer } from "./comparison/ComparisonDrawer";
import {
  beginComparisonSession,
  comparisonSessionStatus,
  completeComparisonSession,
  createComparisonSessionState,
  failComparisonSession,
  markComparisonConfigurationChanged,
  resetComparisonSessionState,
  type ComparisonSessionState,
} from "./comparison/comparisonSessionState";
import {
  comparisonSessionViewModel,
} from "./comparison/comparisonSessionViewModel";
import { ComparisonSessionActionSlot } from "./comparison/ComparisonSessionControls";
import {
  debugRuntimeFailureMessage,
  stageComparisonRuntimes,
} from "./comparison/comparisonSessionRuntime";
import "./CustomCreate.css";

const MarkdownPromptEditor = lazy(() => import("./MarkdownPromptEditor"));

const DEBUG_TEST_RUN_STORAGE_KEY = "veadk.generatedAgentTestRuns";
const GENERATED_AGENT_REQUIREMENT_MIN_LENGTH = 4;

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

/** Trigger a browser download of a text file. */
function downloadText(filename: string, text: string, mime = "text/plain") {
  const url = URL.createObjectURL(
    new Blob([text], { type: `${mime};charset=utf-8` }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
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

function A2aSelectChevronIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="m7 9 5 5 5-5" />
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
  options,
  value,
  onChange,
}: {
  options: BackendOption[];
  value: string | undefined;
  onChange: (id: string) => void;
}) {
  return (
    <div className="cw-segmented">
      {options.map((o) => {
        const on = (value ?? options[0]?.id) === o.id;
        return (
          <button
            key={o.id}
            type="button"
            className={`cw-seg ${on ? "is-on" : ""}`}
            onClick={() => onChange(o.id)}
            aria-pressed={on}
          >
            <span className="cw-seg-title">{o.label}</span>
          </button>
        );
      })}
    </div>
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
  if (env.length === 0) {
    return <p className="cw-env-empty">此后端无需额外运行参数。</p>;
  }
  return (
    <div className="cw-env-fields">
      {env.map((item) => {
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
                <textarea
                  id={controlId}
                  className="cw-input cw-env-textarea"
                  value={value}
                  placeholder={item.placeholder || "请输入参数值"}
                  autoComplete="off"
                  spellCheck={false}
                  aria-invalid={!!jsonError}
                  onChange={(event) => onChange(item.key, event.currentTarget.value)}
                />
              ) : (
                <input
                  id={controlId}
                  className="cw-input"
                  type={isSensitiveEnv(item.key) ? "password" : "text"}
                  value={value}
                  placeholder={item.placeholder || "请输入参数值"}
                  autoComplete="off"
                  aria-invalid={!!jsonError}
                  onChange={(event) => onChange(item.key, event.currentTarget.value)}
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
      <input
        id={controlId}
        className="cw-input"
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
  const [open, setOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const pickerRef = useRef<HTMLDivElement | null>(null);

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
  const filteredSpaces = useMemo(
    () =>
      spaces.filter((space) =>
        localPickerMatches(searchQuery, [
          a2aSpaceDisplayName(space),
          space.id,
          space.projectName,
        ]),
      ),
    [searchQuery, spaces],
  );
  const showUnknownSpace = Boolean(
    value &&
      !selectedKnown &&
      localPickerMatches(searchQuery, ["已选择的智能体中心", value]),
  );

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (
        target instanceof Node &&
        pickerRef.current &&
        !pickerRef.current.contains(target)
      ) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const selectSpace = (spaceId: string) => {
    onChange(spaceId);
    setOpen(false);
  };

  return (
    <div className={`cw-a2a-space-picker${open ? " is-open" : ""}`} ref={pickerRef}>
      <div className="cw-a2a-space-row">
        <div className="cw-a2a-space-select-wrap">
          <button
            type="button"
            className={`cw-a2a-space-trigger ${invalid ? "is-error" : ""}`}
            disabled={disabled}
            aria-haspopup="listbox"
            aria-expanded={open}
            aria-label="选择 AgentKit 智能体中心"
            onClick={() => {
              setSearchQuery("");
              setOpen((current) => !current);
            }}
          >
            <span className={!value ? "is-placeholder" : undefined}>
              {selectedLabel}
            </span>
            <A2aSelectChevronIcon className="cw-a2a-space-trigger-icon" />
          </button>
          {open && (
            <div
              className="cw-a2a-space-menu"
            >
              <div className="cw-picker-search">
                <input
                  className="cw-picker-search-input"
                  type="search"
                  value={searchQuery}
                  autoFocus
                  autoComplete="off"
                  aria-label="搜索 AgentKit 智能体中心"
                  placeholder="搜索名称或 ID"
                  onChange={(event) => setSearchQuery(event.currentTarget.value)}
                />
              </div>
              <div
                className="cw-picker-options"
                role="listbox"
                aria-label="AgentKit 智能体中心"
              >
                {showUnknownSpace && (
                  <button
                    type="button"
                    role="option"
                    aria-selected
                    className="cw-a2a-space-option is-selected"
                    onClick={() => selectSpace(value)}
                  >
                    已选择的智能体中心
                  </button>
                )}
                {filteredSpaces.map((space) => {
                  const optionLabel = a2aSpaceDisplayName(space);
                  const selected = space.id === value;
                  return (
                    <button
                      key={space.id}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      className={`cw-a2a-space-option ${
                        selected ? "is-selected" : ""
                      }`}
                      title={`${optionLabel} (${space.id})`}
                      onClick={() => selectSpace(space.id)}
                    >
                      {optionLabel}
                    </button>
                  );
                })}
                {!showUnknownSpace && filteredSpaces.length === 0 && (
                  <div className="cw-picker-empty">未找到匹配的智能体中心</div>
                )}
              </div>
            </div>
          )}
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
        <div className="cw-banner cw-a2a-space-error">
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
  const [open, setOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const pickerRef = useRef<HTMLDivElement | null>(null);

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

  const selectedKnown =
    !value || items.some((item) => item.id === value.trim());
  const selectedItem = items.find((item) => item.id === value.trim());
  const selectedLabel = selectedItem
    ? vikingKnowledgebaseDisplayName(selectedItem)
    : value && !selectedKnown
      ? value
      : "请选择 VikingDB 知识库";
  const disabled = loading && items.length === 0;
  const filteredItems = useMemo(
    () =>
      items.filter((item) =>
        localPickerMatches(searchQuery, [
          vikingKnowledgebaseDisplayName(item),
          item.id,
          item.description,
          item.projectName,
          item.resourceId,
          item.agentkitKnowledgeId,
          item.providerKnowledgeId,
          item.sourceLabel,
        ]),
      ),
    [items, searchQuery],
  );
  const showUnknownItem = Boolean(
    value && !selectedKnown && localPickerMatches(searchQuery, [value]),
  );

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (
        target instanceof Node &&
        pickerRef.current &&
        !pickerRef.current.contains(target)
      ) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const selectItem = (item: VikingKnowledgebaseRef) => {
    onChange(item);
    setOpen(false);
  };

  if (loading && items.length === 0) {
    return (
      <span className="cw-viking-kb-inline-status" role="status">
        <Loader2 className="cw-i cw-i-sm cw-spin" />
        正在加载…
      </span>
    );
  }

  return (
    <div
      className={`cw-a2a-space-picker cw-viking-kb-picker${open ? " is-open" : ""}`}
      ref={pickerRef}
    >
      <div className="cw-a2a-space-row">
        <div className="cw-a2a-space-select-wrap">
          <button
            type="button"
            className="cw-a2a-space-trigger"
            disabled={disabled}
            aria-haspopup="listbox"
            aria-expanded={open}
            aria-label="选择 VikingDB 知识库"
            onClick={() => {
              setSearchQuery("");
              setOpen((current) => !current);
            }}
          >
            <span className={!value ? "is-placeholder" : undefined}>
              {selectedLabel}
            </span>
            <A2aSelectChevronIcon className="cw-a2a-space-trigger-icon" />
          </button>
          {open && (
            <div
              className="cw-a2a-space-menu cw-viking-kb-menu"
            >
              <div className="cw-picker-search">
                <input
                  className="cw-picker-search-input"
                  type="search"
                  value={searchQuery}
                  autoFocus
                  autoComplete="off"
                  aria-label="搜索 VikingDB 知识库"
                  placeholder="搜索名称或 ID"
                  onChange={(event) => setSearchQuery(event.currentTarget.value)}
                />
              </div>
              <div
                className="cw-picker-options"
                role="listbox"
                aria-label="VikingDB 知识库"
              >
                {showUnknownItem && (
                  <button
                    type="button"
                    role="option"
                    aria-selected
                    className="cw-a2a-space-option is-selected"
                    onClick={() =>
                      selectItem({
                        id: value,
                        name: value,
                        description: "",
                        projectName: "",
                        region: "",
                        sourceKind: "knowledge",
                        sourceLabel: "Knowledge Engine",
                        resourceId: "",
                      })
                    }
                  >
                    {value}
                  </button>
                )}
                {filteredItems.map((item) => {
                  const optionLabel = vikingKnowledgebaseDisplayName(item);
                  const selected = item.id === value;
                  const optionIds = [
                    item.id,
                    item.resourceId,
                    item.agentkitKnowledgeId,
                    item.providerKnowledgeId,
                  ]
                    .filter(Boolean)
                    .join(" / ");
                  return (
                    <button
                      key={item.id}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      className={`cw-a2a-space-option ${
                        selected ? "is-selected" : ""
                      }`}
                      title={optionIds ? `${optionLabel} (${optionIds})` : optionLabel}
                      onClick={() => selectItem(item)}
                    >
                      {optionLabel}
                    </button>
                  );
                })}
                {!showUnknownItem && filteredItems.length === 0 && (
                  <div className="cw-picker-empty">未找到匹配的知识库</div>
                )}
              </div>
            </div>
          )}
        </div>
        <button
          type="button"
          className="cw-icon-btn cw-a2a-space-refresh cw-viking-kb-refresh"
          title="刷新知识库列表"
          aria-label="刷新知识库列表"
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
        <div className="cw-banner cw-a2a-space-error">
          <Info className="cw-i" />
          <span>{error}</span>
        </div>
      ) : items.length === 0 ? (
        <span className="cw-help">此账号下暂无 VikingDB 知识库。</span>
      ) : (
        <span className="cw-help">
          已加载 {items.length} 个知识库，选择的知识库会用于当前 Agent。
        </span>
      )}
    </div>
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
                  <div className="cw-mcp-transport">
                    <button
                      type="button"
                      className={`cw-seg cw-seg-sm ${
                        t.transport === "http" ? "is-on" : ""
                      }`}
                      onClick={() => update(i, { transport: "http" })}
                      aria-pressed={t.transport === "http"}
                    >
                      <span className="cw-seg-title">HTTP</span>
                    </button>
                    <button
                      type="button"
                      className={`cw-seg cw-seg-sm ${
                        t.transport === "stdio" ? "is-on" : ""
                      }`}
                      onClick={() => update(i, { transport: "stdio" })}
                      aria-pressed={t.transport === "stdio"}
                    >
                      <span className="cw-seg-title">stdio</span>
                    </button>
                  </div>
                  <button
                    type="button"
                    className="cw-icon-btn cw-icon-danger"
                    onClick={() => remove(i)}
                    aria-label="移除 MCP 工具"
                  >
                    <Trash2 className="cw-i cw-i-sm" />
                  </button>
                </div>

                <input
                  className="cw-input"
                  value={t.name}
                  placeholder="名称（用于命名，可留空）"
                  onChange={(e) => update(i, { name: e.target.value })}
                />

                {t.transport === "http" ? (
                  <>
                    <input
                      className="cw-input"
                      value={t.url ?? ""}
                      placeholder="MCP 服务地址（StreamableHTTP）"
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
                    <input
                      className="cw-input"
                      value={mcpAuthTokenInputValue(t)}
                      placeholder="Bearer Token（可选）"
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
                    <input
                      className="cw-input"
                      value={t.command ?? ""}
                      placeholder="启动命令，例如 npx"
                      onChange={(e) => update(i, { command: e.target.value })}
                    />
                    <input
                      className="cw-input"
                      value={(t.args ?? []).join(" ")}
                      placeholder="参数（用空格分隔），例如 -y @playwright/mcp@latest"
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

      {tools.length === 0 && (
        <p className="cw-empty-line">
          暂无 MCP 工具，点击「添加 MCP 工具」连接外部 MCP 服务。
        </p>
      )}
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
  const pickerId = useId();
  const dialogTitleId = `${pickerId}-title`;
  const tabPanelId = `${pickerId}-panel`;
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
              aria-labelledby={dialogTitleId}
              initial={{ opacity: 0, y: 10, scale: 0.985 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 6, scale: 0.99 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
            >
              <div className="cw-skill-dialog-head">
                <h3 id={dialogTitleId}>添加 Skill</h3>
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
                      id={`${pickerId}-tab-${id}`}
                      aria-controls={tabPanelId}
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
                  id={tabPanelId}
                  className="cw-skill-tabbody"
                  role="tabpanel"
                  aria-labelledby={`${pickerId}-tab-${active}`}
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
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  title: string;
  desc: string;
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

const nodePathKey = (path: NodePath) =>
  path.length === 0 ? "root" : path.join(".");

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
  const visit = (node: AgentDraft) => {
    for (const toolId of node.builtinTools ?? []) {
      const tool = BUILTIN_TOOLS.find((item) => item.id === toolId);
      if (tool) selections.push({ env: providerRuntimeEnv(tool.env, cloudProvider) });
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
        env:
          providerRuntimeEnv(
            STM_BACKENDS.find(
              (item) => item.id === (node.shortTermBackend ?? "local"),
            )?.env ?? [],
            cloudProvider,
          ),
      });
    }
    if (node.memory.longTerm) {
      selections.push({
        env:
          providerRuntimeEnv(
            LTM_BACKENDS.find(
              (item) => item.id === (node.longTermBackend ?? "local"),
            )?.env ?? [],
            cloudProvider,
          ),
      });
    }
    if (node.knowledgebase) {
      selections.push({
        env:
          providerRuntimeEnv(
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

type DebugPhase =
  | "idle"
  | "starting"
  | "ready"
  | "sending"
  | "canceled"
  | "error";

type WorkspaceMode = "build" | "validate" | "publish";
interface DebugMessage {
  role: "user" | "assistant";
  content: string;
  blocks?: Block[];
  error?: string;
}

interface DebugVariantChange {
  id: string;
  modelName: string;
  modelProvider: string;
  modelApiBase: string;
  apiKey: string;
  apiKeyLocked: boolean;
  apiKeyVisible: boolean;
  instruction: string;
  selectedSkills: SelectedSkill[];
  agentKey: string;
  dimension: ComparisonDimension;
}

interface DebugVariant {
  id: string;
  name: string;
  modelName: string;
  modelProvider: string;
  modelApiBase: string;
  apiKey: string;
  apiKeyLocked: boolean;
  apiKeyVisible: boolean;
  instruction: string;
  selectedSkills: SelectedSkill[];
  agentKey: string;
  dimension: ComparisonDimension;
  additionalChanges: DebugVariantChange[];
  verdict:
    | ""
    | "采用候选"
    | "保留基线"
    | "持平"
    | "各有取舍"
    | "证据不足";
  verdictReason: string;
  ttftMs: number | null;
  latencyMs: number | null;
  toolCalls: number | null;
  tokens: number | null;
  inputDiverged: boolean;
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
  const nextSubAgents = draft.subAgents.map((child) =>
    draftForCloudProvider(child, cloudProvider),
  );
  const nextModelName = shouldUseProviderDefaultModel(
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

type DebugActionConfirm =
  | { kind: "new-session"; variantCount: number }
  | { kind: "delete"; variantId: string; variantName: string }
  | { kind: "baseline-failed-apply"; variantId: string };

interface PreparedDebugRuntime {
  runtime: { run: GeneratedAgentTestRun; sessionId: string };
  runtimeSnapshot: string;
  credentialAgentPaths: number[][];
}

class DebugRuntimePreparationError extends Error {
  constructor(
    readonly stage: "run" | "session",
    message: string,
  ) {
    super(message);
    this.name = "DebugRuntimePreparationError";
  }
}

function codegenDraft(draft: AgentDraft): AgentDraft {
  const prepared = prepareMcpAuth(draft).draft;
  return {
    ...prepared,
    deployment: {
      feishuEnabled: !!draft.deployment?.feishuEnabled,
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

function debugRuntimeDraft(draft: AgentDraft): AgentDraft {
  const runtimeEnv = collectDeploymentEnv(draft);
  const values = {
    ...(draft.deployment?.envValues ?? {}),
    ...runtimeEnv.fixedValues,
  };
  return {
    ...codegenDraft(draft),
    deployment: {
      feishuEnabled: !!draft.deployment?.feishuEnabled,
      envValues: Object.fromEntries(
        runtimeEnvVars(runtimeEnv.specs, values).map(({ key, value }) => [
          key,
          value,
        ]),
      ),
    },
  };
}

function debugSnapshotKey(draft: AgentDraft): string {
  return JSON.stringify(debugRuntimeDraft(draft));
}

function debugVariantSnapshot(
  draftSnapshot: string,
  variant: Pick<
    DebugVariant,
    | "modelName"
    | "modelProvider"
    | "modelApiBase"
    | "instruction"
    | "selectedSkills"
    | "agentKey"
    | "dimension"
    | "additionalChanges"
  >,
): string {
  return JSON.stringify({
    draftSnapshot,
    modelName: variant.modelName,
    modelProvider: variant.modelProvider,
    modelApiBase: variant.modelApiBase,
    instruction: variant.instruction,
    selectedSkills: variant.selectedSkills,
    agentKey: variant.agentKey,
    dimension: variant.dimension,
    additionalChanges: variant.additionalChanges.map(debugChangeConfiguration),
  });
}

function debugVariantConfigurationKey(
  draft: AgentDraft,
  variant: DebugVariant,
): string {
  if (variant.id === "baseline") return "[]";
  return JSON.stringify(
    effectiveDebugChanges(draft, variant)
      .map(debugChangeConfiguration)
      .sort((left, right) =>
        `${left.agentKey}:${left.dimension}`.localeCompare(
          `${right.agentKey}:${right.dimension}`,
        ),
      ),
  );
}

function primaryDebugChange(variant: DebugVariant): DebugVariantChange {
  return {
    id: "primary",
    modelName: variant.modelName,
    modelProvider: variant.modelProvider,
    modelApiBase: variant.modelApiBase,
    apiKey: variant.apiKey,
    apiKeyLocked: variant.apiKeyLocked,
    apiKeyVisible: variant.apiKeyVisible,
    instruction: variant.instruction,
    selectedSkills: variant.selectedSkills,
    agentKey: variant.agentKey,
    dimension: variant.dimension,
  };
}

function debugChangesForVariant(variant: DebugVariant): DebugVariantChange[] {
  return [primaryDebugChange(variant), ...variant.additionalChanges];
}

function debugChangeConfiguration(change: DebugVariantChange) {
  return {
    modelName: change.modelName.trim(),
    modelProvider: change.modelProvider.trim(),
    modelApiBase: change.modelApiBase.trim(),
    instruction: change.instruction.trim(),
    selectedSkills: change.selectedSkills,
    agentKey: change.agentKey,
    dimension: change.dimension,
  };
}

function debugVariantConfigurationProblem(
  draft: AgentDraft,
  variant: DebugVariant,
): string {
  if (variant.id === "baseline") return "";
  const seen = new Set<string>();
  for (const change of debugChangesForVariant(variant)) {
    const key = `${change.agentKey}:${change.dimension}`;
    if (seen.has(key)) return "同一 Agent 的同一维度只能配置一次";
    seen.add(key);
    if (change.dimension === "model" && !change.modelName.trim()) {
      return "请填写 Model ID";
    }
    if (change.dimension === "instruction" && !change.instruction.trim()) {
      return "请填写系统提示词";
    }
  }
  if (effectiveDebugChanges(draft, variant).length === 0) {
    return "请至少修改一个配置项";
  }
  return "";
}

function baselineDebugChange(
  draft: AgentDraft,
  baselineApiKeys: Record<string, string>,
  agentKey: string,
  dimension: ComparisonDimension,
): DebugVariantChange | null {
  const agent = listConfigurableAgents(draft).find(
    (item) => item.key === agentKey,
  );
  if (!agent) return null;
  const target = getNode(draft, agent.path);
  return {
    id: `${agentKey}:${dimension}`,
    modelName: target.modelName ?? "",
    modelProvider: target.modelProvider ?? "",
    modelApiBase: target.modelApiBase ?? "",
    apiKey: baselineApiKeys[agentKey] ?? "",
    apiKeyLocked: false,
    apiKeyVisible: false,
    instruction: target.instruction,
    selectedSkills: structuredClone(target.selectedSkills ?? []),
    agentKey,
    dimension,
  };
}

function debugApiKeyForAgent(
  variant: DebugVariant,
  agentKey: string,
  baselineApiKeys: Record<string, string>,
): string {
  if (variant.id === "baseline") return baselineApiKeys[agentKey] ?? "";
  const modelChange = debugChangesForVariant(variant).find(
    (change) =>
      change.agentKey === agentKey && change.dimension === "model",
  );
  return modelChange?.apiKey ?? baselineApiKeys[agentKey] ?? "";
}

const COMPARISON_DIFF_PREVIEW_LIMIT = 3;

interface DebugConfigurationDiffLine {
  label: string;
  baseline: string;
  candidate: string;
  long?: boolean;
}

function debugDimensionLabel(dimension: ComparisonDimension): string {
  return dimension === "model"
    ? "模型"
    : dimension === "instruction"
      ? "系统提示词"
      : "Skills";
}

function debugSkillListLabel(skills: SelectedSkill[]): string {
  return skills.length
    ? skills
        .map(
          (skill) =>
            `${skill.name || skill.folder}${skill.version ? `@${skill.version}` : ""}`,
        )
        .join("、")
    : "无 Skill";
}

function debugCredentialLabel(change: DebugVariantChange): string {
  return change.apiKeyLocked || change.apiKey
    ? "临时凭据已配置"
    : "服务端凭据";
}

function debugChangeDiffLines(
  baseline: DebugVariantChange,
  change: DebugVariantChange,
): DebugConfigurationDiffLine[] {
  if (change.dimension === "model") {
    const lines: DebugConfigurationDiffLine[] = [
      {
        label: "Model ID",
        baseline: baseline.modelName || "Studio 默认 Model ID",
        candidate: change.modelName || "Studio 默认 Model ID",
      },
      {
        label: "Provider",
        baseline: baseline.modelProvider || "Studio 默认 Provider",
        candidate: change.modelProvider || "Studio 默认 Provider",
      },
      {
        label: "API Base",
        baseline: baseline.modelApiBase || "Studio 默认 API Base",
        candidate: change.modelApiBase || "Studio 默认 API Base",
        long: true,
      },
      {
        label: "凭据",
        baseline: debugCredentialLabel(baseline),
        candidate: debugCredentialLabel(change),
      },
    ];
    return lines.filter((line) => line.baseline !== line.candidate);
  }
  if (change.dimension === "instruction") {
    return [
      {
        label: "提示词内容",
        baseline: baseline.instruction || "空提示词",
        candidate: change.instruction || "空提示词",
        long: true,
      },
    ];
  }
  return [
    {
      label: "Skills 列表",
      baseline: debugSkillListLabel(baseline.selectedSkills),
      candidate: debugSkillListLabel(change.selectedSkills),
      long: true,
    },
  ];
}

function debugChangeDiffText(
  draft: AgentDraft,
  change: DebugVariantChange,
): string {
  const agent = listConfigurableAgents(draft).find(
    (item) => item.key === change.agentKey,
  );
  if (!agent) return "Agent 已不在当前 Draft 中";
  const baseline = getNode(draft, agent.path);
  if (change.dimension === "model") {
    const before = [
      baseline.modelName || "Studio 默认 Model ID",
      baseline.modelProvider || "Studio 默认 Provider",
      baseline.modelApiBase || "Studio 默认 API Base",
    ].join(" / ");
    const after = [
      change.modelName || "Studio 默认 Model ID",
      change.modelProvider || "Studio 默认 Provider",
      change.modelApiBase || "Studio 默认 API Base",
    ].join(" / ");
    return `${before} → ${after}`;
  }
  if (change.dimension === "instruction") {
    return `系统提示词 ${baseline.instruction.length} 字 → ${change.instruction.length} 字`;
  }
  return `${debugSkillListLabel(baseline.selectedSkills ?? [])} → ${debugSkillListLabel(change.selectedSkills)}`;
}

function debugVariantHasA2uiAction(
  variant: DebugVariant,
  actionName: string,
  nodeId: string,
): boolean {
  return variant.messages.some((message) =>
    (message.blocks ?? []).some(
      (block) =>
        block.kind === "a2ui" &&
        block.messages.some((a2uiMessage) => {
          const update = (
            a2uiMessage as {
              updateComponents?: { components?: A2uiComponent[] };
            }
          ).updateComponents;
          const components = Array.isArray(update?.components)
            ? update.components
            : [];
          return Boolean(
            components.some((component) => {
              const componentAction = component.action as
                | A2uiAction
                | undefined;
              return (
                component.id === nodeId &&
                (componentAction?.event?.name ?? component.id) === actionName
              );
            }),
          );
        }),
    ),
  );
}

function draftForDebugVariant(
  baseline: AgentDraft,
  variant: DebugVariant,
): AgentDraft {
  if (variant.id === "baseline") return baseline;
  return buildCandidateDraft(baseline, debugOverridesForVariant(variant));
}

function debugOverridesForVariant(
  variant: DebugVariant,
): AgentComparisonOverride[] {
  return debugChangesForVariant(variant).map((change) => ({
      agentKey: change.agentKey,
      dimensions: [change.dimension],
      model:
        change.dimension === "model"
          ? {
              modelName: change.modelName,
              modelProvider: change.modelProvider,
              modelApiBase: change.modelApiBase,
            }
          : undefined,
      instruction:
        change.dimension === "instruction" ? change.instruction : undefined,
      selectedSkills:
        change.dimension === "skills" ? change.selectedSkills : undefined,
    }));
}

function effectiveDebugChanges(
  draft: AgentDraft,
  variant: DebugVariant,
): DebugVariantChange[] {
  if (variant.id === "baseline") return [];
  const effective = new Set(
    effectiveComparisonOverrides(draft, debugOverridesForVariant(variant)).flatMap(
      (override) =>
        override.dimensions.map(
          (dimension) => `${override.agentKey}:${dimension}`,
        ),
    ),
  );
  return debugChangesForVariant(variant).filter((change) =>
    effective.has(`${change.agentKey}:${change.dimension}`),
  );
}

function debugComparisonSessionProblem(
  draft: AgentDraft,
  variants: DebugVariant[],
  baselineApiKeys: Record<string, string>,
): string {
  if (variants.length < 2) return "请至少添加一个对照组";
  if (variants.length > 4) return "测试组最多为 4 个";

  for (const variant of variants) {
    if (variant.configOpen) return `请先保存「${variant.name}」的配置`;
  }
  for (const variant of variants) {
    if (variant.phase === "starting" || variant.phase === "sending") {
      return `请等待「${variant.name}」完成当前操作`;
    }
  }
  for (const variant of variants) {
    const problem = debugVariantConfigurationProblem(draft, variant);
    if (problem) return `请先完成「${variant.name}」的配置：${problem}`;
  }

  const seenConfigurations = new Set<string>();
  for (const variant of variants) {
    const configurationKey = debugVariantConfigurationKey(draft, variant);
    if (seenConfigurations.has(configurationKey)) {
      return `「${variant.name}」的配置与已有测试组相同`;
    }
    seenConfigurations.add(configurationKey);
  }

  for (const variant of variants) {
    let variantDraft: AgentDraft;
    try {
      variantDraft = draftForDebugVariant(draft, variant);
    } catch {
      return `「${variant.name}」的配置已失效，请重新选择 Agent`;
    }
    for (const { path, key } of listConfigurableAgents(variantDraft)) {
      const modelNode = getNode(variantDraft, path);
      const validation = validateModelConnection({
        modelName: modelNode.modelName ?? "",
        modelProvider: modelNode.modelProvider ?? "",
        modelApiBase: modelNode.modelApiBase ?? "",
        apiKey: debugApiKeyForAgent(variant, key, baselineApiKeys),
        studioApiBase: defaultModelApiBase(
          draft.cloudProvider ?? "volcengine",
        ),
      });
      if (!validation.ok) {
        return `请先完成「${variant.name}」的模型连接配置：${validation.reason}`;
      }
    }
  }
  return "";
}

function DebugVariantDifferenceSummary({
  draft,
  baselineApiKeys,
  changes,
  configurableAgents,
  variantName,
}: {
  draft: AgentDraft;
  baselineApiKeys: Record<string, string>;
  changes: DebugVariantChange[];
  configurableAgents: ReturnType<typeof listConfigurableAgents>;
  variantName: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const titleId = useId();
  const contentId = useId();
  const groups = summarizeDebugChanges(
    changes,
    configurableAgents.map((agent) => agent.key),
    "",
    "model",
  );
  const totalCount = changes.length;
  const visible = expanded
    ? { groups, hiddenCount: 0 }
    : previewDebugChangeSummary(groups, COMPARISON_DIFF_PREVIEW_LIMIT);

  return (
    <section className="cw-comparison-diff-summary" aria-labelledby={titleId}>
      <header className="cw-comparison-diff-head">
        <h3 id={titleId}>与基准组的配置差异</h3>
        <span>{totalCount} 项</span>
      </header>
      <div id={contentId} className="cw-comparison-diff-groups">
        {visible.groups.map((group) => {
          const agentName =
            configurableAgents.find((agent) => agent.key === group.agentKey)
              ?.name ?? group.agentKey;
          const groupTotalCount =
            groups.find((item) => item.agentKey === group.agentKey)?.changes
              .length ?? group.changes.length;
          return (
            <section className="cw-comparison-diff-group" key={group.agentKey}>
              <h4>
                <span title={agentName}>{agentName}</span>
                <span>{groupTotalCount} 项变化</span>
              </h4>
              {group.changes.map(({ change }) => {
                const baseline = baselineDebugChange(
                  draft,
                  baselineApiKeys,
                  change.agentKey,
                  change.dimension,
                );
                if (!baseline) return null;
                return (
                  <section
                    className="cw-comparison-diff-item"
                    key={`${change.agentKey}:${change.dimension}`}
                  >
                    <strong>{debugDimensionLabel(change.dimension)}</strong>
                    <dl>
                      {debugChangeDiffLines(baseline, change).map((line) => (
                        <div key={line.label}>
                          <dt>{line.label}</dt>
                          <dd>
                            <span className="cw-comparison-diff-value">
                              <small>基准</small>
                              <span
                                className={
                                  line.long ? "cw-comparison-diff-long" : ""
                                }
                                title={line.baseline}
                                tabIndex={line.long ? 0 : undefined}
                              >
                                {line.baseline}
                              </span>
                            </span>
                            <span
                              className="cw-comparison-diff-arrow"
                              aria-hidden="true"
                            >
                              →
                            </span>
                            <span className="cw-comparison-diff-value">
                              <small>本组</small>
                              <span
                                className={
                                  line.long ? "cw-comparison-diff-long" : ""
                                }
                                title={line.candidate}
                                tabIndex={line.long ? 0 : undefined}
                              >
                                {line.candidate}
                              </span>
                            </span>
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </section>
                );
              })}
            </section>
          );
        })}
      </div>
      {totalCount > COMPARISON_DIFF_PREVIEW_LIMIT ? (
        <button
          type="button"
          className="cw-comparison-diff-toggle"
          aria-label={
            expanded
              ? `收起${variantName}的配置差异，仅显示前 ${COMPARISON_DIFF_PREVIEW_LIMIT} 项`
              : `查看${variantName}全部 ${totalCount} 项配置差异`
          }
          aria-expanded={expanded}
          aria-controls={contentId}
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded
            ? `收起，仅显示前 ${COMPARISON_DIFF_PREVIEW_LIMIT} 项`
            : `查看全部 ${totalCount} 项`}
        </button>
      ) : null}
    </section>
  );
}

type DebugChangeField =
  | "agentKey"
  | "dimension"
  | "modelName"
  | "modelProvider"
  | "modelApiBase"
  | "apiKey"
  | "instruction";

function DebugVariantConfigurationPanel({
  variant,
  variants,
  draft,
  busy,
  onClose,
  onRemoveVariant,
  onCompleteConfig,
  onSelectChange,
  onRemoveChange,
  onConfigChange,
  onSkillsChange,
  onToggleApiKey,
}: {
  variant: DebugVariant;
  variants: DebugVariant[];
  draft: AgentDraft;
  busy: boolean;
  onClose: () => void;
  onRemoveVariant: (id: string) => void;
  onCompleteConfig: (id: string) => void;
  onSelectChange: (
    id: string,
    agentKey: string,
    dimension: ComparisonDimension,
  ) => void;
  onRemoveChange: (
    id: string,
    agentKey: string,
    dimension: ComparisonDimension,
  ) => void;
  onConfigChange: (
    id: string,
    field: DebugChangeField,
    value: string,
  ) => void;
  onSkillsChange: (id: string, skills: SelectedSkill[]) => void;
  onToggleApiKey: (id: string) => void;
}) {
  const configurableAgents = listConfigurableAgents(draft);
  const configurationKey = debugVariantConfigurationKey(draft, variant);
  const variantIndex = variants.findIndex((item) => item.id === variant.id);
  const duplicateConfiguration = variants.findIndex(
    (item) => debugVariantConfigurationKey(draft, item) === configurationKey,
  ) !== variantIndex;
  const configurationProblem = debugVariantConfigurationProblem(draft, variant);
  const disabledReason =
    configurationProblem ||
    (duplicateConfiguration ? "该配置与已有测试组相同" : "");
  const summaryTitleId = useId();
  const effectiveChanges = effectiveDebugChanges(draft, variant);
  const changeSummary = summarizeDebugChanges(
    effectiveChanges,
    configurableAgents.map((agent) => agent.key),
    variant.agentKey,
    variant.dimension,
  );
  const changeCountByAgent = new Map(
    changeSummary.map((group) => [group.agentKey, group.changes.length]),
  );
  const changedDimensions = new Set(
    effectiveChanges.map(
      (change) => `${change.agentKey}:${change.dimension}`,
    ),
  );
  const dimensionLabel = (dimension: ComparisonDimension) =>
    dimension === "model"
      ? "模型"
      : dimension === "instruction"
        ? "系统提示词"
        : "Skills";

  return (
    <ComparisonDrawer
      title={`测试配置 · ${variant.name}`}
      description="选择 Agent 与维度后修改。切换维度会保留当前编辑，临时凭据仅注入调试环境。"
      width="wide"
      busy={busy}
      closeLabel={`关闭${variant.name}测试配置`}
      onClose={onClose}
      footer={
        <div className="cw-comparison-drawer-footer">
          <button
            type="button"
            className="cw-comparison-danger-action"
            disabled={busy}
            onClick={() => onRemoveVariant(variant.id)}
          >
            删除测试组
          </button>
          <span>
            <button
              type="button"
              className="is-primary"
              disabled={busy}
              onClick={() => onCompleteConfig(variant.id)}
            >
              保存配置
            </button>
          </span>
        </div>
      }
    >
      <fieldset
        className="cw-comparison-config-panel"
        aria-label={`${variant.name}测试配置`}
        disabled={busy}
      >
        <aside className="cw-comparison-agent-nav" aria-label="选择 Agent">
          <strong>Agent</strong>
          {configurableAgents.map((agent) => {
            const changeCount = changeCountByAgent.get(agent.key) ?? 0;
            const agentName = agent.name || agent.key;
            return (
              <button
                key={agent.key}
                type="button"
                className={agent.key === variant.agentKey ? "is-active" : ""}
                aria-label={`${agentName}，${changeCount} 项变化`}
                aria-pressed={agent.key === variant.agentKey}
                disabled={busy}
                onClick={() =>
                  onSelectChange(variant.id, agent.key, variant.dimension)
                }
              >
                <span>{agentName}</span>
                <span className="cw-comparison-agent-change-count">
                  · {changeCount}
                </span>
              </button>
            );
          })}
        </aside>

        <div className="cw-comparison-config-main">
        <div
          className="cw-comparison-dimension-tabs"
          role="tablist"
          aria-label="选择对照维度"
        >
          {(["model", "instruction", "skills"] as ComparisonDimension[]).map(
            (dimension) => {
              const changed = changedDimensions.has(
                `${variant.agentKey}:${dimension}`,
              );
              return (
                <button
                  key={dimension}
                  type="button"
                  role="tab"
                  aria-label={`${dimensionLabel(dimension)}${changed ? "，已修改" : ""}`}
                  aria-selected={variant.dimension === dimension}
                  disabled={busy}
                  onClick={() =>
                    onSelectChange(variant.id, variant.agentKey, dimension)
                  }
                >
                  <span>{dimensionLabel(dimension)}</span>
                  {changed && (
                    <span className="cw-comparison-dimension-status">
                      已修改
                    </span>
                  )}
                </button>
              );
            },
          )}
        </div>

        {disabledReason && (
          <p className="cw-comparison-config-problem" role="alert">
            {disabledReason}
          </p>
        )}

        <div className="cw-ab-config">
          {variant.dimension === "model" && (
            <>
              <label>
                <span>Model ID</span>
                <input
                  value={variant.modelName}
                  disabled={busy}
                  onChange={(event) =>
                    onConfigChange(variant.id, "modelName", event.target.value)
                  }
                />
              </label>
              <label>
                <span>Provider</span>
                <input
                  value={variant.modelProvider}
                  placeholder="留空使用 Studio 默认值"
                  disabled={busy}
                  onChange={(event) =>
                    onConfigChange(
                      variant.id,
                      "modelProvider",
                      event.target.value,
                    )
                  }
                />
              </label>
              <label>
                <span>API Base</span>
                <input
                  value={variant.modelApiBase}
                  placeholder="留空使用 Studio 默认值"
                  disabled={busy}
                  onChange={(event) =>
                    onConfigChange(
                      variant.id,
                      "modelApiBase",
                      event.target.value,
                    )
                  }
                />
              </label>
              <label>
                <span>临时 API Key</span>
                {variant.apiKeyLocked ? (
                  <div className="cw-model-secret-configured">
                    <span role="status">已配置临时凭据</span>
                    <button
                      type="button"
                      className="cw-link-btn"
                      disabled={busy}
                      onClick={() => onConfigChange(variant.id, "apiKey", "")}
                    >
                      清除并重新输入
                    </button>
                  </div>
                ) : (
                  <div className="cw-model-secret-input">
                    <input
                      className="cw-input"
                      type={variant.apiKeyVisible ? "text" : "password"}
                      value={variant.apiKey}
                      autoComplete="off"
                      placeholder="可留空；自定义 API Base 时必填"
                      disabled={busy}
                      onChange={(event) =>
                        onConfigChange(variant.id, "apiKey", event.target.value)
                      }
                    />
                    <button
                      type="button"
                      className="cw-model-secret-toggle"
                      aria-label={
                        variant.apiKeyVisible ? "隐藏 API Key" : "显示 API Key"
                      }
                      aria-pressed={variant.apiKeyVisible}
                      disabled={busy}
                      onClick={() => onToggleApiKey(variant.id)}
                    >
                      {variant.apiKeyVisible ? (
                        <EyeOff className="cw-i cw-i-sm" />
                      ) : (
                        <Eye className="cw-i cw-i-sm" />
                      )}
                    </button>
                  </div>
                )}
              </label>
            </>
          )}
          {variant.dimension === "instruction" && (
            <label>
              <span>系统提示词</span>
              <textarea
                rows={12}
                value={variant.instruction}
                disabled={busy}
                onChange={(event) =>
                  onConfigChange(variant.id, "instruction", event.target.value)
                }
              />
            </label>
          )}
          {variant.dimension === "skills" && (
            <div className="cw-comparison-skills">
              <span>本轮 Skills</span>
              <SkillsSourceTabs
                selected={variant.selectedSkills}
                onChange={(next) => onSkillsChange(variant.id, next)}
                cloudProvider={draft.cloudProvider ?? "volcengine"}
              />
              <small>
                可从 SkillHub、SkillSpace 或本地新增；在 SkillSpace 中选择目标版本即可进行版本对照。
              </small>
            </div>
          )}
        </div>

        {changeSummary.length > 0 && (
          <section
            className="cw-comparison-change-summary"
            aria-labelledby={summaryTitleId}
          >
            <h3 id={summaryTitleId}>
              本方案全部变化（{effectiveChanges.length}）
            </h3>
            <div className="cw-comparison-change-groups">
              {changeSummary.map((group) => {
                const agentName =
                  configurableAgents.find(
                    (agent) => agent.key === group.agentKey,
                  )?.name ?? group.agentKey;
                return (
                  <section
                    key={group.agentKey}
                    className="cw-comparison-change-group"
                  >
                    <h4>
                      <span>{agentName}</span>
                      <span>{group.changes.length} 项变化</span>
                    </h4>
                    <ul>
                      {group.changes.map(({ change, active }) => (
                        <li
                          key={`${change.agentKey}:${change.dimension}`}
                          className={active ? "is-active" : ""}
                        >
                          <div className="cw-comparison-change-detail">
                            <strong>{dimensionLabel(change.dimension)}</strong>
                            <span>{debugChangeDiffText(draft, change)}</span>
                          </div>
                          <div className="cw-comparison-change-actions">
                            {active ? (
                              <span
                                className="cw-comparison-change-editing"
                                aria-current="true"
                              >
                                正在编辑
                              </span>
                            ) : (
                              <button
                                type="button"
                                className="cw-link-btn"
                                disabled={busy}
                                onClick={() =>
                                  onSelectChange(
                                    variant.id,
                                    change.agentKey,
                                    change.dimension,
                                  )
                                }
                              >
                                编辑
                              </button>
                            )}
                            <button
                              type="button"
                              className="cw-link-btn"
                              disabled={busy}
                              onClick={() =>
                                onRemoveChange(
                                  variant.id,
                                  change.agentKey,
                                  change.dimension,
                                )
                              }
                            >
                              移除
                            </button>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </section>
                );
              })}
            </div>
          </section>
        )}
        <p className="cw-comparison-locked-note">
          Tools、Knowledge、Memory、拓扑、Handoff 与部署配置在本轮保持锁定。
        </p>
        </div>
      </fieldset>
    </ComparisonDrawer>
  );
}

function DebugComparisonWorkspace({
  enabled,
  disabledReason,
  draft,
  variants,
  draftSnapshot,
  input,
  onInput,
  onSend,
  comparisonSessionState,
  sessionProblem,
  onStartSession,
  onStopVariant,
  onStopAll,
  onDeployVariant,
  onAddVariant,
  onRemoveVariant,
  onToggleConfig,
  onCompleteConfig,
  onSelectChange,
  baselineApiKeys,
  onRemoveChange,
  onConfigChange,
  onSkillsChange,
  onToggleApiKey,
  onVerdictChange,
  canUndo,
  onUndo,
  history,
  onOpenTrace,
  onOpenComparisonTrace,
  onVariantAction,
}: {
  enabled: boolean;
  disabledReason: string;
  draft: AgentDraft;
  variants: DebugVariant[];
  draftSnapshot: string;
  input: string;
  onInput: (v: string) => void;
  onSend: () => void;
  comparisonSessionState: ComparisonSessionState;
  sessionProblem: string;
  onStartSession: () => void;
  onStopVariant: (id: string) => void;
  onStopAll: () => void;
  onDeployVariant: (id: string) => void;
  onAddVariant: () => void;
  onRemoveVariant: (id: string) => void;
  onToggleConfig: (id: string) => void;
  onCompleteConfig: (id: string) => void;
  onSelectChange: (
    id: string,
    agentKey: string,
    dimension: ComparisonDimension,
  ) => void;
  baselineApiKeys: Record<string, string>;
  onRemoveChange: (
    id: string,
    agentKey: string,
    dimension: ComparisonDimension,
  ) => void;
  onConfigChange: (
    id: string,
    field: DebugChangeField,
    value: string,
  ) => void;
  onSkillsChange: (id: string, skills: SelectedSkill[]) => void;
  onToggleApiKey: (id: string) => void;
  onVerdictChange: (
    id: string,
    verdict: DebugVariant["verdict"],
    reason: string,
  ) => void;
  canUndo: boolean;
  onUndo: () => void;
  history: ComparisonHistoryRecord[];
  onOpenTrace: (id: string) => void;
  onOpenComparisonTrace: () => void;
  onVariantAction: (
    id: string,
    action: A2uiAction | undefined,
    node: A2uiComponent,
  ) => void;
}) {
  const configurableAgents = listConfigurableAgents(draft);
  const [narrowVariantId, setNarrowVariantId] = useState("baseline");
  const [safetyExpanded, setSafetyExpanded] = useState(true);
  const [baselineDrawerOpen, setBaselineDrawerOpen] = useState(false);
  const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false);
  useEffect(() => {
    if (!variants.some((variant) => variant.id === narrowVariantId)) {
      setNarrowVariantId(variants[0]?.id ?? "baseline");
    }
  }, [narrowVariantId, variants]);
  const runningVariants = variants.filter((variant) => {
    if (variant.phase !== "ready" || variant.configOpen) return false;
    return (
      variant.runtimeSnapshot === debugVariantSnapshot(draftSnapshot, variant)
    );
  });
  const sending = variants.some((variant) => variant.phase === "sending");
  const sessionPresentation = comparisonSessionViewModel(
    comparisonSessionState,
    {
      problem: sessionProblem || (!enabled ? disabledReason : ""),
      canSendReadySession: runningVariants.length > 0 && !sending,
      readyComposerPlaceholder:
        "输入测试消息，将发送到所有已启动测试组...",
    },
  );
  const canSend = !sessionPresentation.composerDisabled;
  const { sessionReady, sessionStarting } = sessionPresentation;
  const baselineVariant = variants.find((variant) => variant.id === "baseline");
  const comparisonTraceAvailable = Boolean(
    baselineVariant?.messages.some((message) => message.role === "assistant") &&
      variants.some(
        (variant) =>
          variant.id !== "baseline" &&
          variant.messages.some((message) => message.role === "assistant"),
      ),
  );
  const baselineFailed = Boolean(
    baselineVariant?.error ||
      [...(baselineVariant?.messages ?? [])]
        .reverse()
        .find((message) => message.role === "assistant")?.error,
  );
  const editingVariant = variants.find(
    (variant) => variant.id !== "baseline" && variant.configOpen,
  );

  return (
    <section className="cw-ab-workspace" aria-label="多维对照调试工作台">
      <div className="cw-comparison-safety" role="note">
        <div className="cw-comparison-safety-head">
          <strong>真实外部操作风险</strong>
          <span>
            {canUndo ? (
              <button
                type="button"
                className="cw-link-btn"
                disabled={sessionStarting}
                onClick={onUndo}
              >
                撤销刚才采用的候选
              </button>
            ) : null}
            <button
              type="button"
              className="cw-comparison-collapse-trigger"
              aria-expanded={safetyExpanded}
              aria-controls="cw-comparison-safety-content"
              onClick={() => setSafetyExpanded((expanded) => !expanded)}
            >
              {safetyExpanded ? "收起" : "展开"}
            </button>
          </span>
        </div>
        {safetyExpanded ? (
          <p id="cw-comparison-safety-content">
            每个测试组都会独立执行一次真实 Agent。同一输入可能重复发送消息、创建任务或审批、写入外部系统，并分别产生模型和工具调用费用。开始前请确认使用测试账号、测试数据，且这些外部操作可以安全重复执行。
          </p>
        ) : null}
      </div>
      <div className="cw-comparison-toolbar" aria-label="对照调试操作">
        <div>
          <strong>方案对照</strong>
          <span>{variants.length} 个测试组，基准组固定在左侧</span>
        </div>
        <div className="cw-comparison-toolbar-actions">
          <button
            type="button"
            className="cw-btn cw-btn-soft"
            onClick={() => setHistoryDrawerOpen(true)}
          >
            最近对照记录{history.length ? ` (${history.length})` : ""}
          </button>
          <button
            type="button"
            className="cw-btn cw-btn-soft"
            disabled={!comparisonTraceAvailable || sessionStarting}
            title={
              comparisonTraceAvailable
                ? "按精确调用标识或稳定调用路径对齐基线与候选 Trace"
                : "完成基线和至少一个候选运行后可对齐 Trace"
            }
            onClick={onOpenComparisonTrace}
          >
            对齐 Trace
          </button>
          {sessionReady &&
          variants.some((variant) =>
            ["starting", "ready", "sending"].includes(variant.phase),
          ) ? (
            <button
              type="button"
              className="cw-btn cw-btn-soft is-danger"
              onClick={onStopAll}
            >
              停止全部
            </button>
          ) : null}
          {variants.length < 4 ? (
            <button
              type="button"
              className="cw-btn cw-btn-soft"
              disabled={!enabled || sessionStarting}
              onClick={onAddVariant}
            >
              <Plus className="cw-i" />
              添加对照组
            </button>
          ) : null}
          <ComparisonSessionActionSlot
            placement="toolbar"
            viewModel={sessionPresentation}
            onStartSession={onStartSession}
          />
        </div>
      </div>
      <ComparisonSessionActionSlot
        placement="alert"
        viewModel={sessionPresentation}
        onStartSession={onStartSession}
      />
      <div className="cw-comparison-tabs" role="tablist" aria-label="调试方案">
        {variants.map((variant) => (
          <button
            key={variant.id}
            type="button"
            role="tab"
            aria-selected={narrowVariantId === variant.id}
            onClick={() => setNarrowVariantId(variant.id)}
          >
            {variant.name}
          </button>
        ))}
      </div>
      <div className="cw-ab-stage">
        {!enabled ? (
          <div className="cw-debug-empty">{disabledReason}</div>
        ) : (
          <div
            className="cw-ab-grid"
            style={
              {
                "--cw-ab-column-count": variants.length,
              } as CSSProperties
            }
          >
            {variants.map((variant) => {
              const effectiveChanges = effectiveDebugChanges(draft, variant);
              const starting = variant.phase === "starting";
              const ready = sessionReady && variant.phase === "ready";
              const busy = starting || variant.phase === "sending";
              const traceAvailable =
                !sessionStarting &&
                (sessionReady || sessionPresentation.transcriptReadOnly) &&
                variant.messages.some((message) => message.role === "assistant");
              const latestAssistant = [...variant.messages]
                .reverse()
                .find((message) => message.role === "assistant");
              const hasLatestSuccess = Boolean(
                latestAssistant &&
                  !latestAssistant.error &&
                  (latestAssistant.content || latestAssistant.blocks?.length),
              );
              return (
                <article
                  key={variant.id}
                  className={`cw-ab-card${narrowVariantId === variant.id ? " is-narrow-selected" : ""}`}
                >
                      <header className="cw-ab-card-head">
                        <div className="cw-ab-card-title">
                          <strong>{variant.name}</strong>
                          <span>
                            {variant.id === "baseline"
                              ? "当前 Draft（只读）"
                              : effectiveChanges.length === 0
                                ? "尚未修改配置"
                                : effectiveChanges.length > 1 ||
                                    variant.inputDiverged
                                  ? `${new Set(effectiveChanges.map((change) => change.agentKey)).size} 个 Agent · ${effectiveChanges.length} 项变化 · 方案级结论`
                                  : `${configurableAgents.find((item) => item.key === effectiveChanges[0].agentKey)?.name ?? effectiveChanges[0].agentKey} · ${
                                    effectiveChanges[0].dimension === "model"
                                      ? "模型"
                                      : effectiveChanges[0].dimension === "instruction"
                                        ? "系统提示词"
                                        : "Skills"
                                  } · 维度级归因`}
                          </span>
                          <em
                            className={`cw-comparison-status ${sessionPresentation.cardStatusLabel ? "is-read-only" : `is-${variant.phase}`}`}
                          >
                            {sessionPresentation.cardStatusLabel ??
                              (variant.phase === "starting"
                                ? "正在启动"
                                : variant.phase === "ready"
                                  ? "环境就绪"
                                  : variant.phase === "sending"
                                    ? "正在运行"
                                    : variant.phase === "error"
                                      ? "运行失败"
                                    : variant.phase === "canceled"
                                        ? "已停止"
                                        : "未启动")}
                          </em>
                          {baselineFailed && variant.id !== "baseline" && hasLatestSuccess ? (
                            <em className="cw-comparison-repair-badge">故障修复证据</em>
                          ) : null}
                          {variant.inputDiverged ? (
                            <em className="cw-comparison-diverged-badge">
                              互动输入已分叉
                            </em>
                          ) : null}
                        </div>
                        <div className="cw-ab-card-actions">
                          {variant.id !== "baseline" && <button
                            type="button"
                            className="cw-ab-config-trigger"
                            disabled={variant.configOpen || busy || sessionStarting}
                            onClick={() => onToggleConfig(variant.id)}
                          >
                            测试配置
                          </button>}
                          {variant.id !== "baseline" && (
                            <button
                              type="button"
                              className="cw-ab-remove"
                              aria-label={`删除${variant.name}`}
                              disabled={variant.configOpen || busy || sessionStarting}
                              onClick={() => onRemoveVariant(variant.id)}
                            >
                              <DebugVariantDeleteIcon className="cw-i" />
                            </button>
                          )}
                        </div>
                      </header>

                      {variant.id !== "baseline" &&
                        effectiveChanges.length > 0 && (
                          <DebugVariantDifferenceSummary
                            draft={draft}
                            baselineApiKeys={baselineApiKeys}
                            changes={effectiveChanges}
                            configurableAgents={configurableAgents}
                            variantName={variant.name}
                          />
                        )}

                      {variant.id === "baseline" && (
                        <section className="cw-comparison-baseline-config">
                          <div className="cw-comparison-baseline-head">
                            <h3>基准配置</h3>
                            <button
                              type="button"
                              className="cw-link-btn"
                              onClick={() => setBaselineDrawerOpen(true)}
                            >
                              查看全部配置
                            </button>
                          </div>
                          {configurableAgents.map((agent) => {
                            const agentDraft = getNode(draft, agent.path);
                            return (
                              <div
                                className="cw-comparison-baseline-agent"
                                key={agent.key}
                              >
                                <strong title={agent.name || agent.key}>
                                  {agent.name || agent.key}
                                </strong>
                                <span
                                  title={[
                                    agentDraft.modelName || "Studio 默认 Model ID",
                                    agentDraft.modelProvider || "Studio 默认 Provider",
                                    agentDraft.modelApiBase || "Studio 默认 API Base",
                                  ].join(" · ")}
                                >
                                  {agentDraft.modelName || "Studio 默认 Model ID"} · {agentDraft.modelProvider || "默认 Provider"}
                                </span>
                                <small>
                                  提示词 {agentDraft.instruction.length} 字 · Skills {(agentDraft.selectedSkills ?? []).length} 个 · {baselineApiKeys[agent.key] ? "临时凭据已配置" : "服务端凭据"}
                                </small>
                              </div>
                            );
                          })}
                        </section>
                      )}

                      <div className="cw-ab-conversation">
                        {variant.error ? (
                          <DeploymentErrorMessage
                            message={variant.error}
                            className="cw-debug-error-detail"
                            defaultExpanded
                          />
                        ) : (starting ||
                            (sessionStarting &&
                              !sessionPresentation.transcriptReadOnly)) &&
                          variant.messages.length === 0 ? (
                          <div className="cw-ab-empty cw-ab-starting">
                            <Loader2 className="cw-i cw-spin" />
                            <span>正在创建独立测试环境</span>
                          </div>
                        ) : variant.messages.length === 0 ? (
                          <div className="cw-ab-empty cw-ab-launch">
                            {ready ? (
                              <>
                                <strong className="cw-ab-ready-title">已就绪</strong>
                                <span className="cw-ab-launch-hint">
                                  可在下方输入测试消息
                                </span>
                              </>
                            ) : (
                              <span className="cw-ab-launch-hint">
                                开启 Session 后即可加入本轮测试
                              </span>
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
                                  <Blocks
                                    blocks={message.blocks}
                                    readOnly={sessionPresentation.transcriptReadOnly}
                                    onAction={(action, node) =>
                                      onVariantAction(variant.id, action, node)
                                    }
                                  />
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
                      </div>

                      <dl className="cw-comparison-metrics" aria-label={`${variant.name}运行指标`}>
                        <div>
                          <dt>首字耗时</dt>
                          <dd>{variant.ttftMs == null ? "—" : `${variant.ttftMs} ms`}</dd>
                        </div>
                        <div>
                          <dt>总耗时</dt>
                          <dd>{variant.latencyMs == null ? "—" : `${variant.latencyMs} ms`}</dd>
                        </div>
                        <div>
                          <dt>Tools</dt>
                          <dd>{variant.toolCalls == null ? "—" : variant.toolCalls}</dd>
                        </div>
                        <div>
                          <dt>Tokens</dt>
                          <dd>{variant.tokens == null ? "—" : variant.tokens.toLocaleString()}</dd>
                        </div>
                      </dl>

                      {variant.id !== "baseline" && (
                        <div className="cw-comparison-verdict">
                          <label>
                            <span>人工判定</span>
                            <select
                              value={variant.verdict}
                              disabled={!sessionPresentation.verdictEditable}
                              onChange={(event) =>
                                sessionPresentation.verdictEditable &&
                                  onVerdictChange(
                                    variant.id,
                                    event.target.value as DebugVariant["verdict"],
                                    variant.verdictReason,
                                  )
                              }
                            >
                              <option value="">请选择</option>
                              <option value="采用候选">采用候选</option>
                              <option value="保留基线">保留基线</option>
                              <option value="持平">持平</option>
                              <option value="各有取舍">各有取舍</option>
                              <option value="证据不足">证据不足</option>
                            </select>
                          </label>
                          <label>
                            <span>理由</span>
                            <input
                              value={variant.verdictReason}
                              placeholder="采用候选前必填"
                              disabled={!sessionPresentation.verdictEditable}
                              onChange={(event) =>
                                sessionPresentation.verdictEditable &&
                                  onVerdictChange(
                                    variant.id,
                                    variant.verdict,
                                    event.target.value,
                                  )
                              }
                            />
                          </label>
                        </div>
                      )}

                      <footer className="cw-ab-deploy-footer">
                        <button
                          type="button"
                          className="cw-ab-trace"
                          disabled={!traceAvailable}
                          title={
                            sessionStarting
                              ? "正在开启新 Session，完成后可查看调用链路"
                              : traceAvailable
                              ? `查看${variant.name}调用链路`
                              : "完成一次调试后可查看调用链路"
                          }
                          onClick={() => onOpenTrace(variant.id)}
                        >
                          调用链路
                        </button>
                        {(ready || busy) && (
                          <button
                            type="button"
                            className="cw-ab-trace"
                            disabled={!sessionReady}
                            onClick={() => onStopVariant(variant.id)}
                          >
                            停止
                          </button>
                        )}
                        {variant.id !== "baseline" && <button
                          type="button"
                          className="cw-ab-deploy"
                          disabled={
                            !sessionReady ||
                            busy ||
                            variant.id === "baseline" ||
                            variant.verdict !== "采用候选" ||
                            !variant.verdictReason.trim() ||
                            !hasLatestSuccess
                          }
                          onClick={() => onDeployVariant(variant.id)}
                        >
                          采用候选
                        </button>}
                      </footer>
                </article>
              );
            })}

          </div>
        )}
      </div>

      <div className="cw-ab-composer">
        <div className="cw-debug-composerbox">
          <textarea
            className="cw-debug-input"
            rows={1}
            value={input}
            placeholder={sessionPresentation.composerPlaceholder}
            disabled={sessionPresentation.composerDisabled}
            aria-describedby={
              sessionPresentation.showAlert
                ? "cw-comparison-session-warning"
                : undefined
            }
            onChange={(e) => onInput(e.target.value)}
            onKeyDown={(e) => {
              if (isImeCompositionEvent(e.nativeEvent)) return;
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                onSend();
              }
            }}
          />
          <button
            type="button"
            className="cw-debug-send"
            title="发送"
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
      </div>
      {editingVariant ? (
        <DebugVariantConfigurationPanel
          variant={editingVariant}
          variants={variants}
          draft={draft}
          busy={
            sessionStarting ||
            ["starting", "sending"].includes(editingVariant.phase)
          }
          onClose={() => onToggleConfig(editingVariant.id)}
          onRemoveVariant={onRemoveVariant}
          onCompleteConfig={onCompleteConfig}
          onSelectChange={onSelectChange}
          onRemoveChange={onRemoveChange}
          onConfigChange={onConfigChange}
          onSkillsChange={onSkillsChange}
          onToggleApiKey={onToggleApiKey}
        />
      ) : null}
      {baselineDrawerOpen ? (
        <ComparisonDrawer
          title="基准配置"
          description="当前 Draft 的只读快照。凭据只展示来源状态，不显示明文。"
          width="wide"
          closeLabel="关闭基准配置"
          onClose={() => setBaselineDrawerOpen(false)}
        >
          <div className="cw-comparison-baseline-detail">
            {configurableAgents.map((agent) => {
              const agentDraft = getNode(draft, agent.path);
              return (
                <section key={agent.key}>
                  <h3>{agent.name || agent.key}</h3>
                  <dl>
                    <div><dt>Model ID</dt><dd>{agentDraft.modelName || "Studio 默认值"}</dd></div>
                    <div><dt>Provider</dt><dd>{agentDraft.modelProvider || "Studio 默认值"}</dd></div>
                    <div><dt>API Base</dt><dd>{agentDraft.modelApiBase || "Studio 默认值"}</dd></div>
                    <div><dt>API Key</dt><dd>{baselineApiKeys[agent.key] ? "已配置临时凭据" : "由 Studio 服务端凭据解析"}</dd></div>
                    <div className="is-long"><dt>系统提示词</dt><dd>{agentDraft.instruction || "未配置"}</dd></div>
                    <div className="is-long"><dt>Skills</dt><dd>{(agentDraft.selectedSkills ?? []).length ? (agentDraft.selectedSkills ?? []).map((skill) => `${skill.name || skill.folder}${skill.version ? `@${skill.version}` : ""}`).join("、") : "未配置"}</dd></div>
                  </dl>
                </section>
              );
            })}
          </div>
        </ComparisonDrawer>
      ) : null}
      {historyDrawerOpen ? (
        <ComparisonDrawer
          title="最近对照记录"
          description="最多保留当前 Draft 最近 20 条判断摘要。调试环境释放后，Trace 证据可能不可打开。"
          width="wide"
          closeLabel="关闭最近对照记录"
          onClose={() => setHistoryDrawerOpen(false)}
        >
          {history.length ? (
            <div className="cw-comparison-history-table-wrap">
              <table className="cw-comparison-history-table">
                <thead>
                  <tr>
                    <th>时间</th>
                    <th>候选</th>
                    <th>判定</th>
                    <th>Tokens</th>
                    <th>证据</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((record) => (
                    <tr key={`${record.timestamp}:${record.runId}`}>
                      <td>{new Date(record.timestamp).toLocaleString()}</td>
                      <td title={record.reason}>{record.candidateName}</td>
                      <td>{record.verdict}</td>
                      <td>{record.metrics.tokens ?? "—"}</td>
                      <td>{record.traceId || record.sessionId ? "运行时可用" : "不可用"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="cw-comparison-drawer-empty">
              完成候选判断并采用后，这里会保存对照摘要。
            </div>
          )}
        </ComparisonDrawer>
      ) : null}
    </section>
  );
}

const WORKSPACE_MODES: Array<{
  id: WorkspaceMode;
  label: string;
}> = [
  { id: "build", label: "架构" },
  { id: "validate", label: "调试" },
  { id: "publish", label: "发布" },
];

function WorkspaceHeader({ mode }: { mode: WorkspaceMode }) {
  const title =
    mode === "validate"
      ? "调试您的智能体"
      : mode === "publish"
        ? "准备好部署您的智能体"
        : "个性化您的智能体架构";
  return (
    <header className="cw-workspace-header">
      <h1>{title}</h1>
    </header>
  );
}

function WorkspaceLifecycleFooter({
  mode,
  busy,
  onChange,
  assistant,
}: {
  mode: WorkspaceMode;
  busy: boolean;
  onChange: (mode: WorkspaceMode) => void;
  assistant?: React.ReactNode;
}) {
  const activeIndex = WORKSPACE_MODES.findIndex((item) => item.id === mode);
  const previousMode = WORKSPACE_MODES[activeIndex - 1];
  const nextMode = WORKSPACE_MODES[activeIndex + 1];
  return (
    <footer className="cw-workspace-footer">
      <div
        className={`cw-workspace-nav-actions${assistant ? " has-assistant" : ""}`}
      >
        <button
          type="button"
          className={`cw-workspace-nav-button${mode === "build" ? " is-placeholder" : ""}`}
          aria-hidden={mode === "build" || undefined}
          tabIndex={mode === "build" ? -1 : 0}
          disabled={!previousMode || busy}
          onClick={() => previousMode && onChange(previousMode.id)}
        >
          上一步
        </button>
        <span aria-hidden="true" />
        {assistant ? (
          <div className="cw-workspace-ai-slot">{assistant}</div>
        ) : null}
        {mode === "build" ? (
          <div className="cw-workspace-build-actions">
            <button
              type="button"
              className="cw-workspace-nav-button"
              disabled={busy}
              onClick={() => onChange("validate")}
            >
              进入调试
            </button>
            <button
              type="button"
              className="cw-workspace-nav-button is-primary"
              disabled={busy}
              onClick={() => onChange("publish")}
            >
              跳过调试，直接发布
            </button>
          </div>
        ) : mode === "publish" ? (
          <div
            id="cw-publish-primary-action"
            className="cw-publish-action-slot"
          />
        ) : (
          <button
            type="button"
            className="cw-workspace-nav-button is-primary"
            disabled={!nextMode || busy}
            onClick={() => nextMode && onChange(nextMode.id)}
          >
            下一步
          </button>
        )}
      </div>
      <nav className="cw-workspace-progress" aria-label="Agent 创建进度">
        {WORKSPACE_MODES.map((item, index) => {
          const active = item.id === mode;
          return (
            <button
              key={item.id}
              type="button"
              className={`${active ? "is-active" : ""}${index < activeIndex ? " is-complete" : ""}`}
              aria-current={active ? "step" : undefined}
              aria-label={item.label}
              disabled={busy}
              onClick={() => onChange(item.id)}
            >
              <span aria-hidden="true" />
            </button>
          );
        })}
      </nav>
    </footer>
  );
}

/* ================================================================ *
 * Main component
 * ================================================================ */
interface CustomCreateProps extends CreateModeProps {
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
  cloudProvider = "volcengine",
  initialDeployRegion = defaultCloudRegion(cloudProvider),
  onDeploymentComplete,
  onDeploymentStarted,
  onDraftChange,
  onDiscard,
}: CustomCreateProps) {
  void onCreate; // outcome is the in-pane project preview, not a navigation
  void onBack; // no footer nav in the single-scroll layout; back lives in app chrome
  void onDiscard; // the discard action is intentionally hidden in this flow
  const [draft, setDraft] = useState<AgentDraft>(
    () =>
      draftForCloudProvider(
        initialDraft ?? emptyDraft(cloudProvider),
        cloudProvider,
      ),
  );
  useEffect(() => {
    setDraft((current) => draftForCloudProvider(current, cloudProvider));
  }, [cloudProvider]);
  const [aiRequirement, setAiRequirement] = useState("");
  const [aiGenerating, setAiGenerating] = useState(false);
  const [aiGenerated, setAiGenerated] = useState(false);
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
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("build");
  const [showErrors, setShowErrors] = useState(false);
  const [validationPulse, setValidationPulse] = useState(0);
  const [project, setProject] = useState<AgentProject | null>(null);
  const [building, setBuilding] = useState(false);
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
        modelProvider: initialProviderDraft.modelProvider ?? "",
        modelApiBase: initialProviderDraft.modelApiBase ?? "",
        apiKey: "",
        apiKeyLocked: false,
        apiKeyVisible: false,
        instruction: initialProviderDraft.instruction,
        selectedSkills: initialProviderDraft.selectedSkills ?? [],
        agentKey: "root",
        dimension: "model",
        additionalChanges: [],
        verdict: "",
        verdictReason: "",
        ttftMs: null,
        latencyMs: null,
        toolCalls: null,
        tokens: null,
        inputDiverged: false,
        configOpen: false,
        phase: "idle",
        runtimeSnapshot: "",
        messages: [],
        error: null,
      },
    ];
  });
  const [selectedVariantId, setSelectedVariantId] = useState("baseline");
  const [comparisonFingerprint, setComparisonFingerprint] = useState("");
  const [comparisonSessionState, setComparisonSessionState] =
    useState<ComparisonSessionState>(() => createComparisonSessionState());
  const comparisonSessionStateRef = useRef(comparisonSessionState);
  comparisonSessionStateRef.current = comparisonSessionState;
  const comparisonSessionAttemptRef = useRef(0);
  const comparisonSessionStatusValue = comparisonSessionStatus(
    comparisonSessionState,
  );
  const sessionReadOnly =
    comparisonSessionState.activeSessionRevision !== null &&
    comparisonSessionStatusValue !== "ready";
  const comparisonRoundIdRef = useRef("");
  const undoDraftRef = useRef<AgentDraft | null>(null);
  const undoModelApiKeysRef = useRef<Record<string, string> | null>(null);
  const [canUndoCandidate, setCanUndoCandidate] = useState(false);
  const [comparisonHistoryRevision, setComparisonHistoryRevision] = useState(0);
  const comparisonHistory = useMemo(
    () => readComparisonRecords(draft.name || "untitled-draft"),
    [draft.name, comparisonHistoryRevision],
  );
  const debugVariantSequenceRef = useRef(1);
  const debugRunsRef = useRef(
    new Map<string, { run: GeneratedAgentTestRun; sessionId: string }>(),
  );
  const [activeDebugRunCount, setActiveDebugRunCount] = useState(0);
  const [debugInput, setDebugInput] = useState("");
  const [debugTraceTarget, setDebugTraceTarget] =
    useState<DebugTraceTarget | null>(null);
  const [debugComparisonTraceTargets, setDebugComparisonTraceTargets] =
    useState<ComparisonTraceTarget[] | null>(null);
  const [debugLeaveConfirmOpen, setDebugLeaveConfirmOpen] = useState(false);
  const [debugLeaveCleaning, setDebugLeaveCleaning] = useState(false);
  const [debugActionConfirm, setDebugActionConfirm] =
    useState<DebugActionConfirm | null>(null);
  const debugLeaveConfirmResolverRef =
    useRef<((confirmed: boolean) => void) | null>(null);
  const [buildErr, setBuildErr] = useState("");
  const [modelAdvancedOpen, setModelAdvancedOpen] = useState(false);
  const [modelApiKeys, setModelApiKeys] = useState<Record<string, string>>({});
  const [revealedModelApiKeys, setRevealedModelApiKeys] = useState<Set<string>>(
    () => new Set(),
  );
  const [lockedModelApiKeys, setLockedModelApiKeys] = useState<Set<string>>(
    () => new Set(),
  );
  const [a2aRegistryAdvancedOpen, setA2aRegistryAdvancedOpen] =
    useState(false);

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
      comparisonSessionAttemptRef.current += 1;
      for (const { run } of debugRunsRef.current.values()) {
        deleteGeneratedAgentTestRun(run.runId)
          .then(() => forgetDebugTestRun(run.runId))
          .catch((err) => console.warn("清理调试运行失败", err));
      }
      debugRunsRef.current.clear();
    };
  }, []);

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
        className="cw-section"
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
  const selectedModelSecretKey = nodePathKey(safePath);
  const selectedModelApiKey = modelApiKeys[selectedModelSecretKey] ?? "";
  const selectedModelApiKeyLocked = lockedModelApiKeys.has(
    selectedModelSecretKey,
  );
  const selectedModelApiKeyRevealed = revealedModelApiKeys.has(
    selectedModelSecretKey,
  );
  const isRootAgent = safePath.length === 0;
  const modelAdvancedId = `cw-model-advanced-${safePath.join("-") || "root"}`;
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

  const handleGenerateDraft = async () => {
    const requirement = aiRequirement.trim();
    if (!requirement || aiGenerating) return;
    if (requirement.length < GENERATED_AGENT_REQUIREMENT_MIN_LENGTH) return;
    if (
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
      const result = await generateAgentDraftFromRequirement(requirement);
      setDraft(
        draftForCloudProvider(
          sanitizeGeneratedDraftCapabilities(
            normalizeDraft(result.draft),
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
    } catch (error) {
      setAiErrorDialog(
        error instanceof Error ? error.message : String(error),
      );
    } finally {
      setAiGenerating(false);
    }
  };

  const addCanvasStep = (path: NodePath) => {
    const parent = getNode(draft, path);
    if (!nodeAcceptsChildren(parent) || path.length >= MAX_TREE_DEPTH) return;
    const next = addChild(draft, path, cloudProvider);
    const childIndex = getNode(next, path).subAgents.length - 1;
    applyTree(next, [...path, childIndex]);
  };

  const insertCanvasStep = (parentPath: NodePath, index: number) => {
    const parent = getNode(draft, parentPath);
    if (
      !nodeAcceptsChildren(parent) ||
      parentPath.length >= MAX_TREE_DEPTH
    ) {
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
  const invalidClass = (missing: boolean) =>
    showErrors && missing
      ? `is-error cw-error-shake-${validationPulse % 2}`
      : "";

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
  const currentDebugSnapshot = useMemo(
    () => debugSnapshotKey(providerDraft),
    [providerDraft],
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

  // Smooth-scroll to the first invalid section during validation.
  const scrollToSection = (id: StepId) => {
    sectionRefs.current[id]?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  const requireCompleteDraft = () => {
    if (canFinish) return true;
    setShowErrors(true);
    setValidationPulse((pulse) => pulse + 1);
    if (problems[0]) {
      setSelectedPath(problems[0].path);
      window.requestAnimationFrame(() =>
        scrollToSection(problems[0].problem === "缺少子 Agent" ? "type" : "basic"),
      );
    }
    return false;
  };

  const cleanupDebugRuns = async () => {
    comparisonSessionAttemptRef.current += 1;
    comparisonRoundIdRef.current = "";
    const resetSessionState = resetComparisonSessionState();
    comparisonSessionStateRef.current = resetSessionState;
    setComparisonSessionState(resetSessionState);
    setDebugTraceTarget(null);
    setDebugComparisonTraceTargets(null);
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

  const openDebugComparisonTrace = () => {
    const targets = debugVariants.flatMap((variant) => {
      const runtime = debugRunsRef.current.get(variant.id);
      const hasAssistant = variant.messages.some(
        (message) => message.role === "assistant",
      );
      return runtime && hasAssistant
        ? [
            {
              id: variant.id,
              name: variant.name,
              runId: runtime.run.runId,
              sessionId: runtime.sessionId,
            },
          ]
        : [];
    });
    if (
      targets.some((target) => target.id === "baseline") &&
      targets.some((target) => target.id !== "baseline")
    ) {
      setDebugComparisonTraceTargets(targets);
    }
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
    if (workspaceMode !== "validate") return true;
    const pendingSessionStart =
      comparisonSessionStateRef.current.pendingSessionRevision !== null;
    if (activeDebugRunCount === 0 && !pendingSessionStart) return true;
    if (debugLeaveConfirmResolverRef.current) return false;
    return new Promise<boolean>((resolve) => {
      debugLeaveConfirmResolverRef.current = resolve;
      setDebugLeaveConfirmOpen(true);
    });
  };

  const openPublishPreview = async (variantId?: string) => {
    if (!(await confirmLeaveDebug())) return;
    setBuildErr("");
    if (!requireCompleteDraft()) {
      setWorkspaceMode("build");
      return;
    }
    const invalidEnv = firstInvalidRuntimeEnv(
      deploymentEnv.specs,
      providerDraft.deployment?.envValues ?? {},
    );
    if (invalidEnv) {
      setBuildErr(
        `${invalidEnv.spec.comment || invalidEnv.spec.key}：${invalidEnv.error}`,
      );
      setWorkspaceMode("build");
      return;
    }
    setBuilding(true);
    try {
      const releaseVariant = variantId
        ? debugVariants.find((variant) => variant.id === variantId)
        : selectedDebugVariant;
      if (releaseVariant) setSelectedVariantId(releaseVariant.id);
      const releaseDraft = releaseVariant
        ? draftForDebugVariant(providerDraft, releaseVariant)
        : providerDraft;
      const generated = await generateAgentProject(codegenDraft(releaseDraft));
      if (releaseDraft !== draft) setDraft(releaseDraft);
      setProject(generated);
      setWorkspaceMode("publish");
    } catch (error) {
      setBuildErr(error instanceof Error ? error.message : String(error));
    } finally {
      setBuilding(false);
    }
  };

  const markComparisonConfigChanged = (changed = true) => {
    if (!changed) return;
    setComparisonSessionState((current) => {
      const next = markComparisonConfigurationChanged(current, true);
      comparisonSessionStateRef.current = next;
      return next;
    });
  };

  const comparisonSessionProblem = () =>
    debugComparisonSessionProblem(draft, debugVariants, modelApiKeys);

  const createDebugVariantRuntime = async (
    variant: DebugVariant,
    comparisonId: string,
  ): Promise<PreparedDebugRuntime> => {
    const operation = beginAgentDebug({
      agentId: String(providerDraft.name || "unknown"),
      variantType: variant.id === "baseline" ? "baseline" : "comparison",
    });
    let failedPhase: AgentDebugFailedProps["failedPhase"] = "create_test_run";
    let run: GeneratedAgentTestRun | null = null;

    try {
      const variantDraft = draftForDebugVariant(providerDraft, variant);
      const configurableAgents = listConfigurableAgents(variantDraft);
      const modelCredentials = configurableAgents
        .map(({ path, key }) => ({
          agentPath: path,
          apiKey: debugApiKeyForAgent(variant, key, modelApiKeys),
        }))
        .filter(({ apiKey }) => apiKey.trim().length > 0);
      const runtimeSnapshot = debugVariantSnapshot(
        currentDebugSnapshot,
        variant,
      );

      for (const { path, key } of configurableAgents) {
        const modelNode = getNode(variantDraft, path);
        const validation = validateModelConnection({
          modelName: modelNode.modelName ?? "",
          modelProvider: modelNode.modelProvider ?? "",
          modelApiBase: modelNode.modelApiBase ?? "",
          apiKey: debugApiKeyForAgent(variant, key, modelApiKeys),
          studioApiBase: defaultModelApiBase(
            variantDraft.cloudProvider ?? cloudProvider,
          ),
        });
        if (!validation.ok) {
          throw new DebugRuntimePreparationError("run", validation.reason);
        }
      }

      try {
        run = await createGeneratedAgentTestRun(
          debugRuntimeDraft(variantDraft),
          {
            runtime: deploymentTarget
              ? {
                  runtimeId: deploymentTarget.runtimeId,
                  region: deploymentTarget.region,
                }
              : undefined,
            modelCredentials,
            comparisonId,
          },
        );
      } catch (error) {
        throw new DebugRuntimePreparationError(
          "run",
          debugRuntimeFailureMessage(error),
        );
      }
      rememberDebugTestRun(run.runId);

      failedPhase = "create_test_session";
      let sessionId: string;
      try {
        sessionId = await createGeneratedAgentTestSession(
          run.runId,
          "test_user",
        );
      } catch {
        try {
          await deleteGeneratedAgentTestRun(run.runId);
        } catch {
          console.warn("清理调试运行失败");
        } finally {
          forgetDebugTestRun(run.runId);
        }
        throw new DebugRuntimePreparationError(
          "session",
          "创建 ADK Session 失败，请稍后重试。",
        );
      }

      operation.succeed({ debugRunId: String(run.runId) });
      return {
        runtime: { run, sessionId },
        runtimeSnapshot,
        credentialAgentPaths: modelCredentials.map(
          ({ agentPath }) => agentPath,
        ),
      };
    } catch (error) {
      operation.fail({
        failedPhase,
        ...classifyTelemetryError(error, { phase: failedPhase }),
      });
      throw error;
    }
  };

  const cleanupPreparedDebugRuntime = async (
    prepared: PreparedDebugRuntime,
  ) => {
    try {
      await deleteGeneratedAgentTestRun(prepared.runtime.run.runId);
    } finally {
      forgetDebugTestRun(prepared.runtime.run.runId);
    }
  };

  const startNewComparisonSession = async (confirmed = false) => {
    if (
      !debugEnabled ||
      building ||
      comparisonSessionStatusValue === "starting" ||
      comparisonSessionStateRef.current.pendingSessionRevision !== null
    ) {
      return;
    }
    if (!requireCompleteDraft() || comparisonSessionProblem()) return;
    if (
      comparisonSessionState.activeSessionRevision !== null &&
      !confirmed
    ) {
      setDebugActionConfirm({
        kind: "new-session",
        variantCount: debugVariants.length,
      });
      return;
    }

    const attemptedRevision = comparisonSessionState.configurationRevision;
    const attemptId = ++comparisonSessionAttemptRef.current;
    const nextComparisonId = globalThis.crypto.randomUUID();
    setComparisonSessionState((current) => {
      const next = beginComparisonSession(current);
      comparisonSessionStateRef.current = next;
      return next;
    });

    const staged = await stageComparisonRuntimes(
      debugVariants,
      (variant) => createDebugVariantRuntime(variant, nextComparisonId),
      cleanupPreparedDebugRuntime,
    );

    const latestSessionState = comparisonSessionStateRef.current;
    const attemptIsObsolete =
      attemptId !== comparisonSessionAttemptRef.current ||
      latestSessionState.pendingSessionRevision !== attemptedRevision ||
      latestSessionState.configurationRevision !== attemptedRevision;

    if (!staged.ok) {
      if (attemptIsObsolete) return;
      const failedVariant = debugVariants.find(
        (variant) => variant.id === staged.failedTargetId,
      );
      const preparationError =
        staged.error instanceof DebugRuntimePreparationError
          ? staged.error
          : new DebugRuntimePreparationError(
              "run",
              "调试环境启动失败，请稍后重试。",
            );
      setComparisonSessionState((current) => {
        const next = failComparisonSession(current, attemptedRevision, {
          variantId: staged.failedTargetId,
          variantName: failedVariant?.name ?? staged.failedTargetId,
          stage: preparationError.stage,
          message: preparationError.message,
        });
        comparisonSessionStateRef.current = next;
        return next;
      });
      setDebugActionConfirm(null);
      return;
    }

    if (attemptIsObsolete) {
      await Promise.allSettled(
        [...staged.runtimes.values()].map(cleanupPreparedDebugRuntime),
      );
      return;
    }

    const oldRuntimes = debugRunsRef.current;
    const preparedByVariant = staged.runtimes;
    debugRunsRef.current = new Map(
      [...preparedByVariant].map(([variantId, prepared]) => [
        variantId,
        prepared.runtime,
      ]),
    );
    setActiveDebugRunCount(debugRunsRef.current.size);
    comparisonRoundIdRef.current = nextComparisonId;
    setDebugTraceTarget(null);
    setDebugComparisonTraceTargets(null);

    const credentialPathKeys = new Set(
      [...preparedByVariant.values()].flatMap((prepared) =>
        prepared.credentialAgentPaths.map(nodePathKey),
      ),
    );
    setLockedModelApiKeys(new Set(credentialPathKeys));
    setRevealedModelApiKeys((current) => {
      const next = new Set(current);
      credentialPathKeys.forEach((pathKey) => next.delete(pathKey));
      return next;
    });
    setDebugVariants((current) =>
      current.map((variant) => {
        const prepared = preparedByVariant.get(variant.id);
        if (!prepared) return variant;
        const variantDraft = draftForDebugVariant(draft, variant);
        const agentPaths = new Map(
          listConfigurableAgents(variantDraft).map(({ key, path }) => [
            key,
            nodePathKey(path),
          ]),
        );
        const preparedCredentialPaths = new Set(
          prepared.credentialAgentPaths.map(nodePathKey),
        );
        const credentialWasUsed = (change: DebugVariantChange) =>
          change.dimension === "model" &&
          preparedCredentialPaths.has(agentPaths.get(change.agentKey) ?? "");
        return {
          ...variant,
          configOpen: false,
          phase: "ready",
          runtimeSnapshot: prepared.runtimeSnapshot,
          apiKeyLocked: credentialWasUsed(primaryDebugChange(variant)),
          apiKeyVisible: false,
          additionalChanges: variant.additionalChanges.map((change) => ({
            ...change,
            apiKeyLocked: credentialWasUsed(change),
            apiKeyVisible: false,
          })),
          messages: [],
          ttftMs: null,
          latencyMs: null,
          toolCalls: null,
          tokens: null,
          error: null,
          verdict: "",
          verdictReason: "",
          inputDiverged: false,
        };
      }),
    );
    setDebugInput("");
    setComparisonSessionState((current) => {
      const next = completeComparisonSession(current, attemptedRevision);
      comparisonSessionStateRef.current = next;
      return next;
    });
    setDebugActionConfirm(null);

    const cleanupResults = await Promise.allSettled(
      [...oldRuntimes.values()].map(async ({ run }) => {
        try {
          await deleteGeneratedAgentTestRun(run.runId);
        } finally {
          forgetDebugTestRun(run.runId);
        }
      }),
    );
    if (cleanupResults.some((result) => result.status === "rejected")) {
      console.warn("清理调试运行失败");
    }
  };

  const sendDebugText = async (text: string, targets: DebugVariant[]) => {
    if (
      !text ||
      targets.length === 0 ||
      sessionReadOnly ||
      comparisonSessionStatusValue !== "ready"
    ) {
      return;
    }

    const targetIds = new Set(targets.map((variant) => variant.id));
    setDebugVariants((current) =>
      current.map((variant) =>
        targetIds.has(variant.id)
          ? {
              ...variant,
              phase: "sending",
              ttftMs: null,
              latencyMs: null,
              toolCalls: null,
              tokens: null,
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
        const startedAt = performance.now();
        const runtime = debugRunsRef.current.get(variant.id);
        if (!runtime) return;
        try {
          let acc = emptyAcc();
          let firstVisibleAt: number | null = null;
          for await (const event of runGeneratedAgentTestSSE({
            runId: runtime.run.runId,
            userId: "test_user",
            sessionId: runtime.sessionId,
            text,
          })) {
            const eventError =
              event.error || event.errorMessage || event.error_message;
            const usage = event.usageMetadata ?? event.usage_metadata;
            if (!eventError) acc = applyEvent(acc, event);
            if (
              !eventError &&
              firstVisibleAt == null &&
              acc.blocks.some(
                (block) => block.kind === "text" && block.text.length > 0,
              )
            ) {
              firstVisibleAt = performance.now();
            }
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
                return {
                  ...item,
                  messages,
                  ttftMs:
                    firstVisibleAt == null
                      ? item.ttftMs
                      : Math.round(firstVisibleAt - startedAt),
                  toolCalls: acc.blocks.filter(
                    (block) => block.kind === "tool" && block.done,
                  ).length,
                  tokens: usage?.totalTokenCount ?? item.tokens,
                };
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
              item.id === variant.id
                ? item.phase === "canceled"
                  ? item
                  : {
                    ...item,
                    phase: "ready",
                    latencyMs: Math.round(performance.now() - startedAt),
                  }
                : item,
            ),
          );
        }
      }),
    );
  };

  const sendDebugMessage = async () => {
    if (sessionReadOnly || comparisonSessionStatusValue !== "ready") return;
    const text = debugInput.trim();
    const targets = debugVariants.filter(
      (variant) =>
        variant.phase === "ready" &&
        !variant.configOpen &&
        variant.runtimeSnapshot ===
          debugVariantSnapshot(currentDebugSnapshot, variant) &&
        debugRunsRef.current.has(variant.id),
    );
    if (!text || targets.length === 0) return;
    setDebugInput("");
    await sendDebugText(text, targets);
  };

  const handleDebugVariantAction = (
    variantId: string,
    action: A2uiAction | undefined,
    node: A2uiComponent,
  ) => {
    if (sessionReadOnly || comparisonSessionStatusValue !== "ready") return;
    const actionName = action?.event?.name ?? node.id;
    const text = `[ui-action] ${actionName}: ${JSON.stringify(action?.event?.context ?? {})}`;
    const runningTargets = debugVariants.filter(
      (variant) =>
        variant.phase === "ready" &&
        !variant.configOpen &&
        variant.runtimeSnapshot ===
          debugVariantSnapshot(currentDebugSnapshot, variant) &&
        debugRunsRef.current.has(variant.id),
    );
    const matchingTargets = runningTargets.filter((variant) =>
      debugVariantHasA2uiAction(variant, actionName, node.id),
    );
    const shareAction =
      runningTargets.length > 0 &&
      matchingTargets.length === runningTargets.length;
    const targets = shareAction
      ? runningTargets
      : runningTargets.filter((variant) => variant.id === variantId);
    if (!shareAction) {
      const runningIds = new Set(runningTargets.map((variant) => variant.id));
      setDebugVariants((current) =>
        current.map((variant) =>
          runningIds.has(variant.id)
            ? { ...variant, inputDiverged: true }
            : variant,
        ),
      );
    }
    void sendDebugText(text, targets);
  };

  const addDebugVariant = () => {
    if (debugVariants.length >= 4) return;
    const initialAgent = firstConfigurableAgent(draft);
    if (!initialAgent) return;
    const sequence = debugVariantSequenceRef.current++;
    const id = `variant-${sequence}`;
    const initialTarget = getNode(draft, initialAgent.path);
    setDebugVariants((current) => {
      return [
        ...current.map((variant) => ({ ...variant, configOpen: false })),
        {
          id,
          name: `对照组 ${sequence}`,
          modelName: initialTarget.modelName ?? "",
          modelProvider: initialTarget.modelProvider ?? "",
          modelApiBase: initialTarget.modelApiBase ?? "",
          apiKey: modelApiKeys[initialAgent.key] ?? "",
          apiKeyLocked: false,
          apiKeyVisible: false,
          instruction: initialTarget.instruction,
          selectedSkills: structuredClone(initialTarget.selectedSkills ?? []),
          agentKey: initialAgent.key,
          dimension: "model",
          additionalChanges: [],
          verdict: "",
          verdictReason: "",
          ttftMs: null,
          latencyMs: null,
          toolCalls: null,
          tokens: null,
          inputDiverged: false,
          configOpen: true,
          phase: "idle",
          runtimeSnapshot: "",
          messages: [],
          error: null,
        },
      ];
    });
    markComparisonConfigChanged();
  };

  const removeDebugVariant = (id: string) => {
    const variant = debugVariants.find((item) => item.id === id);
    if (!variant || variant.id === "baseline") return;
    setDebugVariants((current) =>
      current.map((item) =>
        item.id === id ? { ...item, configOpen: false } : item,
      ),
    );
    setDebugActionConfirm({
      kind: "delete",
      variantId: id,
      variantName: variant.name,
    });
  };

  const stopDebugVariant = async (id: string) => {
    await cleanupDebugVariantRun(id);
    patchDebugVariant(id, {
      phase: "canceled",
      error: null,
      ttftMs: null,
      latencyMs: null,
      toolCalls: null,
      tokens: null,
    });
  };

  const stopAllDebugVariants = async () => {
    await Promise.all(
      debugVariants
        .filter((variant) =>
          ["starting", "ready", "sending"].includes(variant.phase),
        )
        .map((variant) => stopDebugVariant(variant.id)),
    );
  };

  const applyDebugVariant = async (
    id: string,
    baselineFailureConfirmed = false,
  ) => {
    if (sessionReadOnly || comparisonSessionStatusValue !== "ready") return;
    const variant = debugVariants.find((item) => item.id === id);
    const runtime = debugRunsRef.current.get(id);
    const latestAssistant = [...(variant?.messages ?? [])]
      .reverse()
      .find((message) => message.role === "assistant");
    if (
      !variant ||
      variant.id === "baseline" ||
      variant.phase !== "ready" ||
      !runtime ||
      !latestAssistant ||
      latestAssistant.error ||
      variant.verdict !== "采用候选" ||
      !variant.verdictReason.trim() ||
      !comparisonFingerprint
    ) {
      return;
    }

    const baseline = debugVariants.find((item) => item.id === "baseline");
    const baselineLatestAssistant = [...(baseline?.messages ?? [])]
      .reverse()
      .find((message) => message.role === "assistant");
    const baselineFailed = Boolean(
      baseline?.error || baselineLatestAssistant?.error,
    );
    if (baselineFailed && !baselineFailureConfirmed) {
      setDebugActionConfirm({
        kind: "baseline-failed-apply",
        variantId: id,
      });
      return;
    }

    const result = await applyCandidateAtomically(
      draft,
      comparisonFingerprint,
      debugOverridesForVariant(variant),
    );
    if (!result.ok) {
      patchDebugVariant(id, { error: result.reason });
      return;
    }
    const nextFingerprint = await fingerprintDraft(result.draft);

    undoDraftRef.current = structuredClone(draft);
    undoModelApiKeysRef.current = { ...modelApiKeys };
    setDraft(result.draft);
    setModelApiKeys((current) => {
      const next = { ...current };
      debugChangesForVariant(variant)
        .filter((change) => change.dimension === "model")
        .forEach((change) => {
          next[change.agentKey] = change.apiKey;
        });
      return next;
    });
    setComparisonFingerprint(nextFingerprint);
    markComparisonConfigChanged();
    setCanUndoCandidate(true);
    setSelectedVariantId(id);
    persistComparisonRecord(draft.name || "untitled-draft", {
      timestamp: Date.now(),
      fingerprint: comparisonFingerprint,
      candidateName: variant.name,
      configDiffs: effectiveDebugChanges(draft, variant).map((change) => ({
        agentKey: change.agentKey,
        dimension: change.dimension,
      })),
      metrics: {
        ttftMs: variant.ttftMs,
        latencyMs: variant.latencyMs,
        toolCalls: variant.toolCalls,
        tokens: variant.tokens,
      },
      verdict: variant.verdict,
      reason: variant.verdictReason.trim(),
      inputDiverged: variant.inputDiverged,
      runId: runtime.run.runId,
      sessionId: runtime.sessionId,
      traceId: runtime.sessionId,
    });
    setComparisonHistoryRevision((revision) => revision + 1);
  };

  const undoAppliedCandidate = async () => {
    const previous = undoDraftRef.current;
    if (!previous) return;
    setDraft(previous);
    if (undoModelApiKeysRef.current) {
      setModelApiKeys(undoModelApiKeysRef.current);
    }
    setComparisonFingerprint(await fingerprintDraft(previous));
    markComparisonConfigChanged();
    undoDraftRef.current = null;
    undoModelApiKeysRef.current = null;
    setCanUndoCandidate(false);
    setSelectedVariantId("baseline");
  };

  const patchDebugVariant = (id: string, patch: Partial<DebugVariant>) =>
    setDebugVariants((current) =>
      current.map((variant) =>
        variant.id === id ? { ...variant, ...patch } : variant,
      ),
    );

  const patchDebugVariantConfiguration = (
    id: string,
    patch: Partial<DebugVariant>,
  ) =>
    setDebugVariants((current) =>
      current.map((variant) =>
        variant.id === id
          ? preserveDebugVariantEvidence(variant, patch)
          : variant,
      ),
    );

  const selectDebugVariantChange = (
    id: string,
    agentKey: string,
    dimension: ComparisonDimension,
  ) => {
    if (id === "baseline") return;
    const selected = debugVariants.find((variant) => variant.id === id);
    if (
      !selected ||
      (selected.agentKey === agentKey && selected.dimension === dimension)
    ) {
      return;
    }
    const currentBaseline = baselineDebugChange(
      draft,
      modelApiKeys,
      selected.agentKey,
      selected.dimension,
    );
    const targetBaseline = baselineDebugChange(
      draft,
      modelApiKeys,
      agentKey,
      dimension,
    );
    if (!currentBaseline || !targetBaseline) return;
    setDebugVariants((current) =>
      current.map((variant) => {
        if (variant.id !== id) return variant;
        return preserveDebugVariantEvidence(
          variant,
          switchPrimaryDebugChange(
            variant,
            currentBaseline,
            targetBaseline,
          ),
        );
      }),
    );
    markComparisonConfigChanged();
  };

  const removeDebugVariantChange = (
    id: string,
    agentKey: string,
    dimension: ComparisonDimension,
  ) => {
    if (id === "baseline") return;
    const variant = debugVariants.find((item) => item.id === id);
    const hasExistingChange = Boolean(
      variant &&
        effectiveDebugChanges(draft, variant).some(
          (change) =>
            change.agentKey === agentKey && change.dimension === dimension,
        ),
    );
    if (!variant || !hasExistingChange) return;
    const targetBaseline = baselineDebugChange(
      draft,
      modelApiKeys,
      agentKey,
      dimension,
    );
    if (!targetBaseline) return;
    setDebugVariants((current) =>
      current.map((variant) =>
        variant.id === id
          ? preserveDebugVariantEvidence(
              variant,
              removeDebugChange(variant, targetBaseline),
            )
          : variant,
      ),
    );
    markComparisonConfigChanged();
  };

  const updateDebugVariantConfig = (
    id: string,
    field:
      | "agentKey"
      | "dimension"
      | "modelName"
      | "modelProvider"
      | "modelApiBase"
      | "apiKey"
      | "instruction",
    value: string,
  ) => {
    if (id === "baseline") return;
    const variant = debugVariants.find((item) => item.id === id);
    if (!variant) return;
    if (field === "agentKey") {
      selectDebugVariantChange(id, value, variant.dimension);
      return;
    }
    if (field === "dimension") {
      selectDebugVariantChange(
        id,
        variant.agentKey,
        value as ComparisonDimension,
      );
      return;
    }
    if (field === "modelProvider" || field === "modelApiBase") {
      if (variant[field] === value) return;
      patchDebugVariantConfiguration(id, {
        [field]: value,
        apiKey: "",
        apiKeyLocked: false,
        apiKeyVisible: false,
      });
      markComparisonConfigChanged();
      return;
    }
    if (field === "apiKey") {
      if (variant.apiKey === value) return;
      patchDebugVariantConfiguration(id, {
        apiKey: value,
        apiKeyLocked: false,
        ...(value ? {} : { apiKeyVisible: false }),
      });
      markComparisonConfigChanged();
      return;
    }
    if (variant[field] === value) return;
    patchDebugVariantConfiguration(id, {
      [field]: value,
    } as Partial<DebugVariant>);
    markComparisonConfigChanged();
    if (selectedVariantId !== id || id === "baseline") return;
    setSelectedVariantId("baseline");
  };

  const completeDebugVariantConfig = (id: string) => {
    if (!debugVariants.some((variant) => variant.id === id)) return;
    patchDebugVariant(id, { configOpen: false });
  };

  const confirmDebugAction = () => {
    const action = debugActionConfirm;
    if (!action) return;
    if (action.kind === "new-session") {
      void startNewComparisonSession(true);
      return;
    }
    setDebugActionConfirm(null);
    if (action.kind === "baseline-failed-apply") {
      void applyDebugVariant(action.variantId, true);
      return;
    }
    setDebugVariants((current) =>
      current.filter((variant) => variant.id !== action.variantId),
    );
    if (selectedVariantId === action.variantId) {
      setSelectedVariantId("baseline");
    }
    markComparisonConfigChanged();
    void cleanupDebugVariantRun(action.variantId);
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
        appName: deploymentTarget?.appName,
        description: draft.description,
      },
    );
  };

  const openValidation = async () => {
    if (!requireCompleteDraft()) return;
    setComparisonFingerprint(await fingerprintDraft(draft));
    undoDraftRef.current = null;
    undoModelApiKeysRef.current = null;
    setCanUndoCandidate(false);
    setDebugVariants((current) =>
      current.map((variant) =>
        variant.id === "baseline" && !debugRunsRef.current.has(variant.id)
          ? {
              ...variant,
              modelName: defaultDebugModelName(providerDraft),
              modelProvider: providerDraft.modelProvider ?? "",
              modelApiBase: providerDraft.modelApiBase ?? "",
              instruction: providerDraft.instruction,
              selectedSkills: structuredClone(
                providerDraft.selectedSkills ?? [],
              ),
            }
          : variant,
      ),
    );
    setWorkspaceMode("validate");
  };

  const handleWorkspaceChange = async (nextMode: WorkspaceMode) => {
    if (nextMode === "publish") {
      if (!requireCompleteDraft()) return;
      if (project) setWorkspaceMode("publish");
      else openPublishPreview();
      return;
    }
    if (nextMode === "validate") {
      await openValidation();
      return;
    }
    undoDraftRef.current = null;
    setCanUndoCandidate(false);
    if (!(await confirmLeaveDebug())) return;
    setWorkspaceMode(nextMode);
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
              <input
                type="text"
                value={aiRequirement}
                maxLength={8000}
                disabled={aiGenerating}
                placeholder={`描述目标，使用 ${plannerModelName(cloudProvider)} 模型一键生成配置`}
                aria-invalid={Boolean(aiRequirementError)}
                aria-describedby={
                  aiRequirementError ? "ai-requirement-error" : undefined
                }
                onChange={(event) => setAiRequirement(event.target.value)}
                onKeyDown={(event) => {
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

  return (
    <div className={`cw-root is-${workspaceMode}`}>
      <WorkspaceHeader mode={workspaceMode} />
      {buildErr && (
        <DeploymentErrorMessage
          className="cw-workspace-alert"
          message={buildErr}
        />
      )}
      <main className="cw-workspace-main" id="cw-workspace-main">
      {workspaceMode === "build" && (
        <div className="cw-build-workspace">
        <div className="cw-editor">
        <AgentBuildCanvas
          draft={draft}
          direction="horizontal"
          selectedPath={safePath}
          onSelect={setSelectedPath}
          onAdd={addCanvasStep}
          onInsert={insertCanvasStep}
          onDelete={deleteCanvasStep}
        />
        {/* Right: the form for the currently-selected node. */}
        <div className="cw-detail">
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
                  const remoteTypeDisabled = isRootAgent && t.id === "a2a";
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
                          <strong>{AGENT_TYPE_BAR_LABELS[t.id]}</strong>
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
              {showErrors && orchestrator && node.subAgents.length === 0 && (
                <span className="cw-error-text">
                  {validationProblemMessage({
                    path: safePath,
                    name: node.name.trim() || "未命名",
                    typeLabel: agentTypeMeta(node.agentType).label,
                    problem: "缺少子 Agent",
                  })}
                </span>
              )}
            </Section>
            <Section meta={metaOf("basic")}>
                <div className="cw-form">
                      {!a2a && (
                        <>
                    <div className="cw-field">
                      <label className="cw-label">
                        {isRootAgent ? "Agent 名称" : "名称"}
                        <span className="cw-req">*</span>
                      </label>
                      <input
                        className={`cw-input ${invalidClass(nameInvalid)}`}
                        value={node.name}
                        placeholder="assistant"
                        onChange={(e) => patch({ name: e.target.value })}
                      />
                      {showErrors && nameProblem ? (
                              <span className="cw-error-text">
                                {nameProblem}
                              </span>
                      ) : (
                        <span className="cw-help">
                                遵循 Google ADK 命名规则，且在执行流程中保持唯一。
                        </span>
                      )}
                    </div>
                    <div className="cw-field">
                      <label className="cw-label">
                        {isRootAgent ? "描述" : "智能体描述"}
                        <span className="cw-req">*</span>
                      </label>
                      <textarea
                        className={`cw-textarea cw-textarea-sm ${invalidClass(
                          descriptionMissing,
                        )}`}
                        value={node.description}
                        placeholder="简要描述这个 Agent 的用途，便于团队识别…"
                        onChange={(e) =>
                          patch({ description: e.target.value })
                        }
                      />
                      {showErrors && descriptionMissing ? (
                              <span className="cw-error-text">
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
                        <p className="cw-section-desc cw-dependency-hint">
                            这是一个协作容器，本身不生成回答。请在左侧画布中
                            添加任务步骤，并通过拖拽调整它们的位置。
                        </p>
                        {node.agentType === "loop" && (
                          <div className="cw-field">
                            <label className="cw-label">最大轮次</label>
                            <input
                              className="cw-input"
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
                        <div className="cw-field cw-remote-center-fields">
                          <div className="cw-remote-center-head">
                            <div className="cw-label">
                              AgentKit 智能体中心
                              <span className="cw-req">*</span>
                            </div>
                            <p className="cw-help cw-remote-center-description">
                              远程 Agent 的名称、描述和能力来自中心返回的 Agent Card。
                              系统会根据每轮任务动态发现并挂载匹配的 Agent。
                            </p>
                          </div>
                          <A2aSpaceSelect
                            value={node.a2aRegistry?.registrySpaceId ?? ""}
                            region={
                              node.a2aRegistry?.registryRegion ||
                              A2A_REGISTRY_DEFAULTS.region
                            }
                            invalid={showErrors && a2aRegistrySpaceMissing}
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
                            <span className="cw-error-text">
                              请选择 AgentKit 智能体中心
                          </span>
                        )}
                      </div>
                    ) : (
                      <div className="cw-field">
                        <label className="cw-label">
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
                            onChange={(instruction) => patch({ instruction })}
                          />
                        </Suspense>
                        {showErrors && instructionMissing ? (
                          <span className="cw-error-text">
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
                  <div className="cw-form">
                    <div className="cw-field">
                      <label className="cw-label">模型名称</label>
                      <input
                        className="cw-input"
                        value={node.modelName ?? ""}
                        placeholder={defaultModelName(cloudProvider)}
                              onChange={(e) =>
                                patch({ modelName: e.target.value })
                              }
                      />
                    </div>
                    <button
                      type="button"
                      className="cw-more-options cw-model-more-options"
                      aria-expanded={modelAdvancedOpen}
                      aria-controls={modelAdvancedId}
                            onClick={() =>
                              setModelAdvancedOpen((open) => !open)
                            }
                    >
                      <span>更多选项</span>
                      <ChevronRight
                        className={`cw-more-options-chevron ${
                          modelAdvancedOpen ? "is-open" : ""
                        }`}
                        aria-hidden
                      />
                    </button>
                    <AnimatePresence initial={false}>
                      {modelAdvancedOpen && (
                        <motion.div
                          id={modelAdvancedId}
                          className="cw-model-advanced"
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.18, ease: "easeOut" }}
                        >
                          <div className="cw-field">
                                  <label className="cw-label">
                                    服务商 Provider
                                  </label>
                            <input
                              className="cw-input"
                              value={node.modelProvider ?? ""}
                              placeholder="openai"
                              onChange={(e) =>
                                patch({ modelProvider: e.target.value })
                              }
                            />
                          </div>
                          <div className="cw-field">
                            <label className="cw-label">API Base</label>
                            <input
                              className="cw-input"
                              value={node.modelApiBase ?? ""}
                              placeholder={defaultModelApiBase(cloudProvider)}
                              onChange={(e) =>
                                patch({ modelApiBase: e.target.value })
                              }
                            />
                            <span className="cw-help cw-dependency-hint">
                              留空或使用当前云的官方 Ark 地址时，Studio
                              会提供服务端凭据；填写自定义 API Base
                              时，需要在下方输入临时 API Key。
                            </span>
                          </div>
                          <div className="cw-field">
                            <label className="cw-label">
                              调试 API Key（临时）
                            </label>
                            {selectedModelApiKeyLocked ? (
                              <div className="cw-model-secret-configured">
                                <span role="status">已配置临时凭据</span>
                                <button
                                  type="button"
                                  className="cw-link-btn"
                                  onClick={() => {
                                    setModelApiKeys((current) => ({
                                      ...current,
                                      [selectedModelSecretKey]: "",
                                    }));
                                    setLockedModelApiKeys((current) => {
                                      const next = new Set(current);
                                      next.delete(selectedModelSecretKey);
                                      return next;
                                    });
                                  }}
                                >
                                  清除并重新输入
                                </button>
                              </div>
                            ) : (
                              <div className="cw-model-secret-input">
                                <input
                                  className="cw-input"
                                  type={
                                    selectedModelApiKeyRevealed
                                      ? "text"
                                      : "password"
                                  }
                                  value={selectedModelApiKey}
                                  autoComplete="off"
                                  placeholder="可留空"
                                  aria-label="模型 API Key"
                                  onChange={(event) =>
                                    setModelApiKeys((current) => ({
                                      ...current,
                                      [selectedModelSecretKey]:
                                        event.target.value,
                                    }))
                                  }
                                />
                                <button
                                  type="button"
                                  className="cw-model-secret-toggle"
                                  aria-label={
                                    selectedModelApiKeyRevealed
                                      ? "隐藏 API Key"
                                      : "显示 API Key"
                                  }
                                  aria-pressed={selectedModelApiKeyRevealed}
                                  onClick={() =>
                                    setRevealedModelApiKeys((current) => {
                                      const next = new Set(current);
                                      if (next.has(selectedModelSecretKey)) {
                                        next.delete(selectedModelSecretKey);
                                      } else {
                                        next.add(selectedModelSecretKey);
                                      }
                                      return next;
                                    })
                                  }
                                >
                                  {selectedModelApiKeyRevealed ? (
                                    <EyeOff className="cw-i cw-i-sm" />
                                  ) : (
                                    <Eye className="cw-i cw-i-sm" />
                                  )}
                                </button>
                              </div>
                            )}
                            <span className="cw-help cw-dependency-hint">
                              可留空；留空时使用 Studio 服务端凭据。自定义 API
                              Base 必须输入临时 Key。Key
                              仅保存在当前页面内存并注入调试环境，不写入
                              Draft、源码或部署配置，也不会自动带入发布页。发布
                              自定义模型时需在发布页重新确认 API Key。
                            </span>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
            </Section>

            <Section meta={metaOf("tools")}>
                  <div className="cw-form">
                    <div className="cw-field">
                      <label className="cw-label">内置工具</label>
                      <span className="cw-help">
                              勾选 VeADK 提供的内置能力，生成时会自动补全 import
                              与所需环境变量。
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
                            transition={{ duration: 0.16, ease: "easeOut" }}
                          >
                            <div className="cw-tool-config-head">
                              <span className="cw-label">代码执行配置</span>
                              <span className="cw-help">
                                指定 AgentKit 代码执行沙箱。
                              </span>
                            </div>
                            <RuntimeEnvFields
                              env={
                                BUILTIN_TOOLS.find(
                                  (item) => item.id === "run_code",
                                )?.env ?? []
                              }
                              values={draft.deployment?.envValues ?? {}}
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
                        onChange={(next) => patch({ mcpTools: next })}
                      />
                    </div>
                  </div>
            </Section>

            <Section meta={metaOf("skills")}>
                  <div className="cw-form">
                    <SkillsSourceTabs
                      selected={selectedSkills}
                      onChange={(next) => patch({ selectedSkills: next })}
                      cloudProvider={cloudProvider}
                    />
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
                        <label className="cw-label">知识库后端</label>
                        <BackendSelect
                          options={KB_BACKENDS}
                          value={node.knowledgebaseBackend}
                          onChange={(id) =>
                            patch({
                              knowledgebaseBackend: id,
                              knowledgebaseIndex:
                                id === "viking" || id === "openviking"
                                  ? node.knowledgebaseIndex
                                  : "",
                            })
                          }
                        />
                        {(node.knowledgebaseBackend ?? DEFAULT_KB_BACKEND) ===
                          "viking" && (
                          <div className="cw-field cw-subfield">
                            <label className="cw-label">VikingDB 知识库</label>
                            <VikingKnowledgebaseSelect
                              value={node.knowledgebaseIndex ?? ""}
                              onChange={(knowledgebase) => {
                                patch({
                                  knowledgebaseIndex: knowledgebase.id,
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
                            (node.knowledgebaseBackend ?? DEFAULT_KB_BACKEND) ===
                            "openviking"
                              ? (item) =>
                                  item.key === "DATABASE_OPENVIKING_USER_ID" ? (
                                    <OpenVikingKnowledgeIndexField
                                      value={node.knowledgebaseIndex ?? ""}
                                      onChange={(knowledgebaseIndex) =>
                                        patch({ knowledgebaseIndex })
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
                          desc="在单次会话内保留上下文，跨轮次记住对话内容。"
                          icon={Layers}
                        />
                        {node.memory.shortTerm && (
                          <div className="cw-field cw-subfield">
                                        <label className="cw-label">
                                          短期记忆后端
                                        </label>
                            <BackendSelect
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
                          desc="跨会话持久化关键信息，让 Agent 记住历史偏好。"
                          icon={Database}
                        />
                        {node.memory.longTerm && (
                          <div className="cw-field cw-subfield">
                                        <label className="cw-label">
                                          长期记忆后端
                                        </label>
                            <BackendSelect
                              options={LTM_BACKENDS}
                              value={node.longTermBackend}
                                          onChange={(id) =>
                                            patch({ longTermBackend: id })
                                          }
                            />
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
        </div>
        {/* cw-detail */}
        </div>
        </div>
      )}

      {workspaceMode === "validate" && (
        <div className="cw-validation-workspace">
          <div className="cw-validation-content">
            <DebugComparisonWorkspace
              enabled={debugEnabled}
              disabledReason={debugDisabledReason}
              draft={draft}
              variants={debugVariants}
              draftSnapshot={currentDebugSnapshot}
              input={debugInput}
              onInput={setDebugInput}
              onSend={sendDebugMessage}
              comparisonSessionState={comparisonSessionState}
              sessionProblem={comparisonSessionProblem()}
              onStartSession={() => void startNewComparisonSession()}
              onStopVariant={(id) => void stopDebugVariant(id)}
              onStopAll={() => void stopAllDebugVariants()}
              onDeployVariant={(id) => void applyDebugVariant(id)}
              onAddVariant={addDebugVariant}
              onRemoveVariant={removeDebugVariant}
              onToggleConfig={(id) => {
                setDebugVariants((current) => {
                  const selected = current.find((item) => item.id === id);
                  if (!selected) return current;
                  const nextOpen = !selected.configOpen;
                  return current.map((variant) => ({
                    ...variant,
                    configOpen: variant.id === id ? nextOpen : false,
                  }));
                });
              }}
              onCompleteConfig={completeDebugVariantConfig}
              onSelectChange={selectDebugVariantChange}
              baselineApiKeys={modelApiKeys}
              onRemoveChange={removeDebugVariantChange}
              onConfigChange={updateDebugVariantConfig}
              onSkillsChange={(id, selectedSkills) => {
                const variant = debugVariants.find((item) => item.id === id);
                if (
                  !variant ||
                  JSON.stringify(variant.selectedSkills) ===
                    JSON.stringify(selectedSkills)
                ) {
                  return;
                }
                patchDebugVariantConfiguration(id, { selectedSkills });
                markComparisonConfigChanged();
              }}
              onToggleApiKey={(id) => {
                const variant = debugVariants.find((item) => item.id === id);
                if (!variant || variant.apiKeyLocked) return;
                patchDebugVariant(id, { apiKeyVisible: !variant.apiKeyVisible });
              }}
              onVerdictChange={(id, verdict, verdictReason) =>
                patchDebugVariant(id, { verdict, verdictReason })
              }
              canUndo={canUndoCandidate}
              onUndo={() => void undoAppliedCandidate()}
              history={comparisonHistory}
              onOpenTrace={openDebugTrace}
              onOpenComparisonTrace={openDebugComparisonTrace}
              onVariantAction={handleDebugVariantAction}
            />
          </div>
        </div>
      )}

      {workspaceMode === "publish" && (
        <div className="cw-preview-body">
          {project ? (
            <ProjectPreview
              embedded
              cloudProvider={cloudProvider}
              project={project}
              agentDraft={draft}
              agentName={draft.name || "未命名 Agent"}
              agentCount={countDraftAgents(draft)}
              onChange={setProject}
              onDeploy={handleDeploy}
              onAgentAdded={onAgentAdded}
              onDeploymentTaskChange={onDeploymentTaskChange}
              deploymentActionLabel={deploymentTarget ? "更新并发布" : "部署"}
              deploymentActionTargetId="cw-publish-primary-action"
              deploymentRuntimeId={deploymentTarget?.runtimeId}
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
              deploymentEnvValues={{
                ...providerDraft.deployment?.envValues,
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
              onExportYaml={() =>
                downloadText(
                  `${providerDraft.name || "agent"}.yaml`,
                  draftToYaml(providerDraft),
                  "text/yaml",
                )
              }
            />
          ) : (
            <div className="cw-publish-loading" role="status">
              <Loader2 className="cw-i cw-spin" />
              <strong>正在生成发布配置</strong>
              <span>校验 Agent 结构并准备部署快照…</span>
            </div>
          )}
        </div>
      )}
      </main>
      <WorkspaceLifecycleFooter
        mode={workspaceMode}
        busy={building}
        onChange={handleWorkspaceChange}
        assistant={workspaceMode === "build" ? aiComposer : undefined}
      />
      {debugTraceTarget && (
        <TraceDrawer
          testRunId={debugTraceTarget.runId}
          sessionId={debugTraceTarget.sessionId}
          title={`调用链路 · ${debugTraceTarget.variantName}`}
          onClose={() => setDebugTraceTarget(null)}
        />
      )}
      {debugComparisonTraceTargets && (
        <ComparisonTraceDrawer
          targets={debugComparisonTraceTargets}
          onClose={() => setDebugComparisonTraceTargets(null)}
        />
      )}
      {debugActionConfirm ? (
        <StudioConfirmDialog
          variant={
            debugActionConfirm.kind === "new-session" ||
            debugActionConfirm.kind === "delete"
              ? "danger"
              : "warning"
          }
          title={
            debugActionConfirm.kind === "new-session"
              ? "开启新的对照 Session？"
              : debugActionConfirm.kind === "delete"
              ? `删除测试组 · ${debugActionConfirm.variantName}`
              : "基线失败，仍采用候选？"
          }
          description={
            debugActionConfirm.kind === "new-session"
              ? `将清空 ${debugActionConfirm.variantCount} 个测试组在上一 Session 中的对话、运行指标和人工判定，并停止旧测试环境。所有已保存配置会保留，新 Session 不会重放历史输入。`
              : debugActionConfirm.kind === "delete"
              ? "删除后将清除该测试组的配置、调试消息、临时环境变量、临时凭据和未保留的 Trace 证据，并释放对应调试环境。此操作无法恢复。"
              : "候选成功只能证明它在本次输入下可以运行，无法证明整体优于失败的基线。继续后会直接替换当前 Draft 中对应配置，并保留一次撤销机会。"
          }
          confirmLabel={
            debugActionConfirm.kind === "new-session"
              ? comparisonSessionStatusValue === "starting"
                ? "正在开启..."
                : "清空并开启"
              : debugActionConfirm.kind === "delete"
              ? "删除测试组"
              : "仍然采用"
          }
          closeLabel="关闭调试操作确认"
          onCancel={() => setDebugActionConfirm(null)}
          onConfirm={confirmDebugAction}
          busy={
            debugActionConfirm.kind === "new-session" &&
            comparisonSessionStatusValue === "starting"
          }
        />
      ) : null}
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
            <div
              className="cw-ai-error-message"
              id="ai-generate-error-message"
            >
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
