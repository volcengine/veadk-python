import {
  lazy,
  Suspense,
  type ReactNode,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  ChevronDown,
  ChevronRight,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  File,
  FileDown,
  FilePlus,
  Folder,
  Loader2,
  Maximize2,
  MessageSquare,
  Pencil,
  Plus,
  Trash2,
  X,
} from "lucide-react";
// Use the core build + register only the languages we map, so we don't ship
// all ~190 highlight.js grammars (keeps the bundle small).
import hljs from "highlight.js/lib/core";
import python from "highlight.js/lib/languages/python";
import typescript from "highlight.js/lib/languages/typescript";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import yaml from "highlight.js/lib/languages/yaml";
import markdown from "highlight.js/lib/languages/markdown";
import bash from "highlight.js/lib/languages/bash";
import ini from "highlight.js/lib/languages/ini";
import dockerfile from "highlight.js/lib/languages/dockerfile";
import makefile from "highlight.js/lib/languages/makefile";
hljs.registerLanguage("python", python);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("json", json);
hljs.registerLanguage("yaml", yaml);
hljs.registerLanguage("markdown", markdown);
hljs.registerLanguage("bash", bash);
hljs.registerLanguage("ini", ini);
hljs.registerLanguage("dockerfile", dockerfile);
hljs.registerLanguage("makefile", makefile);
import type { AgentProject, ProjectFile } from "../create/project";
import type { AgentDraft, NetworkConfig } from "../create/types";
import { AgentBuildCanvas } from "../create/AgentBuildCanvas";
import {
  FEISHU_ENV,
  type EnvVar,
} from "../create/veadkCatalog";
import {
  firstMissingRuntimeEnv,
  runtimeEnvDisplayRows,
  runtimeEnvVars,
} from "../create/deploymentEnv";
import {
  listIdentityUserPools,
  RuntimeProbeError,
  type DeployAuthentication,
  type DeployBuildLogSnapshot,
  type DeployStage,
  type IdentityUserPool,
} from "../adk/client";
import feishuLogo from "../assets/feishu-logo.svg";
import { buildZip } from "./zip";
import { ProjectCodeBrowser } from "./CodeBrowserDialog";
import { DeploymentErrorMessage } from "./DeploymentErrorMessage";
import { mergeDeployBuildLog } from "./deployBuildLog";
import "./ProjectPreview.css";

const CodeEditor = lazy(() => import("./CodeEditor"));
const ignoreCanvasAction = () => undefined;

interface DeploymentConfirmDialogProps {
  open: boolean;
  isUpdate: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

function DeploymentConfirmDialog({
  open,
  isUpdate,
  onCancel,
  onConfirm,
}: DeploymentConfirmDialogProps) {
  const cancelButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    cancelButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onCancel, open]);

  if (!open) return null;

  return createPortal(
    <div
      className="code-browser-backdrop pp-confirm-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <section
        className="code-browser-dialog pp-confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="pp-confirm-title"
        aria-describedby="pp-confirm-description"
      >
        <header className="code-browser-head pp-confirm-head">
          <div className="code-browser-title-wrap">
            <span className="code-browser-title-icon pp-confirm-icon" aria-hidden="true">
              <AlertTriangle />
            </span>
            <h2 id="pp-confirm-title">{isUpdate ? "确认更新" : "确认部署"}</h2>
          </div>
          <button
            type="button"
            className="code-browser-close"
            onClick={onCancel}
            aria-label="关闭部署确认"
          >
            <X aria-hidden="true" />
          </button>
        </header>
        <div className="pp-confirm-body">
          <p id="pp-confirm-description">
            {isUpdate
              ? "将更新并发布到当前云端 Runtime，过程可能需要几分钟。确定继续吗？"
              : "将创建新的云端 Runtime，部署过程可能需要几分钟。确定继续吗？"}
          </p>
        </div>
        <footer className="pp-confirm-actions">
          <button ref={cancelButtonRef} type="button" onClick={onCancel}>
            取消
          </button>
          <button type="button" className="is-primary" onClick={onConfirm}>
            {isUpdate ? "确定更新" : "确定部署"}
          </button>
        </footer>
      </section>
    </div>,
    document.body,
  );
}

interface DeploymentSelectOption {
  value: string;
  label: string;
  description?: string;
  badge?: string;
}

interface DeploymentSelectProps {
  ariaLabel: string;
  value: string;
  placeholder: string;
  options: DeploymentSelectOption[];
  disabled?: boolean;
  onChange: (value: string) => void;
}

