import {
  type CSSProperties,
  type ComponentType,
  lazy,
  Suspense,
  useEffect,
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
  Info,
  Layers,
  Loader2,
  Plus,
  RefreshCw,
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
  CREATE_BUILTIN_TOOLS,
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
import {
  createGeneratedAgentTestRun,
  createGeneratedAgentTestSession,
  deleteGeneratedAgentTestRun,
  deployAgentkitProject,
  generateAgentDraftFromRequirement,
  generateAgentProject,
  runGeneratedAgentTestSSE,
} from "../adk/client";
import type {
  DeployStage,
  GeneratedAgentTestRun,
  UiFeatures,
} from "../adk/client";
import { applyEvent, emptyAcc, type Block } from "../blocks";
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

/** Debug-run mark: a play head breaking through two lightweight motion rails. */
function DebugRunIcon({ className }: { className?: string }) {
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
      <path d="M9 7.15v9.7a1.15 1.15 0 0 0 1.78.96l7.2-4.85a1.15 1.15 0 0 0 0-1.92l-7.2-4.85A1.15 1.15 0 0 0 9 7.15Z" />
      <path d="M5.75 8.25v7.5" opacity="0.8" />
      <path d="M3 10v4" opacity="0.45" />
      <path d="M17.9 5.25v2.2M19 6.35h-2.2" strokeWidth="1.55" />
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
}: {
  env: EnvVar[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
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
          <label className="cw-env-field" key={item.key} htmlFor={controlId}>
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
        );
      })}
    </div>
  );
}

function a2aSpaceDisplayName(space: A2aSpaceRef): string {
  return space.name.trim() || "未命名智能体中心";
}

