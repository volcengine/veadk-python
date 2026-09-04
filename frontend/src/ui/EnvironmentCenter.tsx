import {
  useCallback,
  useDeferredValue,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type RefObject,
  type SVGProps,
} from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import { createPortal } from "react-dom";
import { ExternalLink, X } from "lucide-react";
import { Badge } from "@openai/apps-sdk-ui/components/Badge";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { EmptyMessage } from "@openai/apps-sdk-ui/components/EmptyMessage";
import { ArrowRotateCw, FileCode } from "@openai/apps-sdk-ui/components/Icon";
import { Input } from "@openai/apps-sdk-ui/components/Input";
import { Select, type Option } from "@openai/apps-sdk-ui/components/Select";
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
import { formatRelativeTimeLabel } from "./relativeTime";
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
  AIO_BASE_IMAGE,
  CODEX_SANDBOX_BASE_IMAGES,
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
  composeDockerfile,
  dockerfileBaseImage,
  dockerfileBody,
  dockerfileByteSize,
  readDockerfileUpload,
  validateDockerfileBody,
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

type EnvironmentCreationMethod = "custom" | "dockerfile" | "git" | "image";
type GitRepositoryMode = "managed" | "existing";
type DockerfilePresetEnvironment = "none" | "aio-sandbox" | "codex-sandbox";

function environmentCreationOptions(t: TFunction): Option[] {
  return [
    { value: "custom", label: t("environmentCenter.creation.custom.label"), description: t("environmentCenter.creation.custom.description") },
    { value: "dockerfile", label: t("environmentCenter.creation.dockerfile.label"), description: t("environmentCenter.creation.dockerfile.description") },
    { value: "git", label: t("environmentCenter.creation.git.label"), description: t("environmentCenter.creation.git.description") },
    { value: "image", label: t("environmentCenter.creation.image.label"), description: t("environmentCenter.creation.image.description") },
  ];
}

const ENVIRONMENT_BASE_OPTIONS: Option[] = ENVIRONMENT_BASE_ENVIRONMENTS.map((item) => ({
  value: item.id,
  label: item.label,
  description: item.description,
}));

function dockerfilePresetEnvironmentOptions(t: TFunction): Option[] {
  return [
    { value: "none", label: t("common.none"), description: t("environmentCenter.presets.none") },
    { value: "aio-sandbox", label: "AIO Sandbox", description: t("environmentCenter.presets.aio") },
    { value: "codex-sandbox", label: "Codex Sandbox", description: t("environmentCenter.presets.codex") },
  ];
}

function dockerfilePresetEnvironmentFromContent(content: string): DockerfilePresetEnvironment {
  const baseImage = dockerfileBaseImage(content, "");
  if (baseImage === AIO_BASE_IMAGE) return "aio-sandbox";
  if (baseImage.includes("/codexenv:")) return "codex-sandbox";
  return "none";
}

const ENVIRONMENT_OS_OPTIONS: Option[] = ENVIRONMENT_OPERATING_SYSTEMS.map((item) => ({
  value: item.id,
  label: item.label,
}));

const ENVIRONMENT_LANGUAGE_OPTIONS: Option[] = ENVIRONMENT_LANGUAGES.map((item) => ({
  value: item.id,
  label: item.label,
}));

function environmentRepositoryModeOptions(t: TFunction): Option[] {
  return [
    { value: "managed", label: t("environmentCenter.repository.managed") },
    { value: "existing", label: t("environmentCenter.repository.existing") },
  ];
}

const MAX_ENVIRONMENT_SHARE_CODES = 20;
const promptedClipboardShareTexts = new Set<string>();

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

function RequiredMark() {
  return <span className="environment-required-mark" aria-hidden="true">*</span>;
}

function ImportEnvironmentIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M12 3v11m0 0 4-4m-4 4-4-4" />
      <path d="M5 16v2.5A2.5 2.5 0 0 0 7.5 21h9a2.5 2.5 0 0 0 2.5-2.5V16" />
    </svg>
  );
}

function repositoryInputError(repositoryUrl: string, t: TFunction): string {
  const trimmed = repositoryUrl.trim();
  if (!trimmed) return t("environmentCenter.errors.repositoryRequired");
  try {
    const url = new URL(trimmed);
    if (url.protocol !== "https:" || !url.hostname) {
      return t("environmentCenter.errors.repositoryHttps");
    }
  } catch {
    return t("environmentCenter.errors.repositoryInvalid");
  }
  return "";
}

function repositorySelected(value: EnvironmentContainerRepository | undefined): boolean {
  return Boolean(
    value?.region && value.registry && value.namespace && value.repository,
  );
}

