import {
  useCallback,
  useDeferredValue,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type FormEvent,
  type RefObject,
  type SVGProps,
} from "react";
import { createPortal } from "react-dom";
import { ExternalLink, FileUp, SlidersHorizontal, X } from "lucide-react";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { EmptyMessage } from "@openai/apps-sdk-ui/components/EmptyMessage";
import { ArrowRotateCw, FileCode } from "@openai/apps-sdk-ui/components/Icon";
import { Input } from "@openai/apps-sdk-ui/components/Input";
import { RadioGroup } from "@openai/apps-sdk-ui/components/RadioGroup";
import { SegmentedControl } from "@openai/apps-sdk-ui/components/SegmentedControl";
import { Textarea } from "@openai/apps-sdk-ui/components/Textarea";
import feishuLogo from "../assets/feishu-logo.svg";
import pandocLogo from "../assets/pandoc-logo.svg";
import opencliLogo from "../assets/opencli-logo.svg";
import uvLogo from "../assets/uv-logo.svg";
import playwrightLogo from "../assets/playwright-logo.svg";
import chromiumLogo from "../assets/chromium-logo.svg";
import gitLogo from "../assets/git-logo.svg";
import curlLogo from "../assets/curl-logo.svg";
import ffmpegLogo from "../assets/ffmpeg-logo.svg";
import imagemagickLogo from "../assets/imagemagick-logo.svg";
import veadkLogo from "../assets/logo.svg";
import { GitHubLogo } from "./GitHubLogo";
import { LibraryResourceCard } from "./LibraryResourceCard";
import {
  ResourceCreateCard,
  ResourceDetailLayout,
  ResourceGrid,
  ResourceLoadingState,
  ResourcePageHeader,
  ResourcePageShell,
  ResourceResults,
  ResourceSearch,
  ResourceTabs,
  ResourceToolbar,
} from "./ResourceCollection";
import { StudioConfirmDialog } from "./StudioConfirmDialog";
import { StudioBuildProgress } from "./StudioBuildProgress";
import { StudioPackageOption } from "./StudioPackageOption";
import CodeEditor from "./CodeEditor";
import {
  buildEnvironment,
  createEnvironment,
  deleteEnvironment,
  exportEnvironmentShareCode,
  getEnvironmentBuild,
  getEnvironmentManifest,
  importEnvironmentShareCodes,
  inspectEnvironmentRepository,
  inspectEnvironmentShareCodes,
  listEnvironments,
  parseEnvironmentShareCodes,
  updateEnvironment,
  writeEnvironmentShareCode,
  type EnvironmentBuildStatus,
  type EnvironmentBuildVersion,
  type EnvironmentManifest,
  type EnvironmentContainerRepository,
  type EnvironmentInput,
  type EnvironmentRepositoryInspection,
  type EnvironmentShareCodeInspection,
  type StudioEnvironment,
} from "../adk/client";
import {
  buildEnvironmentDockerfile,
  EMPTY_ENVIRONMENT_DRAFT,
  ENVIRONMENT_BASE_ENVIRONMENTS,
  ENVIRONMENT_CATEGORIES,
  ENVIRONMENT_LANGUAGES,
  ENVIRONMENT_OPERATING_SYSTEMS,
  environmentBaseEnvironmentLabel,
  environmentBaseFromDockerfile,
  environmentLanguageLabel,
  environmentOperatingSystemLabel,
  type EnvironmentBaseEnvironment,
  type EnvironmentDraft,
  type EnvironmentLanguage,
  type EnvironmentOperatingSystem,
  type EnvironmentOption,
} from "./environmentModel";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import { SkillSourcePicker } from "./SkillSourcePicker";
import {
  dockerfileByteSize,
  readDockerfileUpload,
  validateDockerfileUpload,
} from "./environmentDockerfileUpload";
import { formatEnvironmentManifest } from "./environmentManifest";
import {
  cloudRegionOptions,
  defaultCloudRegion,
  type CloudProvider,
  type CloudRegion,
} from "../adk/cloudProvider";
import { ContainerRepositorySelector } from "./DeploymentResources";
import { DeploymentSelect } from "./DeploymentSelect";
import "./EnvironmentCenter.css";

type EnvironmentView =
  | { kind: "list" }
  | { kind: "editor"; environmentId: string | null };

type EnvironmentEditorTab = "configuration" | "dockerfile";
type EnvironmentCreationMethod = "custom" | "dockerfile" | "git" | "image";
type GitRepositoryMode = "managed" | "existing";

const MAX_ENVIRONMENT_SHARE_CODES = 20;
const promptedClipboardShareTexts = new Set<string>();
const CLIPBOARD_READ_ERROR = "未能读取剪贴板。请允许剪贴板权限，或点击“导入环境”后手动粘贴分享码。";
const CLIPBOARD_UNSUPPORTED_ERROR = "当前浏览器无法自动读取剪贴板；请点击“导入环境”后手动粘贴分享码。";

async function clipboardReadPermissionDenied(): Promise<boolean> {
  if (typeof navigator === "undefined" || !navigator.permissions?.query) return false;
  try {
    const permission = await navigator.permissions.query({ name: "clipboard-read" as PermissionName });
    return permission.state === "denied";
  } catch {
    return false;
  }
}

export interface EnvironmentClipboardImportRequest {
  key: number;
  text: string;
}

const TOOL_LOGOS: Readonly<Record<string, string>> = {
  opencli: opencliLogo,
  uv: uvLogo,
  playwright: playwrightLogo,
  chromium: chromiumLogo,
  git: gitLogo,
  curl: curlLogo,
  ffmpeg: ffmpegLogo,
  imagemagick: imagemagickLogo,
};

function AddIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true" {...props}>
      <path d="M8 3.25v9.5M3.25 8h9.5" />
    </svg>
  );
}

function GitRepositoryIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="6" cy="5" r="2" />
      <circle cx="6" cy="19" r="2" />
      <circle cx="18" cy="12" r="2" />
      <path d="M8 5h2a4 4 0 0 1 4 4v0a3 3 0 0 0 3 3M8 19h2a4 4 0 0 0 4-4v0a3 3 0 0 1 3-3" />
    </svg>
  );
}

function ContainerImageIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="m4.5 7.5 7.5-4 7.5 4v9l-7.5 4-7.5-4v-9Z" />
      <path d="m4.5 7.5 7.5 4 7.5-4M12 11.5v9" />
      <path d="m8.5 5.4 7.3 4" />
    </svg>
  );
}

function ImportEnvironmentIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M12 3v11m0 0 4-4m-4 4-4-4" />
      <path d="M5 16v2.5A2.5 2.5 0 0 0 7.5 21h9a2.5 2.5 0 0 0 2.5-2.5V16" />
    </svg>
  );
}

function repositoryInputError(repositoryUrl: string): string {
  const trimmed = repositoryUrl.trim();
  if (!trimmed) return "请输入公开代码仓库地址。";
  try {
    const url = new URL(trimmed);
    if (url.protocol !== "https:" || !url.hostname) {
      return "请输入公开仓库的 HTTPS 地址。";
    }
  } catch {
    return "请输入有效的公开仓库 HTTPS 地址。";
  }
  return "";
}

function repositorySelected(value: EnvironmentContainerRepository | undefined): boolean {
  return Boolean(
    value?.region && value.registry && value.namespace && value.repository,
  );
}

function imageReferenceError(reference: string): string {
  const value = reference.trim();
  if (!value) return "";
  if (/\s/.test(value)) return "Tag 或 Digest 不能包含空格。";
  if (value.startsWith("sha256:")) {
    return /^sha256:[0-9a-fA-F]{64}$/.test(value)
      ? ""
      : "Digest 必须是完整的 sha256 值。";
  }
  if (/[@/]/.test(value)) return "这里只填写 Tag，不要重复填写镜像仓库路径。";
  return "";
}

function conciseErrorMessage(cause: unknown): string {
  const message = cause instanceof Error ? cause.message : String(cause);
  return message.split("\n原始响应：", 1)[0].trim();
}

function EnvironmentEmptyIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M5.5 10.5 16 5l10.5 5.5L16 16 5.5 10.5Z" />
      <path d="M5.5 16 16 21.5 26.5 16M5.5 21.5 16 27l10.5-5.5" />
    </svg>
  );
}

function PackageFallback({ label }: { label: string }) {
  return <span className="environment-package-fallback">{label.slice(0, 1).toUpperCase()}</span>;
}

function EnvironmentPackageIcon({ option }: { option: EnvironmentOption }) {
  if (option.id === "lark-cli") return <img src={feishuLogo} alt="" />;
  if (option.id === "pandoc") return <img src={pandocLogo} alt="" />;
  if (option.id === "github-cli") return <GitHubLogo />;
  const src = TOOL_LOGOS[option.id];
  if (!src) return <PackageFallback label={option.label} />;
  return <img src={src} alt="" />;
}

function environmentDraft(environment?: StudioEnvironment): EnvironmentDraft {
  if (!environment) {
    return {
      ...EMPTY_ENVIRONMENT_DRAFT,
      optionIds: [...EMPTY_ENVIRONMENT_DRAFT.optionIds],
      selectedSkills: [...EMPTY_ENVIRONMENT_DRAFT.selectedSkills],
    };
  }
  return {
    name: environment.name,
    description: environment.description,
    baseEnvironment: environment.baseEnvironment,
    operatingSystem: environment.operatingSystem,
    language: environment.language,
    optionIds: [...environment.optionIds],
    selectedSkills: [...environment.selectedSkills],
    dockerfile:
      environment.dockerfile === buildEnvironmentDockerfile(environment)
        ? undefined
        : environment.dockerfile,
    gitSource: environment.gitSource,
    containerRepository: environment.containerRepository,
    imageSource: environment.imageSource,
  };
}

const ACTIVE_BUILD_STATUSES = new Set<EnvironmentBuildStatus>([
  "preparing",
  "queued",
  "building",
  "scanning",
]);

