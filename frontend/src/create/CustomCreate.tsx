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
import {
  ArrowRight,
  ArrowUp,
  Bot,
  Boxes,
  Check,
  ChevronRight,
  Cpu,
  Database,
  Eye,
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
  STM_BACKENDS,
  LTM_BACKENDS,
  KB_BACKENDS,
  TRACING_EXPORTERS,
  type BackendOption,
  type EnvVar,
} from "./veadkCatalog";
import {
  runtimeEnvConfiguration,
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
import { draftToYaml } from "./configYaml";
import type { AgentProject } from "./project";
import type { SkillSource } from "./skills/types";
import { SkillHubPicker } from "./SkillHubPicker";
import { LocalPicker } from "./LocalPicker";
import { SkillSpacePicker } from "./SkillSpacePicker";
import {
  ProjectPreview,
  type DeploymentTaskUpdate,
} from "../ui/ProjectPreview";
import { Blocks, ThinkingPlaceholder } from "../ui/Blocks";
import { DeploymentErrorMessage } from "../ui/DeploymentErrorMessage";
import {
  createGeneratedAgentTestRun,
  createGeneratedAgentTestSession,
  deleteGeneratedAgentTestRun,
  deployAgentkitProject,
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
  | "advanced"
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
    label: "类型",
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
  { id: "advanced", label: "进阶配置", hint: "记忆与观测", icon: Layers },
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

/** Custom debug-console mark: a compact runtime panel with a live trace. */
function DebugConsoleIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="3.25" y="4.25" width="17.5" height="15.5" rx="2.75" />
      <path d="M3.75 8.75h16.5" />
      <circle cx="6.35" cy="6.5" r="0.72" fill="currentColor" stroke="none" />
      <circle
        cx="8.85"
        cy="6.5"
        r="0.72"
        fill="currentColor"
        stroke="none"
        opacity="0.45"
      />
      <path d="M6 14h2.2l1.35-2.8 2.1 5.5 1.7-3.1H18" />
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

const AGENT_TYPE_GAP_PX = 4;
const AGENT_TYPE_BAR_LABELS: Record<
  NonNullable<AgentDraft["agentType"]>,
  string
> = {
  llm: "LLM 智能体",
  sequential: "顺序型智能体",
  parallel: "并行型智能体",
  loop: "循环型智能体",
  a2a: "远程智能体",
};

const A2A_REGISTRY_ENV_TO_FIELD = {
  REGISTRY_SPACE_ID: "registrySpaceId",
  REGISTRY_TOP_K: "registryTopK",
  REGISTRY_REGION: "registryRegion",
  REGISTRY_ENDPOINT: "registryEndpoint",
} as const;

type A2aRegistryEnvKey = keyof typeof A2A_REGISTRY_ENV_TO_FIELD;

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
              "--cw-checklist-max-height": `${scrollRows * 65 + (scrollRows - 1) * 8}px`,
            } as CSSProperties)
          : undefined
      }
    >
      {items.map((it) => {
        const on = selected.includes(it.id);
        return (
          <button
            key={it.id}
            type="button"
            className={`cw-check ${on ? "is-on" : ""}`}
            onClick={() => onToggle(it.id)}
            aria-pressed={on}
          >
            <span className="cw-check-box" aria-hidden>
              {on && <Check className="cw-i cw-i-sm" />}
            </span>
            <span className="cw-check-text">
              <span className="cw-check-title">{it.label}</span>
              <span className="cw-check-desc">
                {displayDescription(it.desc)}
              </span>
            </span>
          </button>
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
            title={displayDescription(o.desc)}
          >
            <span className="cw-seg-title">{o.label}</span>
            <span className="cw-seg-desc">{displayDescription(o.desc)}</span>
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
      {env.map((item) => (
        <label className="cw-env-field" key={item.key}>
          <span className="cw-env-field-head">
            <span className="cw-env-field-label">
              {item.comment || item.key}
              {item.required && <span className="cw-req">*</span>}
            </span>
            {item.comment && <code title={item.key}>{item.key}</code>}
          </span>
          <input
            className="cw-input"
            type={isSensitiveEnv(item.key) ? "password" : "text"}
            value={values[item.key] ?? ""}
            placeholder={item.placeholder || "请输入参数值"}
            autoComplete="off"
            onChange={(event) => onChange(item.key, event.currentTarget.value)}
          />
        </label>
      ))}
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
  desc,
  icon: Icon,
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
      <span className="cw-toggle-icon">
        <Icon className="cw-i" />
      </span>
      <span className="cw-toggle-text">
        <span className="cw-toggle-title">{title}</span>
        <span className="cw-toggle-desc">{displayDescription(desc)}</span>
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
      : "缺少 AgentKit 智能体中心 ID";
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
            (item) => item.id === (node.knowledgebaseBackend ?? "local"),
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
function TreeNode({
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
  "idle" | "building" | "starting" | "ready" | "sending" | "error";

interface DebugMessage {
  role: "user" | "assistant";
  content: string;
  blocks?: Block[];
  error?: string;
}

function codegenDraft(draft: AgentDraft): AgentDraft {
  return {
    ...draft,
    deployment: {
      feishuEnabled: !!draft.deployment?.feishuEnabled,
    },
  };
}

function debugSnapshotKey(draft: AgentDraft): string {
  return JSON.stringify(codegenDraft(draft));
}

function DebugPanel({
  enabled,
  disabledReason,
  phase,
  stale,
  run,
  projectName,
  logs,
  messages,
  input,
  error,
  deploying,
  deployError,
  onInput,
  onSend,
  onRestart,
  onIgnoreChanges,
  onDeploy,
}: {
  enabled: boolean;
  disabledReason: string;
  phase: DebugPhase;
  stale: boolean;
  run: GeneratedAgentTestRun | null;
  projectName: string;
  logs: string[];
  messages: DebugMessage[];
  input: string;
  error: string | null;
  deploying: boolean;
  deployError: string;
  onInput: (v: string) => void;
  onSend: () => void;
  onRestart: () => void;
  onIgnoreChanges: () => void;
  onDeploy: () => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const ready = phase === "ready" || phase === "sending";
  const busy =
    phase === "building" || phase === "starting" || phase === "sending";
  const showInitialOverlay = enabled && !run && phase === "idle";
  const showProgressOverlay =
    enabled && (phase === "building" || phase === "starting");
  const showStaleOverlay = Boolean(run && stale && !showProgressOverlay);

  if (collapsed) {
    return (
      <aside className="cw-debug is-collapsed" aria-label="调试窗口（已收起）">
        <button
          type="button"
          className="cw-debug-expand"
          onClick={() => setCollapsed(false)}
          aria-label="展开调试栏"
          title="展开调试栏"
        >
          <DebugConsoleIcon className="cw-i" />
        </button>
      </aside>
    );
  }

  return (
    <aside className="cw-debug" aria-label="调试窗口">
      <div className="cw-debug-head">
        <div className="cw-debug-title">
          <button
            type="button"
            className="cw-debug-collapse"
            onClick={() => setCollapsed(true)}
            aria-label="收起调试栏"
            title="收起调试栏"
          >
            <ChevronRight className="cw-i cw-i-sm" />
          </button>
          <span>调试</span>
        </div>
        <div className="cw-debug-head-actions">
          <button
            type="button"
            className="cw-debug-deploy"
            disabled={deploying}
            onClick={onDeploy}
            title="查看源码、填写环境变量并部署"
          >
            去部署
            {deploying ? (
              <Loader2 className="cw-i cw-spin" />
            ) : (
              <ArrowRight className="cw-i" />
            )}
          </button>
        </div>
      </div>

      {!run && phase === "idle" && !enabled && (
        <div className="cw-debug-sub">
          <span>{disabledReason}</span>
        </div>
      )}

      {deployError && (
        <div className="cw-debug-deploy-error" role="alert">
          {deployError}
        </div>
      )}

      <div className="cw-debug-stage">
        <div className="cw-debug-body">
        {!enabled ? (
            <div className="cw-debug-empty">{disabledReason}</div>
        ) : phase === "error" ? (
          <div className="cw-debug-error">
            <DeploymentErrorMessage
              message={error || "调试失败"}
              className="cw-debug-error-detail"
              onRetry={async () => {
                await onRestart();
              }}
            />
            {logs.length > 0 && (
              <div className="cw-debug-progress">
                {logs.map((line, i) => (
                  <div key={`${line}-${i}`} className="cw-debug-logline">
                    <span>{line}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="cw-debug-chat">
            {messages.length === 0 ? (
              <div className="cw-debug-chat-empty">
                输入消息开始验证当前 Agent。
              </div>
            ) : (
              messages.map((msg, i) => (
                <div
                  key={i}
                  className={`cw-debug-msg cw-debug-msg-${msg.role}`}
                >
                  <div className="cw-debug-role">
                    {msg.role === "user" ? "你" : projectName || "Agent"}
                  </div>
                  <div className="cw-debug-content">
                    {msg.role === "user" ? (
                      msg.content
                    ) : msg.error ? (
                      <DeploymentErrorMessage
                        message={msg.error}
                        className="cw-debug-msg-error"
                      />
                    ) : msg.blocks && msg.blocks.length > 0 ? (
                      <Blocks blocks={msg.blocks} onAction={() => {}} />
                    ) : msg.content ? (
                      msg.content
                    ) : i === messages.length - 1 && phase === "sending" ? (
                      <ThinkingPlaceholder />
                    ) : null}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      <div className="cw-debug-composer">
        <div className="cw-debug-composerbox">
          <textarea
            className="cw-debug-input"
            rows={1}
            value={input}
            placeholder={
              stale
                ? "更新 Agent 后可继续调试"
                : ready
                  ? "输入测试消息..."
                  : "调试环境启动后可输入"
            }
            disabled={!ready || busy || stale}
            onChange={(e) => onInput(e.target.value)}
            onKeyDown={(e) => {
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
            disabled={!ready || busy || stale || !input.trim()}
            onClick={onSend}
          >
            {phase === "sending" ? (
              <Loader2 className="cw-i cw-spin" />
            ) : (
              <ArrowUp className="cw-i" />
            )}
          </button>
        </div>
      </div>

        {(showInitialOverlay || showProgressOverlay || showStaleOverlay) && (
          <div className="cw-debug-overlay" role="status" aria-live="polite">
            <div className="cw-debug-overlay-content">
              <strong className="cw-debug-overlay-title">
                {showProgressOverlay
                  ? "正在初始化调试环境"
                  : showStaleOverlay
                    ? "Agent 配置已变更"
                    : "启动调试环境"}
              </strong>
              {showProgressOverlay ? (
                <div className="cw-debug-overlay-progress">
                  {logs.map((line, i) => (
                    <div key={`${line}-${i}`} className="cw-debug-logline">
                      {i === logs.length - 1 ? (
                        <Loader2 className="cw-i cw-spin" />
                      ) : (
                        <Check className="cw-i" />
                      )}
                      <span>{line}</span>
                    </div>
                  ))}
                </div>
              ) : showStaleOverlay ? (
                <>
                  <span className="cw-debug-overlay-copy">
                    当前对话仍在使用上一次配置。更新后，新配置才会生效。
                  </span>
                <div className="cw-debug-overlay-actions">
                  <button
                    type="button"
                    className="cw-debug-ignore"
                    disabled={busy}
                    onClick={onIgnoreChanges}
                  >
                    忽略
                  </button>
                  <button
                    type="button"
                    className="cw-debug-start"
                    disabled={busy}
                    onClick={onRestart}
                  >
                    <RefreshCw className="cw-i" />
                    更新 Agent
                  </button>
                </div>
                </>
              ) : (
                <>
                  <span className="cw-debug-overlay-copy">
                    启动后会生成代码并创建临时运行环境。
                  </span>
                  <button
                    type="button"
                    className="cw-debug-start"
                    onClick={onRestart}
                  >
                    <DebugRunIcon className="cw-i cw-debug-run-icon" />
                    启动调试环境
                  </button>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </aside>
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
}

export function CustomCreate({
  onBack,
  onCreate,
  onAgentAdded,
  initialDraft,
  features,
  onDeploymentTaskChange,
}: CustomCreateProps) {
  void onCreate; // outcome is the in-pane project preview, not a navigation
  void onBack; // no footer nav in the single-scroll layout; back lives in app chrome
  const [draft, setDraft] = useState<AgentDraft>(
    () => initialDraft ?? emptyDraft(),
  );
  const [showErrors, setShowErrors] = useState(false);
  const [validationPulse, setValidationPulse] = useState(0);
  const [project, setProject] = useState<AgentProject | null>(null);
  const [building, setBuilding] = useState(false);
  const [deployRegion, setDeployRegion] = useState<string>("cn-beijing");
  const debugEnabled = features?.generatedAgentTestRun === true;
  const debugDisabledReason =
    features?.generatedAgentTestRunDisabledReason ||
    "当前后端暂不支持生成 Agent 调试运行。";
  const [debugPhase, setDebugPhase] = useState<DebugPhase>("idle");
  const [debugRun, setDebugRun] = useState<GeneratedAgentTestRun | null>(null);
  const debugRunRef = useRef<GeneratedAgentTestRun | null>(null);
  const [debugSessionId, setDebugSessionId] = useState<string | null>(null);
  const [debugProjectName, setDebugProjectName] = useState("");
  const [debugLogs, setDebugLogs] = useState<string[]>([]);
  const [debugMessages, setDebugMessages] = useState<DebugMessage[]>([]);
  const [debugInput, setDebugInput] = useState("");
  const [debugError, setDebugError] = useState<string | null>(null);
  const [debugSnapshot, setDebugSnapshot] = useState("");
  const [ignoredDebugSnapshot, setIgnoredDebugSnapshot] = useState("");
  // The section nearest the top of the scroll container (scroll-spy) — drives
  // the right-hand step nav highlight.
  const [activeId, setActiveId] = useState<StepId>("basic");
  const [buildErr, setBuildErr] = useState("");
  const [modelAdvancedOpen, setModelAdvancedOpen] = useState(false);
  const [moreToolTypesOpen, setMoreToolTypesOpen] = useState(false);
  const [advancedConfigOpen, setAdvancedConfigOpen] = useState(false);

  // Which tree node is being edited ([] = root). The detail pane and per-node
  // inline errors are driven by this selection.
  const [selectedPath, setSelectedPath] = useState<NodePath>([]);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const sectionRefs = useRef<Partial<Record<StepId, HTMLElement | null>>>({});

  useEffect(() => {
    return () => {
      const run = debugRunRef.current;
      if (run) {
        deleteGeneratedAgentTestRun(run.runId).catch((err) =>
          console.warn("清理调试运行失败", err),
        );
      }
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
          <h2 className="cw-sec-title">
            {meta.label}
            {meta.required && <span className="cw-sec-required">必填</span>}
          </h2>
        </header>
        {children}
      </section>
    );
  }

  // The selection is clamped to a path that still exists (a deletion may have
  // removed the previously-selected node). `patch` always edits this node.
  const safePath = pathExists(draft, selectedPath) ? selectedPath : [];
  const node = getNode(draft, safePath);
  const isRootAgent = safePath.length === 0;
  const modelAdvancedId = `cw-model-advanced-${safePath.join("-") || "root"}`;
  const moreToolTypesId = `cw-more-tool-types-${safePath.join("-") || "root"}`;
  const advancedConfigId = `cw-advanced-config-${safePath.join("-") || "root"}`;
  const activeTypeIndex = Math.max(
    0,
    AGENT_TYPES.findIndex((type) => type.id === (node.agentType ?? "llm")),
  );

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

  const clearRootAgent = () => {
    if (
      !window.confirm("清空根 Agent 的全部配置和子 Agent？此操作无法撤销。")
    ) {
      return;
    }
    setDraft(emptyDraft());
    setSelectedPath([]);
    setShowErrors(false);
    setAdvancedConfigOpen(false);
  };

  // Root-only rich sections read these off the root draft directly.
  const builtinTools = node.builtinTools ?? [];
  const mcpTools = node.mcpTools ?? [];
  const tracingExporters = node.tracingExporters ?? [];
  const selectedSkills = node.selectedSkills ?? [];
  const advancedEnabledCount = [
    node.memory.shortTerm,
    node.memory.longTerm,
    node.tracing,
  ].filter(Boolean).length;

  const toggleBuiltin = (id: string) =>
    patch({
      builtinTools: builtinTools.includes(id)
        ? builtinTools.filter((x) => x !== id)
        : [...builtinTools, id],
    });

  const toggleExporter = (id: string) => {
    const next = tracingExporters.includes(id)
      ? tracingExporters.filter((x) => x !== id)
      : [...tracingExporters, id];
    // Auto-enable tracing when at least one exporter is chosen.
    patch({
      tracingExporters: next,
      tracing: next.length > 0 ? true : node.tracing,
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
  const currentDebugSnapshot = useMemo(() => debugSnapshotKey(draft), [draft]);
  const deploymentEnv = useMemo(() => collectDeploymentEnv(draft), [draft]);
  const debugStale = Boolean(
    debugRun &&
      debugSnapshot &&
      debugSnapshot !== currentDebugSnapshot &&
      ignoredDebugSnapshot !== currentDebugSnapshot,
  );

  useEffect(() => {
    if (ignoredDebugSnapshot && ignoredDebugSnapshot !== currentDebugSnapshot) {
      setIgnoredDebugSnapshot("");
    }
  }, [currentDebugSnapshot, ignoredDebugSnapshot]);

  // Per-step completion, for the nav's done-checkmarks + progress fill.
  const completion = useMemo<Record<StepId, boolean>>(
    () => ({
      type: true,
      basic: a2a
        ? !a2aRegistrySpaceMissing
        : !nameInvalid && (orchestrator || !instructionMissing),
      model: Boolean(
        node.modelName?.trim() ||
          node.modelProvider?.trim() ||
          node.modelApiBase?.trim(),
      ),
      tools: builtinTools.length > 0 || mcpTools.length > 0,
      skills: selectedSkills.length > 0,
      knowledge: node.knowledgebase,
      advanced: node.memory.shortTerm || node.memory.longTerm || node.tracing,
      subagents: (node.subAgents?.length ?? 0) > 0,
      review: canFinish,
    }),
    [
      node,
      nameInvalid,
      instructionMissing,
      orchestrator,
      a2a,
      canFinish,
      builtinTools,
      mcpTools,
      selectedSkills,
    ],
  );

  // The nav only lists the sections actually rendered for THIS node's type —
  // orchestrators / A2A leaves have far fewer than an LLM (type lives in the
  // top bar; sub-agents live in the left tree; both are excluded here).
  const rootOnlyStepIds: StepId[] = isRootAgent ? ["advanced"] : [];
  const navStepIds: StepId[] =
    orchestrator || a2a
      ? ["basic"]
      : ["basic", "model", "tools", "skills", "knowledge", ...rootOnlyStepIds];
  const navSteps = STEPS.filter((s) => navStepIds.includes(s.id));
  const navStepKey = navStepIds.join("|");
  const selectedNodeKey = safePath.join(".");
  const activeIndex = navSteps.findIndex((s) => s.id === activeId);

  // Smooth-scroll a section into view (nav click is a convenience).
  const scrollToSection = (id: StepId) => {
    sectionRefs.current[id]?.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  };

  // Scroll-spy: follow the section that has crossed the scroll area's top edge.
  // A passive scroll listener is more reliable here than IntersectionObserver:
  // tall sections may stay intersecting for a long time, so no observer callback
  // fires while the user moves through them.
  useEffect(() => {
    if (project) return;
    const root = scrollRef.current;
    if (!root) return;
    const ids = navStepKey.split("|") as StepId[];
    let frame = 0;

    const syncActiveSection = () => {
      frame = 0;
      const lastId = ids[ids.length - 1];
      let nextId = ids[0];

      if (root.scrollTop + root.clientHeight >= root.scrollHeight - 2) {
        nextId = lastId;
      } else {
        const anchor = root.getBoundingClientRect().top + 24;
        for (const id of ids) {
          const section = sectionRefs.current[id];
          if (!section || section.getBoundingClientRect().top > anchor) break;
          nextId = id;
        }
      }

      if (nextId)
        setActiveId((current) => (current === nextId ? current : nextId));
    };

    const scheduleSync = () => {
      if (!frame) frame = window.requestAnimationFrame(syncActiveSection);
    };

    syncActiveSection();
    root.addEventListener("scroll", scheduleSync, { passive: true });
    window.addEventListener("resize", scheduleSync);
    return () => {
      root.removeEventListener("scroll", scheduleSync);
      window.removeEventListener("resize", scheduleSync);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [project, navStepKey, selectedNodeKey]);

  const requireCompleteDraft = () => {
    if (canFinish) return true;
    setShowErrors(true);
    setValidationPulse((pulse) => pulse + 1);
    if (problems[0]) {
      setSelectedPath(problems[0].path);
      window.requestAnimationFrame(() => scrollToSection("basic"));
    }
    return false;
  };

  const cleanupDebugRun = async () => {
    const run = debugRunRef.current;
    debugRunRef.current = null;
    setDebugRun(null);
    setDebugSessionId(null);
    setDebugSnapshot("");
    setIgnoredDebugSnapshot("");
    if (run) {
      try {
        await deleteGeneratedAgentTestRun(run.runId);
      } catch (err) {
        console.warn("清理调试运行失败", err);
      }
    }
  };

  const finish = async () => {
    setBuildErr("");
    if (!requireCompleteDraft()) return;
    // NOTE: do NOT call onCreate() here — it navigates away from the create
    // view. The generated project preview below IS the outcome of this step.

    setBuilding(true);
    try {
      // Network settings are deployment-only and are not part of the codegen
      // API schema. Keep them in the local draft while sending only the
      // channel flag needed to generate the project.
      const proj = await generateAgentProject(codegenDraft(draft));
      await cleanupDebugRun();
      setDebugPhase("idle");
      setDebugProjectName("");
      setDebugLogs([]);
      setDebugMessages([]);
      setDebugInput("");
      setDebugError(null);
      setProject(proj);
    } catch (err) {
      setBuildErr(
        `打开部署页失败：${err instanceof Error ? err.message : String(err)}`,
      );
    } finally {
      setBuilding(false);
    }
  };

  const startDebug = async () => {
    if (!debugEnabled || building) return;
    if (!requireCompleteDraft()) return;

    const snapshot = debugSnapshotKey(draft);
    setIgnoredDebugSnapshot("");
    setDebugError(null);
    setDebugMessages([]);
    setDebugInput("");
    setDebugLogs([]);
    setDebugPhase("building");

    try {
      await cleanupDebugRun();
      const logs: string[] = [];
      const pushLog = (line: string) => {
        logs.push(line);
        setDebugLogs([...logs]);
      };
      pushLog("提交 Agent 配置");
      setDebugPhase("starting");
      pushLog("初始化调试环境");
      const run = await createGeneratedAgentTestRun(codegenDraft(draft));
      debugRunRef.current = run;
      setDebugRun(run);
      setDebugProjectName(run.appName);
      pushLog("创建调试会话");
      const sid = await createGeneratedAgentTestSession(run.runId, "test_user");
      setDebugSessionId(sid);
      setDebugSnapshot(snapshot);
      pushLog("调试环境就绪");
      setDebugPhase("ready");
    } catch (err) {
      setDebugError(err instanceof Error ? err.message : String(err));
      setDebugPhase("error");
    }
  };

  const sendDebugMessage = async () => {
    const run = debugRunRef.current;
    const sessionId = debugSessionId;
    const text = debugInput.trim();
    if (!run || !sessionId || !text || debugPhase === "sending") return;

    setDebugInput("");
    setDebugPhase("sending");
    setDebugMessages((prev) => [
      ...prev,
      { role: "user", content: text },
      { role: "assistant", content: "", blocks: [] },
    ]);

    try {
      let acc = emptyAcc();
      let fullText = "";
      for await (const event of runGeneratedAgentTestSSE({
        runId: run.runId,
        userId: "test_user",
        sessionId,
        text,
      })) {
        const error = event.error || event.errorMessage || event.error_message;
        if (error) {
          setDebugMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            if (last?.role === "assistant") last.error = String(error);
            return next;
          });
          break;
        }
        acc = applyEvent(acc, event);
        fullText = acc.blocks
          .filter((b) => b.kind === "text")
          .map((b) => (b as { text: string }).text)
          .join("");
        setDebugMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          if (last?.role === "assistant") {
            last.content = fullText;
            last.blocks = acc.blocks;
          }
          return next;
        });
      }
      setDebugPhase("ready");
    } catch (err) {
      setDebugMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role === "assistant") {
          last.error = err instanceof Error ? err.message : String(err);
        }
        return next;
      });
      setDebugPhase("ready");
    }
  };

  // ----------------------------------------------------------------
  // Preview mode: takes over the whole pane, hiding the wizard chrome.
  // ----------------------------------------------------------------
  if (project) {
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
        { region: deployRegion, projectName: "default", network },
        { ...options, onStage },
      );
    };

    return (
      <div className="cw-root cw-root-preview">
        <div className="cw-preview-body">
          <ProjectPreview
            project={project}
            agentDraft={draft}
            agentName={draft.name || "未命名 Agent"}
            agentCount={countDraftAgents(draft)}
            onChange={setProject}
            onDeploy={handleDeploy}
            onAgentAdded={onAgentAdded}
            onDeploymentTaskChange={onDeploymentTaskChange}
            feishuEnabled={!!draft.deployment?.feishuEnabled}
            onFeishuEnabledChange={async (feishuEnabled) => {
              const nextDraft: AgentDraft = {
                ...draft,
                deployment: {
                  ...(draft.deployment ?? { feishuEnabled: false }),
                  feishuEnabled,
                },
              };
              const nextProject = await generateAgentProject(codegenDraft(nextDraft));
              setDraft(nextDraft);
              setProject(nextProject);
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
            onBack={() => setProject(null)}
            onExportYaml={() =>
              downloadText(
                `${draft.name || "agent"}.yaml`,
                draftToYaml(draft),
                "text/yaml",
              )
            }
          />
        </div>
      </div>
    );
  }

  const Section = sectionImpl.current;

  const metaOf = (id: StepId) => STEPS.find((s) => s.id === id)!;

  return (
    <div className="cw-root">
      <div className="cw-editor">
        {/* Left: the Agent structure tree (select / add / remove / reorder). */}
        <aside className="cw-tree" aria-label="Agent 结构">
          <div className="cw-tree-head">Agent 结构</div>
          <TreeNode
            root={draft}
            path={[]}
            selectedPath={safePath}
            duplicateNames={duplicateNames}
            showErrors={showErrors}
            validationPulse={validationPulse}
            onSelect={setSelectedPath}
            onChange={applyTree}
            onClearRoot={clearRootAgent}
          />
        </aside>
        {/* Right: the form for the currently-selected node. The agent-type bar
            is fixed on top (outside the scroll area); the form (left) + step
            nav (right) scroll below it. */}
        <div className="cw-detail">
          {/* Fixed top bar: pick the agent type. */}
          <div className="cw-typebar">
            <div className="cw-typebar-inner">
              <div
                className="cw-typeradio cw-typeradio--row"
                role="radiogroup"
                aria-label="Agent 类型"
                style={
                  {
                    "--cw-agent-type-gap": `${AGENT_TYPE_GAP_PX}px`,
                    "--cw-agent-type-slider-width": `calc((100% - ${
                      8 + AGENT_TYPE_GAP_PX * (AGENT_TYPES.length - 1)
                    }px) / ${AGENT_TYPES.length})`,
                    "--cw-active-type-offset": `calc(${activeTypeIndex * 100}% + ${
                      activeTypeIndex * AGENT_TYPE_GAP_PX
                    }px)`,
                  } as CSSProperties
                }
              >
                <span className="cw-typeradio-slider" aria-hidden />
                {AGENT_TYPES.map((t) => {
                  const on = (node.agentType ?? "llm") === t.id;
                  const remoteTypeDisabled = isRootAgent && t.id === "a2a";
                  const disabledHintId = remoteTypeDisabled
                    ? "cw-remote-agent-disabled-hint"
                    : undefined;
                  return (
                    <label
                      key={t.id}
                      className={`cw-typeradio-item ${on ? "is-on" : ""} ${
                        remoteTypeDisabled ? "is-disabled" : ""
                      }`}
                      title={remoteTypeDisabled ? undefined : t.desc}
                      tabIndex={remoteTypeDisabled ? 0 : undefined}
                      aria-describedby={disabledHintId}
                    >
                      <input
                        type="radio"
                        name="agentType"
                        className="cw-typeradio-input"
                        checked={on}
                        disabled={remoteTypeDisabled}
                        onChange={() => selectAgentType(t.id)}
                      />
                      <span className="cw-typeradio-title">
                        {AGENT_TYPE_BAR_LABELS[t.id].replace("智能体", "")}
                        <wbr />
                        智能体
                      </span>
                      {remoteTypeDisabled && (
                        <span
                          id={disabledHintId}
                          className="cw-typeradio-disabled-hint"
                          role="tooltip"
                        >
                          远程 Agent 仅可作为子 Agent
                        </span>
                      )}
                    </label>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Scroll area: form on the left, step nav on the right. */}
          <div className="cw-detail-scroll" ref={scrollRef}>
          <div className="cw-detail-inner">
            <div className="cw-lower">
            <div className="cw-form-col">
            <Section meta={metaOf("basic")}>
                <div className="cw-form">
                      {!a2a && (
                        <>
                    <div className="cw-field">
                      <label className="cw-label">
                        Agent 名称<span className="cw-req">*</span>
                      </label>
                      <input
                        className={`cw-input ${invalidClass(nameInvalid)}`}
                        value={node.name}
                        placeholder="customer_service"
                        onChange={(e) => patch({ name: e.target.value })}
                      />
                      {showErrors && nameProblem ? (
                              <span className="cw-error-text">
                                {nameProblem}
                              </span>
                      ) : (
                        <span className="cw-help">
                                遵循 Google ADK 命名规则，且在 Agent
                                结构中保持唯一。
                        </span>
                      )}
                    </div>
                    <div className="cw-field">
                      <label className="cw-label">
                        描述<span className="cw-req">*</span>
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
                          描述会显示在 Agent 列表与选择器中。
                        </span>
                      )}
                    </div>
                        </>
                      )}
                    {orchestrator ? (
                      <>
                        <p className="cw-section-desc">
                            编排型 Agent 只负责调度子
                            Agent，不需要模型或系统提示词。请在左侧 「Agent
                            结构」中为它添加、排序子 Agent。
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
                            </div>
                            <p className="cw-help cw-remote-center-description">
                              远程 Agent 的名称、描述和能力来自中心返回的 Agent Card。
                              系统会根据每轮任务动态发现并挂载匹配的 Agent。
                            </p>
                          </div>
                          <RuntimeEnvFields
                            env={A2A_REGISTRY_ENV}
                            values={a2aRegistryEnvValues(node.a2aRegistry, {
                              includeDefaults: false,
                            })}
                            onChange={patchA2aRegistryEnv}
                          />
                          {showErrors && a2aRegistrySpaceMissing && (
                            <span className="cw-error-text">
                              AgentKit 智能体中心 ID 为必填项
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
                      className="cw-more-options"
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
                            <span className="cw-help">
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
                          items={BUILTIN_TOOLS}
                          selected={builtinTools}
                          onToggle={toggleBuiltin}
                          scrollRows={6}
                        />
                      </div>
                    </div>
                    <button
                      type="button"
                      className="cw-more-options"
                      aria-expanded={moreToolTypesOpen}
                      aria-controls={moreToolTypesId}
                            onClick={() =>
                              setMoreToolTypesOpen((open) => !open)
                            }
                    >
                      <span>更多类型工具</span>
                      {mcpTools.length > 0 && (
                        <span className="cw-more-options-count">
                          已配置 {mcpTools.length}
                        </span>
                      )}
                      <ChevronRight
                        className={`cw-more-options-chevron ${
                          moreToolTypesOpen ? "is-open" : ""
                        }`}
                        aria-hidden
                      />
                    </button>
                    <AnimatePresence initial={false}>
                      {moreToolTypesOpen && (
                        <motion.div
                          id={moreToolTypesId}
                          className="cw-model-advanced"
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.18, ease: "easeOut" }}
                        >
                          <div className="cw-field">
                            <label className="cw-label">MCP 工具</label>
                            <span className="cw-help">
                                    连接外部 MCP
                                    服务，生成时会为每个条目创建对应的
                                    MCPToolset。
                            </span>
                            <McpToolEditor
                              tools={mcpTools}
                                    onChange={(next) =>
                                      patch({ mcpTools: next })
                                    }
                            />
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
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
                            patch({ knowledgebaseBackend: id })
                          }
                        />
                        <RuntimeEnvFields
                          env={
                            KB_BACKENDS.find(
                                    (item) =>
                                      item.id ===
                                      (node.knowledgebaseBackend ?? "local"),
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
              <section
                ref={(el) => {
                  sectionRefs.current.advanced = el;
                }}
                id="cw-sec-advanced"
                data-step-id="advanced"
                className="cw-section cw-advanced-section"
              >
                <button
                  type="button"
                  className="cw-advanced-disclosure"
                  aria-expanded={advancedConfigOpen}
                  aria-controls={advancedConfigId}
                            onClick={() =>
                              setAdvancedConfigOpen((open) => !open)
                            }
                >
                  <span className="cw-advanced-disclosure-title">进阶配置</span>
                  <ChevronRight
                    className={`cw-advanced-disclosure-chevron ${
                      advancedConfigOpen ? "is-open" : ""
                    }`}
                    aria-hidden
                  />
                  {advancedEnabledCount > 0 && (
                    <span className="cw-more-options-count">
                      已启用 {advancedEnabledCount}
                    </span>
                  )}
                </button>
                <AnimatePresence initial={false}>
                  {advancedConfigOpen && (
                    <motion.div
                      id={advancedConfigId}
                      className="cw-advanced-content"
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2, ease: "easeOut" }}
                    >
                    <div className="cw-advanced-group">
                      <div className="cw-advanced-group-head">
                        <span>记忆</span>
                      </div>
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
                    </div>
                    <div className="cw-advanced-group">
                      <div className="cw-advanced-group-head">
                        <span>观测</span>
                      </div>
                      <div className="cw-form cw-toggle-stack">
                        <Toggle
                          checked={node.tracing}
                          onChange={(v) => patch({ tracing: v })}
                          title="观测 / Tracing"
                          desc="记录每一步的调用链路与耗时，便于调试与性能分析。"
                          icon={Eye}
                        />
                        {node.tracing && (
                          <div className="cw-field cw-subfield">
                                        <label className="cw-label">
                                          Tracing 导出器
                                        </label>
                            <span className="cw-help">
                                          选择一个或多个观测平台，生成时会写入对应的
                                          ENABLE_* 开关与环境变量。
                            </span>
                            <Checklist
                              items={TRACING_EXPORTERS}
                              selected={tracingExporters}
                              onToggle={toggleExporter}
                            />
                            <RuntimeEnvFields
                                          env={TRACING_EXPORTERS.filter(
                                            (item) =>
                                              tracingExporters.includes(
                                                item.id,
                                              ),
                              ).flatMap((item) => item.env)}
                                          values={
                                            draft.deployment?.envValues ?? {}
                                          }
                              onChange={patchDeploymentEnv}
                            />
                          </div>
                        )}
                      </div>
                    </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </section>
            )}
              </>
            )}
          </div>

            {/* Right rail: scroll-spy step nav (click to jump to a section).
                Only the sections rendered for this node's type are listed. */}
            <nav className="cw-rail" aria-label="步骤导航">
              <ol className="cw-steps">
                <div className="cw-rail-track" aria-hidden>
                  <motion.div
                    className="cw-rail-fill"
                    animate={{
                      height: `${(Math.max(activeIndex, 0) / Math.max(navSteps.length - 1, 1)) * 100}%`,
                    }}
                        transition={{
                          type: "spring",
                          stiffness: 260,
                          damping: 32,
                        }}
                  />
                </div>
                {navSteps.map((s) => {
                  const active = s.id === activeId;
                  const done = completion[s.id];
                  return (
                    <li key={s.id}>
                      <button
                        type="button"
                        className={`cw-step ${active ? "is-active" : ""} ${done ? "is-done" : ""}`}
                        onClick={() => scrollToSection(s.id)}
                        aria-current={active ? "step" : undefined}
                        aria-label={s.label}
                      >
                        <span className="cw-step-marker" aria-hidden>
                          {active ? (
                            <span className="cw-dot" />
                          ) : done ? (
                            <Check className="cw-step-check" />
                          ) : (
                            <span className="cw-dot" />
                          )}
                        </span>
                        <span className="cw-step-tooltip" aria-hidden>
                          {s.label}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ol>
            </nav>
              </div>
              {/* cw-lower */}
            </div>
            {/* cw-detail-inner */}
          </div>
          {/* cw-detail-scroll */}
        </div>
        {/* cw-detail */}
        <DebugPanel
          enabled={debugEnabled}
          disabledReason={debugDisabledReason}
          phase={debugPhase}
          stale={debugStale}
          run={debugRun}
          projectName={debugProjectName || draft.name}
          logs={debugLogs}
          messages={debugMessages}
          input={debugInput}
          error={debugError}
          deploying={building}
          deployError={buildErr}
          onInput={setDebugInput}
          onSend={sendDebugMessage}
          onRestart={startDebug}
          onIgnoreChanges={() => setIgnoredDebugSnapshot(currentDebugSnapshot)}
          onDeploy={finish}
        />
      </div>
      {/* cw-editor */}
    </div>
  );
}