function imageReferenceError(reference: string, t: TFunction): string {
  const value = reference.trim();
  if (!value) return "";
  if (/\s/.test(value)) return t("environmentCenter.errors.imageReferenceWhitespace");
  if (value.startsWith("sha256:")) {
    return /^sha256:[0-9a-fA-F]{64}$/.test(value)
      ? ""
      : t("environmentCenter.errors.imageDigestInvalid");
  }
  if (/[@/]/.test(value)) return t("environmentCenter.errors.imageTagOnly");
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

function environmentDraft(
  environment: StudioEnvironment | undefined,
  cloudProvider: CloudProvider,
): EnvironmentDraft {
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
      environment.dockerfile === buildEnvironmentDockerfile(environment, cloudProvider)
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

const BUILD_STATUS_KEYS: Record<EnvironmentBuildStatus, string> = {
  preparing: "environmentCenter.buildStatus.preparing",
  queued: "environmentCenter.buildStatus.queued",
  building: "environmentCenter.buildStatus.building",
  scanning: "environmentCenter.buildStatus.scanning",
  available: "environmentCenter.buildStatus.available",
  failed: "environmentCenter.buildStatus.failed",
};

function environmentStatus(environment: StudioEnvironment, t: TFunction): {
  label: string;
  color: "secondary" | "success" | "warning" | "danger";
} {
  const status = environment.latestVersion?.status;
  if (!status) return { label: t("environmentCenter.buildStatus.notBuilt"), color: "secondary" };
  if (status === "available") return { label: t(BUILD_STATUS_KEYS[status]), color: "success" };
  if (status === "failed") return { label: t(BUILD_STATUS_KEYS[status]), color: "danger" };
  return { label: t(BUILD_STATUS_KEYS[status]), color: "warning" };
}

function environmentUpdatedAt(value: string, locale: string): string {
  return formatRelativeTimeLabel(value, Date.now(), locale);
}

function environmentUpdatedAtTitle(value: string, locale: string): string {
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return value;
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(timestamp);
}

function buildElapsed(build: EnvironmentBuildVersion, t: TFunction, now = Date.now()): string {
  const start = Date.parse(build.createdAt);
  const active = ACTIVE_BUILD_STATUSES.has(build.status);
  const end = active ? now : Date.parse(build.updatedAt);
  if (Number.isNaN(start) || Number.isNaN(end)) return "";
  const seconds = Math.max(0, Math.floor((end - start) / 1000));
  if (seconds < 60) return t("environmentCenter.duration.seconds", { count: seconds });
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  if (minutes < 60) return t("environmentCenter.duration.minutesSeconds", { minutes, seconds: remainder });
  return t("environmentCenter.duration.hoursMinutes", { hours: Math.floor(minutes / 60), minutes: minutes % 60 });
}

function EnvironmentManifestDialog({
  environment,
  onClose,
}: {
  environment: StudioEnvironment;
  onClose: () => void;
}) {
  const { t } = useTranslation("ui");
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
              <h2 id={titleId}>{t("environmentCenter.manifest.title")}</h2>
            </div>
            <p>{environment.name} / {versionId}</p>
          </div>
          <Button type="button" color="secondary" variant="ghost" size="sm" uniform onClick={onClose} aria-label={t("environmentCenter.manifest.closeLabel")}>
            <X aria-hidden />
          </Button>
        </header>

        <div className="environment-manifest-dialog__body">
          {loading ? (
            <div className="environment-manifest-dialog__state" role="status">
              <TextShimmer as="span">{t("environmentCenter.manifest.loading")}</TextShimmer>
            </div>
          ) : error ? (
            <div className="environment-manifest-dialog__state is-error" role="alert">
              <p>{error}</p>
              <Button type="button" color="secondary" variant="soft" size="sm" onClick={() => setReloadKey((key) => key + 1)}>
                {t("common.reload")}
              </Button>
            </div>
          ) : (
            <div className="environment-manifest-dialog__editor" aria-label={t("environmentCenter.manifest.editorLabel")}>
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
            <span className="environment-manifest-dialog__copy-error" role="alert">{t("environmentCenter.manifest.copyFailed")}</span>
          ) : null}
          <Button type="button" color="secondary" variant="ghost" size="sm" onClick={onClose}>{t("common.close")}</Button>
          <Button type="button" color="info" size="sm" disabled={!manifestYaml} onClick={() => void copyManifest()}>
            {copyState === "copied" ? t("environmentCenter.manifest.copied") : t("environmentCenter.manifest.copy")}
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
  const { t } = useTranslation("ui");
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
    ? environmentStatus({ ...environment, latestVersion: build }, t)
    : { label: t("environmentCenter.buildStatus.notBuilt"), color: "secondary" as const };
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
              <h2 id={titleId}>{t("environmentCenter.buildDetails.title")}</h2>
              <Badge color={status.color} size="sm">{status.label}</Badge>
            </div>
            <p>{environment.name}</p>
          </div>
          <Button type="button" color="secondary" variant="ghost" size="sm" uniform onClick={onClose} aria-label={t("environmentCenter.buildDetails.closeLabel")}>
            <X aria-hidden />
          </Button>
        </header>

        <div className="environment-build-dialog__summary">
          <div><span>{t("environmentCenter.buildDetails.currentStep")}</span><strong>{build?.currentStep || t("environmentCenter.buildDetails.waiting")}</strong></div>
          <div><span>{t("environmentCenter.buildDetails.elapsed")}</span><strong>{build ? buildElapsed(build, t, now) : "-"}</strong></div>
          {build?.sourceCommitSha ? (
            <div>
              <span>{t("environmentCenter.buildDetails.sourceCommit")}</span>
              <strong title={build.sourceCommitSha}>{build.sourceCommitSha.slice(0, 12)}</strong>
            </div>
          ) : null}
          {cpUrl ? (
            <a href={cpUrl} target="_blank" rel="noreferrer">
              {t("environmentCenter.buildDetails.openCodePipeline")} <ExternalLink aria-hidden />
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
          <Button type="button" color="secondary" variant="ghost" size="sm" onClick={onClose}>{t("common.close")}</Button>
          {build && !environment.imageSource && !ACTIVE_BUILD_STATUSES.has(build.status) ? (
            <Button type="button" color="info" size="sm" disabled={rebuilding} onClick={() => {
              setRebuilding(true);
              void onRebuild().then(onClose).finally(() => setRebuilding(false));
            }}>
              {rebuilding ? t("environmentCenter.buildDetails.starting") : t("environmentCenter.buildDetails.rebuild")}
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
  const { t } = useTranslation("ui");
  const options: Option[] = cloudRegionOptions(cloudProvider).map((option) => ({
    value: option.value,
    label: option.label,
  }));
  return (
    <label className="environment-field environment-region-field">
      <span>{t("environmentCenter.region")}<RequiredMark /></span>
      <Select
        id="environment-region"
        value={value}
        options={options}
        optionClassName="environment-select-option"
        required
        size="lg"
        block
        pill={false}
        disabled={disabled}
        triggerClassName="environment-select-trigger"
        onChange={(option) => onChange(option.value as CloudRegion)}
      />
    </label>
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
  const { t } = useTranslation("ui");
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
    const inputError = repositoryInputError(repositoryUrl, t);
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
    t,
  ]);

  useEffect(() => {
    if (
      disabled
      || inspectionIsCurrent
      || autoAttemptedKeyRef.current === currentKey
      || repositoryInputError(repositoryUrl, t)
    ) {
      return;
    }
    const timer = window.setTimeout(() => void inspectRepository(), 600);
    return () => window.clearTimeout(timer);
  }, [currentKey, disabled, inspectRepository, inspectionIsCurrent, repositoryUrl, t]);

  const dockerfiles = inspectionIsCurrent ? inspection?.dockerfiles ?? [] : [];
  return (
    <section className="environment-source-section" aria-label={t("environmentCenter.git.sectionLabel")}>
      <div className="environment-form-grid environment-git-fields">
        <label className="environment-field">
          <span>{t("environmentCenter.git.address")}<RequiredMark /></span>
          <Input
            size="lg"
            type="url"
            required
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
        <label className="environment-field">
          <span>{t("environmentCenter.git.ref")}</span>
          <Input
            size="lg"
            value={gitRef}
            placeholder={t("environmentCenter.git.defaultBranch")}
            autoComplete="off"
            disabled={disabled}
            onChange={(event) => {
              resetInspection();
              onGitRefChange(event.currentTarget.value);
            }}
          />
        </label>
      </div>
      <div className="environment-inspection-status environment-form-feedback" aria-live="polite">
        {inspecting ? <TextShimmer as="span">{t("environmentCenter.git.inspecting")}</TextShimmer> : null}
        {inspectError ? (
          <div className="environment-source-error" role="alert">
            <span>{inspectError}</span>
            <Button type="button" color="primary" size="sm" pill={false} disabled={disabled} onClick={() => void inspectRepository()}>
              <ArrowRotateCw />
              {t("common.retry")}
            </Button>
          </div>
        ) : null}
        {!inspecting && !inspectError && inspectionIsCurrent && inspection ? (
          dockerfiles.length > 0 ? (
            <span>
              {inspection.commitSha
                ? t("environmentCenter.git.foundDockerfiles", { commit: inspection.commitSha.slice(0, 12), count: dockerfiles.length })
                : t("environmentCenter.git.savedDockerfileLoaded")}
            </span>
          ) : (
            <div className="environment-source-error" role="alert">
              <span>{t("environmentCenter.git.noDockerfile")}</span>
              <button type="button" disabled={disabled} onClick={() => void inspectRepository()}>{t("environmentCenter.git.inspectAgain")}</button>
            </div>
          )
        ) : null}
      </div>
      {dockerfiles.length > 0 ? (
        <label className="environment-field environment-dockerfile-picker">
          <span>Dockerfile<RequiredMark /></span>
          <DeploymentSelect
            ariaLabel={t("environmentCenter.git.selectDockerfile")}
            value={dockerfilePath}
            valueLabel={dockerfilePath}
            placeholder={t("environmentCenter.git.selectDockerfile")}
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
  const { t } = useTranslation("ui");
  return (
    <section className="environment-source-section" aria-label={t("environmentCenter.repository.outputSection")}>
      <div className="environment-form-grid">
        <label className="environment-field">
          <span>{t("environmentCenter.repository.type")}<RequiredMark /></span>
          <Select
            id="environment-repository-mode"
            value={mode}
            options={environmentRepositoryModeOptions(t)}
            optionClassName="environment-select-option"
            required
            size="lg"
            block
            pill={false}
            disabled={disabled}
            triggerClassName="environment-select-trigger"
            onChange={(option) => onModeChange(option.value as GitRepositoryMode)}
          />
        </label>
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
          <p className="environment-source-note environment-form-feedback">{t("environmentCenter.repository.managedHint")}</p>
        )}
      </div>
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
  const { t } = useTranslation("ui");
  const referenceError = imageReferenceError(reference, t);
  return (
    <section className="environment-source-section" aria-label={t("environmentCenter.existingImage.sectionLabel")}>
      <div className="environment-form-grid">
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
        <label className="environment-field environment-image-reference">
          <span>{t("environmentCenter.existingImage.reference")}<RequiredMark /></span>
          <Input
            size="lg"
            value={reference}
            required
            placeholder={t("environmentCenter.existingImage.placeholder")}
            autoComplete="off"
            disabled={disabled}
            aria-invalid={Boolean(referenceError)}
            onChange={(event) => onReferenceChange(event.currentTarget.value)}
          />
          {referenceError ? (
            <small className="environment-source-field__error" role="alert">{referenceError}</small>
          ) : (
            <small>{t("environmentCenter.existingImage.hint")}</small>
          )}
        </label>
      </div>
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
  const { t } = useTranslation("ui");
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
            <h2 id={titleId}>{t("environmentCenter.share.title")}</h2>
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
            aria-label={t("environmentCenter.share.closeLabel")}
          >
            <X aria-hidden />
          </Button>
        </header>
        <div className="environment-share-dialog__body">
          {state === "loading" ? (
            <TextShimmer as="p">{t("environmentCenter.share.generating")}</TextShimmer>
          ) : (
            <div className="environment-share-dialog__result">
              {state === "copied" ? (
                <p className="environment-share-dialog__success" role="status" aria-live="polite">
                  {t("environmentCenter.share.copied")}
                </p>
              ) : (
                <div className="environment-share-dialog__error" role="alert">
                  <strong>{t("environmentCenter.share.failed")}</strong>
                  <span>{error}</span>
                </div>
              )}
              {shareCode ? (
                <label className="environment-share-dialog__field environment-share-dialog__manual-code">
                  <span>{t("environmentCenter.share.code")}</span>
                  <Textarea
                    size="lg"
                    rows={4}
                    value={shareCode}
                    readOnly
                    aria-label={t("environmentCenter.share.fullCode")}
                    onFocus={(event) => event.currentTarget.select()}
                    onClick={(event) => event.currentTarget.select()}
                  />
                  <small>
                    {state === "copied"
                      ? t("environmentCenter.share.copiedHint")
                      : t("environmentCenter.share.copyFailedHint")}
                  </small>
                </label>
              ) : null}
              <p className="environment-share-dialog__safety">
                {t("environmentCenter.share.safety")}
              </p>
            </div>
          )}
        </div>
        <footer className="environment-build-dialog__actions">
          <Button type="button" color="secondary" variant="ghost" size="sm" disabled={busy} onClick={onClose}>
            {t("common.close")}
          </Button>
          {state === "error" ? (
            <Button type="button" color="info" size="sm" onClick={() => void copyShareCode(shareCode)}>
              {t("common.retry")}
            </Button>
          ) : state === "copied" ? (
            <Button type="button" color="info" size="sm" onClick={() => void copyShareCode(shareCode)}>
              {t("environmentCenter.share.copyAgain")}
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
  const { t } = useTranslation("ui");
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
          ? [{ code, name, status: "valid" as const, error: item?.error || t("environmentCenter.import.noResult") }]
          : [];
      });
      const invalid = invalidInspections.flatMap((item) => {
        const code = shareCodes[item.index];
        return code
          ? [{ code, name: "", status: "invalid" as const, error: item.error || t("environmentCenter.import.invalidCode") }]
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
      setRequestError(t("environmentCenter.import.partial", { created: createdCount, remaining: retained.length }));
      setPhase("ready");
    } catch (cause) {
      setRequestError(cause instanceof Error ? cause.message : String(cause));
      setPhase("ready");
    }
  };

  const primaryLabel = phase === "inspecting"
    ? t("environmentCenter.import.inspecting")
    : phase === "importing"
      ? t("environmentCenter.import.importing")
      : readyToImport
        ? failedItems.length ? t("environmentCenter.import.retryImport") : t("environmentCenter.import.confirm")
        : t("environmentCenter.import.inspectCodes");

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
            <h2 id={titleId}>{t("environmentCenter.import.title")}</h2>
            <p id={descriptionId}>{t("environmentCenter.import.description")}</p>
          </div>
          <Button
            type="button"
            color="secondary"
            variant="ghost"
            size="sm"
            uniform
            disabled={busy}
            onClick={onClose}
            aria-label={t("environmentCenter.import.closeLabel")}
          >
            <X aria-hidden />
          </Button>
        </header>
        <div className="environment-share-dialog__body">
          <label className="environment-share-dialog__field">
            <span>{t("environmentCenter.import.code")}</span>
            <Textarea
              ref={textareaRef}
              size="lg"
              rows={6}
              value={value}
              disabled={busy}
              aria-invalid={tooMany || invalidInspections.length > 0 || undefined}
              aria-describedby={helpId}
              placeholder="akenv://v1/..."
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
              ? t("environmentCenter.import.tooMany", { max: MAX_ENVIRONMENT_SHARE_CODES, count: shareCodes.length })
              : t("environmentCenter.import.multipleHint")}
          </p>
          <p className="environment-share-dialog__safety">
            {t("environmentCenter.import.safety")}
          </p>
          {phase === "inspecting" ? (
            <TextShimmer as="p">{t("environmentCenter.import.inspectingCodes")}</TextShimmer>
          ) : validInspections.length ? (
            <p className="environment-share-dialog__summary" role="status" aria-live="polite">
              {t("environmentCenter.import.found", {
                count: validInspections.length,
                names: validInspections.map((item) => item.name || t("environmentCenter.unnamed")).join(t("environmentCenter.listSeparator")),
              })}
            </p>
          ) : null}
          {invalidInspections.length ? (
            <ul className="environment-share-dialog__failures" role="alert">
              {invalidInspections.map((item) => (
                <li key={item.index}>{t("environmentCenter.import.itemError", { index: item.index + 1, error: item.error || t("environmentCenter.import.invalidCode") })}</li>
              ))}
            </ul>
          ) : null}
          {failedItems.length ? (
            <ul className="environment-share-dialog__failures" role="alert">
              {failedItems.map((item, index) => (
                <li key={`${item.code}:${index}`}>{t("environmentCenter.import.itemError", { index: index + 1, error: item.error })}</li>
              ))}
            </ul>
          ) : null}
          {requestError ? <p className="environment-share-dialog__error-text" role="alert">{requestError}</p> : null}
        </div>
        <footer className="environment-build-dialog__actions">
          <Button type="button" color="secondary" variant="ghost" size="sm" disabled={busy} onClick={onClose}>
            {t("common.cancel")}
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
  const { t, i18n } = useTranslation("ui");
  const creationOptions = environmentCreationOptions(t);
  const initialEnvironmentDraft = environmentDraft(environment, cloudProvider);
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
  const [uploadedDockerfile, setUploadedDockerfile] = useState(
    hasCustomDockerfile ? environment?.dockerfile ?? "" : "",
  );
  const [dockerfileFileError, setDockerfileFileError] = useState("");
  const dockerfileInputRef = useRef<HTMLInputElement>(null);
  const [dockerfilePresetEnvironment, setDockerfilePresetEnvironment] = useState<DockerfilePresetEnvironment>(() => (
    hasCustomDockerfile
      ? dockerfilePresetEnvironmentFromContent(environment?.dockerfile ?? "")
      : initialEnvironmentDraft.baseEnvironment === "aio-sandbox"
          || initialEnvironmentDraft.baseEnvironment === "codex-sandbox"
        ? initialEnvironmentDraft.baseEnvironment
        : "none"
  ));
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
  const [veadkSelected, setVeadkSelected] = useState(false);
  const generatedDockerfile = useMemo(
    () => buildEnvironmentDockerfile(draft, cloudProvider),
    [cloudProvider, draft.baseEnvironment, draft.operatingSystem, draft.language, draft.optionIds],
  );
  const customDockerfile = draft.dockerfile ?? generatedDockerfile;
  const hasDockerfilePresetEnvironment = dockerfilePresetEnvironment !== "none";
  const selectedBaseImage = dockerfilePresetEnvironment === "aio-sandbox"
    ? AIO_BASE_IMAGE
    : dockerfilePresetEnvironment === "codex-sandbox"
      ? CODEX_SANDBOX_BASE_IMAGES[cloudProvider]
      : "";
  const dockerfileEditorValue = hasDockerfilePresetEnvironment
    ? dockerfileBody(uploadedDockerfile)
    : uploadedDockerfile;
  const dockerfileTemplate = hasDockerfilePresetEnvironment
    ? composeDockerfile(selectedBaseImage, "")
    : "";
  const resolvedUploadedDockerfile = hasDockerfilePresetEnvironment
    ? composeDockerfile(selectedBaseImage, dockerfileEditorValue)
    : uploadedDockerfile;
  const uploadError = dockerfileFileError || (
    hasDockerfilePresetEnvironment
      ? validateDockerfileBody(dockerfileEditorValue, selectedBaseImage, t)
      : validateDockerfileUpload(uploadedDockerfile, undefined, t)
  );
  const isEditing = Boolean(environment);
  const formId = "environment-editor-form";
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const uploadIsValid = Boolean(resolvedUploadedDockerfile.trim()) && !uploadError;
  const gitSourceKey = `${gitRepositoryUrl.trim()}\u0000${gitRef.trim()}`;
  const gitIsValid = !repositoryInputError(gitRepositoryUrl, t)
    && gitInspectedKey === gitSourceKey
    && Boolean(gitDockerfilePath)
    && (gitRepositoryMode === "managed" || repositorySelected(gitContainerRepository));
  const imageIsValid = repositorySelected(imageRepository)
    && Boolean(imageReference.trim())
    && !imageReferenceError(imageReference, t);
  const canSubmit = Boolean(draft.name.trim())
    && !saving
    && (
      creationMethod === "custom"
      || creationMethod === "dockerfile" && uploadIsValid
      || creationMethod === "git" && gitIsValid
      || creationMethod === "image" && imageIsValid
    );

  const toggleOption = (optionId: string, selected: boolean) => {
    setDraft((current) => ({
      ...current,
      optionIds: selected
        ? [...current.optionIds, optionId]
        : current.optionIds.filter((id) => id !== optionId),
    }));
  };

  const updateUploadedDockerfile = (value: string) => {
    setDockerfileFileError("");
    setUploadedDockerfile(
      hasDockerfilePresetEnvironment
        ? composeDockerfile(selectedBaseImage, value)
        : value,
    );
  };

  const uploadDockerfile = async (file: File | undefined) => {
    if (!file) return;
    const result = await readDockerfileUpload(file, t);
    setDockerfileFileError(result.error);
    if (!result.content) return;
    setUploadedDockerfile(result.content);
  };

  const resetDockerfile = () => {
    setDockerfileFileError("");
    setUploadedDockerfile(dockerfileTemplate);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setSaveError("");
    try {
      const uploadedBase = environmentBaseFromDockerfile(resolvedUploadedDockerfile);
      await onSave({
        ...draft,
        name: draft.name.trim(),
        description: draft.description.trim(),
        optionIds: creationMethod === "custom" ? draft.optionIds : [],
        selectedSkills: creationMethod === "custom" ? draft.selectedSkills : [],
        dockerfile: creationMethod === "dockerfile"
          ? resolvedUploadedDockerfile
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

  const detailTitle = draft.name.trim() || (isEditing ? environment?.name || t("environmentCenter.configure") : t("environmentCenter.create"));

  return (
    <ResourcePageShell className="environment-editor" aria-label={isEditing ? t("environmentCenter.details") : t("environmentCenter.create")}>
      <ResourceDetailLayout
        title={detailTitle}
        description={t("environmentCenter.editorDescription")}
        identitySeed={detailTitle}
        backLabel={t("environmentCenter.backToList")}
        onBack={onCancel}
        actions={(
          <>
          {onDelete ? (
            <Button type="button" color="danger" variant="ghost" size="sm" onClick={onDelete} disabled={saving}>
              {t("common.delete")}
            </Button>
          ) : null}
          {onShare ? (
            <Button color="secondary" variant="soft" size="sm" onClick={onShare} disabled={saving}>
              {t("environmentCenter.share.action")}
            </Button>
          ) : null}
          <Button color="secondary" variant="soft" size="sm" onClick={onCancel} disabled={saving}>{t("common.cancel")}</Button>
          <Button color="info" size="sm" type="submit" form={formId} disabled={!canSubmit}>
            {saving
              ? t("common.saving")
              : creationMethod === "image"
                ? isEditing ? t("environmentCenter.save") : t("environmentCenter.create")
                : isEditing ? t("environmentCenter.saveAndBuild") : t("environmentCenter.createAndBuild")}
          </Button>
          </>
        )}
      >

      <form id={formId} className="environment-form" onSubmit={submit}>
        <div className="environment-fields">
          <label className="environment-field">
            <span>{t("environmentCenter.name")}<RequiredMark /></span>
            <Input
              className="environment-text-input"
              type="text"
              size="lg"
              required
              value={draft.name}
              maxLength={60}
              placeholder={t("environmentCenter.namePlaceholder")}
              onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
            />
          </label>
          <label className="environment-field">
            <span>{t("common.description")}</span>
            <Textarea
              className="environment-description-input"
              size="lg"
              rows={3}
              value={draft.description}
              maxLength={180}
              placeholder={t("environmentCenter.descriptionPlaceholder")}
              onChange={(event) => setDraft((current) => ({ ...current, description: event.target.value }))}
            />
          </label>
        </div>

        <label className="environment-field environment-creation-method">
          <span>{t("environmentCenter.creationMethod")}<RequiredMark /></span>
          <Select
            id="environment-creation-method"
            value={creationMethod}
            options={creationOptions}
            optionClassName="environment-select-option"
            required
            size="lg"
            block
            pill={false}
            triggerClassName="environment-select-trigger"
            onChange={(option) => {
              const nextMethod = option.value as EnvironmentCreationMethod;
              setCreationMethod(nextMethod);
              if (nextMethod === "dockerfile" && !uploadedDockerfile.trim()) {
                setUploadedDockerfile(dockerfileTemplate);
              }
              setSaveError("");
            }}
          />
          <small>{creationOptions.find((item) => item.value === creationMethod)?.description}</small>
        </label>

        {saveError ? <p className="environment-form-error" role="alert">{saveError}</p> : null}

        {creationMethod === "custom" ? (
          <div className="environment-configuration">
                <section className="environment-section environment-form-section" aria-label={t("environmentCenter.baseConfiguration")}>
                  <div className="environment-form-grid">
                    <label className="environment-field">
                      <span>{t("environmentCenter.baseEnvironment")}<RequiredMark /></span>
                      <Select
                        id="environment-base-environment"
                        value={draft.baseEnvironment}
                        options={ENVIRONMENT_BASE_OPTIONS.map((item) => ({ ...item, description: t(`environmentCenter.baseDescriptions.${item.value}`) }))}
                        optionClassName="environment-select-option"
                        required
                        size="lg"
                        block
                        pill={false}
                        triggerClassName="environment-select-trigger"
                        onChange={(option) => {
                          const baseEnvironment = option.value as EnvironmentBaseEnvironment;
                          const usesPresetRuntime = baseEnvironment === "aio-sandbox"
                            || baseEnvironment === "codex-sandbox";
                          setDraft((current) => ({
                            ...current,
                            baseEnvironment,
                            operatingSystem: usesPresetRuntime ? "ubuntu-22.04" : current.operatingSystem,
                            language: usesPresetRuntime ? "python-3.12" : current.language,
                          }));
                        }}
                      />
                      <small>{t(`environmentCenter.baseDescriptions.${draft.baseEnvironment}`)}</small>
                    </label>
                    <label className="environment-field">
                      <span>{t("environmentCenter.operatingSystem")}<RequiredMark /></span>
                      <Select
                        id="environment-operating-system"
                        value={draft.operatingSystem}
                        options={ENVIRONMENT_OS_OPTIONS}
                        optionClassName="environment-select-option"
                        required
                        size="lg"
                        block
                        pill={false}
                        disabled={draft.baseEnvironment !== "ubuntu"}
                        triggerClassName="environment-select-trigger"
                        onChange={(option) => setDraft((current) => ({
                          ...current,
                          operatingSystem: option.value as EnvironmentOperatingSystem,
                        }))}
                      />
                      <small>{draft.baseEnvironment !== "ubuntu" ? t("environmentCenter.fixedByBase", { base: environmentBaseEnvironmentLabel(draft.baseEnvironment), value: "Ubuntu 22.04" }) : t("environmentCenter.selectUbuntuVersion")}</small>
                    </label>
                    <label className="environment-field">
                      <span>{t("environmentCenter.pythonVersion")}<RequiredMark /></span>
                      <Select
                        id="environment-python-version"
                        value={draft.language}
                        options={draft.baseEnvironment !== "ubuntu"
                          ? ENVIRONMENT_LANGUAGE_OPTIONS.filter((item) => item.value === "python-3.12")
                          : ENVIRONMENT_LANGUAGE_OPTIONS}
                        optionClassName="environment-select-option"
                        required
                        size="lg"
                        block
                        pill={false}
                        disabled={draft.baseEnvironment !== "ubuntu"}
                        triggerClassName="environment-select-trigger"
                        onChange={(option) => setDraft((current) => ({
                          ...current,
                          language: option.value as EnvironmentLanguage,
                        }))}
                      />
                      <small>{draft.baseEnvironment !== "ubuntu" ? t("environmentCenter.fixedByBase", { base: environmentBaseEnvironmentLabel(draft.baseEnvironment), value: "Python 3.12" }) : t("environmentCenter.selectPythonVersion")}</small>
                    </label>
                  </div>
                </section>

            <section className="environment-section" aria-labelledby="environment-skills-title">
              <h2 id="environment-skills-title">{t("environmentCenter.skills")}</h2>
              <div className="environment-skill-grid">
                <StudioPackageOption
                  name="VeADK"
                  description={t("environmentCenter.veadkDescription")}
                  selected={veadkSelected}
                  disabled={saving}
                  onChange={setVeadkSelected}
                  icon={<img src={veadkLogo} alt="" />}
                />
                <SkillSourcePicker
                  selected={draft.selectedSkills}
                  onChange={(selectedSkills) => setDraft((current) => ({ ...current, selectedSkills }))}
                  cloudProvider={cloudProvider}
                  disabled={saving}
                  addLabel={t("environmentCenter.addSkill")}
                  showSelectedCount={false}
                />
              </div>
            </section>

            {ENVIRONMENT_CATEGORIES.map((category) => (
              <section className="environment-section" key={category.id} aria-labelledby={`environment-${category.id}-title`}>
                <h2 id={`environment-${category.id}-title`}>{t(`environmentCenter.categories.${category.id}`)}</h2>
                <div className="environment-option-grid">
                  {category.options.map((option) => {
                    const selected = draft.optionIds.includes(option.id);
                    return (
                      <StudioPackageOption
                        key={option.id}
                        name={option.label}
                        description={t(`environmentCenter.options.${option.id}`, { defaultValue: option.description })}
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
        ) : creationMethod === "dockerfile" ? (
          <section className="environment-upload" aria-label={t("environmentCenter.customDockerfile")}>
            <div className="environment-dockerfile-settings environment-form-grid">
              <label className="environment-field">
                <span>{t("environmentCenter.presetEnvironment")}</span>
                <Select
                  id="environment-dockerfile-base-environment"
                  value={dockerfilePresetEnvironment}
                  options={dockerfilePresetEnvironmentOptions(t)}
                  optionClassName="environment-select-option"
                  size="lg"
                  block
                  pill={false}
                  triggerClassName="environment-select-trigger"
                  onChange={(option) => {
                    setDockerfileFileError("");
                    setDockerfilePresetEnvironment(option.value as DockerfilePresetEnvironment);
                  }}
                />
                <small>{t("environmentCenter.presetHint")}</small>
              </label>
            </div>
            <div className="environment-upload__preview">
              <div>
                <h3>Dockerfile<RequiredMark /></h3>
                <div className="environment-upload__actions">
                  <span className="environment-upload__size">
                    {t("environmentCenter.dockerfileSize", { size: dockerfileByteSize(resolvedUploadedDockerfile).toLocaleString(i18n.resolvedLanguage ?? i18n.language), max: (131072).toLocaleString(i18n.resolvedLanguage ?? i18n.language) })}
                  </span>
                  <input
                    ref={dockerfileInputRef}
                    className="environment-upload__file-input"
                    type="file"
                    accept=".dockerfile,text/plain"
                    tabIndex={-1}
                    hidden
                    onChange={(event) => {
                      const input = event.currentTarget;
                      void uploadDockerfile(input.files?.[0]).finally(() => {
                        input.value = "";
                      });
                    }}
                  />
                  <Button
                    className="environment-upload__action"
                    type="button"
                    color="secondary"
                    variant="soft"
                    size="sm"
                    pill={false}
                    disabled={saving}
                    onClick={() => dockerfileInputRef.current?.click()}
                  >{t("environmentCenter.upload")}</Button>
                  <Button
                    className="environment-upload__action"
                    type="button"
                    color="secondary"
                    variant="ghost"
                    size="sm"
                    pill={false}
                    disabled={saving || !dockerfileEditorValue}
                    onClick={resetDockerfile}
                  >{t("environmentCenter.reset")}</Button>
                </div>
              </div>
              <div className={`environment-dockerfile-editor${hasDockerfilePresetEnvironment ? " has-fixed-base" : ""}${uploadError ? " is-invalid" : ""}`}>
                {hasDockerfilePresetEnvironment ? (
                  <div className="environment-dockerfile-from" aria-label={t("environmentCenter.dockerfileBaseImage")}>
                    <span className="environment-dockerfile-from__line" aria-hidden="true">1</span>
                    <code>
                      <span className="environment-dockerfile-from__keyword">FROM</span>
                      <span title={selectedBaseImage}>{selectedBaseImage}</span>
                    </code>
                  </div>
                ) : null}
                <div className="environment-dockerfile__editor environment-upload__editor" aria-label={t("environmentCenter.dockerfileContent")}>
                  <CodeEditor
                    value={dockerfileEditorValue}
                    path="Dockerfile"
                    lineNumberStart={hasDockerfilePresetEnvironment ? 2 : 1}
                    height="auto"
                    minHeight="28px"
                    maxHeight="var(--environment-dockerfile-editor-max-height)"
                    onChange={updateUploadedDockerfile}
                  />
                </div>
              </div>
            </div>
            {uploadError ? <p className="environment-upload__error environment-upload__error--below" role="alert">{uploadError}</p> : null}
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
  const { t, i18n } = useTranslation("ui");
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
      setClipboardMessage(t("environmentCenter.clipboardUnsupported"));
      return;
    }
    try {
      const text = await navigator.clipboard.readText();
      const opened = openClipboardImport(text);
      if (!opened && !text.trim() && await clipboardReadPermissionDenied()) {
        setClipboardMessage(t("environmentCenter.clipboardReadError"));
      }
    } catch {
      setClipboardMessage(t("environmentCenter.clipboardReadError"));
    }
  }, [importDialog, openClipboardImport, t, view.kind]);

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
      dockerfile: draft.dockerfile ?? buildEnvironmentDockerfile(draft, cloudProvider),
    };
    const saved = editingEnvironment
      ? await updateEnvironment(editingEnvironment.id, input)
      : await createEnvironment(input);
    setEnvironments((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
    setView({ kind: "list" });
    setStatusError(false);
    if (input.imageSource) {
      setStatusMessage(t("environmentCenter.status.boundImage", { name: saved.name }));
      return;
    }
    try {
      const latestVersion = await buildEnvironment(saved.id);
      setEnvironments((current) => current.map((item) =>
        item.id === saved.id ? { ...item, latestVersion } : item,
      ));
      setStatusMessage(t("environmentCenter.status.queued", { name: saved.name }));
    } catch (cause) {
      setStatusError(true);
      setStatusMessage(
        t("environmentCenter.status.savedBuildFailed", { error: cause instanceof Error ? cause.message : String(cause) }),
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
      setStatusMessage(t("environmentCenter.status.queued", { name: environment.name }));
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
        ? t("environmentCenter.status.importedFailed", { created: createdCount, failed: failedCount })
        : duplicateCount > 0
          ? t("environmentCenter.status.importedDuplicate", { created: createdCount, duplicate: duplicateCount })
          : t("environmentCenter.status.imported", { count: createdCount }),
    );
  };

  const deleteDialog = deleteTarget ? (
    <StudioConfirmDialog
      title={t("environmentCenter.deleteTitle")}
      description={t("environmentCenter.deleteDescription", { name: deleteTarget.name })}
      confirmLabel={t("common.delete")}
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
            setStatusMessage(t("environmentCenter.status.deleted", { name: target.name }));
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
    <ResourcePageShell className="environment-center" aria-label={t("environmentCenter.title")}>
      <ResourcePageHeader
        title={t("environmentCenter.title")}
      />

      <ResourceToolbar className="environment-toolbar">
        {onWorkspace ? (
          <ResourceTabs
            items={[
              { id: "workspaces", label: t("workspace.title") },
              { id: "environments", label: t("environmentCenter.title") },
            ]}
            value="environments"
            onChange={(value) => {
              if (value === "workspaces") onWorkspace();
            }}
            ariaLabel={t("workspace.resourceType")}
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
            aria-label={t("environmentCenter.search")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("environmentCenter.search")}
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
            {t("environmentCenter.manualImport")}
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
              {t("common.reload")}
            </Button>
          </div>
        ) : visibleEnvironments.length === 0 && query.trim() ? (
          <div className="environment-empty">
            <EmptyMessage fill="none">
              <EmptyMessage.Icon><EnvironmentEmptyIcon /></EmptyMessage.Icon>
              <EmptyMessage.Title>{t("environmentCenter.noMatches")}</EmptyMessage.Title>
              <EmptyMessage.Description>{t("environmentCenter.tryAnotherName")}</EmptyMessage.Description>
            </EmptyMessage>
          </div>
        ) : (
          <ResourceGrid>
            {!query.trim() ? (
              <>
                <ResourceCreateCard
                  aria-label={t("environmentCenter.create")}
                  icon={<AddIcon />}
                  onClick={() => setView({ kind: "editor", environmentId: null })}
                >
                  {t("environmentCenter.create")}
                </ResourceCreateCard>
                <ResourceCreateCard
                  aria-label={t("environmentCenter.import.title")}
                  icon={<ImportEnvironmentIcon />}
                  onClick={() => openImportDialog()}
                >
                  {t("environmentCenter.import.title")}
                </ResourceCreateCard>
              </>
            ) : null}
            {visibleEnvironments.map((environment) => {
              const status = environmentStatus(environment, t);
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
                    t("common.noDescription")
                  }
                  metadata={[
                    {
                      label: t("workspace.updated"),
                      value: environmentUpdatedAt(environment.updatedAt, i18n.resolvedLanguage ?? i18n.language),
                      title: environmentUpdatedAtTitle(environment.updatedAt, i18n.resolvedLanguage ?? i18n.language),
                    },
                  ]}
                  action={{
                    label: environment.latestVersion ? t("environmentCenter.buildDetails.title") : rebuilding ? t("environmentCenter.buildDetails.starting") : t("environmentCenter.startBuild"),
                    icon: "play",
                    title: t("environmentCenter.build"),
                    disabled: rebuilding,
                    onClick: () => environment.latestVersion
                      ? setBuildDetailsId(environment.id)
                      : void rebuildEnvironment(environment),
                  }}
                  auxiliaryAction={{
                    label: t("environmentCenter.manifest.view"),
                    icon: <FileCode />,
                    title: environment.latestVersion ? t("environmentCenter.manifest.viewShort") : t("environmentCenter.manifest.unavailable"),
                    disabled: !environment.latestVersion,
                    onClick: () => setManifestTarget(environment),
                  }}
                  detailAction={{ label: t("environmentCenter.configure"), onClick: () => setView({ kind: "editor", environmentId: environment.id }) }}
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
