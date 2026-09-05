import {
  type CSSProperties,
  Fragment,
  lazy,
  type ReactNode,
  Suspense,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { createPortal } from "react-dom";
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
} from "lucide-react";
import {
  type CreateModeProps,
  type AgentDraft,
  type CloudEnvironmentConfig,
  type HarnessSidecarOptionId,
  type HarnessSidecarProfileId,
  type McpTool,
  emptyDraft,
} from "./types";
import { createT } from "./i18n";
import {
  HARNESS_SIDECAR_OPTIONS,
  HARNESS_SIDECAR_OPTION_GROUPS,
  HARNESS_SIDECAR_PROFILES,
  harnessIntentFromOptimizations,
  harnessProfileDefaultOptimizations,
  harnessSidecarProviderNotice,
  harnessSidecarOptionLabel,
  releaseDraftFromDebugVariant,
  selectedHarnessModelProxyOptimizations,
  selectedHarnessProfile,
  selectedHarnessOptimizations,
} from "./harnessSidecarOptions";
import {
  A2A_REGISTRY_DEFAULTS,
  A2A_REGISTRY_ENV,
  a2aRegistryDefaults,
  BUILTIN_TOOLS,
  createBuiltinToolsForProvider,
  STM_BACKENDS,
  LTM_BACKENDS,
  KB_BACKENDS,
  DEFAULT_KB_BACKEND,
  TRACING_EXPORTERS,
  FEISHU_ENV,
  type BackendOption,
  type EnvVar,
} from "./veadkCatalog";
import {
  firstMissingRuntimeEnv,
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
import { localPickerMatches } from "./localPickerSearch";
import { draftToYaml } from "./configYaml";
import {
  confirmMcpCredentialReuse,
  clearMcpConfiguredAuth,
  deploymentMcpSecretValues,
  mcpAuthTokenInputValue,
  mcpCredentialActionRequired,
  mcpCredentialReuseValues,
  mcpUrlNeedsPathWarning,
  prepareMcpAuth,
  removeMcpCredentialForChangedUrl,
  replaceMcpCredentialForChangedUrl,
  removedConfiguredMcpEnvKeys,
  sourcePreservingMcpSecretValues,
  updateMcpAuthTokenInput,
  updateMcpUrlInput,
} from "./mcpAuth";
import { resolveMcpGatewayEnv } from "./mcpGatewayEnv";
import {
  normalizeDraft,
  sanitizeGeneratedDraftCapabilities,
} from "./normalizeDraft";
import {
  activeModelConfiguration,
  resolvedModelSource,
  type ModelSource,
} from "./modelSource";
import { resolveRuntimeName, runtimeNameProblem } from "./runtimeName";
import type { AgentProject } from "./project";
import { AgentBuildCanvas } from "./AgentBuildCanvas";
import {
  NewAgentWorkbench,
  type NewAgentDeploymentOptions,
} from "./NewAgentWorkbench";
import { CloudEnvironmentConfigurator } from "../ui/CloudEnvironmentConfigurator";
import { SkillSourcePicker } from "../ui/SkillSourcePicker";
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
  checkRuntimeNameAvailability,
  deleteGeneratedAgentTestRun,
  deployAgentkitProject,
  generateAgentDraftFromRequirement,
  generateAgentProject,
  listModelApiKeys,
  listModelOptions,
  type ModelApiKeyOption,
  runGeneratedAgentTestSSE,
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
    label: "traditional.sections.type.label",
    hint: "traditional.sections.type.hint",
    icon: Shapes,
    required: true,
  },
  {
    id: "basic",
    label: "traditional.sections.basic.label",
    hint: "traditional.sections.basic.hint",
    icon: Info,
    required: true,
  },
  { id: "model", label: "traditional.sections.model.label", hint: "traditional.sections.model.hint", icon: Cpu },
  { id: "tools", label: "traditional.sections.tools.label", hint: "traditional.sections.tools.hint", icon: Wrench },
  { id: "skills", label: "traditional.sections.skills.label", hint: "traditional.sections.skills.hint", icon: Sparkles },
  { id: "knowledge", label: "traditional.sections.knowledge.label", hint: "traditional.sections.knowledge.hint", icon: Database },
  { id: "memory", label: "traditional.sections.memory.label", hint: "traditional.sections.memory.hint", icon: Layers },
  { id: "subagents", label: "traditional.sections.subagents.label", hint: "traditional.sections.subagents.hint", icon: Boxes },
  { id: "review", label: "traditional.sections.review.label", hint: "traditional.sections.review.hint", icon: Rocket },
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
  llm: "traditional.agentTypes.llm.label",
  sequential: "traditional.agentTypes.sequential.label",
  parallel: "traditional.agentTypes.parallel.label",
  loop: "traditional.agentTypes.loop.label",
  a2a: "traditional.agentTypes.a2a.label",
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
  cloudProvider: CloudProvider = "volcengine",
): Record<string, string> {
  if (!registry?.enabled) return {};
  const defaults = a2aRegistryDefaults(cloudProvider);
  const values: Record<string, string> = {
    REGISTRY_SPACE_ID: registry.registrySpaceId ?? "",
  };
  if (options.includeDefaults) {
    values.REGISTRY_TOP_K = registry.registryTopK?.trim() || defaults.topK;
    values.REGISTRY_REGION = registry.registryRegion?.trim() || defaults.region;
    values.REGISTRY_ENDPOINT =
      registry.registryEndpoint?.trim() || defaults.endpoint;
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
  const a2aDefaults = a2aRegistryDefaults(cloudProvider);
  return env.map((item) => {
    if (item.key === "REGISTRY_REGION") {
      return { ...item, placeholder: a2aDefaults.region };
    }
    if (item.key === "REGISTRY_ENDPOINT") {
      return { ...item, placeholder: a2aDefaults.endpoint };
    }
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
  const { t } = useTranslation("create");
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
                <span className="cw-check-title">{t(`traditional.catalog.${it.id}.label`, { defaultValue: it.label })}</span>
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
  translationGroup,
}: {
  options: BackendOption[];
  value: string | undefined;
  onChange: (id: string) => void;
  translationGroup: "knowledge" | "shortTerm" | "longTerm";
}) {
  const { t } = useTranslation("create");
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
            <span className="cw-seg-title">
              {t(
                `traditional.backends.${translationGroup}.${o.id}.label`,
                { defaultValue: o.label },
              )}
            </span>
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
  const { t } = useTranslation("create");
  const visibleEnv = env.filter((item) => !item.hidden);
  if (visibleEnv.length === 0) {
    return <p className="cw-env-empty">{t("traditional.env.noAdditionalParameters")}</p>;
  }
  return (
    <div className="cw-env-fields">
      {visibleEnv.map((item) => {
        const value = values[item.key] ?? item.defaultValue ?? "";
        const jsonError = runtimeEnvJsonError(item, values, t("traditional.env.invalidJson"));
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
                      aria-label={t("traditional.env.helpAriaLabel", { label: item.comment || item.key, help: item.help })}
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
                      title={t("traditional.env.openOpenViking", { label: item.link.label })}
                      aria-label={t("traditional.env.openOpenViking", { label: item.link.label })}
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
                  placeholder={item.placeholder || t("traditional.env.valuePlaceholder")}
                  autoComplete="off"
                  spellCheck={false}
                  aria-invalid={!!jsonError}
                  onChange={(event) =>
                    onChange(item.key, event.currentTarget.value)
                  }
                />
              ) : (
                <input
                  id={controlId}
                  className="cw-input"
                  type={isSensitiveEnv(item.key) ? "password" : "text"}
                  value={value}
                  placeholder={item.placeholder || t("traditional.env.valuePlaceholder")}
                  autoComplete="off"
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

function OpenVikingKnowledgeIndexField({
  value,
  onChange,
}: {
  value: string;
  onChange: (index: string) => void;
}) {
  const { t } = useTranslation("create");
  const controlId = "cw-openviking-knowledge-index";
  const help = t("traditional.env.openVikingIndexHelp");
  return (
    <label className="cw-env-field" htmlFor={controlId}>
      <span className="cw-env-field-head">
        <span className="cw-env-field-title">
          <span className="cw-env-field-label">{t("traditional.env.openVikingIndex")}</span>
          <span
            className="cw-env-help"
            tabIndex={0}
            data-help={help}
            aria-label={t("traditional.env.openVikingIndexAriaLabel", { help })}
          >
            ?
            <span className="cw-env-help-popover" role="tooltip">
              {help}
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

function a2aSpaceDisplayName(space: A2aSpaceRef, fallback = createT("traditional.resources.unnamedAgentCenter")): string {
  return space.name.trim() || fallback;
}

function vikingKnowledgebaseDisplayName(item: VikingKnowledgebaseRef, fallback = createT("traditional.resources.unnamedKnowledgeBase")): string {
  const name = item.name.trim() || item.id || fallback;
  const details = [item.sourceLabel, item.projectName].filter(Boolean);
  return details.length ? `${name} · ${details.join(" · ")}` : name;
}

function vikingMemoryDisplayName(item: VikingMemoryRef, fallback = createT("traditional.resources.unnamedMemory")): string {
  return item.name.trim() || item.id || fallback;
}

function modelAvailabilityKey(model: ModelOption): string {
  if (model.available) return "traditional.model.available";
  if (model.lifecycleStatus === "Retiring") return "traditional.model.retiring";
  if (model.activationState && model.activationState !== "Available") {
    return "traditional.model.notActivated";
  }
  return "traditional.model.unavailable";
}

function isModelSelectable(model: ModelOption): boolean {
  return model.available || model.lifecycleStatus === "Retiring";
}

interface ModelMenuPosition {
  top?: number;
  bottom?: number;
  left: number;
  width: number;
  maxHeight: number;
  opensUp: boolean;
}

function CatalogSelect({
  selectedLabel,
  placeholder,
  disabled,
  triggerAriaLabel,
  menuAriaLabel,
  searchAriaLabel,
  searchValue,
  searchPlaceholder,
  onSearchChange,
  empty,
  emptyLabel,
  triggerClassName = "",
  optionsClassName = "",
  renderOptions,
}: {
  selectedLabel: string;
  placeholder: boolean;
  disabled: boolean;
  triggerAriaLabel: string;
  menuAriaLabel: string;
  searchAriaLabel: string;
  searchValue: string;
  searchPlaceholder: string;
  onSearchChange: (value: string) => void;
  empty: boolean;
  emptyLabel: string;
  triggerClassName?: string;
  optionsClassName?: string;
  renderOptions: (closeMenu: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const pickerRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const menuId = useId();
  const [menuPosition, setMenuPosition] = useState<ModelMenuPosition | null>(
    null,
  );

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (
        target instanceof Node &&
        pickerRef.current &&
        !pickerRef.current.contains(target) &&
        !menuRef.current?.contains(target)
      ) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      setMenuPosition(null);
      return;
    }
    const positionMenu = () => {
      const trigger = triggerRef.current;
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      const viewportPadding = 12;
      const gap = 6;
      const availableBelow =
        window.innerHeight - rect.bottom - viewportPadding - gap;
      const availableAbove = rect.top - viewportPadding - gap;
      const opensUp = availableBelow < 300 && availableAbove > availableBelow;
      const available = Math.max(96, opensUp ? availableAbove : availableBelow);
      const width = Math.min(
        rect.width,
        window.innerWidth - viewportPadding * 2,
      );
      const left = Math.min(
        Math.max(viewportPadding, rect.left),
        window.innerWidth - viewportPadding - width,
      );
      setMenuPosition({
        ...(opensUp
          ? { bottom: window.innerHeight - rect.top + gap }
          : { top: rect.bottom + gap }),
        left,
        width,
        maxHeight: available,
        opensUp,
      });
    };
    positionMenu();
    window.addEventListener("resize", positionMenu);
    window.addEventListener("scroll", positionMenu, true);
    return () => {
      window.removeEventListener("resize", positionMenu);
      window.removeEventListener("scroll", positionMenu, true);
    };
  }, [open]);

  const closeMenu = () => setOpen(false);
  const moveOptionFocus = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const options = Array.from(
      menuRef.current?.querySelectorAll<HTMLElement>(
        '[role="option"]:not(:disabled)',
      ) ?? [],
    );
    if (!options.length) return;
    event.preventDefault();
    const currentIndex = options.findIndex(
      (option) => option === document.activeElement,
    );
    const nextIndex =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? options.length - 1
          : event.key === "ArrowUp"
            ? currentIndex <= 0
              ? options.length - 1
              : currentIndex - 1
            : currentIndex < 0 || currentIndex === options.length - 1
              ? 0
              : currentIndex + 1;
    options[nextIndex]?.focus();
  };

  return (
    <div
      className={`cw-a2a-space-select-wrap cw-catalog-select${open ? " is-open" : ""}`}
      ref={pickerRef}
    >
      <button
        ref={triggerRef}
        type="button"
        className={`cw-a2a-space-trigger ${triggerClassName}`.trim()}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-controls={open ? menuId : undefined}
        aria-expanded={open}
        aria-label={triggerAriaLabel}
        title={selectedLabel}
        onClick={() => {
          if (!open) onSearchChange("");
          setOpen((current) => !current);
        }}
      >
        <span className={placeholder ? "is-placeholder" : undefined}>
          {selectedLabel}
        </span>
        <A2aSelectChevronIcon className="cw-a2a-space-trigger-icon" />
      </button>
      {open &&
        menuPosition &&
        createPortal(
          <div
            ref={menuRef}
            className={`cw-a2a-space-menu cw-catalog-menu cw-catalog-menu-portal${menuPosition.opensUp ? " is-up" : ""}`}
            style={{
              top: menuPosition.top ?? "auto",
              bottom: menuPosition.bottom ?? "auto",
              left: menuPosition.left,
              width: menuPosition.width,
              maxHeight: menuPosition.maxHeight,
            }}
            onKeyDown={moveOptionFocus}
          >
            <div className="cw-picker-search">
              <input
                className="cw-picker-search-input"
                type="search"
                value={searchValue}
                autoFocus
                autoComplete="off"
                aria-label={searchAriaLabel}
                placeholder={searchPlaceholder}
                onChange={(event) => onSearchChange(event.currentTarget.value)}
              />
            </div>
            <div
              id={menuId}
              className={`cw-picker-options cw-catalog-options ${optionsClassName}`.trim()}
              role="listbox"
              aria-label={menuAriaLabel}
            >
              {renderOptions(closeMenu)}
              {empty && <div className="cw-picker-empty">{emptyLabel}</div>}
            </div>
          </div>,
          document.body,
        )}
    </div>
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
  const { t } = useTranslation("create");
  const [apiKeys, setApiKeys] = useState<ModelApiKeyOption[]>([]);
  const [keysLoading, setKeysLoading] = useState(false);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [modelsApiKeyId, setModelsApiKeyId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [keySelectionRevision, setKeySelectionRevision] = useState(0);
  const [apiKeySearchQuery, setApiKeySearchQuery] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setKeysLoading(true);
    setError(null);
    listModelApiKeys(controller.signal, reloadKey > 0)
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
            err instanceof Error ? err.message : t("traditional.model.apiKeyLoadError"),
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setKeysLoading(false);
      });
    return () => controller.abort();
  }, [cloudProvider, reloadKey, t]);

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
      refresh: reloadKey > 0 || keySelectionRevision > 0,
    })
      .then((response) => {
        if (!controller.signal.aborted) {
          setModels(response.models);
          setModelsApiKeyId(apiKeyId);
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : t("traditional.model.loadError"));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [apiKeyId, cloudProvider, keySelectionRevision, reloadKey, t]);

  const normalizedValue = value.trim();
  const modelsAreCurrent = modelsApiKeyId === apiKeyId;
  const visibleModels = modelsAreCurrent ? models : [];
  const selectedApiKey = apiKeys.find((key) => key.id === apiKeyId);
  const selectedApiKeyLabel = selectedApiKey
    ? selectedApiKey.name
    : apiKeyId
      ? t("traditional.model.currentApiKey")
      : keysLoading
        ? t("traditional.model.loadingApiKeys")
        : apiKeys.length === 0
          ? t("traditional.model.noApiKeys")
          : t("traditional.model.selectApiKey");
  const filteredApiKeys = useMemo(
    () =>
      apiKeys.filter((key) =>
        localPickerMatches(apiKeySearchQuery, [key.name]),
      ),
    [apiKeySearchQuery, apiKeys],
  );
  const selectedModel = visibleModels.find(
    (model) => model.id === normalizedValue,
  );
  const selectedLabel =
    loading && !modelsAreCurrent
      ? t("traditional.model.refreshing")
      : selectedModel
        ? `${selectedModel.displayName} (${selectedModel.id})`
        : normalizedValue || t("traditional.model.selectModel");
  const filteredModels = useMemo(
    () =>
      visibleModels.filter((model) =>
        localPickerMatches(searchQuery, [
          model.displayName,
          model.id,
          model.name,
          model.vendorName,
          model.activationState,
          model.lifecycleStatus,
        ]),
      ),
    [searchQuery, visibleModels],
  );
  const showUnknownModel = Boolean(
    normalizedValue &&
    !selectedModel &&
    localPickerMatches(searchQuery, [normalizedValue]),
  );
  const availableCount = visibleModels.filter(
    (model) => model.available,
  ).length;
  const providerLabel =
    cloudProvider === "byteplus" ? "BytePlus ModelArk" : t("traditional.model.volcengineArk");
  const activationConsoleUrl = modelActivationConsoleUrl(cloudProvider);

  return (
    <div className="cw-a2a-space-picker cw-model-picker">
      <div className="cw-model-picker-stack">
        <div className="cw-model-picker-field">
          <span className="cw-model-picker-label">API Key</span>
          <CatalogSelect
            selectedLabel={selectedApiKeyLabel}
            placeholder={!apiKeyId}
            disabled={keysLoading}
            triggerAriaLabel={t("traditional.model.selectApiKey")}
            menuAriaLabel={t("traditional.model.apiKeyList")}
            searchAriaLabel={t("traditional.model.searchApiKey")}
            searchValue={apiKeySearchQuery}
            searchPlaceholder={t("traditional.model.searchApiKeyName")}
            onSearchChange={setApiKeySearchQuery}
            empty={filteredApiKeys.length === 0}
            emptyLabel={t("traditional.model.noMatchingApiKey")}
            optionsClassName="cw-model-key-options"
            renderOptions={(closeMenu) =>
              filteredApiKeys.map((key) => {
                const selected = key.id === apiKeyId;
                return (
                  <button
                    key={key.id}
                    type="button"
                    role="option"
                    aria-selected={selected}
                    className={`cw-a2a-space-option cw-model-key-option ${
                      selected ? "is-selected" : ""
                    }`}
                    title={key.name}
                    onClick={() => {
                      setKeySelectionRevision((revision) => revision + 1);
                      onApiKeyChange(key);
                      closeMenu();
                    }}
                  >
                    <span>{key.name}</span>
                  </button>
                );
              })
            }
          />
        </div>
        <div className="cw-model-picker-field">
          <span className="cw-model-picker-label">{t("traditional.model.label")}</span>
          <div className="cw-a2a-space-row">
            <CatalogSelect
              selectedLabel={selectedLabel}
              placeholder={!normalizedValue}
              disabled={loading}
              triggerAriaLabel={t("traditional.model.selectProviderModel", { provider: providerLabel })}
              menuAriaLabel={t("traditional.model.providerModels", { provider: providerLabel })}
              searchAriaLabel={t("traditional.model.search")}
              searchValue={searchQuery}
              searchPlaceholder={t("traditional.model.searchPlaceholder")}
              onSearchChange={setSearchQuery}
              empty={!showUnknownModel && filteredModels.length === 0}
              emptyLabel={t("traditional.model.noMatches")}
              triggerClassName="cw-model-trigger"
              optionsClassName="cw-model-options"
              renderOptions={(closeMenu) => (
                <>
                  {showUnknownModel && (
                    <button
                      type="button"
                      role="option"
                      aria-selected
                      className="cw-a2a-space-option cw-model-option is-selected"
                      onClick={() => {
                        onChange(normalizedValue);
                        closeMenu();
                      }}
                    >
                      <span className="cw-model-option-copy">
                        <strong>{t("traditional.model.currentConfiguration")}</strong>
                        <small>{normalizedValue}</small>
                      </span>
                      <span className="cw-model-status is-unknown">
                        {t("traditional.model.unknownStatus")}
                      </span>
                    </button>
                  )}
                  {filteredModels.map((model) => {
                    const selected = model.id === normalizedValue;
                    const selectable = isModelSelectable(model);
                    const activationRequired =
                      !selectable && model.activationState !== "Available";
                    if (activationRequired) {
                      return (
                        <button
                          key={model.id}
                          type="button"
                          role="option"
                          aria-selected={false}
                          className="cw-a2a-space-option cw-model-option is-activation-link"
                          title={t("traditional.model.activate", { provider: providerLabel, model: model.displayName })}
                          onClick={() => {
                            window.open(
                              activationConsoleUrl,
                              "_blank",
                              "noopener,noreferrer",
                            );
                            closeMenu();
                          }}
                        >
                          <span className="cw-model-option-copy">
                            <strong>{model.displayName}</strong>
                            <small>
                              {model.id}
                              {model.vendorName ? ` · ${model.vendorName}` : ""}
                            </small>
                          </span>
                          <span className="cw-model-status is-unavailable">
                            {t("traditional.model.activateAction")}
                          </span>
                        </button>
                      );
                    }
                    return (
                      <button
                        key={model.id}
                        type="button"
                        role="option"
                        aria-selected={selected}
                        disabled={!selectable}
                        className={`cw-a2a-space-option cw-model-option ${
                          selected ? "is-selected" : ""
                        }`}
                        title={`${model.displayName} (${model.id})`}
                        onClick={() => {
                          onChange(model.id);
                          closeMenu();
                        }}
                      >
                        <span className="cw-model-option-copy">
                          <strong>{model.displayName}</strong>
                          <small>
                            {model.id}
                            {model.vendorName ? ` · ${model.vendorName}` : ""}
                          </small>
                        </span>
                        <span
                          className={`cw-model-status ${
                            model.available
                              ? "is-available"
                              : model.lifecycleStatus === "Retiring"
                                ? "is-retiring"
                                : "is-unavailable"
                          }`}
                        >
                          {t(modelAvailabilityKey(model))}
                        </span>
                      </button>
                    );
                  })}
                </>
              )}
            />
            <button
              type="button"
              className="cw-icon-btn cw-a2a-space-refresh"
              title={t("traditional.model.refresh")}
              aria-label={t("traditional.model.refresh")}
              disabled={loading || keysLoading}
              onClick={() => setReloadKey((key) => key + 1)}
            >
              {loading || keysLoading ? (
                <Loader2 className="cw-i cw-i-sm cw-spin" />
              ) : (
                <A2aRefreshIcon className="cw-i cw-i-sm" />
              )}
            </button>
          </div>
        </div>
      </div>
      {error ? (
        <div className="cw-banner cw-a2a-space-error" role="alert">
          <Info className="cw-i" />
          <span>{error}</span>
        </div>
      ) : loading ? (
        <span className="cw-help cw-a2a-space-status" aria-live="polite">
          <Loader2 className="cw-i cw-i-sm cw-spin" />
          {t("traditional.model.loading")}
        </span>
      ) : visibleModels.length === 0 ? (
        <span className="cw-help">{t("traditional.model.empty")}</span>
      ) : (
        <span className="cw-help">
          {t("traditional.model.loaded", { count: visibleModels.length, available: availableCount })}
        </span>
      )}
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
  const { t } = useTranslation("create");
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
          setError(err instanceof Error ? err.message : t("traditional.resources.loadError"));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [normalizedRegion, reloadKey, t]);

  const selectedKnown =
    !value || spaces.some((space) => space.id === value.trim());
  const selectedSpace = spaces.find((space) => space.id === value.trim());
  const selectedLabel = selectedSpace
    ? a2aSpaceDisplayName(selectedSpace, t("traditional.resources.unnamedAgentCenter"))
    : value && !selectedKnown
      ? t("traditional.resources.selectedAgentCenter")
      : t("traditional.resources.selectAgentCenter");
  const disabled = loading && spaces.length === 0;
  const filteredSpaces = useMemo(
    () =>
      spaces.filter((space) =>
        localPickerMatches(searchQuery, [
          a2aSpaceDisplayName(space, t("traditional.resources.unnamedAgentCenter")),
          space.id,
          space.projectName,
        ]),
      ),
    [searchQuery, spaces, t],
  );
  const showUnknownSpace = Boolean(
    value &&
    !selectedKnown &&
    localPickerMatches(searchQuery, [t("traditional.resources.selectedAgentCenter"), value]),
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
    <div
      className={`cw-a2a-space-picker${open ? " is-open" : ""}`}
      ref={pickerRef}
    >
      <div className="cw-a2a-space-row">
        <div className="cw-a2a-space-select-wrap">
          <button
            type="button"
            className={`cw-a2a-space-trigger ${invalid ? "is-error" : ""}`}
            disabled={disabled}
            aria-haspopup="listbox"
            aria-expanded={open}
            aria-label={t("traditional.resources.selectAgentKitCenter")}
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
            <div className="cw-a2a-space-menu">
              <div className="cw-picker-search">
                <input
                  className="cw-picker-search-input"
                  type="search"
                  value={searchQuery}
                  autoFocus
                  autoComplete="off"
                  aria-label={t("traditional.resources.searchAgentKitCenter")}
                  placeholder={t("traditional.resources.searchNameOrId")}
                  onChange={(event) =>
                    setSearchQuery(event.currentTarget.value)
                  }
                />
              </div>
              <div
                className="cw-picker-options"
                role="listbox"
                aria-label={t("traditional.resources.agentKitCenter")}
              >
                {showUnknownSpace && (
                  <button
                    type="button"
                    role="option"
                    aria-selected
                    className="cw-a2a-space-option is-selected"
                    onClick={() => selectSpace(value)}
                  >
                    {t("traditional.resources.selectedAgentCenter")}
                  </button>
                )}
                {filteredSpaces.map((space) => {
                  const optionLabel = a2aSpaceDisplayName(space, t("traditional.resources.unnamedAgentCenter"));
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
                  <div className="cw-picker-empty">{t("traditional.resources.noMatchingAgentCenters")}</div>
                )}
              </div>
            </div>
          )}
        </div>
        <button
          type="button"
          className="cw-icon-btn cw-a2a-space-refresh"
          title={t("traditional.resources.refreshAgentCenters")}
          aria-label={t("traditional.resources.refreshAgentCenters")}
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
          {t("traditional.resources.loadingAgentCenters")}
        </span>
      ) : spaces.length === 0 ? (
        <span className="cw-help">{t("traditional.resources.noAgentCenters")}</span>
      ) : (
        <span className="cw-help">
          {t("traditional.resources.agentCentersLoaded", { count: spaces.length })}
        </span>
      )}
    </div>
  );
}

type ResourcePickerItem = { id: string };

function ResourcePicker<T extends ResourcePickerItem>({
  value,
  items,
  loading,
  error,
  pickerClassName,
  selectLabel,
  searchLabel,
  listLabel,
  placeholder,
  emptyMessage,
  loadedMessage,
  refreshLabel,
  noMatchesMessage,
  getLabel,
  getSearchFields,
  getKey,
  getOptionIds,
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
  const { t } = useTranslation("create");
  const [open, setOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const pickerRef = useRef<HTMLDivElement | null>(null);

  const selectedKnown =
    !value || items.some((item) => item.id === value.trim());
  const selectedItem = items.find((item) => item.id === value.trim());
  const selectedLabel = selectedItem
    ? getLabel(selectedItem)
    : value && !selectedKnown
      ? value
      : placeholder;
  const disabled = loading && items.length === 0;
  const filteredItems = useMemo(
    () =>
      items.filter((item) =>
        localPickerMatches(searchQuery, getSearchFields(item)),
      ),
    [getSearchFields, items, searchQuery],
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

  const selectItem = (item: T) => {
    onChange(item);
    setOpen(false);
  };

  if (loading && items.length === 0) {
    return (
      <span className="cw-viking-kb-inline-status" role="status">
        <Loader2 className="cw-i cw-i-sm cw-spin" />
        {t("common.loading")}
      </span>
    );
  }

  return (
    <div
      className={`cw-a2a-space-picker ${pickerClassName}${open ? " is-open" : ""}`}
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
            aria-label={selectLabel}
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
            <div className="cw-a2a-space-menu cw-viking-kb-menu">
              <div className="cw-picker-search">
                <input
                  className="cw-picker-search-input"
                  type="search"
                  value={searchQuery}
                  autoFocus
                  autoComplete="off"
                  aria-label={searchLabel}
                  placeholder={t("traditional.resources.searchNameOrId")}
                  onChange={(event) =>
                    setSearchQuery(event.currentTarget.value)
                  }
                />
              </div>
              <div
                className="cw-picker-options"
                role="listbox"
                aria-label={listLabel}
              >
                {showUnknownItem && (
                  <button
                    type="button"
                    role="option"
                    aria-selected
                    className="cw-a2a-space-option is-selected"
                    onClick={() => selectItem(makeUnknownItem(value))}
                  >
                    {value}
                  </button>
                )}
                {filteredItems.map((item) => {
                  const optionLabel = getLabel(item);
                  const selected = item.id === value;
                  const optionIds = getOptionIds(item)
                    .filter(Boolean)
                    .join(" / ");
                  return (
                    <button
                      key={getKey(item)}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      className={`cw-a2a-space-option ${
                        selected ? "is-selected" : ""
                      }`}
                      title={
                        optionIds
                          ? `${optionLabel} (${optionIds})`
                          : optionLabel
                      }
                      onClick={() => selectItem(item)}
                    >
                      {optionLabel}
                    </button>
                  );
                })}
                {!showUnknownItem && filteredItems.length === 0 && (
                  <div className="cw-picker-empty">{noMatchesMessage}</div>
                )}
              </div>
            </div>
          )}
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
        <div className="cw-banner cw-a2a-space-error">
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
  const { t } = useTranslation("create");
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
          setError(err instanceof Error ? err.message : t("traditional.resources.loadError"));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey, t]);

  return (
    <ResourcePicker
      value={value}
      items={items}
      loading={loading}
      error={error}
      pickerClassName="cw-viking-kb-picker"
      selectLabel={t("traditional.resources.selectKnowledgeBase")}
      searchLabel={t("traditional.resources.searchKnowledgeBase")}
      listLabel={t("traditional.resources.knowledgeBaseList")}
      placeholder={t("traditional.resources.knowledgeBasePlaceholder")}
      emptyMessage={t("traditional.resources.noKnowledgeBases")}
      loadedMessage={(count) =>
        t("traditional.resources.knowledgeBasesLoaded", { count })
      }
      refreshLabel={t("traditional.resources.refreshKnowledgeBases")}
      noMatchesMessage={t("traditional.resources.noMatchingKnowledgeBases")}
      getLabel={(item) => vikingKnowledgebaseDisplayName(item, t("traditional.resources.unnamedKnowledgeBase"))}
      getSearchFields={(item) => [
        vikingKnowledgebaseDisplayName(item, t("traditional.resources.unnamedKnowledgeBase")),
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
  const { t } = useTranslation("create");
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
          setError(err instanceof Error ? err.message : t("traditional.resources.loadError"));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey, t]);

  return (
    <ResourcePicker
      value={value}
      items={items}
      loading={loading}
      error={error}
      pickerClassName="cw-viking-memory-picker"
      selectLabel={t("traditional.resources.selectMemory")}
      searchLabel={t("traditional.resources.searchMemory")}
      listLabel={t("traditional.resources.memoryList")}
      placeholder={t("traditional.resources.memoryPlaceholder")}
      emptyMessage={t("traditional.resources.noMemories")}
      loadedMessage={(count) =>
        t("traditional.resources.memoriesLoaded", { count })
      }
      refreshLabel={t("traditional.resources.refreshMemories")}
      noMatchesMessage={t("traditional.resources.noMatchingMemories")}
      getLabel={(item) => vikingMemoryDisplayName(item, t("traditional.resources.unnamedMemory"))}
      getSearchFields={(item) => [
        vikingMemoryDisplayName(item, t("traditional.resources.unnamedMemory")),
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
  const { t } = useTranslation("create");
  const update = (i: number, p: Partial<McpTool>) =>
    onChange(tools.map((tool, idx) => (idx === i ? { ...tool, ...p } : tool)));

  const remove = (i: number) => onChange(tools.filter((_, idx) => idx !== i));

  const add = () =>
    onChange([...tools, { name: "", transport: "http", url: "" }]);

  return (
    <div className="cw-mcp">
      {tools.length > 0 && (
        <div className="cw-mcp-list">
          <AnimatePresence initial={false}>
            {tools.map((tool, i) => (
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
                        tool.transport === "http" ? "is-on" : ""
                      }`}
                      onClick={() => update(i, { transport: "http" })}
                      aria-pressed={tool.transport === "http"}
                    >
                      <span className="cw-seg-title">HTTP</span>
                    </button>
                    <button
                      type="button"
                      className={`cw-seg cw-seg-sm ${
                        tool.transport === "stdio" ? "is-on" : ""
                      }`}
                      onClick={() => update(i, { transport: "stdio" })}
                      aria-pressed={tool.transport === "stdio"}
                    >
                      <span className="cw-seg-title">stdio</span>
                    </button>
                  </div>
                  <button
                    type="button"
                    className="cw-icon-btn cw-icon-danger"
                    onClick={() => remove(i)}
                    aria-label={t("traditional.mcp.removeTool")}
                  >
                    <Trash2 className="cw-i cw-i-sm" />
                  </button>
                </div>

                <input
                  className="cw-input"
                  value={tool.name}
                  placeholder={t("traditional.mcp.namePlaceholder")}
                  onChange={(e) => update(i, { name: e.target.value })}
                />

                {tool.transport === "http" ? (
                  <>
                    <input
                      className="cw-input"
                      value={tool.url ?? ""}
                      placeholder={t("traditional.mcp.urlPlaceholder")}
                      onChange={(e) =>
                        onChange(
                          tools.map((tool, index) =>
                            index === i
                              ? updateMcpUrlInput(tool, e.target.value)
                              : tool,
                          ),
                        )
                      }
                    />
                    {mcpUrlNeedsPathWarning(tool.url ?? "") && (
                      <p className="cw-mcp-warning">
                        <Info aria-hidden="true" />
                        <span>
                          {t("traditional.mcp.pathWarning")}
                        </span>
                      </p>
                    )}
                    <input
                      className="cw-input"
                      aria-invalid={mcpCredentialActionRequired(tool)}
                      value={mcpAuthTokenInputValue(tool)}
                      placeholder={
                        tool.credentialConfigured && !tool.authToken
                          ? t("traditional.mcp.configuredPlaceholder")
                          : t("traditional.mcp.tokenPlaceholder")
                      }
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
                    {tool.credentialUpdate === "pending" && (
                      <div
                        className="cw-mcp-auth-state is-warning"
                        role="alert"
                      >
                        <span>
                          {t("traditional.mcp.changedUrlWarning")}
                        </span>
                        <div className="cw-mcp-auth-actions">
                          <button
                            type="button"
                            onClick={() =>
                              onChange(
                                tools.map((tool, index) =>
                                  index === i
                                    ? confirmMcpCredentialReuse(tool)
                                    : tool,
                                ),
                              )
                            }
                          >
                            {t("traditional.mcp.reuseCredential")}
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              onChange(
                                tools.map((tool, index) =>
                                  index === i
                                    ? replaceMcpCredentialForChangedUrl(tool)
                                    : tool,
                                ),
                              )
                            }
                          >
                            {t("traditional.mcp.replaceCredential")}
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              onChange(
                                tools.map((tool, index) =>
                                  index === i
                                    ? removeMcpCredentialForChangedUrl(tool)
                                    : tool,
                                ),
                              )
                            }
                          >
                            {t("traditional.mcp.noAuth")}
                          </button>
                        </div>
                      </div>
                    )}
                    {tool.credentialUpdate === "reuse" && (
                      <div className="cw-mcp-auth-state" role="status">
                        <span>{t("traditional.mcp.reuseHint")}</span>
                        <button
                          type="button"
                          onClick={() =>
                            onChange(
                              tools.map((tool, index) =>
                                index === i
                                  ? replaceMcpCredentialForChangedUrl(tool)
                                  : tool,
                              ),
                            )
                          }
                        >
                          {t("traditional.mcp.changeToReplace")}
                        </button>
                      </div>
                    )}
                    {tool.credentialConfigured &&
                      !tool.authToken &&
                      !tool.credentialUpdate && (
                      <div className="cw-mcp-auth-state" role="status">
                        <span>{t("traditional.mcp.credentialConfigured")}</span>
                        <button
                          type="button"
                          onClick={() =>
                            onChange(
                              tools.map((tool, index) =>
                                index === i
                                  ? clearMcpConfiguredAuth(tool)
                                  : tool,
                              ),
                            )
                          }
                        >
                          {t("traditional.mcp.removeCredential")}
                        </button>
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <input
                      className="cw-input"
                      value={tool.command ?? ""}
                      placeholder={t("traditional.mcp.commandPlaceholder")}
                      onChange={(e) => update(i, { command: e.target.value })}
                    />
                    <input
                      className="cw-input"
                      value={(tool.args ?? []).join(" ")}
                      placeholder={t("traditional.mcp.argsPlaceholder")}
                      onChange={(e) =>
                        update(i, {
                          args: e.target.value.split(/\s+/).filter(Boolean),
                        })
                      }
                    />
                    <p className="cw-mcp-note">
                      {t("traditional.mcp.stdioHint")}
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
        {t("traditional.mcp.addTool")}
      </button>
    </div>
  );
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
): NodeProblemCode | null {
  if (isA2aType(n.agentType)) {
    if (isRoot) return "remoteRoot";
    return n.a2aRegistry?.registrySpaceId.trim()
      ? null
      : "missingRegistry";
  }
  const nameProblem = agentNameProblem(n.name, (key) => `name.${key}`);
  if (nameProblem) return nameProblem as NodeProblemCode;
  if (duplicateNames.has(n.name)) return "duplicateName";
  if (n.description.trim().length === 0) return "missingDescription";
  if ((n.mcpTools ?? []).some(mcpCredentialActionRequired)) {
    return "mcpAuthRequired";
  }
  if (isOrchestratorType(n.agentType))
    return n.subAgents.length === 0 ? "missingSubagent" : null;
  return n.instruction.trim().length === 0 ? "missingPrompt" : null;
}

type NodeProblemCode =
  | "remoteRoot"
  | "missingRegistry"
  | "name.required"
  | "name.reserved"
  | "name.characters"
  | "duplicateName"
  | "missingDescription"
  | "mcpAuthRequired"
  | "missingSubagent"
  | "missingPrompt";

interface TreeProblem {
  path: NodePath;
  name: string;
  agentType: AgentDraft["agentType"];
  problem: NodeProblemCode;
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
      name: remote ? "" : root.name.trim(),
      agentType: root.agentType,
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

function validationProblemMessage(problem: TreeProblem, t: TFunction): string {
  if (problem.problem === "missingSubagent") {
    return t("traditional.validation.missingSubagentDetail", {
      type: t(
        `traditional.agentTypes.${problem.agentType ?? "llm"}.fullLabel`,
      ),
    });
  }
  const name = isA2aType(problem.agentType)
    ? t("traditional.agentTypes.a2a.fullLabel")
    : problem.name || t("traditional.basic.unnamed");
  return t("traditional.validation.problem", {
    name,
    problem: t(`traditional.validation.${problem.problem}`),
  });
}

/** Count the root Agent and every nested sub-Agent in the draft. */
function countDraftAgents(root: AgentDraft): number {
  return (
    1 +
    root.subAgents.reduce((total, child) => total + countDraftAgents(child), 0)
  );
}

/** Collect only settings used by active components across the Agent tree. */
function collectDeploymentEnv(
  root: AgentDraft,
  sourcePreserving = false,
): RuntimeEnvConfiguration {
  const prepared = prepareMcpAuth(root);
  const mcpGatewayManaged = selectedHarnessOptimizations(prepared.draft).includes(
    "mcp_resilience",
  );
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
              secret: true,
              readOnly: mcpGatewayManaged,
              serverManaged: mcpGatewayManaged,
              hidden: mcpGatewayManaged,
            },
          ],
        });
      }
    }
    if (node.a2aRegistry?.enabled) {
      selections.push({
        env: providerRuntimeEnv(A2A_REGISTRY_ENV, cloudProvider),
      });
      Object.assign(
        fixedValues,
        a2aRegistryEnvValues(
          node.a2aRegistry,
          { includeDefaults: true },
          cloudProvider,
        ),
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
          placeholder: createT("helpers.deploymentEnv.selectedApiKeyPlaceholder"),
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
  if (mcpGatewayManaged) {
    if (sourcePreserving) {
      selections.push({
        env: [
          {
            key: "MCP_SERVERS_JSON",
            required: true,
            comment: createT("helpers.deploymentEnv.mcpInjectedComment"),
            placeholder: createT("helpers.deploymentEnv.restoredPlaceholder"),
            help: createT("helpers.deploymentEnv.restoredHelp"),
            readOnly: true,
            serverManaged: true,
            hidden: true,
            requiredBy: [harnessSidecarOptionLabel("mcp_resilience")],
          },
        ],
      });
      const config = runtimeEnvConfiguration(selections);
      return {
        specs: config.specs,
        fixedValues: { ...config.fixedValues, ...fixedValues },
      };
    }
    const gatewayEnv = resolveMcpGatewayEnv(prepared.draft);
    const gatewayError = gatewayEnv.ok ? undefined : gatewayEnv.message;
    selections.push({
      env: [
        {
          key: "MCP_SERVERS_JSON",
          required: true,
          comment: createT("helpers.deploymentEnv.mcpInjectedComment"),
          placeholder: sourcePreserving
            ? createT("helpers.deploymentEnv.restoredPlaceholder")
            : createT("helpers.deploymentEnv.generatedMcpPlaceholder"),
          help: createT("helpers.deploymentEnv.mergedMcpHelp"),
          secret: true,
          readOnly: true,
          serverManaged: gatewayEnv.ok,
          hidden: true,
          requiredBy: [harnessSidecarOptionLabel("mcp_resilience")],
          missingError: gatewayError,
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
  const { t } = useTranslation("create");
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
              ? t("traditional.agentTypes.a2a.fullLabel")
              : node.name.trim() || t("traditional.basic.unnamed")}
          </span>
          <span className="cw-tree-type">
            {t(`traditional.agentTypes.${meta.id}.fullLabel`)}
          </span>
        </span>
        <span className="cw-tree-actions">
          {isRoot && (
            <button
              type="button"
              className="cw-icon-btn cw-tree-clear"
              title={t("traditional.actions.clearRoot")}
              aria-label={t("traditional.actions.clearRoot")}
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
              title={t("traditional.actions.addSubagent")}
              aria-label={t("traditional.actions.addSubagent")}
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
              title={t("common.delete")}
              aria-label={t("common.delete")}
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

type WorkspaceMode =
  "build" | "validate" | "optimize" | "environment" | "publish";
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

function debugVariantDisplayName(
  variant: Pick<DebugVariant, "id" | "name">,
  t: TFunction,
): string {
  if (variant.id === "baseline") return t("traditional.debug.baseline");
  const sequence = /^variant-(\d+)$/.exec(variant.id)?.[1];
  return sequence
    ? t("traditional.debug.comparison", { count: Number(sequence) })
    : variant.name;
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
          Object.entries(initialEnvValues).filter(
            ([key]) => !secretKeys.has(key),
          ),
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

function DebugComparisonWorkspace({
  enabled,
  disabledReason,
  variants,
  draftSnapshot,
  input,
  onInput,
  onSend,
  onStartVariant,
  onUseVariant,
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
  onUseVariant: (id: string) => void;
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
  const { t } = useTranslation("create");
  const runningVariants = variants.filter((variant) => {
    if (variant.phase !== "ready") return false;
    return (
      variant.runtimeSnapshot === debugVariantSnapshot(draftSnapshot, variant)
    );
  });
  const sending = variants.some((variant) => variant.phase === "sending");
  const canSend = runningVariants.length > 0 && !sending;

  return (
    <section className="cw-ab-workspace" aria-label={t("traditional.debug.ariaLabel")}>
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
              const variantName = debugVariantDisplayName(variant, t);
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
                variant.messages.some(
                  (message) => message.role === "assistant",
                );
              const startDisabled =
                busy || variant.configOpen || configurationUnavailable;
              const disabledReason = !modelName
                ? t("traditional.debug.selectModel")
                : !description
                  ? t("traditional.debug.enterDescription")
                  : !instruction
                    ? t("traditional.debug.enterPrompt")
                    : duplicateConfiguration
                      ? t("traditional.debug.duplicateConfiguration")
                      : "";
              const startLabel = starting
                ? t("traditional.debug.starting")
                : stale
                  ? t("traditional.debug.applyAndRestart")
                  : ready
                    ? t("traditional.debug.restart")
                    : variant.phase === "error"
                      ? t("traditional.debug.restart")
                      : t("traditional.debug.start");
              return (
                <article key={variant.id} className="cw-ab-card">
                  <div
                    className={`cw-ab-card-inner${variant.configOpen ? " is-flipped" : ""}`}
                  >
                    <section
                      className="cw-ab-card-face cw-ab-card-front"
                      aria-hidden={variant.configOpen}
                    >
                      <header className="cw-ab-card-head">
                        <div className="cw-ab-card-title">
                          <strong>{variantName}</strong>
                          <span>{variant.modelName || t("traditional.debug.defaultModel")}</span>
                        </div>
                        <div className="cw-ab-card-actions">
                          <button
                            type="button"
                            className="cw-ab-config-trigger"
                            disabled={variant.configOpen || busy}
                            onClick={() => onToggleConfig(variant.id)}
                          >
                            {t("traditional.debug.testConfiguration")}
                          </button>
                          {variant.id !== "baseline" && (
                            <button
                              type="button"
                              className="cw-ab-remove"
                              aria-label={t("traditional.debug.deleteVariant", { name: variantName })}
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
                            <span>{t("traditional.debug.creatingEnvironment")}</span>
                          </div>
                        ) : stale ? (
                          <div className="cw-ab-empty cw-ab-launch">
                            <span>{t("traditional.debug.configurationChanged")}</span>
                          </div>
                        ) : variant.messages.length === 0 ? (
                          <div className="cw-ab-empty cw-ab-launch">
                            {ready ? (
                              <>
                                <strong className="cw-ab-ready-title">
                                  {t("traditional.debug.ready")}
                                </strong>
                                <span className="cw-ab-launch-hint">
                                  {t("traditional.debug.readyHint")}
                                </span>
                              </>
                            ) : (
                              <span className="cw-ab-launch-hint">
                                {disabledReason || t("traditional.debug.startHint")}
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
                                ) : message.blocks &&
                                  message.blocks.length > 0 ? (
                                  <Blocks
                                    blocks={message.blocks}
                                    onAction={() => {}}
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

                      <footer className="cw-ab-deploy-footer">
                        <button
                          type="button"
                          className="cw-ab-trace"
                          disabled={!traceAvailable}
                          title={
                            traceAvailable
                              ? t("traditional.debug.viewTraceNamed", { name: variantName })
                              : t("traditional.debug.traceUnavailable")
                          }
                          onClick={() => onOpenTrace(variant.id)}
                        >
                          {t("traditional.debug.trace")}
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
                          onClick={() => onUseVariant(variant.id)}
                        >
                          {t("traditional.debug.useConfiguration")}
                        </button>
                      </footer>
                    </section>

                    <section
                      className="cw-ab-card-face cw-ab-card-back"
                      aria-hidden={!variant.configOpen}
                    >
                      <header className="cw-ab-config-head">
                        <div>
                          <strong>{t("traditional.debug.testConfiguration")}</strong>
                          <span>{variantName}</span>
                        </div>
                        <div className="cw-ab-config-head-actions">
                          {variant.id !== "baseline" && (
                            <button
                              type="button"
                              className="cw-icon-btn cw-icon-danger cw-ab-config-remove"
                              aria-label={t("traditional.debug.deleteVariant", { name: variantName })}
                              title={t("traditional.debug.deleteVariantGroup")}
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
                              {variant.id === "baseline"
                                ? t("traditional.debug.finishConfiguration")
                                : t("traditional.debug.finishAndStart")}
                            </button>
                            {disabledReason && (
                              <span
                                className="cw-ab-config-done-tip"
                                role="tooltip"
                              >
                                {disabledReason}
                              </span>
                            )}
                          </span>
                        </div>
                      </header>
                      <div className="cw-ab-config">
                        <label>
                          <span>{t("traditional.model.label")}</span>
                          <input
                            value={variant.modelName}
                            placeholder={t("traditional.debug.currentAgentModel")}
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
                          <span>{t("common.description")}</span>
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
                          <span>{t("traditional.basic.systemPrompt")}</span>
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
                        <p>{t("traditional.debug.configurationHint")}</p>
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
                ? t("traditional.debug.messagePlaceholder")
                : t("traditional.debug.startOneFirst")
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
            title={t("common.send")}
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
            {t("traditional.debug.addVariant")}
          </button>
        )}
      </div>
    </section>
  );
}

function HarnessOptimizationWorkspace({
  profile,
  optimizations,
  unavailableMessage,
  onProfileChange,
  onOptimizationChange,
}: {
  profile: HarnessSidecarProfileId;
  optimizations: HarnessSidecarOptionId[];
  unavailableMessage?: string | null;
  onProfileChange: (profile: HarnessSidecarProfileId) => void;
  onOptimizationChange: (
    optionId: HarnessSidecarOptionId,
    selected: boolean,
  ) => void;
}) {
  const { t } = useTranslation("create");
  return (
    <section
      className="cw-optimize-workspace"
      aria-label={t("traditional.optimization.ariaLabel")}
    >
      <div className="cw-optimize-panel">
        {unavailableMessage ? (
          <div className="cw-banner" role="alert">
            <Info className="cw-i" />
            <span>{unavailableMessage}</span>
          </div>
        ) : null}
        <fieldset className="cw-optimize-section">
          <legend>{t("traditional.optimization.scenario")}</legend>
          <RadioGroup<HarnessSidecarProfileId>
            className="cw-optimize-profile-options"
            aria-label={t("traditional.optimization.scenario")}
            value={profile}
            onChange={onProfileChange}
          >
            {HARNESS_SIDECAR_PROFILES.map((item) => (
              <div
                key={item.id}
                className={`cw-optimize-profile-option${
                  profile === item.id ? " is-on" : ""
                }`}
              >
                <RadioGroup.Item
                  value={item.id}
                  block
                  className="cw-optimize-profile-control"
                >
                  <span className="cw-optimize-profile-copy">
                    <strong>
                      {t(`traditional.optimization.profiles.${item.id}.label`)}
                    </strong>
                    <small>
                      {t(
                        `traditional.optimization.profiles.${item.id}.description`,
                      )}
                    </small>
                  </span>
                </RadioGroup.Item>
              </div>
            ))}
          </RadioGroup>
        </fieldset>

        <fieldset className="cw-optimize-section">
          <legend>{t("traditional.optimization.components")}</legend>
          <div className="cw-optimize-option-list">
            {HARNESS_SIDECAR_OPTION_GROUPS.map((group) => (
              <section
                key={group.id}
                className="cw-optimize-option-group"
                aria-labelledby={`cw-optimize-group-${group.id}`}
              >
                <h3
                  id={`cw-optimize-group-${group.id}`}
                  className="cw-optimize-option-group-title"
                >
                  {t(`traditional.optimization.groups.${group.id}`)}
                </h3>
                <div className="cw-optimize-option-group-items">
                  {group.componentIds.map((optionId) => {
                    const item = HARNESS_SIDECAR_OPTIONS.find(
                      (option) => option.id === optionId,
                    );
                    if (!item) return null;
                    const checked = optimizations.includes(item.id);
                    return (
                      <Checkbox
                        key={item.id}
                        checked={checked}
                        onCheckedChange={(next) => {
                          const selected = Boolean(next);
                          if (selected !== checked) {
                            onOptimizationChange(item.id, selected);
                          }
                        }}
                        label={
                          <span className="cw-optimize-option-copy">
                            <strong>
                              {t(
                                `traditional.optimization.options.${item.id}.label`,
                              )}
                            </strong>
                            <small>
                              {t(
                                `traditional.optimization.options.${item.id}.description`,
                              )}
                            </small>
                          </span>
                        }
                        className="cw-optimize-option"
                      />
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        </fieldset>
      </div>
    </section>
  );
}

const WORKSPACE_MODES: Array<{
  id: WorkspaceMode;
  label: string;
}> = [
  { id: "build", label: "traditional.workspace.modes.build" },
  { id: "validate", label: "traditional.workspace.modes.validate" },
  { id: "optimize", label: "traditional.workspace.modes.optimize" },
  { id: "environment", label: "traditional.workspace.modes.environment" },
  { id: "publish", label: "traditional.workspace.modes.publish" },
];

const WORKSPACE_TITLES: Record<WorkspaceMode, string> = {
  build: "traditional.workspace.titles.build",
  validate: "traditional.workspace.titles.validate",
  optimize: "traditional.workspace.titles.optimize",
  environment: "traditional.workspace.titles.environment",
  publish: "traditional.workspace.titles.publish",
};

function WorkspaceHeader({ mode }: { mode: WorkspaceMode }) {
  const { t } = useTranslation("create");
  return (
    <header className="cw-workspace-header">
      <h1>{t(WORKSPACE_TITLES[mode])}</h1>
    </header>
  );
}

function WorkspaceLifecycleFooter({
  mode,
  busy,
  onChange,
  assistant,
  accessory,
}: {
  mode: WorkspaceMode;
  busy: boolean;
  onChange: (mode: WorkspaceMode) => void;
  assistant?: React.ReactNode;
  accessory?: React.ReactNode;
}) {
  const { t } = useTranslation("create");
  const activeIndex = WORKSPACE_MODES.findIndex((item) => item.id === mode);
  const previousMode = WORKSPACE_MODES[activeIndex - 1];
  const nextMode = WORKSPACE_MODES[activeIndex + 1];
  return (
    <footer className="cw-workspace-footer">
      {accessory ? (
        <div className="cw-workspace-footer-accessory">{accessory}</div>
      ) : null}
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
          {t("common.previous")}
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
            {t("common.next")}
          </button>
        )}
      </div>
      <nav
        className="cw-workspace-progress"
        aria-label={t("traditional.workspace.progress")}
      >
        {WORKSPACE_MODES.map((item, index) => {
          const active = item.id === mode;
          return (
            <button
              key={item.id}
              type="button"
              className={`${active ? "is-active" : ""}${index < activeIndex ? " is-complete" : ""}`}
              aria-current={active ? "step" : undefined}
              aria-label={t(item.label)}
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
  /** Fresh custom creation experience selected by the app-level chooser. */
  freshCreationSurface?: "vulcan" | "traditional";
  /** Stable local draft id propagated to persistent deployment tasks. */
  workspaceDraftId?: string;
  /** Existing Runtime target when editing an Agent from the library. */
  deploymentTarget?: {
    runtimeId: string;
    name: string;
    region: string;
    appName?: string;
    currentVersion?: number | null;
    etag?: string;
    editMode?: "source-preserving" | "regenerate";
    configuredMcpEnvKeys?: string[];
    configuredRuntimeEnvKeys?: string[];
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
  freshCreationSurface = "traditional",
  workspaceDraftId,
  deploymentTarget,
  cloudProvider = "volcengine",
  initialDeployRegion = defaultCloudRegion(cloudProvider),
  onDeploymentComplete,
  onDeploymentStarted,
  onDraftChange,
  onDiscard,
}: CustomCreateProps) {
  const { t } = useTranslation("create");
  void onCreate; // outcome is the in-pane project preview, not a navigation
  void onDiscard; // the discard action is intentionally hidden in this flow
  const isVulcanCreation =
    createMode === "custom" && freshCreationSurface === "vulcan";
  const isFreshVulcanCreation = isVulcanCreation && !initialDraft;
  const [initialState] = useState<CustomCreateInitialState>(() => {
    const initialCreationDraft = initialDraft ?? emptyDraft(cloudProvider);
    const creationDraft = isFreshVulcanCreation
      ? {
          ...initialCreationDraft,
          name: initialCreationDraft.name.trim()
            ? initialCreationDraft.name
            : "assistant",
          dynamicAgentDelegation: true,
        }
      : initialCreationDraft;
    return customCreateInitialState(
      creationDraft,
      cloudProvider,
    );
  });
  const [draft, setDraft] = useState<AgentDraft>(initialState.draft);
  const usesNewAgentWorkbench = isVulcanCreation;
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
  const [aiRequirement, setAiRequirement] = useState("");
  const [aiGenerating, setAiGenerating] = useState(false);
  const [aiGenerated, setAiGenerated] = useState(false);
  const [usedAiGeneration, setUsedAiGeneration] = useState(false);
  const [aiErrorDialog, setAiErrorDialog] = useState<string | null>(null);
  const trimmedAiRequirement = aiRequirement.trim();
  const aiRequirementError =
    trimmedAiRequirement.length > 0 &&
    trimmedAiRequirement.length < GENERATED_AGENT_REQUIREMENT_MIN_LENGTH
      ? t("traditional.ai.minimumLength", {
          count: GENERATED_AGENT_REQUIREMENT_MIN_LENGTH,
        })
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
  const [touchedAgentNamePaths, setTouchedAgentNamePaths] = useState<
    ReadonlySet<string>
  >(() => new Set());
  const [validationPulse, setValidationPulse] = useState(0);
  const [project, setProject] = useState<AgentProject | null>(null);
  const [building, setBuilding] = useState(false);
  const [deployRegion, setDeployRegion] = useState<string>(
    deploymentTarget?.region ?? initialDeployRegion,
  );
  const debugEnabled = features?.generatedAgentTestRun === true;
  const debugDisabledReason =
    features?.generatedAgentTestRunDisabledReason ||
    t("traditional.debug.unavailable");
  const [debugVariants, setDebugVariants] = useState<DebugVariant[]>(() => {
    const initialProviderDraft = draftForCloudProvider(
      initialDraft ?? emptyDraft(cloudProvider),
      cloudProvider,
    );
    return [
      {
        id: "baseline",
        name: t("traditional.debug.baseline"),
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
  const [newWorkbenchDeploying, setNewWorkbenchDeploying] = useState(false);
  const [newWorkbenchDeployStage, setNewWorkbenchDeployStage] =
    useState<DeployStage | null>(null);
  const [newWorkbenchDeployError, setNewWorkbenchDeployError] = useState("");
  const [newWorkbenchDeploySucceeded, setNewWorkbenchDeploySucceeded] =
    useState(false);
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
          console.warn("Failed to clean up stale debug run", err);
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
          .catch((err) => console.warn("Failed to clean up debug run", err));
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
          <h2 className="cw-sec-title">{t(meta.label)}</h2>
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
  const selectedNamePathKey = safePath.join(".") || "root";
  const markAgentNameTouched = () => {
    setTouchedAgentNamePaths((current) => {
      if (current.has(selectedNamePathKey)) return current;
      return new Set(current).add(selectedNamePathKey);
    });
  };
  const a2aRegistryAdvancedId = `cw-a2a-registry-advanced-${
    safePath.join("-") || "root"
  }`;
  const patch = (p: Partial<AgentDraft>) =>
    setDraft((d) => updateNode(d, safePath, (n) => ({ ...n, ...p })));

  const patchDeploymentEnvValues = (values: Record<string, string>) =>
    setDraft((current) => ({
      ...current,
      deployment: {
        ...(current.deployment ?? { feishuEnabled: false }),
        envValues: {
          ...(current.deployment?.envValues ?? {}),
          ...values,
        },
      },
    }));

  const patchDeploymentEnv = (key: string, value: string) =>
    patchDeploymentEnvValues({ [key]: value });

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
      !window.confirm(t("traditional.ai.replaceConfirmation"))
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
      setAiErrorDialog(error instanceof Error ? error.message : String(error));
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
    if (!nodeAcceptsChildren(parent) || parentPath.length >= MAX_TREE_DEPTH) {
      return;
    }
    const safeIndex = Math.max(0, Math.min(index, parent.subAgents.length));
    const next = insertChild(draft, parentPath, safeIndex, cloudProvider);
    applyTree(next, [...parentPath, safeIndex]);
  };

  const clearRootAgent = () => {
    if (
      !window.confirm(t("traditional.actions.clearRootConfirmation"))
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
  const a2aDefaults = a2aRegistryDefaults(cloudProvider);
  const modelSource = resolvedModelSource(node, cloudProvider);
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
    : (agentNameProblem(node.name, (key) =>
        t(`validation.agentName.${key}`),
      ) ??
      (duplicateNames.has(node.name)
        ? t("traditional.validation.duplicateName")
        : null));
  const nameInvalid = nameProblem !== null;
  const showNameError =
    showErrors || touchedAgentNamePaths.has(selectedNamePathKey);
  const descriptionMissing = !a2a && node.description.trim().length === 0;
  const instructionMissing = node.instruction.trim().length === 0;
  const a2aRegistrySpaceMissing =
    a2a && !node.a2aRegistry?.registrySpaceId.trim();
  const invalidClass = (missing: boolean, visible = showErrors) =>
    visible && missing
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
    () =>
      collectDeploymentEnv(
        providerDraft,
        deploymentTarget?.editMode === "source-preserving",
      ),
    [deploymentTarget?.editMode, providerDraft],
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
      requirement.label === createT("helpers.customModel.apiKeyLabel", {
        name: node.name.trim() || createT("helpers.customModel.fallbackName"),
      }),
  );

  const updateNewWorkbenchModelApiKey = useCallback(
    (key: ModelApiKeyOption) => {
      setDraft((current) => ({
        ...current,
        deployment: {
          ...(current.deployment ?? { feishuEnabled: false }),
          modelApiKeyId: key.id,
          modelApiKeyName: key.name,
        },
      }));
    },
    [],
  );

  function focusValidationProblem(problem: TreeProblem) {
    const sectionId = problem.problem === "missingSubagent" ? "type" : "basic";
    const section = sectionRefs.current[sectionId];
    section?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });

    const field =
      problem.problem === "missingDescription"
        ? "description"
        : problem.problem === "missingPrompt"
          ? "instruction"
          : problem.problem === "missingRegistry"
            ? "a2a-registry"
            : problem.problem === "missingSubagent" ||
                problem.problem === "remoteRoot"
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
    setValidationPulse((pulse) => pulse + 1);
    if (problems[0]) {
      setSelectedPath(problems[0].path);
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => focusValidationProblem(problems[0]));
      });
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
          console.warn("Failed to clean up debug run", err);
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
      console.warn("Failed to clean up debug run", err);
    }
  };

  const openDebugTrace = (id: string) => {
    const runtime = debugRunsRef.current.get(id);
    const variant = debugVariants.find((item) => item.id === id);
    if (!runtime || !variant) return;
    setDebugTraceTarget({
      runId: runtime.run.runId,
      sessionId: runtime.sessionId,
      variantName: debugVariantDisplayName(variant, t),
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

  const openEnvironment = async (variantId?: string) => {
    if (!(await confirmLeaveDebug())) return;
    if (!requireCompleteDraft()) {
      setWorkspaceMode("build");
      return;
    }
    if (variantId) setSelectedVariantId(variantId);
    setWorkspaceMode("environment");
  };

  const materializePublishRelease = async (variantId?: string) => {
    setBuildErr("");
    if (!requireCompleteDraft()) {
      setWorkspaceMode("build");
      return;
    }
    if (providerDraft.harnessSidecar?.enabled && harnessProviderNotice) {
      setBuildErr(harnessProviderNotice);
      setWorkspaceMode("optimize");
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
        ? releaseDraftFromDebugVariant(providerDraft, releaseVariant)
        : providerDraft;
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

  const openOptimization = async () => {
    if (!(await confirmLeaveDebug())) return;
    if (!requireCompleteDraft()) {
      setWorkspaceMode("build");
      return;
    }
    setWorkspaceMode("optimize");
  };

  const startDebugVariant = async (id: string) => {
    if (!debugEnabled || building) return;
    if (!requireCompleteDraft()) return;
    const variant = debugVariants.find((item) => item.id === id);
    if (
      !variant ||
      variant.phase === "starting" ||
      variant.phase === "sending"
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
    let failedPhase: AgentDebugFailedProps["failedPhase"] = "unknown";
    const variantType = id === "baseline" ? "baseline" : "comparison";
    const operation = beginAgentDebug({
      agentId: String(providerDraft.name || "unknown"),
      variantType,
    });
    try {
      await cleanupDebugVariantRun(id);
      await cleanupStoredDebugRuns();
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
          console.warn("Failed to clean up debug run", cleanupError);
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
          name: t("traditional.debug.comparison", { count: sequence }),
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

  const updateHarnessOptimization = (
    optionId: HarnessSidecarOptionId,
    selected: boolean,
  ) => {
    if (selected && harnessProviderNotice) {
      setBuildErr(harnessProviderNotice);
      return;
    }
    const optimizations = selected
      ? [...new Set([...harnessOptimizations, optionId])]
      : harnessOptimizations.filter((item) => item !== optionId);
    const profile =
      harnessOptimizationProfile === "ops"
        ? "default"
        : harnessOptimizationProfile;
    setDraft((current) => ({
      ...current,
      harnessSidecar: harnessIntentFromOptimizations(optimizations, profile),
    }));
    setBuildErr("");
    setProject(null);
  };

  const updateHarnessOptimizationProfile = (
    profile: HarnessSidecarProfileId,
  ) => {
    const optimizations = harnessProfileDefaultOptimizations(profile);
    if (optimizations.length > 0 && harnessProviderNotice) {
      setBuildErr(harnessProviderNotice);
      return;
    }
    setDraft((current) => ({
      ...current,
      harnessSidecar: harnessIntentFromOptimizations(optimizations, profile),
    }));
    setBuildErr("");
    setProject(null);
  };

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
    const sourcePreserving =
      deploymentTarget?.editMode === "source-preserving";
    const mcpGatewayManaged = selectedHarnessOptimizations(draft).includes(
      "mcp_resilience",
    );
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
        editMode: deploymentTarget?.editMode,
        draft:
          deploymentTarget || mcpGatewayManaged ? codegenDraft(draft) : undefined,
        updateEtag: deploymentTarget?.etag,
        baseRuntimeVersion: deploymentTarget?.currentVersion,
        envs: sourcePreserving ? [] : options?.envs,
        mcpSecretValues: sourcePreserving
          ? sourcePreservingMcpSecretValues(draft)
          : mcpGatewayManaged
            ? deploymentMcpSecretValues(draft)
            : undefined,
        mcpCredentialReuses: deploymentTarget
          ? mcpCredentialReuseValues(draft)
          : undefined,
        removeRuntimeEnvKeys: deploymentTarget
          ? [
              ...removedConfiguredMcpEnvKeys(
                deploymentTarget.configuredMcpEnvKeys ?? [],
                draft,
              ),
              ...(!draft.deployment?.feishuEnabled
                ? ["FEISHU_APP_ID", "FEISHU_APP_SECRET"]
                : []),
            ]
          : undefined,
        description: draft.description,
        harnessSidecar: draft.harnessSidecar,
        environment: draft.cloudEnvironment?.environmentId
          ? {
              environmentId: draft.cloudEnvironment.environmentId,
              environmentVersionId: draft.cloudEnvironment.environmentVersionId,
            }
          : undefined,
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
      if (!(await confirmLeaveDebug())) return;
      await materializePublishRelease();
      return;
    }
    if (nextMode === "validate") {
      openValidation();
      return;
    }
    if (nextMode === "optimize") {
      await openOptimization();
      return;
    }
    if (nextMode === "environment") {
      void openEnvironment();
      return;
    }
    if (!(await confirmLeaveDebug())) return;
    setWorkspaceMode(nextMode);
  };

  const updateCloudEnvironment = (cloudEnvironment: CloudEnvironmentConfig) => {
    setDraft((current) => ({
      ...current,
      cloudEnvironment,
    }));
    setBuildErr("");
    setProject(null);
  };

  const deployFromNewWorkbench = async (
    deploymentOptions: NewAgentDeploymentOptions,
  ) => {
    if (newWorkbenchDeploying) return;
    setNewWorkbenchDeployError("");
    setNewWorkbenchDeploySucceeded(false);
    if (!requireCompleteDraft()) return;

    const runtimeError = runtimeNameProblem(deploymentRuntimeName.trim());
    if (runtimeError) {
      setNewWorkbenchDeployError(runtimeError);
      return;
    }
    const deploymentDraft: AgentDraft = {
      ...providerDraft,
      memory: {
        ...providerDraft.memory,
        shortTerm: deploymentOptions.sessionBackend !== "local",
      },
      shortTermBackend: deploymentOptions.sessionBackend,
    };
    const activeDeploymentEnv = collectDeploymentEnv(
      deploymentDraft,
      deploymentTarget?.editMode === "source-preserving",
    );
    const network = deploymentDraft.deployment?.network;
    if (
      network?.mode !== undefined &&
      network.mode !== "public" &&
      !network.vpcId?.trim()
    ) {
      setNewWorkbenchDeployError(t("traditional.deployment.vpcRequired"));
      return;
    }
    if (
      resolvedModelSource(deploymentDraft, cloudProvider) === "ark" &&
      !deploymentDraft.deployment?.modelApiKeyId?.trim()
    ) {
      setNewWorkbenchDeployError(t("traditional.deployment.apiKeyRequired"));
      return;
    }
    const allEnvValues = {
      ...(deploymentDraft.deployment?.envValues ?? {}),
      ...customModelSecretValues,
      ...activeDeploymentEnv.fixedValues,
    };
    const invalidEnvKey = Object.keys(allEnvValues).find(
      (key) => key && !/^[A-Za-z_][A-Za-z0-9_]*$/.test(key),
    );
    if (invalidEnvKey) {
      setNewWorkbenchDeployError(
        t("traditional.deployment.invalidEnvName", { key: invalidEnvKey }),
      );
      return;
    }
    const activeEnvSpecs = deploymentDraft.deployment?.feishuEnabled
      ? [...activeDeploymentEnv.specs, ...FEISHU_ENV]
      : activeDeploymentEnv.specs;
    const missingEnv = firstMissingRuntimeEnv(activeEnvSpecs, allEnvValues);
    if (missingEnv) {
      setNewWorkbenchDeployError(
        t("traditional.deployment.requiredEnv", {
          name: missingEnv.comment || missingEnv.key,
        }),
      );
      return;
    }
    const invalidEnv = firstInvalidRuntimeEnv(activeEnvSpecs, allEnvValues);
    if (invalidEnv) {
      setNewWorkbenchDeployError(
        `${invalidEnv.spec.comment || invalidEnv.spec.key}：${invalidEnv.error}`,
      );
      return;
    }

    setNewWorkbenchDeploying(true);
    setNewWorkbenchDeployStage({
      level: "info",
      phase: "prepare",
      message: t("traditional.deployment.generatingConfiguration"),
      pct: 0,
    });
    let activeTask: DeploymentTaskUpdate | null = null;
    try {
      if (!deploymentTarget) {
        const availability = await checkRuntimeNameAvailability(
          deploymentRuntimeName.trim(),
          deployRegion,
        );
        if (!availability.available) {
          throw new Error(t("traditional.deployment.runtimeNameExists"));
        }
      }
      const generated = await generateAgentProject(
        codegenDraft(deploymentDraft),
      );
      setProject(generated);
      const taskId = crypto.randomUUID();
      const startedAt = Date.now();
      let latestPhase = "prepare";
      let latestLabel = t("traditional.deployment.preparing");
      let latestMessage = t("traditional.deployment.generatingConfiguration");
      const taskBase = {
        id: taskId,
        ...(workspaceDraftId ? { draftId: workspaceDraftId } : {}),
        agentName: deploymentDraft.name,
        runtimeName: deploymentRuntimeName.trim(),
        region: deployRegion,
        startedAt,
        agentDraft: deploymentDraft,
      };
      const initialTask: DeploymentTaskUpdate = {
        ...taskBase,
        status: "running",
        phase: latestPhase,
        label: latestLabel,
        message: latestMessage,
        pct: 0,
      };
      activeTask = initialTask;
      onDeploymentTaskChange?.(initialTask);
      onDeploymentStarted?.(initialTask);

      const envMap = new Map(
        Object.entries(allEnvValues)
          .map(([key, value]) => [key.trim(), value] as const)
          .filter(([key, value]) => key && value.trim()),
      );
      for (const env of runtimeEnvVars(activeEnvSpecs, allEnvValues)) {
        envMap.set(env.key, env.value);
      }
      const modelApiKeyId = deploymentDraft.deployment?.modelApiKeyId?.trim();
      const modelApiKeyName =
        deploymentDraft.deployment?.modelApiKeyName?.trim();
      if (modelApiKeyId) envMap.set("MODEL_AGENT_API_KEY_ID", modelApiKeyId);
      if (modelApiKeyName)
        envMap.set("MODEL_AGENT_API_KEY_NAME", modelApiKeyName);

      const result = await handleDeploy(
        generated,
        (stage) => {
          latestPhase = stage.phase;
          latestLabel =
            stage.phase === "build"
              ? t("traditional.deployment.stages.build")
              : stage.phase === "deploy"
                ? t("traditional.deployment.stages.deploy")
                : stage.phase === "publish"
                  ? t("traditional.deployment.stages.publish")
                  : t("traditional.deployment.stages.running");
          latestMessage = stage.message;
          setNewWorkbenchDeployStage(stage);
          onDeploymentTaskChange?.({
            ...taskBase,
            runtimeName: stage.runtimeName || taskBase.runtimeName,
            status: "running",
            phase: latestPhase,
            label: latestLabel,
            message: latestMessage,
            messageCode: stage.messageCode,
            pct: stage.pct,
            ...(stage.buildLog ? { buildLog: stage.buildLog } : {}),
          });
        },
        {
          taskId,
          runtimeName: deploymentRuntimeName.trim(),
          sessionStorage: deploymentOptions.sessionStorage,
          minInstance: deploymentOptions.minInstance,
          maxInstance: deploymentOptions.maxInstance,
          authentication: deploymentOptions.authentication,
          createEvaluationSets: deploymentOptions.createEvaluationSets,
          resources: deploymentOptions.resources,
          ...(deploymentDraft.deployment?.feishuEnabled
            ? { im: { feishu: { enabled: true } } }
            : {}),
          envs: [...envMap].map(([key, value]) => ({ key, value })),
        },
      );
      setNewWorkbenchDeploySucceeded(true);
      setNewWorkbenchDeployStage({
        level: "success",
        phase: "complete",
        message: t("traditional.deployment.complete"),
        pct: 100,
      });
      onDeploymentTaskChange?.({
        ...taskBase,
        runtimeName: result.runtimeName || taskBase.runtimeName,
        runtimeId: result.runtimeId,
        region: result.region || deployRegion,
        status: "success",
        phase: "complete",
        label: t("traditional.deployment.complete"),
        message: result.warnings?.join("；"),
        pct: 100,
      });
      await onDeploymentComplete?.(result);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setNewWorkbenchDeployError(message);
      setNewWorkbenchDeployStage(null);
      const failedTask: DeploymentTaskUpdate = {
        ...(activeTask ?? {
          id: crypto.randomUUID(),
          agentName:
            providerDraft.name || t("traditional.basic.unnamedAgent"),
          runtimeName: deploymentRuntimeName.trim(),
          region: deployRegion,
          startedAt: Date.now(),
        }),
        status: "error",
        phase: activeTask?.phase,
        label: t("traditional.deployment.failed"),
        message,
        retry: () => deployFromNewWorkbench(deploymentOptions),
      };
      onDeploymentTaskChange?.(failedTask);
    } finally {
      setNewWorkbenchDeploying(false);
    }
  };

  const Section = sectionImpl.current;

  const metaOf = (id: StepId) => STEPS.find((s) => s.id === id)!;

  const aiComposer = (
    <section
      className={`cw-ai-compose${aiGenerating ? " is-generating" : ""}${aiGenerated ? " is-success" : ""}`}
      aria-label={t("traditional.ai.ariaLabel")}
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
            <strong>{t("traditional.ai.success")}</strong>
            <button
              type="button"
              className="cw-ai-regenerate"
              onClick={() => setAiGenerated(false)}
            >
              {t("traditional.ai.regenerate")}
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
                placeholder={t("traditional.ai.placeholder", {
                  model: plannerModelName(cloudProvider),
                })}
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
                aria-label={
                  aiGenerating
                    ? t("traditional.ai.generating")
                    : t("traditional.ai.generate")
                }
              >
                {aiGenerating ? (
                  <span className="cw-ai-orb" aria-hidden>
                    <span />
                  </span>
                ) : (
                  t("traditional.ai.generate")
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

  if (usesNewAgentWorkbench) {
    return (
      <NewAgentWorkbench
        draft={providerDraft}
        cloudProvider={cloudProvider}
        deployRegion={deployRegion}
        runtimeName={deploymentRuntimeName}
        isRuntimeUpdate={Boolean(deploymentTarget)}
        deploying={newWorkbenchDeploying}
        deployStage={newWorkbenchDeployStage}
        deployError={newWorkbenchDeployError}
        deploySucceeded={newWorkbenchDeploySucceeded}
        showErrors={showErrors}
        onBack={onBack}
        onDraftPatch={(updates) => {
          setDraft((current) => ({ ...current, ...updates }));
          setProject(null);
          setBuildErr("");
        }}
        onDeploymentPatch={(updates) =>
          setDraft((current) => ({
            ...current,
            deployment: {
              ...(current.deployment ?? { feishuEnabled: false }),
              ...updates,
            },
          }))
        }
        onModelApiKeyChange={updateNewWorkbenchModelApiKey}
        customModelApiKey={
          selectedCustomModelCredential
            ? (customModelSecretValues[selectedCustomModelCredential.key] ?? "")
            : ""
        }
        onCustomModelApiKeyChange={(value) => {
          if (!selectedCustomModelCredential) return;
          setCustomModelSecretValues((current) => ({
            ...current,
            [selectedCustomModelCredential.key]: value,
          }));
        }}
        onSelectedSkillsChange={(selectedSkills) =>
          setDraft((current) => ({ ...current, selectedSkills }))
        }
        onCloudEnvironmentChange={updateCloudEnvironment}
        onDeployRegionChange={setDeployRegion}
        onRuntimeNameChange={(runtimeName) =>
          setDraft((current) => ({
            ...current,
            deployment: {
              ...(current.deployment ?? { feishuEnabled: false }),
              runtimeName,
              runtimeNameCustomized: true,
            },
          }))
        }
        onNetworkChange={(network) =>
          setDraft((current) => ({
            ...current,
            deployment: {
              ...(current.deployment ?? { feishuEnabled: false }),
              network,
            },
          }))
        }
        onDeploy={(options) => void deployFromNewWorkbench(options)}
      />
    );
  }

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
                            aria-label={t("traditional.agentTypes.ariaLabel")}
                            value={node.agentType ?? "llm"}
                            onChange={selectAgentType}
                          >
                            {AGENT_TYPES.map((agentType) => {
                              const on =
                                (node.agentType ?? "llm") === agentType.id;
                              const remoteTypeDisabled =
                                isRootAgent && agentType.id === "a2a";
                              const disabledHintId = remoteTypeDisabled
                                ? "cw-remote-agent-disabled-hint"
                                : undefined;
                              return (
                                <div
                                  key={agentType.id}
                                  data-agent-type={agentType.id}
                                  className={`cw-agent-type-option ${on ? "is-on" : ""} ${
                                    remoteTypeDisabled ? "is-disabled" : ""
                                  }`}
                                  tabIndex={remoteTypeDisabled ? 0 : undefined}
                                  aria-describedby={disabledHintId}
                                >
                                  <RadioGroup.Item
                                    value={agentType.id}
                                    disabled={remoteTypeDisabled}
                                    block
                                    className="cw-agent-type-control"
                                  >
                                    <span className="cw-agent-type-copy">
                                      <strong>
                                        {t(
                                          AGENT_TYPE_BAR_LABELS[agentType.id],
                                        )}
                                      </strong>
                                    </span>
                                  </RadioGroup.Item>
                                  {remoteTypeDisabled && (
                                    <span
                                      id={disabledHintId}
                                      className="cw-agent-type-disabled-hint"
                                      role="tooltip"
                                    >
                                      {t("traditional.agentTypes.remoteChildOnly")}
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
                                  name: node.name.trim(),
                                  agentType: node.agentType,
                                  problem: "missingSubagent",
                                }, t)}
                              </span>
                            )}
                        </Section>
                        <Section meta={metaOf("basic")}>
                          <div className="cw-form">
                            {!a2a && (
                              <>
                                <div className="cw-field">
                                  <label className="cw-label">
                                    {isRootAgent
                                      ? t("traditional.basic.agentName")
                                      : t("traditional.basic.name")}
                                    <span className="cw-req">*</span>
                                  </label>
                                  <input
                                    className={`cw-input ${invalidClass(nameInvalid, showNameError)}`}
                                    data-validation-field="name"
                                    value={node.name}
                                    placeholder="assistant"
                                    aria-invalid={showNameError && nameInvalid}
                                    aria-describedby={
                                      showNameError && nameProblem
                                        ? "cw-agent-name-error"
                                        : undefined
                                    }
                                    onBlur={markAgentNameTouched}
                                    onChange={(e) => {
                                      markAgentNameTouched();
                                      patch({ name: e.target.value });
                                    }}
                                  />
                                  {showNameError && nameProblem ? (
                                    <span
                                      id="cw-agent-name-error"
                                      role="alert"
                                      className="cw-error-text"
                                    >
                                      {nameProblem}
                                    </span>
                                  ) : (
                                    <span className="cw-help">
                                      {t("traditional.basic.nameHelp")}
                                    </span>
                                  )}
                                </div>
                                <div className="cw-field">
                                  <label className="cw-label">
                                    {isRootAgent
                                      ? t("common.description")
                                      : t("traditional.basic.agentDescription")}
                                    <span className="cw-req">*</span>
                                  </label>
                                  <textarea
                                    className={`cw-textarea cw-textarea-sm ${invalidClass(
                                      descriptionMissing,
                                    )}`}
                                    data-validation-field="description"
                                    value={node.description}
                                    placeholder={t(
                                      "traditional.basic.descriptionPlaceholder",
                                    )}
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
                                      {t(
                                        "traditional.validation.missingDescription",
                                      )}
                                    </span>
                                  ) : (
                                    <span className="cw-help">
                                      {isRootAgent
                                        ? t("traditional.basic.rootDescriptionHelp")
                                        : t("traditional.basic.descriptionHelp")}
                                    </span>
                                  )}
                                </div>
                              </>
                            )}
                            {orchestrator ? (
                              <>
                                <p className="cw-section-desc cw-dependency-hint">
                                  {t("traditional.basic.orchestratorHelp")}
                                </p>
                                {node.agentType === "loop" && (
                                  <div className="cw-field">
                                    <label className="cw-label">
                                      {t("traditional.basic.maxIterations")}
                                    </label>
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
                                      {t("traditional.basic.maxIterationsHelp")}
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
                                  <div className="cw-label">
                                    {t("traditional.basic.agentCenter")}
                                    <span className="cw-req">*</span>
                                  </div>
                                  <p className="cw-help cw-remote-center-description">
                                    {t("traditional.basic.agentCenterHelp")}
                                  </p>
                                </div>
                                <A2aSpaceSelect
                                  value={
                                    node.a2aRegistry?.registrySpaceId ?? ""
                                  }
                                  region={
                                    node.a2aRegistry?.registryRegion ||
                                    a2aDefaults.region
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
                                  <span>{t("traditional.basic.moreOptions")}</span>
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
                                        env={providerRuntimeEnv(
                                          A2A_REGISTRY_RUNTIME_ENV,
                                          cloudProvider,
                                        )}
                                        values={a2aRegistryEnvValues(
                                          node.a2aRegistry,
                                          { includeDefaults: false },
                                          cloudProvider,
                                        )}
                                        onChange={patchA2aRegistryEnv}
                                      />
                                    </motion.div>
                                  )}
                                </AnimatePresence>
                                {showErrors && a2aRegistrySpaceMissing && (
                                  <span className="cw-error-text" role="alert">
                                    {t("traditional.validation.missingRegistry")}
                                  </span>
                                )}
                              </div>
                            ) : (
                              <div
                                className="cw-field"
                                data-validation-field="instruction"
                              >
                                <label className="cw-label">
                                  {t("traditional.basic.systemPrompt")}
                                  <span className="cw-req">*</span>
                                </label>
                                <Suspense
                                  fallback={
                                    <div
                                      className="cw-markdown-loading"
                                      role="status"
                                    >
                                      {t("traditional.basic.loadingMarkdown")}
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
                                    {t("traditional.validation.missingPrompt")}
                                  </span>
                                ) : (
                                  <span className="cw-help">
                                    {t("traditional.basic.markdownHelp")}
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
                                <div className="cw-field cw-model-source-field">
                                  <label className="cw-label">
                                    {t("traditional.model.source")}
                                  </label>
                                  <RadioGroup<ModelSource | "gateway">
                                    className="cw-model-source-options"
                                    aria-label={t("traditional.model.source")}
                                    value={modelSource}
                                    onChange={(source) => {
                                      if (source !== "gateway")
                                        selectModelSource(source);
                                    }}
                                  >
                                    {[
                                      {
                                        value: "ark" as const,
                                        label:
                                          cloudProvider === "byteplus"
                                            ? t("traditional.model.bytePlusModelArk")
                                            : t("traditional.model.volcanoArk"),
                                      },
                                      {
                                        value: "custom" as const,
                                        label: t("traditional.model.custom"),
                                      },
                                      {
                                        value: "gateway" as const,
                                        label: t("traditional.model.gateway"),
                                        disabled: true,
                                      },
                                    ].map((option) => (
                                      <div
                                        key={option.value}
                                        className={`cw-model-source-option ${
                                          modelSource === option.value
                                            ? "is-on"
                                            : ""
                                        }${option.disabled ? " is-disabled" : ""}`}
                                      >
                                        <RadioGroup.Item
                                          value={option.value}
                                          disabled={option.disabled}
                                          block
                                          className="cw-model-source-control"
                                        >
                                          <span>{option.label}</span>
                                          {option.disabled && (
                                            <span className="cw-model-source-coming-soon">
                                              {t("traditional.model.comingSoon")}
                                            </span>
                                          )}
                                        </RadioGroup.Item>
                                      </div>
                                    ))}
                                  </RadioGroup>
                                </div>
                                {modelSource === "ark" ? (
                                  <div className="cw-field">
                                    <label className="cw-label">
                                      {t("traditional.model.configuration")}
                                    </label>
                                    <ModelOptionSelect
                                      value={node.modelName ?? ""}
                                      cloudProvider={cloudProvider}
                                      apiKeyId={draft.deployment?.modelApiKeyId}
                                      apiKeyName={
                                        draft.deployment?.modelApiKeyName
                                      }
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
                                    <div className="cw-field">
                                      <label className="cw-label">
                                        {t("traditional.model.name")}
                                      </label>
                                      <input
                                        className="cw-input"
                                        value={node.modelName ?? ""}
                                        onChange={(e) =>
                                          patch({ modelName: e.target.value })
                                        }
                                      />
                                    </div>
                                    <div className="cw-field">
                                      <label className="cw-label cw-label-with-link">
                                        <span>{t("traditional.model.provider")}</span>
                                        <a
                                          href="https://docs.litellm.ai/docs/providers"
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          onClick={(event) =>
                                            event.stopPropagation()
                                          }
                                        >
                                          {t("traditional.model.liteLlmProviders")}
                                          <ExternalLink aria-hidden="true" />
                                        </a>
                                      </label>
                                      <input
                                        className="cw-input"
                                        value={node.modelProvider ?? ""}
                                        placeholder="openai"
                                        onChange={(e) =>
                                          patch({
                                            modelProvider: e.target.value,
                                          })
                                        }
                                      />
                                    </div>
                                    <div className="cw-field">
                                      <label className="cw-label">
                                        API Base
                                      </label>
                                      <input
                                        className="cw-input"
                                        value={node.modelApiBase ?? ""}
                                        placeholder={defaultModelApiBase(
                                          cloudProvider,
                                        )}
                                        onChange={(e) =>
                                          patch({
                                            modelApiBase: e.target.value,
                                          })
                                        }
                                      />
                                    </div>
                                    <div className="cw-field">
                                      <label className="cw-label">
                                        API Key
                                      </label>
                                      <input
                                        className="cw-input"
                                        type="password"
                                        value={
                                          selectedCustomModelCredential
                                            ? (customModelSecretValues[
                                                selectedCustomModelCredential
                                                  .key
                                              ] ?? "")
                                            : ""
                                        }
                                        placeholder={t(
                                          "traditional.model.apiKeyPlaceholder",
                                        )}
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
                              <div className="cw-form">
                                <div className="cw-field">
                                  <label className="cw-label">
                                    {t("traditional.tools.builtIn")}
                                  </label>
                                  <span className="cw-help">
                                    {t("traditional.tools.builtInHelp")}
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
                                            {t("traditional.tools.codeExecution")}
                                          </span>
                                          <span className="cw-help">
                                            {t("traditional.tools.codeExecutionHelp")}
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
                                  <label className="cw-label">
                                    {t("traditional.tools.mcp")}
                                  </label>
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
                              <div className="cw-form">
                                <SkillSourcePicker
                                  selected={selectedSkills}
                                  onChange={(next) =>
                                    patch({ selectedSkills: next })
                                  }
                                  cloudProvider={cloudProvider}
                                />
                              </div>
                            </Section>

                            <Section meta={metaOf("knowledge")}>
                              <div className="cw-form cw-toggle-stack">
                                <Toggle
                                  checked={node.knowledgebase}
                                  onChange={(v) => patch({ knowledgebase: v })}
                                  title={t("traditional.knowledge.title")}
                                  desc={t("traditional.knowledge.description")}
                                  icon={Database}
                                />
                                {node.knowledgebase && (
                                  <div className="cw-field cw-subfield">
                                    <label className="cw-label">
                                      {t("traditional.knowledge.backend")}
                                    </label>
                                    <BackendSelect
                                      options={KB_BACKENDS}
                                      value={node.knowledgebaseBackend}
                                      translationGroup="knowledge"
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
                                        <label className="cw-label">
                                          {t("traditional.knowledge.vikingDatabase")}
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
                                    title={t("traditional.memory.shortTerm")}
                                    desc={t("traditional.memory.shortTermDescription")}
                                    showDescription
                                    icon={Layers}
                                  />
                                  {node.memory.shortTerm && (
                                    <div className="cw-field cw-subfield">
                                      <label className="cw-label">
                                        {t("traditional.memory.shortTermBackend")}
                                      </label>
                                      <BackendSelect
                                        options={STM_BACKENDS}
                                        value={node.shortTermBackend}
                                        translationGroup="shortTerm"
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
                                    title={t("traditional.memory.longTerm")}
                                    desc={t("traditional.memory.longTermDescription")}
                                    showDescription
                                    icon={Database}
                                  />
                                  {node.memory.longTerm && (
                                    <div className="cw-field cw-subfield">
                                      <label className="cw-label">
                                        {t("traditional.memory.longTermBackend")}
                                      </label>
                                      <BackendSelect
                                        options={LTM_BACKENDS}
                                        value={node.longTermBackend}
                                        translationGroup="longTerm"
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
                                            {t("traditional.memory.vikingDatabase")}
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
                                              (node.longTermBackend ?? "local"),
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
                                        title={t("traditional.memory.autoSave")}
                                        desc={t("traditional.memory.autoSaveDescription")}
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
                onUseVariant={(id) => void openEnvironment(id)}
                onAddVariant={addDebugVariant}
                onRemoveVariant={removeDebugVariant}
                onToggleConfig={(id) => {
                  const variant = debugVariants.find((item) => item.id === id);
                  if (variant)
                    patchDebugVariant(id, { configOpen: !variant.configOpen });
                }}
                onCompleteConfig={completeDebugVariantConfig}
                onConfigChange={updateDebugVariantConfig}
                onOpenTrace={openDebugTrace}
              />
            </div>
          </div>
        )}

        {workspaceMode === "optimize" && (
          <HarnessOptimizationWorkspace
            profile={harnessOptimizationProfile}
            optimizations={harnessOptimizations}
            unavailableMessage={harnessProviderNotice}
            onProfileChange={updateHarnessOptimizationProfile}
            onOptimizationChange={updateHarnessOptimization}
          />
        )}

        {workspaceMode === "environment" && (
          <div className="cw-environment-workspace">
            <CloudEnvironmentConfigurator
              value={
                draft.cloudEnvironment ?? {
                  environmentId: "",
                  environmentVersionId: "",
                }
              }
              onChange={updateCloudEnvironment}
              disabled={building}
            />
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
                agentName={draft.name || t("traditional.basic.unnamedAgent")}
                agentCount={countDraftAgents(draft)}
                releaseConfiguration={
                  selectedDebugVariant
                    ? {
                        modelName:
                          selectedDebugVariant.modelName ||
                          draft.modelName ||
                          t("traditional.debug.defaultModel"),
                        description: selectedDebugVariant.description,
                        instruction: selectedDebugVariant.instruction,
                        optimizations: [
                          t("traditional.optimization.releaseScenario", {
                            profile: t(
                              `traditional.optimization.profiles.${harnessOptimizationProfile}.label`,
                            ),
                          }),
                          ...harnessOptimizations.map((id) =>
                            t(`traditional.optimization.options.${id}.label`),
                          ),
                        ],
                      }
                    : undefined
                }
                onChange={setProject}
                onDeploy={handleDeploy}
                onAgentAdded={onAgentAdded}
                onDeploymentTaskChange={onDeploymentTaskChange}
                deploymentActionLabel={
                  deploymentTarget
                    ? t("traditional.deployment.updateAndPublish")
                    : t("common.deploy")
                }
                deploymentActionTargetId="cw-publish-primary-action"
                deploymentRuntimeId={deploymentTarget?.runtimeId}
                deploymentRuntimeName={deploymentRuntimeName}
                deploymentRuntimeNameCustomized={
                  !!deploymentTarget ||
                  !!draft.deployment?.runtimeNameCustomized
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
                configuredRuntimeEnvKeys={
                  deploymentTarget?.configuredRuntimeEnvKeys
                }
                onFeishuEnabledChange={async (feishuEnabled) => {
                  const nextDraft: AgentDraft = {
                    ...draft,
                    deployment: {
                      ...(draft.deployment ?? { feishuEnabled: false }),
                      feishuEnabled,
                    },
                  };
                  const generated = await generateAgentProject(
                    codegenDraft(nextDraft),
                  );
                  setDraft(nextDraft);
                  setProject(generated);
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
                onFeishuCredentialsChange={(appId, appSecret) =>
                  patchDeploymentEnvValues({
                    FEISHU_APP_ID: appId,
                    FEISHU_APP_SECRET: appSecret,
                  })
                }
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
                    draftToYaml(providerDraft, {
                      heading: t("yaml.heading"),
                      importHint: t("yaml.importHint"),
                    }),
                    "text/yaml",
                  )
                }
              />
            ) : (
              <div className="cw-publish-loading" role="status">
                <Loader2 className="cw-i cw-spin" />
                <strong>{t("traditional.publish.generating")}</strong>
                <span>{t("traditional.publish.validating")}</span>
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
          title={t("traditional.debug.traceTitle", {
            name: debugTraceTarget.variantName,
          })}
          onClose={() => setDebugTraceTarget(null)}
        />
      )}
      {debugLeaveConfirmOpen && (
        <StudioConfirmDialog
          variant="warning"
          title={t("traditional.debug.leaveTitle")}
          description={t("traditional.debug.leaveDescription")}
          confirmLabel={
            debugLeaveCleaning
              ? t("traditional.debug.cleaning")
              : t("traditional.debug.confirmLeave")
          }
          closeLabel={t("traditional.debug.closeLeaveConfirmation")}
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
              {t("traditional.ai.failed")}
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
                {t("common.close")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
