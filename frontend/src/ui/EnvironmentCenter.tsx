import {
  useDeferredValue,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type FormEvent,
  type SVGProps,
} from "react";
import { createPortal } from "react-dom";
import { ExternalLink, FileUp, SlidersHorizontal, X } from "lucide-react";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { EmptyMessage } from "@openai/apps-sdk-ui/components/EmptyMessage";
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
  ResourceGrid,
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
  getEnvironmentBuild,
  getEnvironmentManifest,
  listEnvironments,
  listWorkspaces,
  updateEnvironment,
  type EnvironmentBuildStatus,
  type EnvironmentBuildVersion,
  type EnvironmentManifest,
  type EnvironmentInput,
  type StudioEnvironment,
  type StudioWorkspace,
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
import type { CloudProvider } from "../adk/cloudProvider";
import "./EnvironmentCenter.css";

type EnvironmentView =
  | { kind: "list" }
  | { kind: "editor"; environmentId: string | null };

type EnvironmentEditorTab = "configuration" | "dockerfile";
type EnvironmentCreationMethod = "custom" | "dockerfile";

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

function BackIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="m14.5 6-6 6 6 6" />
    </svg>
  );
}

function AddIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true" {...props}>
      <path d="M8 3.25v9.5M3.25 8h9.5" />
    </svg>
  );
}

function EnvironmentEmptyIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M5.5 10.5 16 5l10.5 5.5L16 16 5.5 10.5Z" />
      <path d="M5.5 16 16 21.5 26.5 16M5.5 21.5 16 27l10.5-5.5" />
    </svg>
  );
}

function ManifestIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M7 3.75h7l3 3V20.25H7z" />
      <path d="M14 3.75v3h3M9.75 11h4.5M9.75 14.5h4.5" />
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
  const cpUrl = build?.resources?.codePipeline?.consoleUrl;

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
          <div><span>已用时</span><strong>{build ? buildElapsed(build, now) : "—"}</strong></div>
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
          {build && !ACTIVE_BUILD_STATUSES.has(build.status) ? (
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

function EnvironmentEditor({
  environment,
  cloudProvider,
  onCancel,
  onSave,
}: {
  environment?: StudioEnvironment;
  cloudProvider: CloudProvider;
  onCancel: () => void;
  onSave: (draft: EnvironmentDraft) => Promise<void>;
}) {
  const initialEnvironmentDraft = environmentDraft(environment);
  const hasCustomDockerfile = initialEnvironmentDraft.dockerfile !== undefined;
  const [draft, setDraft] = useState<EnvironmentDraft>(() => ({
    ...initialEnvironmentDraft,
    dockerfile: hasCustomDockerfile ? undefined : initialEnvironmentDraft.dockerfile,
  }));
  const [creationMethod, setCreationMethod] = useState<EnvironmentCreationMethod>(
    hasCustomDockerfile ? "dockerfile" : "custom",
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
  const canSubmit = Boolean(draft.name.trim())
    && !saving
    && !readingFile
    && (creationMethod === "custom" || uploadIsValid);

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
        optionIds: creationMethod === "dockerfile" ? [] : draft.optionIds,
        selectedSkills: creationMethod === "dockerfile" ? [] : draft.selectedSkills,
        dockerfile: creationMethod === "dockerfile" ? uploadedDockerfile : customDockerfile,
        ...(creationMethod === "dockerfile" ? uploadedBase : {}),
      });
    } catch (cause) {
      setSaveError(cause instanceof Error ? cause.message : String(cause));
      setSaving(false);
    }
  };

  return (
    <section className="environment-editor" aria-labelledby="environment-editor-title">
      <header className="environment-editor__header">
        <div className="environment-editor__heading">
          <button type="button" className="environment-back" onClick={onCancel} aria-label="返回环境列表">
            <BackIcon />
          </button>
          <div>
            <h1 id="environment-editor-title">{isEditing ? "配置环境" : "新建环境"}</h1>
            <p>上传 Dockerfile，或通过可视化配置生成运行环境</p>
          </div>
        </div>
        <div className="environment-editor__actions">
          <Button color="secondary" variant="soft" size="sm" onClick={onCancel} disabled={saving}>取消</Button>
          <Button color="info" size="sm" type="submit" form={formId} disabled={!canSubmit}>
            {saving ? "正在保存" : isEditing ? "保存并构建" : "创建并构建"}
          </Button>
        </div>
      </header>

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
        ) : (
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
        )}
      </form>
    </section>
  );
}

export function EnvironmentCenter({
  cloudProvider = "volcengine",
  onWorkspace,
}: {
  cloudProvider?: CloudProvider;
  onWorkspace?: () => void;
}) {
  const [environments, setEnvironments] = useState<StudioEnvironment[]>([]);
  const [workspaces, setWorkspaces] = useState<StudioWorkspace[]>([]);
  const [view, setView] = useState<EnvironmentView>({ kind: "list" });
  const [query, setQuery] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<StudioEnvironment | null>(null);
  const [buildDetailsId, setBuildDetailsId] = useState<string | null>(null);
  const [manifestTarget, setManifestTarget] = useState<StudioEnvironment | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [statusError, setStatusError] = useState(false);
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

  useEffect(() => {
    const controller = new AbortController();
    if (environments.length === 0) setLoading(true);
    setLoadError("");
    void Promise.all([listEnvironments(controller.signal), listWorkspaces(controller.signal)])
      .then(([nextEnvironments, nextWorkspaces]) => {
        setEnvironments(nextEnvironments);
        setWorkspaces(nextWorkspaces);
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

  if (view.kind === "editor") {
    return (
      <EnvironmentEditor
        key={view.environmentId ?? "new"}
        environment={editingEnvironment}
        cloudProvider={cloudProvider}
        onCancel={() => setView({ kind: "list" })}
        onSave={saveEnvironment}
      />
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

      <ResourceResults aria-live="polite">
        {loading ? (
          <div className="environment-loading" role="status" aria-live="polite">
            <TextShimmer as="span">正在加载环境</TextShimmer>
          </div>
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
              <ResourceCreateCard
                aria-label="新建环境"
                icon={<AddIcon />}
                onClick={() => setView({ kind: "editor", environmentId: null })}
              >
                新建环境
              </ResourceCreateCard>
            ) : null}
            {visibleEnvironments.map((environment) => {
              const referenceCount = workspaces.filter((workspace) => workspace.environmentIds.includes(environment.id)).length;
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
                    {
                      label: "基础环境",
                      value: environment.baseEnvironment === "aio-sandbox"
                        ? "AIO Sandbox"
                        : environmentOperatingSystemLabel(environment.operatingSystem),
                    },
                    { label: "语言", value: environmentLanguageLabel(environment.language) },
                    { label: "工作区", value: `${referenceCount} 个工作区` },
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
                    icon: <ManifestIcon />,
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

      {deleteTarget ? (
        <StudioConfirmDialog
          title="删除环境"
          description={`确定删除环境“${deleteTarget.name}”吗？删除后无法恢复。`}
          confirmLabel="删除"
          variant="danger"
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => {
            const target = deleteTarget;
            setDeleteTarget(null);
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
      ) : null}
    </ResourcePageShell>
  );
}