function vikingKnowledgebaseDisplayName(item: VikingKnowledgebaseRef): string {
  return item.name.trim() || item.id || "未命名知识库";
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
    <div className="cw-a2a-space-picker" ref={pickerRef}>
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
  onChange: (index: string) => void;
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

  const selectItem = (index: string) => {
    onChange(index);
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
    <div className="cw-a2a-space-picker cw-viking-kb-picker" ref={pickerRef}>
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
                    onClick={() => selectItem(value)}
                  >
                    {value}
                  </button>
                )}
                {filteredItems.map((item) => {
                  const optionLabel = vikingKnowledgebaseDisplayName(item);
                  const selected = item.id === value;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      className={`cw-a2a-space-option ${
                        selected ? "is-selected" : ""
                      }`}
                      title={`${optionLabel} (${item.id})`}
                      onClick={() => selectItem(item.id)}
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
                    <input
                      className="cw-input"
                      value={t.authToken ?? ""}
                      placeholder="Bearer Token（可选）"
                      onChange={(e) => update(i, { authToken: e.target.value })}
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
}: {
  selected: SelectedSkill[];
  onChange: (next: SelectedSkill[]) => void;
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
                    <SkillSpacePicker selected={selected} onChange={onChange} />
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

function addChild(root: AgentDraft, path: NodePath): AgentDraft {
  return updateNode(root, path, (n) => ({
    ...n,
    subAgents: [...n.subAgents, emptyDraft()],
  }));
}

function insertChild(
  root: AgentDraft,
  parentPath: NodePath,
  index: number,
): AgentDraft {
  return updateNode(root, parentPath, (n) => {
    const subAgents = n.subAgents.slice();
    subAgents.splice(index, 0, emptyDraft());
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
  const selections: RuntimeEnvSelection[] = [];
  const fixedValues: Record<string, string> = {};
  const visit = (node: AgentDraft) => {
    for (const toolId of node.builtinTools ?? []) {
      const tool = BUILTIN_TOOLS.find((item) => item.id === toolId);
      if (tool) selections.push({ env: tool.env });
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
          STM_BACKENDS.find(
            (item) => item.id === (node.shortTermBackend ?? "local"),
          )?.env ?? [],
      });
    }
    if (node.memory.longTerm) {
      selections.push({
        env:
          LTM_BACKENDS.find(
            (item) => item.id === (node.longTermBackend ?? "local"),
          )?.env ?? [],
      });
    }
    if (node.knowledgebase) {
      selections.push({
        env:
          KB_BACKENDS.find(
            (item) =>
              item.id === (node.knowledgebaseBackend ?? DEFAULT_KB_BACKEND),
          )?.env ?? [],
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
  visit(root);
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
  optimizations: string[];
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

function codegenDraft(draft: AgentDraft): AgentDraft {
  return {
    ...draft,
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
    "modelName" | "description" | "instruction" | "optimizations"
  >,
): string {
  return JSON.stringify({
    draftSnapshot,
    modelName: variant.modelName,
    description: variant.description,
    instruction: variant.instruction,
    optimizations: variant.optimizations,
  });
}

function debugVariantConfigurationKey(
  variant: Pick<
    DebugVariant,
    "modelName" | "description" | "instruction" | "optimizations"
  >,
): string {
  return JSON.stringify({
    modelName: variant.modelName.trim(),
    description: variant.description.trim(),
    instruction: variant.instruction.trim(),
    optimizations: variant.optimizations,
  });
}

function DebugComparisonWorkspace({
  enabled,
  disabledReason,
  variants,
  draftSnapshot,
  input,
  onInput,
  onSend,
  onStartVariant,
  onDeployVariant,
  onAddVariant,
  onRemoveVariant,
  onToggleConfig,
  onCompleteConfig,
  onConfigChange,
  onOpenTrace,
}: {
  enabled: boolean;
  disabledReason: string;
  variants: DebugVariant[];
  draftSnapshot: string;
  input: string;
  onInput: (v: string) => void;
  onSend: () => void;
  onStartVariant: (id: string) => void;
  onDeployVariant: (id: string) => void;
  onAddVariant: () => void;
  onRemoveVariant: (id: string) => void;
  onToggleConfig: (id: string) => void;
  onCompleteConfig: (id: string) => void;
  onConfigChange: (
    id: string,
    field: "modelName" | "description" | "instruction",
    value: string,
  ) => void;
  onOpenTrace: (id: string) => void;
}) {
  const runningVariants = variants.filter((variant) => {
    if (variant.phase !== "ready") return false;
    return (
      variant.runtimeSnapshot === debugVariantSnapshot(draftSnapshot, variant)
    );
  });
  const sending = variants.some((variant) => variant.phase === "sending");
  const canSend = runningVariants.length > 0 && !sending;

  return (
    <section className="cw-ab-workspace" aria-label="A/B 调试工作台">
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
            {variants.map((variant, variantIndex) => {
              const modelName = variant.modelName.trim();
              const description = variant.description.trim();
              const instruction = variant.instruction.trim();
              const configurationKey = debugVariantConfigurationKey(variant);
              const duplicateConfiguration = Boolean(
                modelName && description && instruction &&
                  variants.findIndex(
                    (item) =>
                      debugVariantConfigurationKey(item) === configurationKey,
                  ) !== variantIndex,
              );
              const configurationUnavailable =
                !modelName || !description || !instruction || duplicateConfiguration;
              const stale = Boolean(
                variant.runtimeSnapshot &&
                  variant.runtimeSnapshot !==
                    debugVariantSnapshot(draftSnapshot, variant),
              );
              const starting = variant.phase === "starting";
              const ready = variant.phase === "ready" && !stale;
              const busy = starting || variant.phase === "sending";
              const traceAvailable =
                ready &&
                variant.phase !== "sending" &&
                variant.messages.some((message) => message.role === "assistant");
              const startDisabled =
                busy || variant.configOpen || configurationUnavailable;
              const disabledReason = !modelName
                ? "请先选择模型"
                : !description
                  ? "请填写描述"
                  : !instruction
                    ? "请填写系统提示词"
                    : duplicateConfiguration
                      ? "该配置与已有测试组相同"
                      : "";
              const startLabel = starting
                ? "正在启动"
                : stale
                  ? "应用配置并重启"
                  : ready
                    ? "重新启动环境"
                    : variant.phase === "error"
                      ? "重新启动环境"
                      : "启动环境";
              return (
                <article
                  key={variant.id}
                  className="cw-ab-card"
                >
                  <div
                    className={`cw-ab-card-inner${variant.configOpen ? " is-flipped" : ""}`}
                  >
                    <section
                      className="cw-ab-card-face cw-ab-card-front"
                      aria-hidden={variant.configOpen}
                    >
                      <header className="cw-ab-card-head">
                        <div className="cw-ab-card-title">
                          <strong>{variant.name}</strong>
                          <span>{variant.modelName || "默认模型"}</span>
                        </div>
                        <div className="cw-ab-card-actions">
                          <button
                            type="button"
                            className="cw-ab-config-trigger"
                            disabled={variant.configOpen || busy}
                            onClick={() => onToggleConfig(variant.id)}
                          >
                            测试配置
                          </button>
                          {variant.id !== "baseline" && (
                            <button
                              type="button"
                              className="cw-ab-remove"
                              aria-label={`删除${variant.name}`}
                              disabled={variant.configOpen || busy}
                              onClick={() => onRemoveVariant(variant.id)}
                            >
                              <DebugVariantDeleteIcon className="cw-i" />
                            </button>
                          )}
                        </div>
                      </header>

                      <div className="cw-ab-conversation">
                        {variant.error ? (
                          <DeploymentErrorMessage
                            message={variant.error}
                            className="cw-debug-error-detail"
                            defaultExpanded
                          />
                        ) : starting ? (
                          <div className="cw-ab-empty cw-ab-starting">
                            <Loader2 className="cw-i cw-spin" />
                            <span>正在创建独立测试环境</span>
                          </div>
                        ) : stale ? (
                          <div className="cw-ab-empty cw-ab-launch">
                            <span>配置已变更，请重新启动此环境</span>
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
                                {disabledReason || "启动环境后即可加入本轮测试"}
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
                      </div>

                      <footer className="cw-ab-deploy-footer">
                        <button
                          type="button"
                          className="cw-ab-trace"
                          disabled={!traceAvailable}
                          title={
                            traceAvailable
                              ? `查看${variant.name}调用链路`
                              : "完成一次调试后可查看调用链路"
                          }
                          onClick={() => onOpenTrace(variant.id)}
                        >
                          调用链路
                        </button>
                        <button
                          type="button"
                          className="cw-ab-start cw-ab-footer-start"
                          disabled={startDisabled}
                          title={disabledReason || undefined}
                          onClick={() => onStartVariant(variant.id)}
                        >
                          {ready || stale || variant.phase === "error" ? (
                            <RefreshCw className="cw-i" />
                          ) : (
                            <DebugRunIcon className="cw-i cw-debug-run-icon" />
                          )}
                          {startLabel}
                        </button>
                        <button
                          type="button"
                          className="cw-ab-deploy"
                          disabled={busy || !modelName}
                          onClick={() => onDeployVariant(variant.id)}
                        >
                          部署该配置
                        </button>
                      </footer>

                    </section>

                    <section
                      className="cw-ab-card-face cw-ab-card-back"
                      aria-hidden={!variant.configOpen}
                    >
                      <header className="cw-ab-config-head">
                        <div>
                          <strong>测试配置</strong>
                          <span>{variant.name}</span>
                        </div>
                        <div className="cw-ab-config-head-actions">
                          {variant.id !== "baseline" && (
                            <button
                              type="button"
                              className="cw-icon-btn cw-icon-danger cw-ab-config-remove"
                              aria-label={`删除${variant.name}`}
                              title="删除配置组"
                              disabled={busy}
                              onClick={() => onRemoveVariant(variant.id)}
                            >
                              <DebugVariantDeleteIcon className="cw-i cw-i-sm" />
                            </button>
                          )}
                          <span
                            className={`cw-ab-config-done-wrap${disabledReason ? " is-disabled" : ""}`}
                            tabIndex={disabledReason ? 0 : undefined}
                          >
                            <button
                              type="button"
                              className="cw-ab-config-done"
                              disabled={
                                !variant.configOpen || configurationUnavailable
                              }
                              onClick={() => onCompleteConfig(variant.id)}
                            >
                              {variant.id === "baseline" ? "完成配置" : "完成并启动"}
                            </button>
                            {disabledReason && (
                              <span className="cw-ab-config-done-tip" role="tooltip">
                                {disabledReason}
                              </span>
                            )}
                          </span>
                        </div>
                      </header>
                      <div className="cw-ab-config">
                        <label>
                          <span>模型</span>
                          <input
                            value={variant.modelName}
                            placeholder="使用 Agent 当前模型"
                            disabled={!variant.configOpen}
                            onChange={(event) =>
                              onConfigChange(
                                variant.id,
                                "modelName",
                                event.target.value,
                              )
                            }
                          />
                        </label>
                        <label>
                          <span>描述</span>
                          <textarea
                            rows={2}
                            value={variant.description}
                            disabled={!variant.configOpen}
                            onChange={(event) =>
                              onConfigChange(
                                variant.id,
                                "description",
                                event.target.value,
                              )
                            }
                          />
                        </label>
                        <label>
                          <span>系统提示词</span>
                          <textarea
                            rows={5}
                            value={variant.instruction}
                            disabled={!variant.configOpen}
                            onChange={(event) =>
                              onConfigChange(
                                variant.id,
                                "instruction",
                                event.target.value,
                              )
                            }
                          />
                        </label>
                        <fieldset className="cw-ab-optimizations-disabled">
                          <legend>
                            <span>优化选项</span>
                            <em>待开放</em>
                          </legend>
                          <div className="cw-ab-optimization-list">
                            {DEBUG_OPTIMIZATIONS.map((item) => (
                              <Checkbox
                                key={item.id}
                                checked={variant.optimizations.includes(item.id)}
                                disabled
                                label={item.label}
                                className="cw-ab-optimization-checkbox"
                              />
                            ))}
                          </div>
                        </fieldset>
                        <p>设置完成后返回正面，再启动当前测试环境。</p>
                      </div>
                    </section>
                  </div>
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
            placeholder={
              canSend
                ? "输入测试消息，将发送到所有已启动测试组..."
                : "请先启动至少一个测试组"
            }
            disabled={!canSend}
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
        {enabled && variants.length < 3 && (
          <button
            type="button"
            className="cw-btn cw-btn-soft cw-ab-add"
            onClick={onAddVariant}
          >
            <Plus className="cw-i" />
            添加对照组
          </button>
        )}
      </div>
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

const DEBUG_OPTIMIZATIONS = [
  {
    id: "context",
    label: "上下文优化",
    description: "压缩历史对话，保留与当前任务相关的信息",
  },
  {
    id: "grounding",
    label: "幻觉抑制",
    description: "对不确定内容要求依据，并明确表达未知",
  },
  {
    id: "tools",
    label: "工具调用优化",
    description: "减少重复调用，优先复用可信的工具结果",
  },
  {
    id: "latency",
    label: "响应加速",
    description: "缓存稳定上下文，降低重复推理开销",
  },
] as const;

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
        {mode === "publish" ? (
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
  deploymentTarget,
  initialDeployRegion = "cn-beijing",
  onDeploymentComplete,
  onDeploymentStarted,
  onDraftChange,
  onDiscard,
}: CustomCreateProps) {
  void onCreate; // outcome is the in-pane project preview, not a navigation
  void onBack; // no footer nav in the single-scroll layout; back lives in app chrome
  void onDiscard; // the discard action is intentionally hidden in this flow
  const [draft, setDraft] = useState<AgentDraft>(
    () => initialDraft ?? emptyDraft(),
  );
  const [aiRequirement, setAiRequirement] = useState("");
  const [aiGenerating, setAiGenerating] = useState(false);
  const [aiGenerated, setAiGenerated] = useState(false);
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
    onDraftChangeRef.current?.(draft, draftDirty);
  }, [draft, draftDirty, draftSnapshot]);
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
  const [debugVariants, setDebugVariants] = useState<DebugVariant[]>(() => [
    {
      id: "baseline",
      name: "基准组",
      modelName: defaultDebugModelName(initialDraft ?? emptyDraft()),
      description: (initialDraft ?? emptyDraft()).description,
      instruction: (initialDraft ?? emptyDraft()).instruction,
      optimizations: [],
      configOpen: false,
      phase: "idle",
      runtimeSnapshot: "",
      messages: [],
      error: null,
    },
  ]);
  const [selectedVariantId, setSelectedVariantId] = useState("baseline");
  const debugVariantSequenceRef = useRef(1);
  const baselineModelEditedRef = useRef(false);
  const debugRunsRef = useRef(
    new Map<string, { run: GeneratedAgentTestRun; sessionId: string }>(),
  );
  const [activeDebugRunCount, setActiveDebugRunCount] = useState(0);
  const [debugInput, setDebugInput] = useState("");
  const [debugTraceTarget, setDebugTraceTarget] =
    useState<DebugTraceTarget | null>(null);
  const [debugLeaveConfirmOpen, setDebugLeaveConfirmOpen] = useState(false);
  const [debugLeaveCleaning, setDebugLeaveCleaning] = useState(false);
  const debugLeaveConfirmResolverRef =
    useRef<((confirmed: boolean) => void) | null>(null);
  const [buildErr, setBuildErr] = useState("");
  const [modelAdvancedOpen, setModelAdvancedOpen] = useState(false);
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
      setDraft(sanitizeGeneratedDraftCapabilities(normalizeDraft(result.draft)));
      setSelectedPath([]);
      setProject(null);
      setShowErrors(false);
      setBuildErr("");
      setAiGenerated(true);
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
    const next = addChild(draft, path);
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
    const next = insertChild(draft, parentPath, safeIndex);
    applyTree(next, [...parentPath, safeIndex]);
  };

  const clearRootAgent = () => {
    if (
      !window.confirm("清空根 Agent 的全部配置和子 Agent？此操作无法撤销。")
    ) {
      return;
    }
    setDraft(emptyDraft());
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
  const mcpTools = node.mcpTools ?? [];
  const selectedSkills = node.selectedSkills ?? [];
  const toggleBuiltin = (id: string) =>
    patch({
      builtinTools: builtinTools.includes(id)
        ? builtinTools.filter((x) => x !== id)
        : [...builtinTools, id],
    });

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
  const currentDebugSnapshot = useMemo(
    () => debugSnapshotKey(draft),
    [draft],
  );
  const selectedDebugVariant =
    debugVariants.find((variant) => variant.id === selectedVariantId) ??
    debugVariants[0];
  const deploymentEnv = useMemo(() => collectDeploymentEnv(draft), [draft]);

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
    if (workspaceMode !== "validate" || activeDebugRunCount === 0) return true;
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
      draft.deployment?.envValues ?? {},
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
        ? {
            ...draft,
            modelName: releaseVariant.modelName || draft.modelName,
            description: releaseVariant.description,
            instruction: releaseVariant.instruction,
          }
        : draft;
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

  const startDebugVariant = async (id: string) => {
    if (!debugEnabled || building) return;
    if (!requireCompleteDraft()) return;
    const variant = debugVariants.find((item) => item.id === id);
    if (!variant || variant.phase === "starting" || variant.phase === "sending") {
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
    ) return;

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
    try {
      await cleanupDebugVariantRun(id);
      await cleanupStoredDebugRuns();
      const variantDraft: AgentDraft = {
        ...draft,
        modelName: variant.modelName || draft.modelName,
        description: variant.description,
        instruction: variant.instruction,
      };
      createdRun = await createGeneratedAgentTestRun(
        debugRuntimeDraft(variantDraft),
      );
      rememberDebugTestRun(createdRun.runId);
      const sessionId = await createGeneratedAgentTestSession(
        createdRun.runId,
        "test_user",
      );
      debugRunsRef.current.set(id, { run: createdRun, sessionId });
      setActiveDebugRunCount(debugRunsRef.current.size);
      setDebugVariants((current) =>
        current.map((item) =>
          item.id === id
            ? { ...item, phase: "ready", runtimeSnapshot: snapshot }
            : item,
        ),
      );
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
    }
  };

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
      if (current.length >= 3) return current;
      const sequence = debugVariantSequenceRef.current++;
      const id = `variant-${sequence}`;
      return [
        ...current,
        {
          id,
          name: `对照组 ${sequence}`,
          modelName: draft.modelName ?? "",
          description: draft.description,
          instruction: draft.instruction,
          optimizations: [],
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
    await cleanupDebugVariantRun(id);
    setDebugVariants((current) => current.filter((variant) => variant.id !== id));
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
    ) return;
    if (id === "baseline") {
      patchDebugVariant(id, { configOpen: false });
      return;
    }
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
        appName: deploymentTarget?.appName,
        description: draft.description,
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
                : defaultDebugModelName(draft),
              description: draft.description,
              instruction: draft.instruction,
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
      openValidation();
      return;
    }
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
                placeholder="描述目标，使用 doubao-seed-2-0-lite-260428 模型一键生成配置"
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
                        placeholder="doubao-seed-2-1-pro-260628"
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
                              placeholder="https://ark.cn-beijing.volces.com/api/v3/"
                              onChange={(e) =>
                                patch({ modelApiBase: e.target.value })
                              }
                            />
                            <span className="cw-help cw-dependency-hint">
                                    留空则使用 VeADK 默认模型配置；Ark API Key
                                    会由 Studio 服务端凭据自动获取。其他服务商的
                                    Key 可在部署页添加。
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
                          items={CREATE_BUILTIN_TOOLS}
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
                                id === "viking"
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
                              onChange={(knowledgebaseIndex) =>
                                patch({ knowledgebaseIndex })
                              }
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
              variants={debugVariants}
              draftSnapshot={currentDebugSnapshot}
              input={debugInput}
              onInput={setDebugInput}
              onSend={sendDebugMessage}
              onStartVariant={startDebugVariant}
              onDeployVariant={(id) => void openPublishPreview(id)}
              onAddVariant={addDebugVariant}
              onRemoveVariant={removeDebugVariant}
              onToggleConfig={(id) => {
                const variant = debugVariants.find((item) => item.id === id);
                if (variant) patchDebugVariant(id, { configOpen: !variant.configOpen });
              }}
              onCompleteConfig={completeDebugVariantConfig}
              onConfigChange={updateDebugVariantConfig}
              onOpenTrace={openDebugTrace}
            />
          </div>
        </div>
      )}

      {workspaceMode === "publish" && (
        <div className="cw-preview-body">
          {project ? (
            <ProjectPreview
              embedded
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
                      optimizations: selectedDebugVariant.optimizations.flatMap(
                        (id) => {
                          const option = DEBUG_OPTIMIZATIONS.find(
                            (item) => item.id === id,
                          );
                          return option ? [option.label] : [];
                        },
                      ),
                    }
                  : undefined
              }
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
              deploymentEnvValues={{
                ...draft.deployment?.envValues,
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
              onExportYaml={() =>
                downloadText(
                  `${draft.name || "agent"}.yaml`,
                  draftToYaml(draft),
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