const BUILD_LOG_REFRESH_INTERVAL_MS = 3_000;

const BUILD_STATUS_LABELS: Record<EnvironmentBuildStatus, string> = {
  preparing: "准备中",
  queued: "排队中",
  building: "构建中",
  scanning: "扫描中",
  available: "可用",
  failed: "构建失败",
};

function environmentStatus(environment: StudioEnvironment): {
  label: string;
  color: "secondary" | "success" | "warning" | "danger";
} {
  const status = environment.latestVersion?.status;
  if (!status) return { label: "未构建", color: "secondary" };
  if (status === "available") return { label: BUILD_STATUS_LABELS[status], color: "success" };
  if (status === "failed") return { label: BUILD_STATUS_LABELS[status], color: "danger" };
  return { label: BUILD_STATUS_LABELS[status], color: "warning" };
}

function environmentUpdatedAt(value: string): string {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(timestamp);
}

function buildElapsed(build: EnvironmentBuildVersion, now = Date.now()): string {
  const start = Date.parse(build.createdAt);
  const active = ACTIVE_BUILD_STATUSES.has(build.status);
  const end = active ? now : Date.parse(build.updatedAt);
  if (Number.isNaN(start) || Number.isNaN(end)) return "";
  const seconds = Math.max(0, Math.floor((end - start) / 1000));
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  if (minutes < 60) return `${minutes} 分 ${remainder} 秒`;
  return `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分`;
}