function DeploymentSelect({
  ariaLabel,
  value,
  placeholder,
  options,
  disabled = false,
  onChange,
}: DeploymentSelectProps) {
  const listboxId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const selectedOption = options.find((option) => option.value === value);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (
        event.target instanceof Node &&
        rootRef.current &&
        !rootRef.current.contains(event.target)
      ) {
        setOpen(false);
      }
    };
    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    optionRefs.current[activeIndex]?.focus();
  }, [activeIndex, open]);

  const openMenu = (direction: 1 | -1 = 1) => {
    const selectedIndex = options.findIndex((option) => option.value === value);
    const nextIndex =
      selectedIndex >= 0
        ? selectedIndex
        : direction === 1
          ? 0
          : Math.max(0, options.length - 1);
    setActiveIndex(nextIndex);
    setOpen(true);
  };

  const moveActiveOption = (nextIndex: number) => {
    if (options.length === 0) return;
    setActiveIndex((nextIndex + options.length) % options.length);
  };

  const selectOption = (option: DeploymentSelectOption) => {
    onChange(option.value);
    setOpen(false);
    triggerRef.current?.focus();
  };

  return (
    <div
      className="pp-deployment-select"
      ref={rootRef}
      onKeyDown={(event) => {
        if (event.key === "Escape" && open) {
          event.preventDefault();
          setOpen(false);
          triggerRef.current?.focus();
          return;
        }
        if (event.key === "Tab") {
          setOpen(false);
          return;
        }
        if (event.key === "ArrowDown") {
          event.preventDefault();
          if (!open) openMenu(1);
          else moveActiveOption(activeIndex + 1);
        } else if (event.key === "ArrowUp") {
          event.preventDefault();
          if (!open) openMenu(-1);
          else moveActiveOption(activeIndex - 1);
        } else if (open && event.key === "Home") {
          event.preventDefault();
          setActiveIndex(0);
        } else if (open && event.key === "End") {
          event.preventDefault();
          setActiveIndex(Math.max(0, options.length - 1));
        }
      }}
    >
      <button
        ref={triggerRef}
        type="button"
        className="pp-deployment-select-trigger"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        disabled={disabled || options.length === 0}
        onClick={() => {
          if (open) setOpen(false);
          else openMenu();
        }}
      >
        <span className={!selectedOption ? "is-placeholder" : undefined}>
          {selectedOption?.label ?? placeholder}
        </span>
        <ChevronDown
          aria-hidden="true"
          className={`pp-deployment-select-chevron${open ? " is-open" : ""}`}
        />
      </button>
      {open && (
        <div
          id={listboxId}
          className="pp-deployment-select-menu"
          role="listbox"
          aria-label={ariaLabel}
        >
          {options.map((option, index) => {
            const selected = option.value === value;
            return (
              <button
                key={option.value}
                ref={(node) => {
                  optionRefs.current[index] = node;
                }}
                type="button"
                role="option"
                aria-selected={selected}
                tabIndex={index === activeIndex ? 0 : -1}
                className={`pp-deployment-select-option${selected ? " is-selected" : ""}`}
                title={option.description}
                onFocus={() => setActiveIndex(index)}
                onClick={() => selectOption(option)}
              >
                <span className="pp-deployment-select-copy">
                  <span className="pp-deployment-select-name">
                    {option.label}
                    {option.badge && (
                      <span className="pp-deployment-select-badge">
                        {option.badge}
                      </span>
                    )}
                  </span>
                  {option.description && <small>{option.description}</small>}
                </span>
                {selected && <Check aria-hidden="true" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function IdentityUserPoolSelect({
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
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    listIdentityUserPools(controller.signal)
      .then((items) => setPools(items))
      .catch((cause) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setPools([]);
        setError(cause instanceof Error ? cause.message : String(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [reloadKey]);

  const options = useMemo(
    () =>
      [...pools]
        .sort((left, right) => Number(right.isCurrent) - Number(left.isCurrent))
        .map((pool) => ({
          value: pool.uid,
          label: pool.name.trim() || "未命名用户池",
          description: pool.domain || pool.uid,
          badge: pool.isCurrent ? "当前 Studio" : undefined,
        })),
    [pools],
  );
  const selectedPool = pools.find((pool) => pool.uid === value);

  return (
    <div className="pp-user-pool-picker">
      <DeploymentSelect
        ariaLabel="部署用户池"
        value={value}
        placeholder={loading ? "正在加载用户池…" : "请选择用户池"}
        options={options}
        disabled={disabled || loading || Boolean(error)}
        onChange={onChange}
      />
      {error ? (
        <div className="pp-user-pool-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setReloadKey((key) => key + 1)}>
            重试
          </button>
        </div>
      ) : loading ? (
        <span className="pp-user-pool-status" aria-live="polite">
          <Loader2 aria-hidden="true" className="pp-user-pool-spinner" />
          正在加载 Identity 用户池…
        </span>
      ) : pools.length === 0 ? (
        <span className="pp-user-pool-status">当前账号下暂无 Identity 用户池。</span>
      ) : selectedPool?.isCurrent ? (
        <span className="pp-user-pool-status">
          当前 Studio 的登录 JWT 将透传访问此 Runtime。
        </span>
      ) : selectedPool ? (
        <span className="pp-user-pool-status">
          访问时需要使用此用户池签发的 JWT。
        </span>
      ) : (
        <span className="pp-user-pool-status">
          当前 Studio 使用的用户池已在列表中标注。
        </span>
      )}
    </div>
  );
}

const DEPLOYMENT_AUTHENTICATION_OPTIONS: DeploymentSelectOption[] = [
  {
    value: "api_key",
    label: "API Key",
    description: "默认方式，使用 Runtime API Key 访问",
  },
  {
    value: "user_pool",
    label: "用户池",
    description: "使用 Identity 用户池签发的 JWT",
  },
];

// --- syntax highlighting ----------------------------------------------------

/** Map a file extension (without dot, lowercased) to an hljs language id. */
const EXT_LANG: Record<string, string> = {
  py: "python",
  pyi: "python",
  ts: "typescript",
  tsx: "typescript",
  mts: "typescript",
  cts: "typescript",
  js: "javascript",
  jsx: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  json: "json",
  jsonc: "json",
  yaml: "yaml",
  yml: "yaml",
  md: "markdown",
  markdown: "markdown",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  toml: "ini",
  ini: "ini",
  cfg: "ini",
  conf: "ini",
  env: "ini",
  txt: "plaintext",
};

/** Map well-known full filenames to an hljs language id. */
const NAME_LANG: Record<string, string> = {
  dockerfile: "dockerfile",
  "requirements.txt": "plaintext",
  "requirements-dev.txt": "plaintext",
  ".env": "ini",
  ".gitignore": "plaintext",
  "makefile": "makefile",
};

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** Pick an hljs language id for a given file path. Returns null when unknown. */
function languageFor(path: string): string | null {
  const file = path.split("/").pop() ?? path;
  const lower = file.toLowerCase();
  if (NAME_LANG[lower]) return NAME_LANG[lower];
  // Handle dotfiles / extensionless names like `.env`, `Dockerfile`.
  if (lower.startsWith("dockerfile")) return "dockerfile";
  if (lower.startsWith(".env")) return "ini";
  const dot = lower.lastIndexOf(".");
  if (dot === -1) return null;
  const ext = lower.slice(dot + 1);
  return EXT_LANG[ext] ?? null;
}

/** Produce highlighted HTML for the given file content. */
function highlight(content: string, path: string): string {
  try {
    const lang = languageFor(path);
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(content, { language: lang, ignoreIllegals: true }).value;
    }
    if (lang === null) {
      // Unknown extension: let hljs guess.
      return hljs.highlightAuto(content).value;
    }
    // Known mapping but language not registered: render as plaintext.
    return escapeHtml(content);
  } catch {
    return escapeHtml(content);
  }
}

export interface DeployResult {
  apikey: string;
  url: string;
  agentName: string;
  runtimeId?: string;
  consoleUrl?: string;
  region?: string;
  version?: number | null;
  feishuChannel?: {
    enabled: boolean;
    transport: string;
    runtimeId?: string;
  };
}

/** The ordered deploy phases shown in the stepper (keys match DeployStage.phase). */
const DEPLOY_STEPS: { phase: string; label: string }[] = [
  { phase: "build", label: "构建镜像" },
  { phase: "deploy", label: "部署" },
  { phase: "publish", label: "发布" },
];

const CODE_PACKAGE_DEPLOY_STEPS: { phase: string; label: string }[] = [
  { phase: "upload", label: "上传代码包" },
  { phase: "build", label: "镜像打包" },
  { phase: "deploy", label: "创建 Runtime" },
  { phase: "publish", label: "发布服务" },
];

const INSTANCE_UPDATE_STEP = {
  phase: "update",
  label: "更新实例配置",
} as const;

function usesInMemorySession(agentDraft?: AgentDraft): boolean {
  if (!agentDraft) return false;
  return (
    !agentDraft.memory.shortTerm ||
    (agentDraft.shortTermBackend || "local") === "local"
  );
}

type RuntimeInstanceRangeValidation =
  | { valid: true; min: number; max: number }
  | { valid: false; error: string };

function validateRuntimeInstanceRange(
  minValue: string,
  maxValue: string,
): RuntimeInstanceRangeValidation {
  const min = Number(minValue);
  const max = Number(maxValue);
  if (
    !minValue.trim() ||
    !maxValue.trim() ||
    !Number.isSafeInteger(min) ||
    !Number.isSafeInteger(max) ||
    min < 1 ||
    max < 1
  ) {
    return { valid: false, error: "实例数必须为大于 0 的整数。" };
  }
  if (min > max) {
    return { valid: false, error: "最小实例数不能大于最大实例数。" };
  }
  return { valid: true, min, max };
}

export interface DeployOptions {
  taskId?: string;
  sessionStorage?: "in-memory" | "persistent";
  minInstance?: number;
  maxInstance?: number;
  authentication?: DeployAuthentication;
  im?: {
    feishu?: {
      enabled: boolean;
    };
  };
  envs?: DeployEnvVar[];
}

export interface DeployEnvVar {
  key: string;
  value: string;
}

export interface DeploymentTaskUpdate {
  id: string;
  runtimeName: string;
  runtimeId?: string;
  region: string;
  startedAt: number;
  status: "running" | "success" | "error" | "cancelled";
  phase?: string;
  label: string;
  message?: string;
  pct?: number;
  buildLog?: DeployBuildLogSnapshot;
  /** Instance range applied through UpdateRuntime after creation. */
  instanceRange?: { min: number; max: number };
  /** Draft used to render the Agent detail while its Runtime is still publishing. */
  agentDraft?: AgentDraft;
  /** Re-runs the same project/config as a new deployment task. */
  retry?: () => Promise<void>;
}

export interface ProjectPreviewProps {
  project: AgentProject;
  /** Render inside the Agent workspace without taking over the app toolbar. */
  embedded?: boolean;
  /** Keep the deployment layout visible while the final action is unavailable. */
  deployDisabledReason?: string;
  /** Draft metadata summarized on the deployment page. */
  agentDraft?: AgentDraft;
  /** Main Agent display name. Generated project names may be normalized. */
  agentName?: string;
  /** Root Agent plus all recursively nested sub-Agents. */
  agentCount?: number;
  /** Debug configuration selected as the release candidate. */
  releaseConfiguration?: {
    modelName: string;
    description: string;
    instruction: string;
    optimizations: string[];
  };
  /** When provided, files are editable and changes call onChange with the new project. Omit for read-only. */
  onChange?: (project: AgentProject) => void;
  /** One-click deploy handler. Should return deploy result (URL + API Key). Omit to hide the deploy button.
   *  `onStage` receives each live build/deploy/publish progress frame. */
  onDeploy?: (
    project: AgentProject,
    onStage?: (s: DeployStage) => void,
    options?: DeployOptions,
  ) => Promise<DeployResult>;
  /** Called after successfully adding the agent to the connection list. */
  onAgentAdded?: (agentId: string, agentName: string) => void;
  /** Called as soon as the Runtime has been deployed or updated successfully. */
  onDeploymentComplete?: (result: DeployResult) => void | Promise<void>;
  /** Label for the floating deployment action. */
  deploymentActionLabel?: string;
  /** Optional external footer slot for the deployment action. */
  deploymentActionTargetId?: string;
  /** Existing Runtime id when this deployment updates an Agent in place. */
  deploymentRuntimeId?: string;
  /** Opens the persistent Agent detail as soon as deployment starts. */
  onDeploymentStarted?: (task: DeploymentTaskUpdate) => void;
  /** Mirrors deployment progress into the app shell so it survives page switches. */
  onDeploymentTaskChange?: (task: DeploymentTaskUpdate) => void;
  /** Whether Feishu Channel was enabled in the configuration step. */
  feishuEnabled?: boolean;
  /** Update the Feishu channel selection from the deploy page. */
  onFeishuEnabledChange?: (enabled: boolean) => void | Promise<void>;
  /** Environment variables required by the selected memory/knowledge backends. */
  deploymentEnv?: EnvVar[];
  /** Deployment-only values entered in each feature's configuration area. */
  deploymentEnvValues?: Record<string, string>;
  onDeploymentEnvChange?: (key: string, value: string) => void;
  /** Runtime network settings edited on the deploy page. */
  network?: NetworkConfig;
  onNetworkChange?: (network: NetworkConfig | undefined) => void;
  /** Selected deploy region (cn-beijing / cn-shanghai). */
  deployRegion?: string;
  /** Called when the user changes the deploy region. */
  onDeployRegionChange?: (region: string) => void;
  /** Deploy-page toolbar actions. */
  onBack?: () => void;
  backLabel?: string;
  onExportYaml?: () => void;
  /** Replaces the Agent preview pane for deployment flows with their own source area. */
  deploymentPrimaryPane?: ReactNode;
  /** Keeps deployment configuration visible while its primary input is incomplete. */
  deployDisabled?: boolean;
}

// --- tree model -------------------------------------------------------------

interface TreeNode {
  name: string;
  /** Full path for file nodes; undefined for folder nodes. */
  path?: string;
  children: Map<string, TreeNode>;
}

function buildTree(files: ProjectFile[]): TreeNode {
  const root: TreeNode = { name: "", children: new Map() };
  for (const f of files) {
    const parts = f.path.split("/").filter(Boolean);
    let node = root;
    parts.forEach((part, i) => {
      let child = node.children.get(part);
      if (!child) {
        child = { name: part, children: new Map() };
        node.children.set(part, child);
      }
      if (i === parts.length - 1) child.path = f.path;
      node = child;
    });
  }
  return root;
}

function sortedChildren(node: TreeNode): TreeNode[] {
  return [...node.children.values()].sort((a, b) => {
    const aFolder = a.children.size > 0 && a.path === undefined;
    const bFolder = b.children.size > 0 && b.path === undefined;
    if (aFolder !== bFolder) return aFolder ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

// --- component --------------------------------------------------------------

interface EnvRow {
  id: string;
  key: string;
  value: string;
}

function newEnvRow(key = "", value = ""): EnvRow {
  return {
    id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    key,
    value,
  };
}

function ProjectHeaderPortal({
  left,
  right,
}: {
  left: ReactNode;
  right: ReactNode;
}) {
  const [targets, setTargets] = useState<{
    left: HTMLElement;
    right: HTMLElement;
  } | null>(null);

  useLayoutEffect(() => {
    const leftTarget = document.getElementById("veadk-page-header-left");
    const rightTarget = document.getElementById("veadk-page-header-actions");
    if (leftTarget && rightTarget) {
      setTargets({ left: leftTarget, right: rightTarget });
    }
  }, []);

  if (!targets) {
    return (
      <header className="pp-toolbar">
        {left}
        {right}
      </header>
    );
  }

  return (
    <>
      {createPortal(left, targets.left)}
      {createPortal(right, targets.right)}
    </>
  );
}

export function ProjectPreview({
  project,
  embedded = false,
  deployDisabledReason,
  agentDraft,
  agentName,
  agentCount,
  releaseConfiguration,
  onChange,
  onDeploy,
  onAgentAdded,
  onDeploymentComplete,
  deploymentActionLabel = "部署",
  deploymentActionTargetId,
  deploymentRuntimeId,
  onDeploymentStarted,
  onDeploymentTaskChange,
  feishuEnabled = false,
  onFeishuEnabledChange,
  deploymentEnv = [],
  deploymentEnvValues = {},
  onDeploymentEnvChange,
  network,
  onNetworkChange,
  deployRegion = "cn-beijing",
  onDeployRegionChange,
  onBack,
  backLabel = "返回配置",
  onExportYaml,
  deploymentPrimaryPane,
  deployDisabled = false,
}: ProjectPreviewProps) {
  const editable = typeof onChange === "function";
  const isRuntimeUpdate = deploymentActionLabel.includes("更新");
  const inMemorySession = usesInMemorySession(agentDraft);

  // Initialize all hooks BEFORE any conditional returns (React hooks rule)
  const [selected, setSelected] = useState<string | null>(
    project?.files?.[0]?.path ?? null,
  );
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const [newPath, setNewPath] = useState("");
  const [deploying, setDeploying] = useState(false);
  const [deployConfirmOpen, setDeployConfirmOpen] = useState(false);
  const [flowPreviewOpen, setFlowPreviewOpen] = useState(false);
  const [feishuUpdating, setFeishuUpdating] = useState(false);
  const [deployError, setDeployError] = useState<string | null>(null);
  const [deployResult, setDeployResult] = useState<DeployResult | null>(null);
  // Latest progress frame per deploy phase + the phase currently in flight,
  // driving the build/deploy/publish stepper.
  const [stageMap, setStageMap] = useState<Record<string, DeployStage>>({});
  const [activePhase, setActivePhase] = useState<string | null>(null);
  const [addingAgent, setAddingAgent] = useState(false);
  const [envRows, setEnvRows] = useState<EnvRow[]>([]);
  const [showEnvValues, setShowEnvValues] = useState(false);
  const [regionMenuOpen, setRegionMenuOpen] = useState(false);
  const [authenticationType, setAuthenticationType] =
    useState<DeployAuthentication["type"]>("api_key");
  const [userPoolUid, setUserPoolUid] = useState("");
  const [minInstance, setMinInstance] = useState("1");
  const [maxInstance, setMaxInstance] = useState(
    inMemorySession ? "1" : "5",
  );
  const [deploymentActionTarget, setDeploymentActionTarget] =
    useState<HTMLElement | null>(null);
  const mountedRef = useRef(true);
  const instanceRange = validateRuntimeInstanceRange(minInstance, maxInstance);
  const needsInstanceUpdate =
    !isRuntimeUpdate &&
    instanceRange.valid &&
    (instanceRange.min !== 1 || instanceRange.max !== 5);
  const baseDeploymentSteps = deploymentPrimaryPane
    ? CODE_PACKAGE_DEPLOY_STEPS
    : DEPLOY_STEPS;
  const deploymentSteps = needsInstanceUpdate
    ? [...baseDeploymentSteps, INSTANCE_UPDATE_STEP]
    : baseDeploymentSteps;

  useEffect(() => {
    if (!deploymentActionTargetId) {
      setDeploymentActionTarget(null);
      return;
    }
    setDeploymentActionTarget(document.getElementById(deploymentActionTargetId));
  }, [deploymentActionTargetId]);

  const deploymentRegionPicker = (showLabel: boolean) => (
    <div
      className="pp-network-region"
      onKeyDown={(event) => {
        if (event.key === "Escape") setRegionMenuOpen(false);
      }}
    >
      {showLabel && <span>发布区域</span>}
      <button
        type="button"
        className="pp-region-trigger"
        aria-label="部署区域"
        aria-haspopup="listbox"
        aria-expanded={regionMenuOpen}
        disabled={deploying || isRuntimeUpdate || !onDeployRegionChange}
        onClick={() => setRegionMenuOpen((open) => !open)}
      >
        <span>
          {deployRegion === "cn-shanghai" ? "华东 2（上海）" : "华北 2（北京）"}
        </span>
        <ChevronDown
          className={`pp-region-chevron${regionMenuOpen ? " is-open" : ""}`}
        />
      </button>
      {regionMenuOpen && (
        <>
          <div className="menu-scrim" onClick={() => setRegionMenuOpen(false)} />
          <div className="pp-region-menu" role="listbox" aria-label="部署区域">
            {[
              { value: "cn-beijing", label: "华北 2（北京）" },
              { value: "cn-shanghai", label: "华东 2（上海）" },
            ].map((region) => {
              const selected = region.value === deployRegion;
              return (
                <button
                  key={region.value}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  className={`pp-region-option${selected ? " is-selected" : ""}`}
                  onClick={() => {
                    onDeployRegionChange?.(region.value);
                    setRegionMenuOpen(false);
                  }}
                >
                  <span>{region.label}</span>
                  {selected && <Check aria-hidden="true" />}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    setMinInstance("1");
    setMaxInstance(inMemorySession ? "1" : "5");
  }, [inMemorySession]);

  useEffect(() => {
    if (!flowPreviewOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setFlowPreviewOpen(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [flowPreviewOpen]);

  const tree = useMemo(() => {
    if (!project?.files || !Array.isArray(project.files)) {
      return { name: "", children: new Map() };
    }
    return buildTree(project.files);
  }, [project?.files]);

  // Validate project structure AFTER all hooks
  if (!project || !Array.isArray(project.files)) {
    return <div className="pp-error">项目数据无效</div>;
  }

  const selectedFile =
    project.files.find((f) => f.path === selected) ?? null;
  const networkMode = network?.mode ?? "public";
  const automaticEnvRows = runtimeEnvDisplayRows(
    feishuEnabled ? [...deploymentEnv, ...FEISHU_ENV] : deploymentEnv,
    deploymentEnvValues,
  );
  const environmentVariableCount = automaticEnvRows.length + envRows.length;

  function toggleFolder(key: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function commitFiles(files: ProjectFile[], nextSelected?: string | null) {
    if (!onChange) return;
    onChange({ ...project, files });
    if (nextSelected !== undefined) setSelected(nextSelected);
  }

  function handleEdit(content: string) {
    if (!selectedFile) return;
    commitFiles(
      project.files.map((f) =>
        f.path === selectedFile.path ? { ...f, content } : f,
      ),
    );
  }

  function handleAddSubmit() {
    const path = newPath.trim();
    setAdding(false);
    setNewPath("");
    if (!path) return;
    if (project.files.some((f) => f.path === path)) {
      setSelected(path);
      return;
    }
    commitFiles([...project.files, { path, content: "" }], path);
  }

  function handleRename() {
    if (!selectedFile) return;
    const next = window.prompt("重命名文件", selectedFile.path);
    const path = next?.trim();
    if (!path || path === selectedFile.path) return;
    if (project.files.some((f) => f.path === path)) return;
    commitFiles(
      project.files.map((f) =>
        f.path === selectedFile.path ? { ...f, path } : f,
      ),
      path,
    );
  }

  function handleDelete() {
    if (!selectedFile) return;
    const remaining = project.files.filter((f) => f.path !== selectedFile.path);
    commitFiles(remaining, remaining[0]?.path ?? null);
  }

  function updateEnvRow(id: string, patch: Partial<EnvRow>) {
    setEnvRows((rows) =>
      rows.map((row) => (row.id === id ? { ...row, ...patch } : row)),
    );
  }

  function removeEnvRow(id: string) {
    setEnvRows((rows) => rows.filter((row) => row.id !== id));
  }

  function addEnvRow() {
    setEnvRows((rows) => [...rows, newEnvRow()]);
  }

  function setNetworkMode(mode: NetworkConfig["mode"]) {
    if (!onNetworkChange) return;
    onNetworkChange(
      mode === "public" ? undefined : { ...(network ?? { mode }), mode },
    );
  }

  function patchNetwork(patch: Partial<NetworkConfig>) {
    onNetworkChange?.({ ...(network ?? { mode: "private" }), ...patch });
  }

  function deployEnvVars(): DeployEnvVar[] {
    const byKey = new Map(
      envRows
        .map((row) => ({ key: row.key.trim(), value: row.value }))
        .filter((row) => row.key.length > 0)
        .map((row) => [row.key, row.value]),
    );
    const featureEnv = feishuEnabled
      ? [...deploymentEnv, ...FEISHU_ENV]
      : deploymentEnv;
    for (const env of runtimeEnvVars(featureEnv, deploymentEnvValues)) {
      byKey.set(env.key, env.value);
    }
    return [...byKey].map(([key, value]) => ({ key, value }));
  }

  async function handleFeishuToggle() {
    if (!onFeishuEnabledChange || deploying || feishuUpdating) return;
    setDeployError(null);
    setFeishuUpdating(true);
    try {
      await onFeishuEnabledChange(!feishuEnabled);
    } catch (error) {
      if (mountedRef.current) {
        setDeployError(
          `更新飞书配置失败：${error instanceof Error ? error.message : String(error)}`,
        );
      }
    } finally {
      if (mountedRef.current) setFeishuUpdating(false);
    }
  }

  async function requestDeploymentConfirmation() {
    if (!onDeploy || deploying || deployDisabled) return;
    if (!instanceRange.valid) {
      setDeployError(instanceRange.error);
      return;
    }
    if (
      !isRuntimeUpdate &&
      authenticationType === "user_pool" &&
      !userPoolUid
    ) {
      setDeployError("请选择用于 Runtime 鉴权的用户池。");
      return;
    }
    if (networkMode !== "public" && !network?.vpcId?.trim()) {
      setDeployError("使用 VPC 网络时，请填写 VPC ID。");
      return;
    }
    const missingFeatureEnv = firstMissingRuntimeEnv(
      deploymentEnv,
      deploymentEnvValues,
    );
    if (missingFeatureEnv) {
      const env = deploymentEnv.find((item) => item.key === missingFeatureEnv.key);
      setDeployError(`请返回配置页填写 ${env?.comment || env?.key}（${env?.key}）。`);
      return;
    }
    if (feishuEnabled) {
      const missingFeishuEnv = firstMissingRuntimeEnv(
        FEISHU_ENV,
        deploymentEnvValues,
      );
      if (missingFeishuEnv) {
        const env = FEISHU_ENV.find((item) => item.key === missingFeishuEnv.key);
        setDeployError(`启用飞书后，请填写${env?.comment || env?.key}。`);
        return;
      }
    }
    setDeployConfirmOpen(true);
  }

  async function performDeployment() {
    if (!onDeploy || deploying) return;
    if (!instanceRange.valid) {
      setDeployConfirmOpen(false);
      setDeployError(instanceRange.error);
      return;
    }
    setDeployConfirmOpen(false);
    const envs = deployEnvVars();
    if (mountedRef.current) {
      setDeployError(null);
      setDeployResult(null);
      setStageMap({});
      setActivePhase(null);
      setDeploying(true);
    }
    const taskId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    let taskRuntimeName = agentName?.trim() || project.name || "生成中…";
    const taskStartedAt = Date.now();
    const initialTask: DeploymentTaskUpdate = {
      id: taskId,
      runtimeName: taskRuntimeName,
      runtimeId: deploymentRuntimeId,
      region: deployRegion,
      startedAt: taskStartedAt,
      status: "running",
      phase: "prepare",
      label: "准备部署",
      agentDraft,
      instanceRange: needsInstanceUpdate
        ? { min: instanceRange.min, max: instanceRange.max }
        : undefined,
    };
    onDeploymentTaskChange?.(initialTask);
    onDeploymentStarted?.(initialTask);
    let latestBuildLog: DeployBuildLogSnapshot | undefined;
    let latestPhase = initialTask.phase ?? "prepare";
    const terminalBuildLog = (
      status: DeployBuildLogSnapshot["status"],
    ): DeployBuildLogSnapshot | undefined => (
      latestBuildLog
        ? { ...latestBuildLog, status, updatedAt: Date.now() }
        : undefined
    );
    const terminalBuildLogUpdate = (
      status: DeployBuildLogSnapshot["status"],
    ): { buildLog?: DeployBuildLogSnapshot } => {
      const buildLog = terminalBuildLog(status);
      return buildLog ? { buildLog } : {};
    };
    const pendingBuildLog = (): DeployBuildLogSnapshot => ({
      source: "code-pipeline",
      status: "running",
      text: "",
      lineCount: 0,
      truncated: false,
      updatedAt: Date.now(),
      pendingMessage: "正在等待构建日志…",
    });
    const mergeBuildFailureLog = (message: string): DeployBuildLogSnapshot | undefined => {
      if (latestPhase !== "build") return undefined;
      const failureText = [
        "",
        "----- 构建失败 -----",
        message,
      ].join("\n");
      latestBuildLog = mergeDeployBuildLog(latestBuildLog, {
        source: "code-pipeline",
        status: "error",
        text: failureText,
        lineCount: failureText.split("\n").length,
        truncated: false,
        updatedAt: Date.now(),
      });
      return latestBuildLog;
    };
    try {
      const result = await onDeploy(
        project,
        (s) => {
          if (s.runtimeName) taskRuntimeName = s.runtimeName;
          latestPhase = s.phase;
          if (s.buildLog) {
            latestBuildLog = mergeDeployBuildLog(latestBuildLog, s.buildLog);
          } else if (s.phase === "build" && !latestBuildLog) {
            latestBuildLog = pendingBuildLog();
          }
          if (mountedRef.current) {
            setStageMap((prev) => ({ ...prev, [s.phase]: s }));
            setActivePhase(s.phase);
          }
          onDeploymentTaskChange?.({
            id: taskId,
            runtimeName: taskRuntimeName,
            runtimeId: deploymentRuntimeId,
            region: deployRegion,
            startedAt: taskStartedAt,
            status: "running",
            phase: s.phase,
            label:
              deploymentSteps.find((step) => step.phase === s.phase)?.label ??
              s.phase,
            message: s.message,
            pct: s.pct,
            ...(latestBuildLog ? { buildLog: latestBuildLog } : {}),
          });
        },
        {
          taskId,
          sessionStorage: inMemorySession ? "in-memory" : "persistent",
          minInstance: instanceRange.min,
          maxInstance: instanceRange.max,
          ...(!isRuntimeUpdate
            ? {
                authentication:
                  authenticationType === "user_pool"
                    ? {
                        type: "user_pool" as const,
                        userPoolUid,
                      }
                    : { type: "api_key" as const },
              }
            : {}),
          ...(feishuEnabled
            ? {
                im: {
                  feishu: {
                    enabled: true,
                  },
                },
              }
            : {}),
          envs,
        },
      );
      if (mountedRef.current) {
        setDeployResult(result);
        setActivePhase(null);
      }
      onDeploymentTaskChange?.({
        id: taskId,
        runtimeName: result.agentName || taskRuntimeName,
        runtimeId: result.runtimeId || deploymentRuntimeId,
        region: result.region || deployRegion,
        startedAt: taskStartedAt,
        status: "success",
        phase: "complete",
        label: "部署完成",
        ...terminalBuildLogUpdate("complete"),
      });
      try {
        await onDeploymentComplete?.(result);
      } catch (error) {
        if (!(error instanceof RuntimeProbeError)) throw error;
        onDeploymentTaskChange?.({
          id: taskId,
          runtimeName: result.agentName || taskRuntimeName,
          runtimeId: result.runtimeId || deploymentRuntimeId,
          region: result.region || deployRegion,
          startedAt: taskStartedAt,
          status: "success",
          phase: "complete",
          label: "部署完成，暂未连接",
          message: error.message,
          ...terminalBuildLogUpdate("complete"),
        });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (err instanceof DOMException && err.name === "AbortError") {
        if (mountedRef.current) {
          setDeployError(null);
          setActivePhase(null);
        }
        onDeploymentTaskChange?.({
          id: taskId,
          runtimeName: taskRuntimeName,
          runtimeId: deploymentRuntimeId,
          region: deployRegion,
          startedAt: taskStartedAt,
          status: "cancelled",
          label: "已取消",
          message: "部署已取消，相关 Runtime 资源已请求销毁。",
          ...terminalBuildLogUpdate("complete"),
        });
        return;
      }
      if (mountedRef.current) setDeployError(message);
      const buildLog = mergeBuildFailureLog(message);
      const failedInBuild = Boolean(buildLog);
      onDeploymentTaskChange?.({
        id: taskId,
        runtimeName: taskRuntimeName,
        runtimeId: deploymentRuntimeId,
        region: deployRegion,
        startedAt: taskStartedAt,
        status: "error",
        phase: latestPhase,
        label: "部署失败",
        message: failedInBuild ? "构建镜像失败，详见构建日志。" : message,
        ...(buildLog ? { buildLog } : terminalBuildLogUpdate("complete")),
        retry: requestDeploymentConfirmation,
      });
    } finally {
      if (mountedRef.current) setDeploying(false);
    }
  }

  function cancelDeploymentConfirmation() {
    setDeployConfirmOpen(false);
  }

  async function handleAddAgent() {
    if (!deployResult || addingAgent) return;
    setAddingAgent(true);
    setDeployError(null);
    try {
      const {
        addConnection,
        addRuntimeConnection,
        remoteAppId,
        loadConnections,
      } = await import("../adk/connections");
      const { probeRuntimeApps } = await import("../adk/client");

      let conn;
      if (deployResult.runtimeId) {
        // Preferred: server-side proxy — data-plane apikey never reaches
        // the browser; /web/runtime-proxy injects it.
        const region = deployResult.region ?? deployRegion;
        const apps =
          (await probeRuntimeApps(deployResult.runtimeId, region, {
            retryProbe: true,
          })) ?? [];
        conn = addRuntimeConnection(
          deployResult.runtimeId,
          deployResult.agentName,
          region,
          apps,
          apps.length > 0
            ? { [apps[0]]: deployResult.agentName }
            : undefined,
          deployResult.version,
        );
      } else {
        // Legacy: direct URL + apikey (older backends / manual deploys).
        conn = await addConnection(
          deployResult.agentName,
          deployResult.url,
          deployResult.apikey,
          "",
        );
      }

      if (conn.apps.length === 0) {
        setDeployError("连接成功，但该地址未发现任何 Agent（/list-apps 为空）。");
      } else {
        const label = { [conn.apps[0]]: deployResult.agentName };
        const updatedConn = {
          ...conn,
          appLabels: { ...(conn.appLabels ?? {}), ...label },
        };

        const allConns = loadConnections();
        const updatedList = allConns.map((c) =>
          c.id === conn.id ? updatedConn : c,
        );
        localStorage.setItem(
          "veadk_agentkit_connections",
          JSON.stringify(updatedList),
        );

        const { registerConnections } = await import("../adk/connections");
        registerConnections(updatedList);

        if (onAgentAdded) {
          const agentId = remoteAppId(conn.id, conn.apps[0]);
          onAgentAdded(agentId, deployResult.agentName);
        } else {
          alert(`🎉 Agent "${deployResult.agentName}" 已添加到左上角下拉列表！`);
        }
      }
    } catch (err) {
      setDeployError(
        `添加 Agent 失败：${err instanceof Error ? err.message : String(err)}`,
      );
    } finally {
      setAddingAgent(false);
    }
  }

  function handleDownloadZip() {
    const blob = buildZip(project.files);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${project.name || "project"}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  const artifactActions = (
    <div
      className={`pp-artifact-actions${embedded ? " is-rail" : ""}`}
      aria-label="发布产物操作"
    >
      {onExportYaml && (
        <button type="button" className="pp-secondary" onClick={onExportYaml}>
          <FileDown className="pp-ic" />
          导出 YAML
        </button>
      )}
      {editable && onChange && (
        <ProjectCodeBrowser
          project={project}
          onChange={onChange}
          className="pp-artifact-source"
          label="查看源代码"
        />
      )}
      {project.files.length > 0 && (
        <button
          type="button"
          className="pp-secondary"
          onClick={handleDownloadZip}
        >
          <Download className="pp-ic" />
          下载源代码
        </button>
      )}
    </div>
  );

  function renderNode(node: TreeNode, depth: number, prefix: string) {
    return sortedChildren(node).map((child) => {
      const key = prefix ? `${prefix}/${child.name}` : child.name;
      const isFile = child.path !== undefined;
      const pad = { paddingLeft: 8 + depth * 14 };

      if (isFile) {
        const active = child.path === selected;
        return (
          <button
            key={key}
            type="button"
            className={`pp-row pp-file${active ? " pp-active" : ""}`}
            style={pad}
            onClick={() => setSelected(child.path!)}
            title={child.path}
          >
            <File className="pp-ic" />
            <span className="pp-label">{child.name}</span>
          </button>
        );
      }

      const isCollapsed = collapsed.has(key);
      return (
        <div key={key}>
          <button
            type="button"
            className="pp-row pp-folder"
            style={pad}
            onClick={() => toggleFolder(key)}
          >
            <ChevronRight className={`pp-ic pp-chevron${isCollapsed ? "" : " pp-open"}`} />
            <Folder className="pp-ic" />
            <span className="pp-label">{child.name}</span>
          </button>
          {!isCollapsed && renderNode(child, depth + 1, key)}
        </div>
      );
    });
  }

  return (
    <div className={`pp-root${onDeploy ? " is-deploy" : ""}${embedded ? " is-embedded" : ""}${deploymentPrimaryPane ? " has-primary-pane" : ""}`}>
      {onDeploy && !embedded && (
        <ProjectHeaderPortal
          left={
            <div className="pp-toolbar-left">
              {onBack && (
                <button type="button" className="pp-toolbar-back" onClick={onBack}>
                  <ArrowLeft className="pp-ic" />
                  {backLabel}
                </button>
              )}
              <span className="pp-toolbar-title">
                部署 {agentName || project.name || "未命名 Agent"}
                {agentCount && agentCount > 1 ? ` 等 ${agentCount} 个智能体` : ""}
              </span>
            </div>
          }
          right={null}
        />
      )}

      <div className="pp-body">
        {onDeploy && !deploymentPrimaryPane && (
          <section className="pp-release-overview" aria-label="发布概览">
            <div className={`pp-release-preview${embedded ? " is-embedded" : ""}`}>
              <div className="pp-flow-thumbnail">
                {agentDraft && (
                  <AgentBuildCanvas
                    draft={agentDraft}
                    direction="horizontal"
                    selectedPath={[]}
                    onSelect={ignoreCanvasAction}
                    onAdd={ignoreCanvasAction}
                    onInsert={ignoreCanvasAction}
                    onDelete={ignoreCanvasAction}
                    readOnly
                    interactivePreview
                  />
                )}
                <button
                  type="button"
                  className="pp-flow-expand"
                  onClick={() => setFlowPreviewOpen(true)}
                  aria-label="放大查看执行流程"
                  title="放大查看"
                >
                  <Maximize2 aria-hidden />
                </button>
              </div>
              {embedded && artifactActions}
              {!embedded && (
                <div className="pp-release-info">
                <div className="pp-release-card-head">Agent 概览</div>
                <div className="pp-release-info-body">
                  <div className="pp-release-info-main">
                    <h2>{agentName || project.name || "未命名 Agent"}</h2>
                    {agentDraft?.description && (
                      <p
                        className="pp-release-description"
                        title={agentDraft.description}
                      >
                        {agentDraft.description}
                      </p>
                    )}
                    <dl className="pp-release-facts">
                    <div>
                      <dt>Agent 数量</dt>
                      <dd>{agentCount ?? 1}</dd>
                    </div>
                    {releaseConfiguration && (
                      <>
                        <div>
                          <dt>模型</dt>
                          <dd>{releaseConfiguration.modelName}</dd>
                        </div>
                        <div>
                          <dt>描述</dt>
                          <dd className="pp-release-fact-long">
                            {releaseConfiguration.description}
                          </dd>
                        </div>
                        <div>
                          <dt>系统提示词</dt>
                          <dd className="pp-release-fact-long pp-release-prompt">
                            {releaseConfiguration.instruction}
                          </dd>
                        </div>
                        <div>
                          <dt>优化选项</dt>
                          <dd>
                            {releaseConfiguration.optimizations.length > 0
                              ? releaseConfiguration.optimizations.join("、")
                              : "未启用"}
                          </dd>
                        </div>
                      </>
                    )}
                    </dl>
                  </div>
                  {artifactActions}
                </div>
                </div>
              )}
            </div>
          </section>
        )}
        <div className="pp-files-area">
          <div className="pp-sidebar">
            <div className="pp-sidebar-head">
              <span className="pp-project-name" title={project.name}>
                文件预览
              </span>
              {editable && (
                <button
                  type="button"
                  className="pp-icon-btn"
                  title="新建文件"
                  onClick={() => {
                    setAdding(true);
                    setNewPath("");
                  }}
                >
                  <FilePlus className="pp-ic" />
                </button>
              )}
            </div>
            <div className="pp-tree">
              {adding && (
                <input
                  className="pp-new-input"
                  autoFocus
                  placeholder="path/to/file.py"
                  value={newPath}
                  onChange={(e) => setNewPath(e.target.value)}
                  onBlur={handleAddSubmit}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleAddSubmit();
                    if (e.key === "Escape") {
                      setAdding(false);
                      setNewPath("");
                    }
                  }}
                />
              )}
              {project.files.length === 0 && !adding ? (
                <div className="pp-empty">暂无文件</div>
              ) : (
                renderNode(tree, 0, "")
              )}
            </div>
          </div>

          <div className="pp-main">
            <div className="pp-main-head">
              <span className="pp-path" title={selectedFile?.path}>
                {selectedFile?.path ?? "未选择文件"}
              </span>
              <div className="pp-actions">
                {editable && selectedFile && (
                  <>
                    <button
                      type="button"
                      className="pp-icon-btn"
                      title="重命名"
                      onClick={handleRename}
                    >
                      <Pencil className="pp-ic" />
                    </button>
                    <button
                      type="button"
                      className="pp-icon-btn pp-danger"
                      title="删除"
                      onClick={handleDelete}
                    >
                      <Trash2 className="pp-ic" />
                    </button>
                  </>
                )}
              </div>
            </div>
            <div className="pp-content">
              {selectedFile == null ? (
                <div className="pp-placeholder">选择左侧文件以查看内容</div>
              ) : editable ? (
                <div className="pp-codemirror">
                  <Suspense fallback={<div className="pp-editor-loading">加载编辑器…</div>}>
                    <CodeEditor
                      value={selectedFile.content}
                      path={selectedFile.path}
                      onChange={handleEdit}
                    />
                  </Suspense>
                </div>
              ) : (
                <pre
                  className="pp-pre hljs"
                  dangerouslySetInnerHTML={{
                    __html: highlight(selectedFile.content, selectedFile.path),
                  }}
                />
              )}
            </div>
          </div>
        </div>

        {onDeploy && (
          <aside className="pp-config" aria-label="部署配置">
            <div className="pp-config-head">
              <div className="pp-config-title">部署配置</div>
            </div>
            <div className="pp-config-scroll">
              {deploymentPrimaryPane}

              {!deploymentPrimaryPane && (
                <section className="pp-config-section">
                  <div className="pp-config-label">发布区域</div>
                  {deploymentRegionPicker(false)}
                </section>
              )}

              {!deploymentPrimaryPane && (
                <section className="pp-config-section pp-auth-section">
                  <div className="pp-config-label">访问鉴权</div>
                  {isRuntimeUpdate ? (
                    <p className="pp-config-note pp-auth-preserved-note">
                      更新时保持现有 Runtime 的鉴权方式不变。
                    </p>
                  ) : (
                    <div className="pp-auth-fields">
                      <label>
                        <span>鉴权方式</span>
                        <DeploymentSelect
                          ariaLabel="部署鉴权方式"
                          value={authenticationType}
                          placeholder="请选择鉴权方式"
                          options={DEPLOYMENT_AUTHENTICATION_OPTIONS}
                          disabled={deploying}
                          onChange={(value) => {
                            setDeployError(null);
                            setAuthenticationType(
                              value as DeployAuthentication["type"],
                            );
                          }}
                        />
                      </label>
                      {authenticationType === "user_pool" && (
                        <label>
                          <span>用户池</span>
                          <IdentityUserPoolSelect
                            value={userPoolUid}
                            disabled={deploying}
                            onChange={(uid) => {
                              setDeployError(null);
                              setUserPoolUid(uid);
                            }}
                          />
                        </label>
                      )}
                    </div>
                  )}
                </section>
              )}

              {!deploymentPrimaryPane && (
                <section className="pp-config-section">
                <div className="pp-config-label">消息渠道</div>
                <div
                  className={`pp-channel-card${feishuEnabled ? " is-flipped" : ""}`}
                >
                  <div className="pp-channel-card-inner">
                    <button
                      type="button"
                      className="pp-channel-card-face pp-channel-card-front"
                      aria-pressed={feishuEnabled}
                      aria-hidden={feishuEnabled}
                      tabIndex={feishuEnabled ? -1 : 0}
                      onClick={() => void handleFeishuToggle()}
                      disabled={
                        feishuEnabled ||
                        deploying ||
                        feishuUpdating ||
                        !onFeishuEnabledChange
                      }
                    >
                      <span className="pp-channel-logo">
                        <img src={feishuLogo} alt="" />
                      </span>
                      <span className="pp-channel-card-copy">
                        <strong>飞书</strong>
                        <small>
                          {feishuUpdating
                            ? "正在启用并更新配置…"
                            : "接收消息并通过飞书机器人回复"}
                        </small>
                      </span>
                    </button>
                    <div
                      className="pp-channel-card-face pp-channel-card-back"
                      aria-hidden={!feishuEnabled}
                    >
                      <div className="pp-channel-card-head">
                        <strong>飞书配置</strong>
                        <button
                          type="button"
                          className="pp-channel-remove"
                          tabIndex={feishuEnabled ? 0 : -1}
                          onClick={() => void handleFeishuToggle()}
                          disabled={
                            !feishuEnabled ||
                            deploying ||
                            feishuUpdating ||
                            !onFeishuEnabledChange
                          }
                        >
                          {feishuUpdating ? "取消中…" : "取消"}
                        </button>
                      </div>
                      <div className="pp-channel-fields">
                        {FEISHU_ENV.map((env) => (
                          <label key={env.key}>
                            <span>
                              {env.comment || env.key}
                              {env.required && <small>必填</small>}
                            </span>
                            <input
                              type={
                                env.key.includes("SECRET") ? "password" : "text"
                              }
                              value={deploymentEnvValues[env.key] ?? ""}
                              placeholder={env.placeholder}
                              tabIndex={feishuEnabled ? 0 : -1}
                              disabled={
                                !feishuEnabled ||
                                deploying ||
                                !onDeploymentEnvChange
                              }
                              autoComplete="off"
                              onChange={(event) =>
                                onDeploymentEnvChange?.(
                                  env.key,
                                  event.currentTarget.value,
                                )
                              }
                            />
                          </label>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              </section>
              )}

              {!isRuntimeUpdate && (
                <section className="pp-config-section">
                  <div className="pp-config-label">实例设置</div>
                  <div className="pp-instance-fields">
                    <label htmlFor="runtime-min-instance">
                      <span>最小实例数</span>
                      <input
                        id="runtime-min-instance"
                        type="number"
                        min="1"
                        step="1"
                        inputMode="numeric"
                        value={minInstance}
                        disabled={deploying}
                        aria-invalid={!instanceRange.valid}
                        onChange={(event) => setMinInstance(event.currentTarget.value)}
                      />
                    </label>
                    <label htmlFor="runtime-max-instance">
                      <span>最大实例数</span>
                      <input
                        id="runtime-max-instance"
                        type="number"
                        min="1"
                        step="1"
                        inputMode="numeric"
                        value={maxInstance}
                        disabled={deploying}
                        aria-invalid={!instanceRange.valid}
                        onChange={(event) => setMaxInstance(event.currentTarget.value)}
                      />
                    </label>
                  </div>
                  {inMemorySession && (
                    <p className="pp-instance-note" role="note">
                      为避免多实例间会话丢失，推荐将 Runtime 固定为 1～1
                    </p>
                  )}
                  {!instanceRange.valid && (
                    <p className="pp-instance-error" role="alert">
                      {instanceRange.error}
                    </p>
                  )}
                </section>
              )}

              <section className="pp-config-section">
                <div className="pp-config-label">网络</div>
                {deploymentPrimaryPane && deploymentRegionPicker(true)}
                {isRuntimeUpdate && (
                  <p className="pp-config-note">现有 Runtime 的区域与网络模式保持不变。</p>
                )}
                <div className="pp-network-layout">
                  <div className="pp-network-modes" role="radiogroup" aria-label="网络模式">
                    {(["public", "private", "both"] as const).map((mode) => (
                      <label className="pp-network-option" key={mode}>
                        <input
                          type="radio"
                          name="deployment-network-mode"
                          value={mode}
                          checked={networkMode === mode}
                          onChange={() => setNetworkMode(mode)}
                          disabled={deploying || isRuntimeUpdate || !onNetworkChange}
                        />
                        <span>
                          {mode === "public"
                            ? "公网"
                            : mode === "private"
                              ? "VPC"
                              : "公网 + VPC"}
                        </span>
                      </label>
                    ))}
                  </div>
                  {networkMode !== "public" && (
                    <div className="pp-network-fields">
                      <label>
                        <span>VPC ID</span>
                        <input
                          value={network?.vpcId ?? ""}
                          placeholder="vpc-xxxxxxxx"
                          disabled={deploying || isRuntimeUpdate}
                          onChange={(e) => patchNetwork({ vpcId: e.target.value })}
                        />
                      </label>
                      <label>
                        <span>子网 ID <small>可选，多个用逗号分隔</small></span>
                        <input
                          value={network?.subnetIds ?? ""}
                          placeholder="subnet-xxx, subnet-yyy"
                          disabled={deploying || isRuntimeUpdate}
                          onChange={(e) => patchNetwork({ subnetIds: e.target.value })}
                        />
                      </label>
                      <label className="pp-network-check">
                        <input
                          type="checkbox"
                          checked={!!network?.enableSharedInternetAccess}
                          disabled={deploying || isRuntimeUpdate}
                          onChange={(e) =>
                            patchNetwork({ enableSharedInternetAccess: e.target.checked })
                          }
                        />
                        VPC 内共享公网出口
                      </label>
                    </div>
                  )}
                </div>
              </section>

              <section className="pp-config-section pp-env-section">
                <div className="pp-env-head">
                  <div>
                    <div className="pp-config-label">
                      环境变量
                      <span className="pp-agent-child-count pp-env-count">
                        {environmentVariableCount} 项
                      </span>
                    </div>
                    <div className="pp-env-sub">
                      组件配置会自动同步到这里，部署前可核对最终值。
                    </div>
                  </div>
                  <button
                    type="button"
                    className="pp-icon-btn"
                    title={showEnvValues ? "隐藏值" : "显示值"}
                    onClick={() => setShowEnvValues((value) => !value)}
                  >
                    {showEnvValues ? <EyeOff className="pp-ic" /> : <Eye className="pp-ic" />}
                  </button>
                </div>
                <button
                  type="button"
                  className="pp-env-add"
                  onClick={addEnvRow}
                  disabled={deploying}
                >
                  <Plus className="pp-ic" />
                  添加变量
                </button>
                {(automaticEnvRows.length > 0 || envRows.length > 0) && (
                  <div className="pp-env-table">
                    {automaticEnvRows.length > 0 && (
                      <div className="pp-env-group">
                        <div className="pp-env-group-head">
                          <span>组件自动生成</span>
                          <small>{automaticEnvRows.length} 项</small>
                        </div>
                        {automaticEnvRows.map((row) => {
                          const fixed = row.key.startsWith("ENABLE_");
                          return (
                            <div
                              className="pp-env-row pp-env-row-derived"
                              key={row.key}
                            >
                              <input
                                className="pp-env-key-fixed"
                                value={row.key}
                                readOnly
                                disabled={deploying}
                                aria-label={`${row.key} 环境变量名`}
                              />
                              <input
                                type={fixed || showEnvValues ? "text" : "password"}
                                value={row.value}
                                placeholder={row.required ? "必填，尚未填写" : "可选，尚未填写"}
                                readOnly={fixed}
                                disabled={
                                  deploying || (!fixed && !onDeploymentEnvChange)
                                }
                                autoComplete="off"
                                aria-label={`${row.key} 环境变量值`}
                                onChange={(event) =>
                                  onDeploymentEnvChange?.(
                                    row.key,
                                    event.currentTarget.value,
                                  )
                                }
                              />
                              <span className="pp-env-source">
                                {fixed ? "自动" : "同步"}
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    {envRows.length > 0 && (
                      <div className="pp-env-group-head pp-env-group-head-custom">
                        <span>自定义变量</span>
                        <small>{envRows.length} 项</small>
                      </div>
                    )}
                    {envRows.map((row) => (
                      <div className="pp-env-row" key={row.id}>
                        <input
                          value={row.key}
                          placeholder="名称"
                          disabled={deploying}
                          autoComplete="off"
                          onChange={(e) => updateEnvRow(row.id, { key: e.currentTarget.value })}
                        />
                        <input
                          type={showEnvValues ? "text" : "password"}
                          value={row.value}
                          placeholder="值"
                          disabled={deploying}
                          autoComplete="off"
                          onChange={(e) => updateEnvRow(row.id, { value: e.currentTarget.value })}
                        />
                        <button
                          type="button"
                          className="pp-icon-btn pp-env-remove"
                          title="删除变量"
                          disabled={deploying}
                          onClick={() => removeEnvRow(row.id)}
                        >
                          <X className="pp-ic" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {(deploying || deployResult || Object.keys(stageMap).length > 0) && (
                <section className="pp-config-section pp-progress-section">
                  <div className="pp-config-label">部署进度</div>
                  <ol className="pp-steps">
                    {deploymentSteps.map((step, index) => {
                      const activeIndex = activePhase
                        ? deploymentSteps.findIndex((item) => item.phase === activePhase)
                        : -1;
                      const failed =
                        !!deployError &&
                        (activeIndex === -1 ? index === 0 : index === activeIndex);
                      let status: "pending" | "active" | "done" | "failed";
                      if (deployResult) status = "done";
                      else if (failed) status = "failed";
                      else if (activeIndex === -1) status = deploying ? "active" : "pending";
                      else if (index < activeIndex) status = "done";
                      else if (index === activeIndex) status = deployError ? "failed" : "active";
                      else status = "pending";
                      const frame = stageMap[step.phase];
                      return (
                        <li key={step.phase} className={`pp-step is-${status}`}>
                          <span className="pp-step-dot">
                            {status === "active" ? (
                              <Loader2 className="pp-ic spin" />
                            ) : status === "done" ? (
                              "✓"
                            ) : status === "failed" ? (
                              "✕"
                            ) : (
                              index + 1
                            )}
                          </span>
                          <span className="pp-step-body">
                            <span className="pp-step-label">{step.label}</span>
                            {status === "active" && frame?.message && (
                              <span className="pp-step-msg">
                                {frame.message}
                                {typeof frame.pct === "number" ? ` (${frame.pct}%)` : ""}
                              </span>
                            )}
                          </span>
                        </li>
                      );
                    })}
                  </ol>
                </section>
              )}

              {deployError && (
                <DeploymentErrorMessage
                  className="pp-error"
                  message={`${activePhase
                    ? `${isRuntimeUpdate ? "更新" : "部署"}失败（${
                        deploymentSteps.find((step) => step.phase === activePhase)?.label ??
                        activePhase
                      }阶段）：`
                    : ""}${deployError}`}
                  onRetry={requestDeploymentConfirmation}
                  retryLabel={
                    isRuntimeUpdate ? "重试更新" : "重试部署"
                  }
                />
              )}

              {deployResult && (
                <section className="pp-deploy-result">
                  <div className="pp-deploy-result-header">
                    {isRuntimeUpdate ? "更新成功" : "部署成功"}
                  </div>
                  <div className="pp-deploy-result-body">
                    {deployResult.region && (
                      <div className="pp-deploy-result-field">
                        <label>区域</label>
                        <code>
                          {deployResult.region === "cn-shanghai"
                            ? "上海 (cn-shanghai)"
                            : "北京 (cn-beijing)"}
                        </code>
                      </div>
                    )}
                    <div className="pp-deploy-result-field">
                      <label>Agent 名称</label>
                      <code>{deployResult.agentName}</code>
                    </div>
                    <div className="pp-deploy-result-field">
                      <label>API 端点</label>
                      <code className="pp-deploy-result-url">{deployResult.url}</code>
                    </div>
                  </div>
                  <div className="pp-deploy-result-actions">
                    <button
                      type="button"
                      className="pp-deploy-result-btn"
                      onClick={handleAddAgent}
                      disabled={addingAgent}
                    >
                      {addingAgent ? (
                        <Loader2 className="pp-ic spin" />
                      ) : (
                        <MessageSquare className="pp-ic" />
                      )}
                      {addingAgent ? "连接中…" : "立即对话"}
                    </button>
                    {deployResult.consoleUrl && (
                      <a
                        href={deployResult.consoleUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="pp-console-link pp-console-link-btn"
                      >
                        <ExternalLink className="pp-ic" />
                        控制台
                      </a>
                    )}
                  </div>
                </section>
              )}
            </div>
            <div
              className={`pp-config-actions${deploymentActionTarget ? " is-external" : ""}`}
            >
              {deploymentActionTarget
                ? createPortal(
                    <button
                      type="button"
                      className="pp-deploy studio-update-action"
                      onClick={requestDeploymentConfirmation}
                      disabled={
                        deploying ||
                        feishuUpdating ||
                        deployDisabled ||
                        !!deployDisabledReason
                      }
                      title={deployDisabledReason}
                    >
                      {deploying
                        ? `${deploymentActionLabel}中…`
                        : deployError
                          ? `重试${deploymentActionLabel}`
                          : deploymentActionLabel}
                    </button>,
                    deploymentActionTarget,
                  )
                : (
              <button
                type="button"
                className="pp-deploy studio-update-action"
                onClick={requestDeploymentConfirmation}
                disabled={deploying || feishuUpdating || deployDisabled || !!deployDisabledReason}
                title={deployDisabledReason}
              >
                {deploying
                  ? `${deploymentActionLabel}中…`
                  : deployError
                    ? `重试${deploymentActionLabel}`
                    : deploymentActionLabel}
              </button>
                  )}
            </div>
          </aside>
        )}
      </div>
      {flowPreviewOpen && agentDraft &&
        createPortal(
          <div
            className="pp-flow-backdrop"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) {
                setFlowPreviewOpen(false);
              }
            }}
          >
            <section
              className="pp-flow-dialog"
              role="dialog"
              aria-modal="true"
              aria-label="执行流程预览"
            >
              <header>
                <div>
                  <strong>执行流程</strong>
                  <span>只读预览，可缩放与拖动画布</span>
                </div>
                <button
                  type="button"
                  onClick={() => setFlowPreviewOpen(false)}
                  aria-label="关闭执行流程预览"
                >
                  <X aria-hidden />
                </button>
              </header>
              <div className="pp-flow-dialog-canvas">
                <AgentBuildCanvas
                  draft={agentDraft}
                  direction="horizontal"
                  selectedPath={[]}
                  onSelect={ignoreCanvasAction}
                  onAdd={ignoreCanvasAction}
                  onInsert={ignoreCanvasAction}
                  onDelete={ignoreCanvasAction}
                  readOnly
                  interactivePreview
                />
              </div>
            </section>
          </div>,
          document.body,
        )}
      <DeploymentConfirmDialog
        open={deployConfirmOpen}
        isUpdate={isRuntimeUpdate}
        onCancel={cancelDeploymentConfirmation}
        onConfirm={() => void performDeployment()}
      />
    </div>
  );
}