function EnvironmentManifestDialog({
  environment,
  onClose,
}: {
  environment: StudioEnvironment;
  onClose: () => void;
}) {
  const versionId = environment.latestVersion?.versionId ?? "";
  const titleId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const onCloseRef = useRef(onClose);
  const [manifest, setManifest] = useState<EnvironmentManifest | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");
  const manifestYaml = useMemo(
    () => manifest ? formatEnvironmentManifest(manifest) : "",
    [manifest],
  );
  onCloseRef.current = onClose;

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    document.body.style.overflow = "hidden";
    dialogRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
      )).filter((item) => item.getClientRects().length > 0);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void getEnvironmentManifest(environment.id, versionId, controller.signal)
      .then(setManifest)
      .catch((cause) => {
        if ((cause as Error)?.name !== "AbortError") {
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [environment.id, reloadKey, versionId]);

  useEffect(() => {
    if (copyState !== "copied") return;
    const timer = window.setTimeout(() => setCopyState("idle"), 1500);
    return () => window.clearTimeout(timer);
  }, [copyState]);

  const copyManifest = async () => {
    try {
      await navigator.clipboard.writeText(manifestYaml);
      setCopyState("copied");
    } catch {
      setCopyState("error");
    }
  };

  return createPortal(
    <div className="environment-build-dialog__backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section
        ref={dialogRef}
        className="environment-build-dialog environment-manifest-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-busy={loading || undefined}
        tabIndex={-1}
      >
        <header className="environment-build-dialog__header">
          <div>
            <div className="environment-build-dialog__title-row">
              <h2 id={titleId}>环境 Manifest</h2>
            </div>
            <p>{environment.name} / {versionId}</p>
          </div>
          <Button type="button" color="secondary" variant="ghost" size="sm" uniform onClick={onClose} aria-label="关闭环境 Manifest">
            <X aria-hidden />
          </Button>
        </header>

        <div className="environment-manifest-dialog__body">
          {loading ? (
            <div className="environment-manifest-dialog__state" role="status">
              <TextShimmer as="span">正在加载 Manifest</TextShimmer>
            </div>
          ) : error ? (
            <div className="environment-manifest-dialog__state is-error" role="alert">
              <p>{error}</p>
              <Button type="button" color="secondary" variant="soft" size="sm" onClick={() => setReloadKey((key) => key + 1)}>
                重新加载
              </Button>
            </div>
          ) : (
            <div className="environment-manifest-dialog__editor" aria-label="环境 Manifest YAML">
              <CodeEditor
                value={manifestYaml}
                path="environment.yaml"
                readOnly
                onChange={() => undefined}
              />
            </div>
          )}
        </div>

        <footer className="environment-build-dialog__actions">
          {copyState === "error" ? (
            <span className="environment-manifest-dialog__copy-error" role="alert">复制失败，请重试</span>
          ) : null}
          <Button type="button" color="secondary" variant="ghost" size="sm" onClick={onClose}>关闭</Button>
          <Button type="button" color="info" size="sm" disabled={!manifestYaml} onClick={() => void copyManifest()}>
            {copyState === "copied" ? "已复制" : "复制 Manifest"}
          </Button>
        </footer>
      </section>
    </div>,
    document.body,
  );
}

function EnvironmentBuildDetailsDialog({
  environment,
  onClose,
  onBuildUpdate,
  onRebuild,
}: {
  environment: StudioEnvironment;
  onClose: () => void;
  onBuildUpdate: (build: EnvironmentBuildVersion) => void;
  onRebuild: () => Promise<void>;
}) {
  const initialBuild = environment.latestVersion;
  const [build, setBuild] = useState(initialBuild);
  const [loading, setLoading] = useState(Boolean(initialBuild));
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());
  const [rebuilding, setRebuilding] = useState(false);
  const titleId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const onCloseRef = useRef(onClose);
  const onBuildUpdateRef = useRef(onBuildUpdate);

  useEffect(() => {
    onCloseRef.current = onClose;
    onBuildUpdateRef.current = onBuildUpdate;
  }, [onBuildUpdate, onClose]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    document.body.style.overflow = "hidden";
    dialogRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseRef.current();
      if (event.key !== "Tab") return;
      const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
      ) ?? []).filter((item) => item.getClientRects().length > 0);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  useEffect(() => {
    if (!initialBuild) return;
    let timer = 0;
    const controller = new AbortController();
    const refresh = async () => {
      setLoading(true);
      try {
        const next = await getEnvironmentBuild(environment.id, initialBuild.versionId, {
          includeLogs: true,
          signal: controller.signal,
        });
        setBuild(next);
        setError("");
        onBuildUpdateRef.current(next);
        if (ACTIVE_BUILD_STATUSES.has(next.status)) {
          timer = window.setTimeout(refresh, BUILD_LOG_REFRESH_INTERVAL_MS);
        }
      } catch (cause) {
        if ((cause as Error)?.name === "AbortError") return;
        setError(cause instanceof Error ? cause.message : String(cause));
        timer = window.setTimeout(refresh, BUILD_LOG_REFRESH_INTERVAL_MS);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    void refresh();
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [environment.id, initialBuild?.versionId]);

  useEffect(() => {
    if (!build || !ACTIVE_BUILD_STATUSES.has(build.status)) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [build?.status]);

  const status = build
    ? environmentStatus({ ...environment, latestVersion: build })
    : { label: "未构建", color: "secondary" as const };
  const cpUrl = environment.imageSource
    ? undefined
    : build?.resources?.codePipeline?.consoleUrl;

  return createPortal(
    <div className="environment-build-dialog__backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section
        ref={dialogRef}
        className="environment-build-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <header className="environment-build-dialog__header">
          <div>
            <div className="environment-build-dialog__title-row">
              <h2 id={titleId}>构建详情</h2>
              <Badge color={status.color} size="sm">{status.label}</Badge>
            </div>
            <p>{environment.name}</p>
          </div>
          <Button type="button" color="secondary" variant="ghost" size="sm" uniform onClick={onClose} aria-label="关闭构建详情">
            <X aria-hidden />
          </Button>
        </header>

        <div className="environment-build-dialog__summary">
          <div><span>当前步骤</span><strong>{build?.currentStep || "等待构建信息"}</strong></div>
          <div><span>已用时</span><strong>{build ? buildElapsed(build, now) : "-"}</strong></div>
          {build?.sourceCommitSha ? (
            <div>
              <span>源码提交</span>
              <strong title={build.sourceCommitSha}>{build.sourceCommitSha.slice(0, 12)}</strong>
            </div>
          ) : null}
          {cpUrl ? (
            <a href={cpUrl} target="_blank" rel="noreferrer">
              在 CodePipeline 中查看 <ExternalLink aria-hidden />
            </a>
          ) : null}
        </div>

        <div className="environment-build-dialog__body">
          {error ? <p className="environment-build-dialog__error" role="alert">{error}</p> : null}
          {build?.progressError ? <p className="environment-build-dialog__notice">{build.progressError}</p> : null}
          <StudioBuildProgress
            steps={build?.steps ?? []}
            log={build?.logTail ?? ""}
            logError={build?.logError}
            logTruncated={build?.logTruncated}
            logUpdatedAt={build?.logUpdatedAt}
            loading={loading && Boolean(build && ACTIVE_BUILD_STATUSES.has(build.status))}
          />
          {build?.status === "failed" && build.error ? (
            <p className="environment-build-dialog__failure" role="alert">{build.error}</p>
          ) : null}
        </div>

        <footer className="environment-build-dialog__actions">
          <Button type="button" color="secondary" variant="ghost" size="sm" onClick={onClose}>关闭</Button>
          {build && !environment.imageSource && !ACTIVE_BUILD_STATUSES.has(build.status) ? (
            <Button type="button" color="info" size="sm" disabled={rebuilding} onClick={() => {
              setRebuilding(true);
              void onRebuild().then(onClose).finally(() => setRebuilding(false));
            }}>
              {rebuilding ? "正在启动" : "重新构建"}
            </Button>
          ) : null}
        </footer>
      </section>
    </div>,
    document.body,
  );
}

function EnvironmentRegionSelector({
  cloudProvider,
  value,
  disabled,
  onChange,
}: {
  cloudProvider: CloudProvider;
  value: CloudRegion;
  disabled: boolean;
  onChange: (region: CloudRegion) => void;
}) {
  const options = cloudRegionOptions(cloudProvider);
  return (
    <div className="environment-source-field">
      <span className="environment-source-field__label">Region</span>
      <SegmentedControl
        className="environment-region-control"
        value={value}
        aria-label="镜像仓库 Region"
        disabled={disabled}
        onChange={(nextValue) => onChange(nextValue as CloudRegion)}
      >
        {options.map((option) => (
          <SegmentedControl.Option key={option.value} value={option.value}>
            {option.label}
          </SegmentedControl.Option>
        ))}
      </SegmentedControl>
    </div>
  );
}

function GitRepositoryFields({
  repositoryUrl,
  gitRef,
  dockerfilePath,
  inspection,
  inspectedKey,
  disabled,
  onRepositoryUrlChange,
  onGitRefChange,
  onDockerfilePathChange,
  onInspectionChange,
  onInspectedKeyChange,
}: {
  repositoryUrl: string;
  gitRef: string;
  dockerfilePath: string;
  inspection: EnvironmentRepositoryInspection | null;
  inspectedKey: string;
  disabled: boolean;
  onRepositoryUrlChange: (value: string) => void;
  onGitRefChange: (value: string) => void;
  onDockerfilePathChange: (value: string) => void;
  onInspectionChange: (value: EnvironmentRepositoryInspection | null) => void;
  onInspectedKeyChange: (value: string) => void;
}) {
  const [inspecting, setInspecting] = useState(false);
  const [inspectError, setInspectError] = useState("");
  const requestRef = useRef<AbortController | null>(null);
  const autoAttemptedKeyRef = useRef("");
  const currentKey = `${repositoryUrl.trim()}\u0000${gitRef.trim()}`;
  const inspectionIsCurrent = inspectedKey === currentKey;

  useEffect(() => () => {
    const controller = requestRef.current;
    requestRef.current = null;
    controller?.abort();
  }, []);

  const resetInspection = () => {
    requestRef.current?.abort();
    requestRef.current = null;
    setInspecting(false);
    setInspectError("");
    onInspectionChange(null);
    onInspectedKeyChange("");
    onDockerfilePathChange("");
    autoAttemptedKeyRef.current = "";
  };

  const inspectRepository = useCallback(async () => {
    const inputError = repositoryInputError(repositoryUrl);
    if (inputError) {
      setInspectError(inputError);
      return;
    }
    autoAttemptedKeyRef.current = currentKey;
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setInspecting(true);
    setInspectError("");
    try {
      const result = await inspectEnvironmentRepository(
        {
          repositoryUrl: repositoryUrl.trim(),
          ...(gitRef.trim() ? { ref: gitRef.trim() } : {}),
        },
        controller.signal,
      );
      if (requestRef.current !== controller) return;
      onInspectionChange(result);
      onInspectedKeyChange(currentKey);
      onDockerfilePathChange(result.dockerfiles.length === 1 ? result.dockerfiles[0] : "");
    } catch (cause) {
      if ((cause as Error)?.name === "AbortError") return;
      setInspectError(conciseErrorMessage(cause));
      onInspectionChange(null);
      onInspectedKeyChange("");
      onDockerfilePathChange("");
    } finally {
      if (requestRef.current === controller) {
        requestRef.current = null;
        setInspecting(false);
      }
    }
  }, [
    currentKey,
    gitRef,
    onDockerfilePathChange,
    onInspectedKeyChange,
    onInspectionChange,
    repositoryUrl,
  ]);

  useEffect(() => {
    if (
      disabled
      || inspectionIsCurrent
      || autoAttemptedKeyRef.current === currentKey
      || repositoryInputError(repositoryUrl)
    ) {
      return;
    }
    const timer = window.setTimeout(() => void inspectRepository(), 600);
    return () => window.clearTimeout(timer);
  }, [currentKey, disabled, inspectRepository, inspectionIsCurrent, repositoryUrl]);

  const dockerfiles = inspectionIsCurrent ? inspection?.dockerfiles ?? [] : [];
  return (
    <section className="environment-source-section" aria-labelledby="environment-git-source-title">
      <div className="environment-source-section__header">
        <h2 id="environment-git-source-title">公开代码仓库</h2>
        <p>输入无需鉴权的 HTTPS Git 地址后，将自动探查并列出 Dockerfile。</p>
      </div>
      <div className="environment-source-fields environment-source-fields--git">
        <label className="environment-source-field environment-source-field--wide">
          <span className="environment-source-field__label">Git 地址</span>
          <Input
            size="lg"
            type="url"
            value={repositoryUrl}
            placeholder="https://github.com/owner/repository.git"
            autoComplete="url"
            disabled={disabled}
            aria-invalid={Boolean(inspectError)}
            onChange={(event) => {
              resetInspection();
              onRepositoryUrlChange(event.currentTarget.value);
            }}
          />
        </label>
        <label className="environment-source-field">
          <span className="environment-source-field__label">Branch、Tag 或 Commit（可选）</span>
          <Input
            size="lg"
            value={gitRef}
            placeholder="默认分支"
            autoComplete="off"
            disabled={disabled}
            onChange={(event) => {
              resetInspection();
              onGitRefChange(event.currentTarget.value);
            }}
          />
        </label>
      </div>
      <div className="environment-inspection-status" aria-live="polite">
        {inspecting ? <TextShimmer as="span">正在拉取仓库并查找 Dockerfile</TextShimmer> : null}
        {inspectError ? (
          <div className="environment-source-error" role="alert">
            <span>{inspectError}</span>
            <Button type="button" color="primary" size="sm" pill={false} disabled={disabled} onClick={() => void inspectRepository()}>
              <ArrowRotateCw />
              重试
            </Button>
          </div>
        ) : null}
        {!inspecting && !inspectError && inspectionIsCurrent && inspection ? (
          dockerfiles.length > 0 ? (
            <span>
              {inspection.commitSha
                ? `已在提交 ${inspection.commitSha.slice(0, 12)} 中找到 ${dockerfiles.length} 个 Dockerfile。`
                : "已载入保存的 Dockerfile，可重新探查仓库更新。"}
            </span>
          ) : (
            <div className="environment-source-error" role="alert">
              <span>仓库中未找到 Dockerfile，请检查分支或仓库内容。</span>
              <button type="button" disabled={disabled} onClick={() => void inspectRepository()}>重新探查</button>
            </div>
          )
        ) : null}
      </div>
      {dockerfiles.length > 0 ? (
        <label className="environment-source-field environment-dockerfile-picker">
          <span className="environment-source-field__label">Dockerfile</span>
          <DeploymentSelect
            ariaLabel="选择 Dockerfile"
            value={dockerfilePath}
            valueLabel={dockerfilePath}
            placeholder="请选择 Dockerfile"
            options={dockerfiles.map((path) => ({ value: path, label: path }))}
            disabled={disabled || inspecting}
            onChange={onDockerfilePathChange}
          />
        </label>
      ) : null}
    </section>
  );
}

function EnvironmentRepositoryDestination({
  cloudProvider,
  mode,
  region,
  value,
  disabled,
  onModeChange,
  onRegionChange,
  onChange,
}: {
  cloudProvider: CloudProvider;
  mode: GitRepositoryMode;
  region: CloudRegion;
  value: EnvironmentContainerRepository | undefined;
  disabled: boolean;
  onModeChange: (mode: GitRepositoryMode) => void;
  onRegionChange: (region: CloudRegion) => void;
  onChange: (value: EnvironmentContainerRepository) => void;
}) {
  return (
    <section className="environment-source-section" aria-labelledby="environment-output-repository-title">
      <div className="environment-source-section__header">
        <h2 id="environment-output-repository-title">构建输出</h2>
        <p>CodePipeline 会把构建完成的镜像推送到所选镜像仓库。</p>
      </div>
      <SegmentedControl
        className="environment-repository-mode"
        value={mode}
        aria-label="构建输出镜像仓库"
        disabled={disabled}
        onChange={(nextMode) => onModeChange(nextMode as GitRepositoryMode)}
      >
        <SegmentedControl.Option value="managed">Studio 默认镜像仓库</SegmentedControl.Option>
        <SegmentedControl.Option value="existing">已有镜像仓库</SegmentedControl.Option>
      </SegmentedControl>
      <EnvironmentRegionSelector
        cloudProvider={cloudProvider}
        value={region}
        disabled={disabled}
        onChange={onRegionChange}
      />
      {mode === "existing" ? (
        <ContainerRepositorySelector
          region={region}
          value={value}
          disabled={disabled}
          onChange={onChange}
        />
      ) : (
        <p className="environment-source-note">构建时自动创建或复用当前 Region 的 Studio 镜像仓库。</p>
      )}
    </section>
  );
}

function ExistingImageFields({
  cloudProvider,
  region,
  repository,
  reference,
  disabled,
  onRegionChange,
  onRepositoryChange,
  onReferenceChange,
}: {
  cloudProvider: CloudProvider;
  region: CloudRegion;
  repository: EnvironmentContainerRepository | undefined;
  reference: string;
  disabled: boolean;
  onRegionChange: (region: CloudRegion) => void;
  onRepositoryChange: (value: EnvironmentContainerRepository) => void;
  onReferenceChange: (value: string) => void;
}) {
  const referenceError = imageReferenceError(reference);
  return (
    <section className="environment-source-section" aria-labelledby="environment-image-source-title">
      <div className="environment-source-section__header">
        <h2 id="environment-image-source-title">已有镜像</h2>
        <p>绑定已由外部流水线交付到 CR 的镜像，创建后不会触发 CodePipeline 构建。</p>
      </div>
      <EnvironmentRegionSelector
        cloudProvider={cloudProvider}
        value={region}
        disabled={disabled}
        onChange={onRegionChange}
      />
      <ContainerRepositorySelector
        region={region}
        value={repository}
        disabled={disabled}
        onChange={onRepositoryChange}
      />
      <label className="environment-source-field environment-image-reference">
        <span className="environment-source-field__label">Tag 或 Digest</span>
        <Input
          size="lg"
          value={reference}
          placeholder="例如：latest 或 sha256:..."
          autoComplete="off"
          disabled={disabled}
          aria-invalid={Boolean(referenceError)}
          onChange={(event) => onReferenceChange(event.currentTarget.value)}
        />
        {referenceError ? (
          <small className="environment-source-field__error" role="alert">{referenceError}</small>
        ) : (
          <small>填写镜像 Tag，或以 sha256: 开头的完整 Digest。</small>
        )}
      </label>
    </section>
  );
}

function useEnvironmentDialogFocus(
  dialogRef: RefObject<HTMLElement | null>,
  initialFocusRef: RefObject<HTMLElement | null>,
  onClose: () => void,
  busy: boolean,
) {
  const onCloseRef = useRef(onClose);
  const busyRef = useRef(busy);
  onCloseRef.current = onClose;
  busyRef.current = busy;

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    document.body.style.overflow = "hidden";
    const frame = window.requestAnimationFrame(() => initialFocusRef.current?.focus());
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busyRef.current) {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), textarea:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ) ?? []).filter((item) => item.getClientRects().length > 0);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.cancelAnimationFrame(frame);
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [dialogRef, initialFocusRef]);
}

function EnvironmentShareDialog({
  environment,
  onClose,
}: {
  environment: StudioEnvironment;
  onClose: () => void;
}) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [shareCode, setShareCode] = useState("");
  const [state, setState] = useState<"loading" | "copied" | "error">("loading");
  const [error, setError] = useState("");
  const busy = state === "loading";
  useEnvironmentDialogFocus(dialogRef, closeButtonRef, onClose, busy);

  const copyShareCode = async (existingCode = "", signal?: AbortSignal) => {
    setState("loading");
    setError("");
    try {
      const code = existingCode || (await exportEnvironmentShareCode(environment.id, signal)).shareCode;
      setShareCode(code);
      await writeEnvironmentShareCode(code);
      if (!signal?.aborted) setState("copied");
    } catch (cause) {
      if ((cause as Error)?.name === "AbortError") return;
      setError(cause instanceof Error ? cause.message : String(cause));
      setState("error");
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    void copyShareCode("", controller.signal);
    return () => controller.abort();
    // Generate once when the dialog opens for this environment.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [environment.id]);

  return createPortal(
    <div
      className="environment-build-dialog__backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className="environment-share-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        aria-busy={busy || undefined}
      >
        <header className="environment-build-dialog__header">
          <div>
            <h2 id={titleId}>分享环境</h2>
            <p id={descriptionId}>{environment.name}</p>
          </div>
          <Button
            ref={closeButtonRef}
            type="button"
            color="secondary"
            variant="ghost"
            size="sm"
            uniform
            disabled={busy}
            onClick={onClose}
            aria-label="关闭分享环境"
          >
            <X aria-hidden />
          </Button>
        </header>
        <div className="environment-share-dialog__body">
          {state === "loading" ? (
            <TextShimmer as="p">正在生成并复制分享码</TextShimmer>
          ) : (
            <div className="environment-share-dialog__result">
              {state === "copied" ? (
                <p className="environment-share-dialog__success" role="status" aria-live="polite">
                  分享码已复制
                </p>
              ) : (
                <div className="environment-share-dialog__error" role="alert">
                  <strong>分享失败</strong>
                  <span>{error}</span>
                </div>
              )}
              {shareCode ? (
                <label className="environment-share-dialog__field environment-share-dialog__manual-code">
                  <span>分享码</span>
                  <Textarea
                    size="lg"
                    rows={4}
                    value={shareCode}
                    readOnly
                    aria-label="完整环境分享码"
                    onFocus={(event) => event.currentTarget.select()}
                    onClick={(event) => event.currentTarget.select()}
                  />
                  <small>
                    {state === "copied"
                      ? "分享码已自动复制，也可在这里查看或手动复制。"
                      : "自动复制失败，可手动复制上方分享码，或重试。"}
                  </small>
                </label>
              ) : null}
              <p className="environment-share-dialog__safety">
                分享码可能包含环境配置与本地 Skill 内容，请仅发送给可信对象。
              </p>
            </div>
          )}
        </div>
        <footer className="environment-build-dialog__actions">
          <Button type="button" color="secondary" variant="ghost" size="sm" disabled={busy} onClick={onClose}>
            关闭
          </Button>
          {state === "error" ? (
            <Button type="button" color="info" size="sm" onClick={() => void copyShareCode(shareCode)}>
              重试
            </Button>
          ) : state === "copied" ? (
            <Button type="button" color="info" size="sm" onClick={() => void copyShareCode(shareCode)}>
              再次复制
            </Button>
          ) : null}
        </footer>
      </section>
    </div>,
    document.body,
  );
}

type EnvironmentImportPhase = "editing" | "inspecting" | "ready" | "importing";

function EnvironmentImportDialog({
  initialValue,
  autoInspect,
  onClose,
  onImported,
}: {
  initialValue: string;
  autoInspect: boolean;
  onClose: () => void;
  onImported: (
    environments: StudioEnvironment[],
    createdCount: number,
    duplicateCount: number,
    failedCount: number,
  ) => void;
}) {
  const titleId = useId();
  const descriptionId = useId();
  const helpId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const autoInspectStartedRef = useRef(false);
  const [value, setValue] = useState(initialValue);
  const [phase, setPhase] = useState<EnvironmentImportPhase>("editing");
  const [inspections, setInspections] = useState<EnvironmentShareCodeInspection[]>([]);
  const [requestError, setRequestError] = useState("");
  const [failedItems, setFailedItems] = useState<Array<{ code: string; error: string }>>([]);
  const shareCodes = useMemo(() => parseEnvironmentShareCodes(value), [value]);
  const tooMany = shareCodes.length > MAX_ENVIRONMENT_SHARE_CODES;
  const busy = phase === "inspecting" || phase === "importing";
  const validInspections = inspections.filter((item) => item.status === "valid");
  const invalidInspections = inspections.filter((item) => item.status === "invalid");
  const readyToImport = phase === "ready"
    && validInspections.length > 0;
  useEnvironmentDialogFocus(dialogRef, textareaRef, onClose, busy);

  const inspectCodes = useCallback(async () => {
    if (!shareCodes.length || tooMany) return;
    setPhase("inspecting");
    setRequestError("");
    setFailedItems([]);
    try {
      const result = await inspectEnvironmentShareCodes(shareCodes);
      setInspections([...result].sort((left, right) => left.index - right.index));
      setPhase("ready");
    } catch (cause) {
      setRequestError(cause instanceof Error ? cause.message : String(cause));
      setPhase("editing");
    }
  }, [shareCodes, tooMany]);

  useEffect(() => {
    if (!autoInspect || autoInspectStartedRef.current) return;
    autoInspectStartedRef.current = true;
    void inspectCodes();
  }, [autoInspect, inspectCodes]);

  const importCodes = async () => {
    if (!readyToImport) return;
    setPhase("importing");
    setRequestError("");
    setFailedItems([]);
    try {
      const importEntries = validInspections.map((item) => ({
        code: shareCodes[item.index],
        name: item.name,
      })).filter((item): item is { code: string; name: string } => Boolean(item.code));
      const result = await importEnvironmentShareCodes(importEntries.map((item) => item.code));
      const createdCount = result.filter((item) => item.status === "created").length;
      const duplicateCount = result.filter((item) => item.status === "duplicate").length;
      const resultByIndex = new Map(result.map((item) => [item.index, item]));
      const failed = importEntries.flatMap(({ code, name }, index) => {
        const item = resultByIndex.get(index);
        return !item || item.status === "failed"
          ? [{ code, name, status: "valid" as const, error: item?.error || "服务未返回该分享码的导入结果。" }]
          : [];
      });
      const invalid = invalidInspections.flatMap((item) => {
        const code = shareCodes[item.index];
        return code
          ? [{ code, name: "", status: "invalid" as const, error: item.error || "分享码无效。" }]
          : [];
      });
      const retained = [...invalid, ...failed];
      const importedById = new Map<string, StudioEnvironment>();
      result.forEach((item) => {
        if (item.environment) importedById.set(item.environment.id, item.environment);
      });
      onImported([...importedById.values()], createdCount, duplicateCount, retained.length);
      if (!retained.length) {
        onClose();
        return;
      }
      setValue(retained.map((item) => item.code).join("\n"));
      setFailedItems(failed);
      setInspections(retained.map((item, index) => ({
        index,
        status: item.status,
        name: item.name,
        error: item.status === "invalid" ? item.error : "",
      })));
      setRequestError(`已导入 ${createdCount} 个环境，${retained.length} 个未完成，可重试有效失败项。`);
      setPhase("ready");
    } catch (cause) {
      setRequestError(cause instanceof Error ? cause.message : String(cause));
      setPhase("ready");
    }
  };

  const primaryLabel = phase === "inspecting"
    ? "正在检测"
    : phase === "importing"
      ? "正在导入"
      : readyToImport
        ? failedItems.length ? "重试导入" : "确认导入"
        : "检测分享码";

  return createPortal(
    <div
      className="environment-build-dialog__backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className="environment-share-dialog environment-import-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        aria-busy={busy || undefined}
      >
        <header className="environment-build-dialog__header">
          <div>
            <h2 id={titleId}>导入环境</h2>
            <p id={descriptionId}>先检测分享码中的环境，再确认添加到当前账号。</p>
          </div>
          <Button
            type="button"
            color="secondary"
            variant="ghost"
            size="sm"
            uniform
            disabled={busy}
            onClick={onClose}
            aria-label="关闭导入环境"
          >
            <X aria-hidden />
          </Button>
        </header>
        <div className="environment-share-dialog__body">
          <label className="environment-share-dialog__field">
            <span>环境分享码</span>
            <Textarea
              ref={textareaRef}
              size="lg"
              rows={6}
              value={value}
              disabled={busy}
              aria-invalid={tooMany || invalidInspections.length > 0 || undefined}
              aria-describedby={helpId}
              placeholder="例如：akenv://v1/..."
              onChange={(event) => {
                setValue(event.currentTarget.value);
                setPhase("editing");
                setInspections([]);
                setRequestError("");
                setFailedItems([]);
              }}
            />
          </label>
          <p id={helpId} className={`environment-share-dialog__help${tooMany ? " is-error" : ""}`}>
            {tooMany
              ? `最多可一次导入 20 个环境，当前检测到 ${shareCodes.length} 个分享码。`
              : "多个分享码可使用英文逗号、中文逗号或换行分隔，重复项会自动忽略。"}
          </p>
          <p className="environment-share-dialog__safety">
            分享码可能包含环境配置与本地 Skill 内容，请仅导入可信来源的分享码。
          </p>
          {phase === "inspecting" ? (
            <TextShimmer as="p">正在检测环境分享码</TextShimmer>
          ) : validInspections.length ? (
            <p className="environment-share-dialog__summary" role="status" aria-live="polite">
              检测到 {validInspections.length} 个环境，名称分别是：
              {validInspections.map((item) => item.name || "未命名环境").join("、")}。
            </p>
          ) : null}
          {invalidInspections.length ? (
            <ul className="environment-share-dialog__failures" role="alert">
              {invalidInspections.map((item) => (
                <li key={item.index}>第 {item.index + 1} 个分享码：{item.error || "分享码无效。"}</li>
              ))}
            </ul>
          ) : null}
          {failedItems.length ? (
            <ul className="environment-share-dialog__failures" role="alert">
              {failedItems.map((item, index) => (
                <li key={`${item.code}:${index}`}>第 {index + 1} 个分享码：{item.error}</li>
              ))}
            </ul>
          ) : null}
          {requestError ? <p className="environment-share-dialog__error-text" role="alert">{requestError}</p> : null}
        </div>
        <footer className="environment-build-dialog__actions">
          <Button type="button" color="secondary" variant="ghost" size="sm" disabled={busy} onClick={onClose}>
            取消
          </Button>
          <Button
            type="button"
            color="info"
            size="sm"
            loading={busy}
            disabled={busy || !shareCodes.length || tooMany || (phase === "ready" && !readyToImport)}
            onClick={() => readyToImport ? void importCodes() : void inspectCodes()}
          >
            {primaryLabel}
          </Button>
        </footer>
      </section>
    </div>,
    document.body,
  );
}

function EnvironmentEditor({
  environment,
  cloudProvider,
  onCancel,
  onDelete,
  onShare,
  onSave,
}: {
  environment?: StudioEnvironment;
  cloudProvider: CloudProvider;
  onCancel: () => void;
  onDelete?: () => void;
  onShare?: () => void;
  onSave: (draft: EnvironmentDraft) => Promise<void>;
}) {
  const initialEnvironmentDraft = environmentDraft(environment);
  const hasCustomDockerfile = initialEnvironmentDraft.dockerfile !== undefined;
  const [draft, setDraft] = useState<EnvironmentDraft>(() => ({
    ...initialEnvironmentDraft,
    dockerfile: hasCustomDockerfile ? undefined : initialEnvironmentDraft.dockerfile,
  }));
  const [creationMethod, setCreationMethod] = useState<EnvironmentCreationMethod>(
    initialEnvironmentDraft.gitSource
      ? "git"
      : initialEnvironmentDraft.imageSource
        ? "image"
        : hasCustomDockerfile
          ? "dockerfile"
          : "custom",
  );
  const [activeTab, setActiveTab] = useState<EnvironmentEditorTab>("configuration");
  const [uploadedDockerfile, setUploadedDockerfile] = useState(
    hasCustomDockerfile ? environment?.dockerfile ?? "" : "",
  );
  const [uploadedFileName, setUploadedFileName] = useState(
    hasCustomDockerfile ? "已保存的 Dockerfile" : "",
  );
  const [uploadError, setUploadError] = useState("");
  const [readingFile, setReadingFile] = useState(false);
  const [draggingFile, setDraggingFile] = useState(false);
  const [gitRepositoryUrl, setGitRepositoryUrl] = useState(
    initialEnvironmentDraft.gitSource?.repositoryUrl ?? "",
  );
  const [gitRef, setGitRef] = useState(initialEnvironmentDraft.gitSource?.ref ?? "");
  const [gitDockerfilePath, setGitDockerfilePath] = useState(
    initialEnvironmentDraft.gitSource?.dockerfilePath ?? "",
  );
  const [gitInspection, setGitInspection] = useState<EnvironmentRepositoryInspection | null>(
    initialEnvironmentDraft.gitSource
      ? {
          repositoryUrl: initialEnvironmentDraft.gitSource.repositoryUrl,
          ref: initialEnvironmentDraft.gitSource.ref ?? "",
          commitSha: "",
          dockerfiles: [initialEnvironmentDraft.gitSource.dockerfilePath],
        }
      : null,
  );
  const [gitInspectedKey, setGitInspectedKey] = useState(
    initialEnvironmentDraft.gitSource
      ? `${initialEnvironmentDraft.gitSource.repositoryUrl}\u0000${initialEnvironmentDraft.gitSource.ref ?? ""}`
      : "",
  );
  const [gitRepositoryMode, setGitRepositoryMode] = useState<GitRepositoryMode>(
    initialEnvironmentDraft.containerRepository ? "existing" : "managed",
  );
  const [gitRegion, setGitRegion] = useState<CloudRegion>(
    (initialEnvironmentDraft.containerRepository?.region as CloudRegion | undefined)
      ?? defaultCloudRegion(cloudProvider),
  );
  const [gitContainerRepository, setGitContainerRepository] = useState<EnvironmentContainerRepository | undefined>(
    initialEnvironmentDraft.containerRepository ?? undefined,
  );
  const [imageRegion, setImageRegion] = useState<CloudRegion>(
    (initialEnvironmentDraft.imageSource?.region as CloudRegion | undefined)
      ?? defaultCloudRegion(cloudProvider),
  );
  const [imageRepository, setImageRepository] = useState<EnvironmentContainerRepository | undefined>(
    initialEnvironmentDraft.imageSource
      ? {
          region: initialEnvironmentDraft.imageSource.region,
          registry: initialEnvironmentDraft.imageSource.registry,
          namespace: initialEnvironmentDraft.imageSource.namespace,
          repository: initialEnvironmentDraft.imageSource.repository,
        }
      : undefined,
  );
  const [imageReference, setImageReference] = useState(
    initialEnvironmentDraft.imageSource?.reference ?? "",
  );
  const fileInputRef = useRef<HTMLInputElement>(null);
  const fileReadSequence = useRef(0);
  const generatedDockerfile = useMemo(
    () => buildEnvironmentDockerfile(draft),
    [draft.baseEnvironment, draft.operatingSystem, draft.language, draft.optionIds],
  );
  const customDockerfile = draft.dockerfile ?? generatedDockerfile;
  const isEditing = Boolean(environment);
  const formId = "environment-editor-form";
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const uploadIsValid = Boolean(uploadedDockerfile.trim()) && !uploadError;
  const gitSourceKey = `${gitRepositoryUrl.trim()}\u0000${gitRef.trim()}`;
  const gitIsValid = !repositoryInputError(gitRepositoryUrl)
    && gitInspectedKey === gitSourceKey
    && Boolean(gitDockerfilePath)
    && (gitRepositoryMode === "managed" || repositorySelected(gitContainerRepository));
  const imageIsValid = repositorySelected(imageRepository)
    && Boolean(imageReference.trim())
    && !imageReferenceError(imageReference);
  const canSubmit = Boolean(draft.name.trim())
    && !saving
    && !readingFile
    && (
      creationMethod === "custom"
      || creationMethod === "dockerfile" && uploadIsValid
      || creationMethod === "git" && gitIsValid
      || creationMethod === "image" && imageIsValid
    );

  useEffect(() => () => {
    fileReadSequence.current += 1;
  }, []);

  const toggleOption = (optionId: string, selected: boolean) => {
    setDraft((current) => ({
      ...current,
      optionIds: selected
        ? [...current.optionIds, optionId]
        : current.optionIds.filter((id) => id !== optionId),
    }));
  };

  const loadDockerfile = async (file: File) => {
    const sequence = fileReadSequence.current + 1;
    fileReadSequence.current = sequence;
    setReadingFile(true);
    setUploadError("");
    try {
      const result = await readDockerfileUpload(file);
      if (fileReadSequence.current !== sequence) return;
      setUploadedDockerfile(result.content);
      setUploadedFileName(file.name || "Dockerfile");
      setUploadError(result.error);
    } catch (cause) {
      if (fileReadSequence.current !== sequence) return;
      setUploadedDockerfile("");
      setUploadedFileName(file.name || "Dockerfile");
      setUploadError(`无法读取 Dockerfile：${cause instanceof Error ? cause.message : String(cause)}`);
    } finally {
      if (fileReadSequence.current === sequence) setReadingFile(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDockerfileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) void loadDockerfile(file);
  };

  const handleDockerfileDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDraggingFile(false);
    if (saving || readingFile) return;
    if (event.dataTransfer.files.length !== 1) {
      setUploadError("请一次只上传一个 Dockerfile。");
      return;
    }
    const file = event.dataTransfer.files[0];
    if (file) void loadDockerfile(file);
  };

  const updateUploadedDockerfile = (value: string) => {
    setUploadedDockerfile(value);
    setUploadError(validateDockerfileUpload(value));
  };

  const clearUploadedDockerfile = () => {
    fileReadSequence.current += 1;
    setReadingFile(false);
    setUploadedDockerfile("");
    setUploadedFileName("");
    setUploadError("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setSaveError("");
    try {
      const uploadedBase = environmentBaseFromDockerfile(uploadedDockerfile);
      await onSave({
        ...draft,
        name: draft.name.trim(),
        description: draft.description.trim(),
        optionIds: creationMethod === "custom" ? draft.optionIds : [],
        selectedSkills: creationMethod === "custom" ? draft.selectedSkills : [],
        dockerfile: creationMethod === "dockerfile"
          ? uploadedDockerfile
          : creationMethod === "custom"
            ? customDockerfile
            : "",
        gitSource: creationMethod === "git"
          ? {
              repositoryUrl: gitRepositoryUrl.trim(),
              ...(gitRef.trim() ? { ref: gitRef.trim() } : {}),
              dockerfilePath: gitDockerfilePath,
            }
          : null,
        containerRepository: creationMethod === "git" && gitRepositoryMode === "existing"
          ? gitContainerRepository
          : null,
        imageSource: creationMethod === "image" && imageRepository
          ? { ...imageRepository, reference: imageReference.trim() }
          : null,
        ...(creationMethod === "dockerfile" ? uploadedBase : {}),
      });
    } catch (cause) {
      setSaveError(cause instanceof Error ? cause.message : String(cause));
      setSaving(false);
    }
  };

  const detailTitle = draft.name.trim() || (isEditing ? environment?.name || "配置环境" : "新建环境");

  return (
    <ResourcePageShell className="environment-editor" aria-label={isEditing ? "环境详情" : "新建环境"}>
      <ResourceDetailLayout
        title={detailTitle}
        description="配置运行环境，或接入代码仓库和已有镜像"
        identitySeed={detailTitle}
        backLabel="返回环境列表"
        onBack={onCancel}
        actions={(
          <>
          {onDelete ? (
            <Button type="button" color="danger" variant="ghost" size="sm" onClick={onDelete} disabled={saving}>
              删除
            </Button>
          ) : null}
          {onShare ? (
            <Button color="secondary" variant="soft" size="sm" onClick={onShare} disabled={saving}>
              分享
            </Button>
          ) : null}
          <Button color="secondary" variant="soft" size="sm" onClick={onCancel} disabled={saving}>取消</Button>
          <Button color="info" size="sm" type="submit" form={formId} disabled={!canSubmit}>
            {saving
              ? "正在保存"
              : creationMethod === "image"
                ? isEditing ? "保存环境" : "创建环境"
                : isEditing ? "保存并构建" : "创建并构建"}
          </Button>
          </>
        )}
      >

      <form id={formId} className="environment-form" onSubmit={submit}>
        <div className="environment-fields">
          <label className="environment-field">
            <span>环境名称</span>
            <Input
              className="environment-text-input"
              type="text"
              size="lg"
              value={draft.name}
              maxLength={60}
              placeholder="例如：Python 数据处理"
              onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
            />
          </label>
          <label className="environment-field">
            <span>描述</span>
            <Textarea
              className="environment-description-input"
              size="lg"
              rows={3}
              value={draft.description}
              maxLength={180}
              placeholder="说明这个环境适合处理的任务"
              onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))}
            />
          </label>
        </div>

        <fieldset className="environment-creation-method">
          <legend>创建方式</legend>
          <RadioGroup<EnvironmentCreationMethod>
            className="environment-creation-options"
            value={creationMethod}
            aria-label="环境创建方式"
            onChange={(value) => {
              setCreationMethod(value);
              setSaveError("");
            }}
          >
            <RadioGroup.Item
              value="custom"
              block
              className={creationMethod === "custom" ? "is-selected" : ""}
            >
              <span className="environment-creation-option__icon"><SlidersHorizontal aria-hidden /></span>
              <span className="environment-creation-option__copy">
                <strong>自定义配置</strong>
                <span>选择基础环境、Python、工具和技能</span>
              </span>
            </RadioGroup.Item>
            <RadioGroup.Item
              value="dockerfile"
              block
              className={creationMethod === "dockerfile" ? "is-selected" : ""}
            >
              <span className="environment-creation-option__icon"><FileUp aria-hidden /></span>
              <span className="environment-creation-option__copy">
                <strong>上传 Dockerfile</strong>
                <span>直接使用已有构建描述文件</span>
              </span>
            </RadioGroup.Item>
            <RadioGroup.Item
              value="git"
              block
              className={creationMethod === "git" ? "is-selected" : ""}
            >
              <span className="environment-creation-option__icon"><GitRepositoryIcon /></span>
              <span className="environment-creation-option__copy">
                <strong>从代码仓库构建</strong>
                <span>探查公开仓库并通过 CodePipeline 构建</span>
              </span>
            </RadioGroup.Item>
            <RadioGroup.Item
              value="image"
              block
              className={creationMethod === "image" ? "is-selected" : ""}
            >
              <span className="environment-creation-option__icon"><ContainerImageIcon /></span>
              <span className="environment-creation-option__copy">
                <strong>使用已有镜像</strong>
                <span>绑定由外部流水线交付的 CR 镜像</span>
              </span>
            </RadioGroup.Item>
          </RadioGroup>
        </fieldset>

        {saveError ? <p className="environment-form-error" role="alert">{saveError}</p> : null}

        {creationMethod === "custom" ? (
          <>
            <SegmentedControl
              className="environment-tabs"
              value={activeTab}
              aria-label="自定义环境编辑内容"
              onChange={(value) => setActiveTab(value as EnvironmentEditorTab)}
            >
              <SegmentedControl.Option value="configuration">配置</SegmentedControl.Option>
              <SegmentedControl.Option value="dockerfile">描述文件</SegmentedControl.Option>
            </SegmentedControl>
            {activeTab === "configuration" ? (
              <div className="environment-configuration">
            <section className="environment-section" aria-labelledby="environment-base-title">
              <h2 id="environment-base-title">基础环境</h2>
              <RadioGroup<EnvironmentBaseEnvironment>
                className="environment-base-options"
                aria-label="基础环境"
                value={draft.baseEnvironment}
                onChange={(baseEnvironment) => setDraft((current) => ({
                  ...current,
                  baseEnvironment,
                  operatingSystem: baseEnvironment === "aio-sandbox" ? "ubuntu-22.04" : current.operatingSystem,
                  language: baseEnvironment === "aio-sandbox" ? "python-3.12" : current.language,
                }))}
              >
                {ENVIRONMENT_BASE_ENVIRONMENTS.map((baseEnvironment) => (
                  <RadioGroup.Item
                    key={baseEnvironment.id}
                    value={baseEnvironment.id}
                    block
                    className={draft.baseEnvironment === baseEnvironment.id ? "is-selected" : ""}
                  >
                    <span className="environment-base-copy">
                      <strong>{baseEnvironment.label}</strong>
                      <span>{baseEnvironment.description}</span>
                    </span>
                  </RadioGroup.Item>
                ))}
              </RadioGroup>
              {draft.baseEnvironment === "ubuntu" ? (
                <RadioGroup<EnvironmentOperatingSystem>
                  className="environment-os-version-options"
                  aria-label="Ubuntu 版本"
                  value={draft.operatingSystem}
                  onChange={(operatingSystem) => setDraft((current) => ({ ...current, operatingSystem }))}
                >
                  {ENVIRONMENT_OPERATING_SYSTEMS.map((operatingSystem) => (
                    <RadioGroup.Item
                      key={operatingSystem.id}
                      value={operatingSystem.id}
                      block
                      className={draft.operatingSystem === operatingSystem.id ? "is-selected" : ""}
                    >
                      <span className="environment-language-copy">{operatingSystem.label}</span>
                    </RadioGroup.Item>
                  ))}
                </RadioGroup>
              ) : null}
            </section>

            <section className="environment-section" aria-labelledby="environment-language-title">
              <h2 id="environment-language-title">语言</h2>
              <RadioGroup<EnvironmentLanguage>
                className="environment-language-options"
                aria-label="Python 版本"
                value={draft.language}
                onChange={(language) => setDraft((current) => ({ ...current, language }))}
              >
                {ENVIRONMENT_LANGUAGES
                  .filter((language) => draft.baseEnvironment !== "aio-sandbox" || language.id === "python-3.12")
                  .map((language) => (
                  <RadioGroup.Item
                    key={language.id}
                    value={language.id}
                    block
                    className={draft.language === language.id ? "is-selected" : ""}
                  >
                    <span className="environment-language-copy">{language.label}</span>
                  </RadioGroup.Item>
                ))}
              </RadioGroup>
            </section>

            <section className="environment-section" aria-labelledby="environment-runtime-title">
              <h2 id="environment-runtime-title">执行环境</h2>
              <div className="environment-option-grid">
                <StudioPackageOption
                  name="VeADK"
                  description="Agent 开发与运行框架"
                  selected
                  disabled
                  onChange={() => undefined}
                  icon={<img src={veadkLogo} alt="" />}
                />
              </div>
            </section>

            <section className="environment-section" aria-labelledby="environment-skills-title">
              <h2 id="environment-skills-title">技能</h2>
              <SkillSourcePicker
                selected={draft.selectedSkills}
                onChange={(selectedSkills) => setDraft((current) => ({ ...current, selectedSkills }))}
                cloudProvider={cloudProvider}
                disabled={saving}
                addLabel="添加环境技能"
              />
            </section>

            {ENVIRONMENT_CATEGORIES.map((category) => (
              <section className="environment-section" key={category.id} aria-labelledby={`environment-${category.id}-title`}>
                <h2 id={`environment-${category.id}-title`}>{category.label}</h2>
                <div className="environment-option-grid">
                  {category.options.map((option) => {
                    const selected = draft.optionIds.includes(option.id);
                    return (
                      <StudioPackageOption
                        key={option.id}
                        name={option.label}
                        description={option.description}
                        selected={selected}
                        onChange={(nextSelected) => toggleOption(option.id, nextSelected)}
                        icon={<EnvironmentPackageIcon option={option} />}
                      />
                    );
                  })}
                </div>
              </section>
            ))}
              </div>
            ) : (
              <section className="environment-dockerfile" aria-labelledby="environment-dockerfile-title">
                <div className="environment-dockerfile__header">
                  <div>
                    <h2 id="environment-dockerfile-title">Dockerfile</h2>
                    <p>可直接编辑；配置页中的软件变更不会覆盖自定义内容。</p>
                  </div>
                  {draft.dockerfile !== undefined ? (
                    <Button
                      type="button"
                      color="secondary"
                      variant="ghost"
                      size="sm"
                      onClick={() => setDraft((current) => ({ ...current, dockerfile: undefined }))}
                    >
                      恢复生成内容
                    </Button>
                  ) : null}
                </div>
                <Textarea
                  className="environment-dockerfile__editor"
                  value={customDockerfile}
                  aria-label="Dockerfile 内容"
                  spellCheck={false}
                  onChange={(event) => setDraft((current) => ({ ...current, dockerfile: event.target.value }))}
                />
              </section>
            )}
          </>
        ) : creationMethod === "dockerfile" ? (
          <section className="environment-upload" aria-labelledby="environment-upload-title">
            <div className="environment-upload__header">
              <div>
                <h2 id="environment-upload-title">上传 Dockerfile</h2>
                <p id="environment-upload-help">支持任意文件名，文件上限 128 KiB。上传后可继续编辑内容。</p>
              </div>
              {uploadedDockerfile ? (
                <Button type="button" color="secondary" variant="ghost" size="sm" onClick={clearUploadedDockerfile} disabled={saving}>
                  移除文件
                </Button>
              ) : null}
            </div>
            <div
              className={`environment-upload-dropzone${draggingFile ? " is-dragging" : ""}${uploadedDockerfile ? " is-ready" : ""}`}
              onDragEnter={(event) => {
                event.preventDefault();
                if (!saving && !readingFile) setDraggingFile(true);
              }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDraggingFile(false);
              }}
              onDrop={handleDockerfileDrop}
            >
              <input
                ref={fileInputRef}
                type="file"
                aria-label="Dockerfile 文件"
                aria-describedby="environment-upload-help"
                disabled={saving || readingFile}
                onChange={handleDockerfileChange}
              />
              <span className="environment-upload-dropzone__icon"><FileUp aria-hidden /></span>
              <span className="environment-upload-dropzone__copy">
                <strong>{readingFile ? "正在读取 Dockerfile" : uploadedFileName || "选择 Dockerfile 或拖拽到这里"}</strong>
                <span>
                  {uploadedDockerfile
                    ? `${dockerfileByteSize(uploadedDockerfile).toLocaleString("zh-CN")} 字节，点击可替换`
                    : "Dockerfile 通常无扩展名"}
                </span>
              </span>
            </div>
            {uploadError ? <p className="environment-upload__error" role="alert">{uploadError}</p> : null}
            {uploadedDockerfile ? (
              <div className="environment-upload__preview">
                <div>
                  <h3>内容预览</h3>
                  <span>{dockerfileByteSize(uploadedDockerfile).toLocaleString("zh-CN")} / 131,072 字节</span>
                </div>
                <Textarea
                  className="environment-dockerfile__editor environment-upload__editor"
                  value={uploadedDockerfile}
                  aria-label="上传的 Dockerfile 内容"
                  aria-invalid={Boolean(uploadError)}
                  spellCheck={false}
                  onChange={(event) => updateUploadedDockerfile(event.target.value)}
                />
              </div>
            ) : null}
          </section>
        ) : creationMethod === "git" ? (
          <div className="environment-source-workflow">
            <GitRepositoryFields
              repositoryUrl={gitRepositoryUrl}
              gitRef={gitRef}
              dockerfilePath={gitDockerfilePath}
              inspection={gitInspection}
              inspectedKey={gitInspectedKey}
              disabled={saving}
              onRepositoryUrlChange={setGitRepositoryUrl}
              onGitRefChange={setGitRef}
              onDockerfilePathChange={setGitDockerfilePath}
              onInspectionChange={setGitInspection}
              onInspectedKeyChange={setGitInspectedKey}
            />
            <EnvironmentRepositoryDestination
              cloudProvider={cloudProvider}
              mode={gitRepositoryMode}
              region={gitRegion}
              value={gitContainerRepository}
              disabled={saving}
              onModeChange={(mode) => {
                setGitRepositoryMode(mode);
                setSaveError("");
              }}
              onRegionChange={(region) => {
                setGitRegion(region);
                setGitContainerRepository(undefined);
                setSaveError("");
              }}
              onChange={setGitContainerRepository}
            />
          </div>
        ) : (
          <ExistingImageFields
            cloudProvider={cloudProvider}
            region={imageRegion}
            repository={imageRepository}
            reference={imageReference}
            disabled={saving}
            onRegionChange={(region) => {
              setImageRegion(region);
              setImageRepository(undefined);
              setSaveError("");
            }}
            onRepositoryChange={setImageRepository}
            onReferenceChange={setImageReference}
          />
        )}
      </form>
      </ResourceDetailLayout>
    </ResourcePageShell>
  );
}

export function EnvironmentCenter({
  cloudProvider = "volcengine",
  onWorkspace,
  clipboardImport = null,
  clipboardReadError = "",
}: {
  cloudProvider?: CloudProvider;
  onWorkspace?: () => void;
  clipboardImport?: EnvironmentClipboardImportRequest | null;
  clipboardReadError?: string;
}) {
  const [environments, setEnvironments] = useState<StudioEnvironment[]>([]);
  const [view, setView] = useState<EnvironmentView>({ kind: "list" });
  const [query, setQuery] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<StudioEnvironment | null>(null);
  const [buildDetailsId, setBuildDetailsId] = useState<string | null>(null);
  const [manifestTarget, setManifestTarget] = useState<StudioEnvironment | null>(null);
  const [shareTarget, setShareTarget] = useState<StudioEnvironment | null>(null);
  const [importDialog, setImportDialog] = useState<{
    key: number;
    initialValue: string;
    autoInspect: boolean;
  } | null>(null);
  const importDialogKeyRef = useRef(0);
  const [statusMessage, setStatusMessage] = useState("");
  const [statusError, setStatusError] = useState(false);
  const [clipboardMessage, setClipboardMessage] = useState(clipboardReadError);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [buildingIds, setBuildingIds] = useState<Set<string>>(() => new Set());
  const deferredQuery = useDeferredValue(query);
  const visibleEnvironments = useMemo(() => {
    const normalized = deferredQuery.trim().toLocaleLowerCase();
    if (!normalized) return environments;
    return environments.filter((environment) =>
      (`${environment.name} ${environment.description} ${environmentOperatingSystemLabel(environment.operatingSystem)} ${environmentLanguageLabel(environment.language)}`
        + ` ${environmentBaseEnvironmentLabel(environment.baseEnvironment)}`)
        .toLocaleLowerCase()
        .includes(normalized),
    );
  }, [deferredQuery, environments]);

  const openImportDialog = useCallback((initialValue = "", autoInspect = false) => {
    importDialogKeyRef.current += 1;
    setImportDialog({
      key: importDialogKeyRef.current,
      initialValue,
      autoInspect,
    });
  }, []);

  const openClipboardImport = useCallback((clipboardText: string, allowRepeat = false): boolean => {
    const normalized = clipboardText.trim();
    if (
      !normalized.startsWith("akenv://") ||
      !allowRepeat && promptedClipboardShareTexts.has(normalized)
    ) {
      return false;
    }
    const shareCodes = parseEnvironmentShareCodes(normalized);
    if (!shareCodes.length || shareCodes.length > MAX_ENVIRONMENT_SHARE_CODES) return false;
    promptedClipboardShareTexts.add(normalized);
    setClipboardMessage("");
    openImportDialog(normalized, true);
    return true;
  }, [openImportDialog]);

  const readClipboardForImport = useCallback(async () => {
    if (view.kind !== "list" || importDialog) return;
    if (typeof navigator === "undefined" || !navigator.clipboard?.readText) {
      setClipboardMessage(CLIPBOARD_UNSUPPORTED_ERROR);
      return;
    }
    try {
      const text = await navigator.clipboard.readText();
      const opened = openClipboardImport(text);
      if (!opened && !text.trim() && await clipboardReadPermissionDenied()) {
        setClipboardMessage(CLIPBOARD_READ_ERROR);
      }
    } catch {
      setClipboardMessage(CLIPBOARD_READ_ERROR);
    }
  }, [importDialog, openClipboardImport, view.kind]);

  useEffect(() => {
    const controller = new AbortController();
    if (environments.length === 0) setLoading(true);
    setLoadError("");
    void listEnvironments(controller.signal)
      .then((nextEnvironments) => {
        setEnvironments(nextEnvironments);
      })
      .catch((cause) => {
        if ((cause as Error)?.name !== "AbortError") {
          setLoadError(cause instanceof Error ? cause.message : String(cause));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [reloadKey]);

  useEffect(() => {
    if (!environments.some((item) => item.latestVersion && ACTIVE_BUILD_STATUSES.has(item.latestVersion.status))) {
      return;
    }
    const timer = window.setTimeout(() => setReloadKey((key) => key + 1), 2500);
    return () => window.clearTimeout(timer);
  }, [environments]);

  useEffect(() => {
    if (!statusMessage || statusError) return;
    const timer = window.setTimeout(() => setStatusMessage(""), 2800);
    return () => window.clearTimeout(timer);
  }, [statusError, statusMessage]);

  useEffect(() => {
    if (clipboardReadError) setClipboardMessage(clipboardReadError);
  }, [clipboardReadError]);

  useEffect(() => {
    if (clipboardImport) openClipboardImport(clipboardImport.text);
  }, [clipboardImport, openClipboardImport]);

  useEffect(() => {
    if (view.kind !== "list") return;
    const handleFocus = () => void readClipboardForImport();
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") void readClipboardForImport();
    };
    const handlePaste = (event: ClipboardEvent) => {
      const target = event.target;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLElement && target.isContentEditable
      ) {
        return;
      }
      const text = event.clipboardData?.getData("text/plain") ?? "";
      if (openClipboardImport(text, true)) event.preventDefault();
    };
    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("paste", handlePaste);
    return () => {
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("paste", handlePaste);
    };
  }, [openClipboardImport, readClipboardForImport, view.kind]);

  const editingEnvironment = view.kind === "editor" && view.environmentId
    ? environments.find((environment) => environment.id === view.environmentId)
    : undefined;

  const saveEnvironment = async (draft: EnvironmentDraft) => {
    const input: EnvironmentInput = {
      ...draft,
      dockerfile: draft.dockerfile ?? buildEnvironmentDockerfile(draft),
    };
    const saved = editingEnvironment
      ? await updateEnvironment(editingEnvironment.id, input)
      : await createEnvironment(input);
    setEnvironments((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
    setView({ kind: "list" });
    setStatusError(false);
    if (input.imageSource) {
      setStatusMessage(`环境“${saved.name}”已绑定已有镜像`);
      return;
    }
    try {
      const latestVersion = await buildEnvironment(saved.id);
      setEnvironments((current) => current.map((item) =>
        item.id === saved.id ? { ...item, latestVersion } : item,
      ));
      setStatusMessage(`环境“${saved.name}”已进入构建队列`);
    } catch (cause) {
      setStatusError(true);
      setStatusMessage(
        `环境已保存，但构建未启动：${cause instanceof Error ? cause.message : String(cause)}`,
      );
    }
  };

  const rebuildEnvironment = async (environment: StudioEnvironment) => {
    if (buildingIds.has(environment.id)) return;
    setBuildingIds((current) => new Set(current).add(environment.id));
    setStatusError(false);
    try {
      const latestVersion = await buildEnvironment(environment.id);
      setEnvironments((current) => current.map((item) =>
        item.id === environment.id ? { ...item, latestVersion } : item,
      ));
      setStatusMessage(`环境“${environment.name}”已进入构建队列`);
    } catch (cause) {
      setStatusError(true);
      setStatusMessage(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBuildingIds((current) => {
        const next = new Set(current);
        next.delete(environment.id);
        return next;
      });
    }
  };

  const handleImportedEnvironments = (
    imported: StudioEnvironment[],
    createdCount: number,
    duplicateCount: number,
    failedCount: number,
  ) => {
    if (imported.length) {
      setEnvironments((current) => {
        const importedIds = new Set(imported.map((item) => item.id));
        return [...imported, ...current.filter((item) => !importedIds.has(item.id))];
      });
    }
    setStatusError(failedCount > 0);
    setStatusMessage(
      failedCount > 0
        ? `已导入 ${createdCount} 个环境，${failedCount} 个失败`
        : duplicateCount > 0
          ? `已导入 ${createdCount} 个环境，${duplicateCount} 个分享码已存在`
          : `已导入 ${createdCount} 个环境`,
    );
  };

  const deleteDialog = deleteTarget ? (
    <StudioConfirmDialog
      title="删除环境"
      description={`确定删除环境“${deleteTarget.name}”吗？删除后无法恢复。`}
      confirmLabel="删除"
      variant="danger"
      onCancel={() => setDeleteTarget(null)}
      onConfirm={() => {
        const target = deleteTarget;
        setDeleteTarget(null);
        setView({ kind: "list" });
        void deleteEnvironment(target.id)
          .then(() => {
            setEnvironments((current) => current.filter((environment) => environment.id !== target.id));
            setStatusError(false);
            setStatusMessage(`已删除环境“${target.name}”`);
          })
          .catch((cause) => {
            setStatusError(true);
            setStatusMessage(cause instanceof Error ? cause.message : String(cause));
          });
      }}
    />
  ) : null;

  if (view.kind === "editor") {
    return (
      <>
        <EnvironmentEditor
          key={view.environmentId ?? "new"}
          environment={editingEnvironment}
          cloudProvider={cloudProvider}
          onCancel={() => setView({ kind: "list" })}
          onDelete={editingEnvironment ? () => setDeleteTarget(editingEnvironment) : undefined}
          onShare={editingEnvironment ? () => setShareTarget(editingEnvironment) : undefined}
          onSave={saveEnvironment}
        />
        {shareTarget ? (
          <EnvironmentShareDialog
            environment={shareTarget}
            onClose={() => setShareTarget(null)}
          />
        ) : null}
        {deleteDialog}
      </>
    );
  }

  return (
    <ResourcePageShell className="environment-center" aria-label="环境">
      <ResourcePageHeader
        title="环境"
      />

      <ResourceToolbar className="environment-toolbar">
        {onWorkspace ? (
          <ResourceTabs
            items={[
              { id: "workspaces", label: "工作区" },
              { id: "environments", label: "环境" },
            ]}
            value="environments"
            onChange={(value) => {
              if (value === "workspaces") onWorkspace();
            }}
            ariaLabel="工作区资源类型"
            idPrefix="environment-center"
          />
        ) : null}
        <div className="resource-toolbar__actions">
          {statusMessage ? (
            <span className={`environment-status${statusError ? " is-error" : ""}`} role={statusError ? "alert" : "status"} aria-live="polite">
              {statusMessage}
            </span>
          ) : null}
          <ResourceSearch
            aria-label="搜索环境"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索环境"
          />
        </div>
      </ResourceToolbar>

      {clipboardMessage ? (
        <div className="environment-clipboard-notice" role="alert">
          <span>{clipboardMessage}</span>
          <Button
            type="button"
            color="secondary"
            variant="soft"
            size="sm"
            onClick={() => {
              setClipboardMessage("");
              openImportDialog();
            }}
          >
            手动导入
          </Button>
        </div>
      ) : null}

      <ResourceResults aria-live="polite">
        {loading ? (
          <ResourceLoadingState />
        ) : loadError ? (
          <div className="environment-load-error" role="alert">
            <p>{loadError}</p>
            <Button color="secondary" variant="soft" size="sm" onClick={() => setReloadKey((key) => key + 1)}>
              重新加载
            </Button>
          </div>
        ) : visibleEnvironments.length === 0 && query.trim() ? (
          <div className="environment-empty">
            <EmptyMessage fill="none">
              <EmptyMessage.Icon><EnvironmentEmptyIcon /></EmptyMessage.Icon>
              <EmptyMessage.Title>没有匹配的环境</EmptyMessage.Title>
              <EmptyMessage.Description>请尝试搜索其他名称</EmptyMessage.Description>
            </EmptyMessage>
          </div>
        ) : (
          <ResourceGrid>
            {!query.trim() ? (
              <>
                <ResourceCreateCard
                  aria-label="新建环境"
                  icon={<AddIcon />}
                  onClick={() => setView({ kind: "editor", environmentId: null })}
                >
                  新建环境
                </ResourceCreateCard>
                <ResourceCreateCard
                  aria-label="导入环境"
                  icon={<ImportEnvironmentIcon />}
                  onClick={() => openImportDialog()}
                >
                  导入环境
                </ResourceCreateCard>
              </>
            ) : null}
            {visibleEnvironments.map((environment) => {
              const status = environmentStatus(environment);
              const buildActive = Boolean(
                environment.latestVersion && ACTIVE_BUILD_STATUSES.has(environment.latestVersion.status),
              );
              const rebuilding = buildingIds.has(environment.id);
              return (
                <LibraryResourceCard
                  key={environment.id}
                  className="environment-card"
                  title={environment.name}
                  status={<Badge color={status.color} size="sm">{status.label}</Badge>}
                  description={
                    environment.latestVersion?.error ||
                    (buildActive ? environment.latestVersion?.currentStep : "") ||
                    environment.description ||
                    "暂无描述"
                  }
                  metadata={[
                    { label: "更新", value: environmentUpdatedAt(environment.updatedAt) },
                  ]}
                  action={{
                    label: environment.latestVersion ? "构建详情" : rebuilding ? "正在启动" : "开始构建",
                    icon: "play",
                    title: "构建",
                    disabled: rebuilding,
                    onClick: () => environment.latestVersion
                      ? setBuildDetailsId(environment.id)
                      : void rebuildEnvironment(environment),
                  }}
                  auxiliaryAction={{
                    label: "查看环境 Manifest",
                    icon: <FileCode />,
                    title: environment.latestVersion ? "查看 Manifest" : "尚无可用 Manifest",
                    disabled: !environment.latestVersion,
                    onClick: () => setManifestTarget(environment),
                  }}
                  detailAction={{ label: "配置", onClick: () => setView({ kind: "editor", environmentId: environment.id }) }}
                />
              );
            })}
          </ResourceGrid>
        )}
      </ResourceResults>

      {buildDetailsId ? (() => {
        const environment = environments.find((item) => item.id === buildDetailsId);
        if (!environment) return null;
        return (
          <EnvironmentBuildDetailsDialog
            environment={environment}
            onClose={() => setBuildDetailsId(null)}
            onBuildUpdate={(latestVersion) => {
              setEnvironments((current) => current.map((item) =>
                item.id === environment.id ? { ...item, latestVersion } : item,
              ));
            }}
            onRebuild={() => rebuildEnvironment(environment)}
          />
        );
      })() : null}

      {manifestTarget?.latestVersion ? (
        <EnvironmentManifestDialog
          environment={manifestTarget}
          onClose={() => setManifestTarget(null)}
        />
      ) : null}

      {deleteDialog}

      {importDialog ? (
        <EnvironmentImportDialog
          key={importDialog.key}
          initialValue={importDialog.initialValue}
          autoInspect={importDialog.autoInspect}
          onClose={() => setImportDialog(null)}
          onImported={handleImportedEnvironments}
        />
      ) : null}
    </ResourcePageShell>
  );
}
