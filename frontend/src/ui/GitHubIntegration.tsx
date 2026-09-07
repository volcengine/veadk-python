import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type SVGProps,
} from "react";

import {
  getGitHubAppConfig,
  getGitHubAppRepositories,
  startGitHubPullRequestReview,
  updateGitHubAppReviewRepositories,
  type GitHubAppConfig,
  type GitHubAppRepositoriesResult,
  type GitHubAppRepository,
  type GitHubPullRequestResult,
  type GitHubPullRequestReviewResult,
  normalizeGitHubRepository,
  repositoryFromGitHubPullRequestUrl,
} from "../adk/githubIntegration";
import {
  cloudRegionOptions,
  type CloudProvider,
} from "../adk/cloudProvider";
import { getGitHubAutomation } from "../automations/registry";
import type {
  AutomationFieldDefinition,
  AutomationFieldName,
  AutomationFormValues,
  GitHubAutomationId,
} from "../automations/types";
import { runtimeNameProblem } from "../create/runtimeName";
import { GitHubLogo } from "./GitHubLogo";
import "./GitHubIntegration.css";

interface GitHubIntegrationProps {
  automation: GitHubAutomationId;
  cloudProvider: CloudProvider;
  onBack: () => void;
  onOpenSandboxSession?: (sessionId: string) => void;
}

type FormFieldName = AutomationFieldName | "region" | "token";
type FieldName = FormFieldName | "pullRequestUrl";
type GitHubAppReviewSettings = Pick<
  GitHubAppRepositoriesResult,
  "reviewSettingsConfigured" | "reviewSettingsReason"
>;

function BackIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path d="m9.8 3.5-4.5 4.5 4.5 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function EyeIcon({ hidden, ...props }: SVGProps<SVGSVGElement> & { hidden: boolean }) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <path d="M2.5 10s2.6-4 7.5-4 7.5 4 7.5 4-2.6 4-7.5 4-7.5-4-7.5-4Z" />
      <circle cx="10" cy="10" r="1.8" />
      {hidden ? <path d="m4 4 12 12" /> : null}
    </svg>
  );
}

function ExternalIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path d="M6.5 4H4.8A1.8 1.8 0 0 0 3 5.8v5.4A1.8 1.8 0 0 0 4.8 13h5.4a1.8 1.8 0 0 0 1.8-1.8V9.5M9 3h4v4M12.5 3.5 7.2 8.8" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChevronIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path d="m4 6 4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CheckIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path d="m3.5 8.2 2.8 2.8 6.2-6.2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function validateField(name: FieldName, value: string, required: boolean): string {
  const text = value.trim();
  if (!text) return required ? "此项不能为空" : "";
  if (name === "repository" && !/^(?:https:\/\/github\.com\/)?[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+(?:\.git)?$/.test(text)) {
    return "请输入 owner/repository 或完整 GitHub Repo URL";
  }
  if (name === "baseBranch" && (!/^[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(text) || text.includes(".."))) {
    return "目标分支格式不正确";
  }
  if (name === "projectPath" && (text.startsWith("/") || text.split("/").includes(".."))) {
    return "请输入仓库内的相对目录";
  }
  if (name === "runtimeName") {
    return runtimeNameProblem(text) ?? "";
  }
  if (name === "runtimeId" && !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(text)) {
    return "Runtime ID 格式不正确";
  }
  if (name === "modelName" && !/^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/.test(text)) {
    return "模型名称格式不正确";
  }
  if (name === "modelBaseUrl") {
    try {
      const url = new URL(text);
      if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash) {
        return "请输入不含凭据、查询参数或锚点的 HTTPS 地址";
      }
    } catch {
      return "请输入有效的 HTTPS 地址";
    }
  }
  if (name === "pullRequestUrl" && !/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/pull\/[1-9][0-9]*\/?$/.test(text)) {
    return "请输入完整的 GitHub Pull Request URL";
  }
  return "";
}

function repositoryUrl(value: string): string {
  try {
    return `https://github.com/${normalizeGitHubRepository(value)}`;
  } catch {
    return "";
  }
}

function requiredMark(value: string, required: boolean) {
  if (!required || value.trim()) return null;
  return <span className="github-required-mark" aria-hidden="true">*</span>;
}

export function GitHubIntegration({
  automation,
  cloudProvider,
  onBack,
  onOpenSandboxSession,
}: GitHubIntegrationProps) {
  const definition = getGitHubAutomation(automation);
  const isPullRequestReview = automation === "review";
  const regionOptions = cloudRegionOptions(cloudProvider);
  const secrets = definition.secrets({ cloudProvider });
  const [form, setForm] = useState<AutomationFormValues>(() => ({
    ...definition.initialValues({ cloudProvider }),
  }));
  const selectedRegion = regionOptions.find((region) => region.value === form.region);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldName, string>>>({});
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showToken, setShowToken] = useState(false);
  const [regionMenuOpen, setRegionMenuOpen] = useState(false);
  const [result, setResult] = useState<GitHubPullRequestResult | null>(null);
  const [pullRequestUrl, setPullRequestUrl] = useState("");
  const [reviewResult, setReviewResult] = useState<GitHubPullRequestReviewResult | null>(null);
  const [reviewError, setReviewError] = useState("");
  const [reviewSubmitting, setReviewSubmitting] = useState(false);
  const [githubAppConfig, setGitHubAppConfig] = useState<GitHubAppConfig | null>(null);
  const [githubAppError, setGitHubAppError] = useState("");
  const [githubAppLoading, setGitHubAppLoading] = useState(isPullRequestReview);
  const [githubAppRepositories, setGitHubAppRepositories] = useState<GitHubAppRepository[]>([]);
  const [githubAppRepositoriesLoading, setGitHubAppRepositoriesLoading] = useState(isPullRequestReview);
  const [githubAppRepositoriesError, setGitHubAppRepositoriesError] = useState("");
  const [githubAppReviewSettings, setGitHubAppReviewSettings] = useState<GitHubAppReviewSettings | null>(null);
  const [updatingRepository, setUpdatingRepository] = useState("");
  const submitAbortRef = useRef<AbortController | null>(null);
  const reviewAbortRef = useRef<AbortController | null>(null);
  const githubAppAbortRef = useRef<AbortController | null>(null);
  const githubAppRepositoriesAbortRef = useRef<AbortController | null>(null);
  const configuredRepositoryUrl = repositoryUrl(form.repository);
  const configuredRepository = configuredRepositoryUrl.replace("https://github.com/", "");
  const repositorySecretsUrl = configuredRepositoryUrl
    ? `${configuredRepositoryUrl}/settings/secrets/actions`
    : "";
  const githubAppName = githubAppConfig?.appSlug || "agentkit-veadk-studio";
  const githubAppInstallUrl = githubAppConfig?.installUrl || `https://github.com/apps/${githubAppName}/installations/new`;
  const reviewRepository = repositoryFromGitHubPullRequestUrl(pullRequestUrl);
  const enabledReviewRepositories = githubAppRepositories.filter((repository) => repository.reviewEnabled);
  const installedReviewRepository = reviewRepository
    ? githubAppRepositories.find((repository) => repository.fullName.toLowerCase() === reviewRepository.toLowerCase())
    : undefined;

  useEffect(() => () => {
    submitAbortRef.current?.abort();
    reviewAbortRef.current?.abort();
    githubAppAbortRef.current?.abort();
    githubAppRepositoriesAbortRef.current?.abort();
  }, []);

  useEffect(() => {
    setForm({ ...definition.initialValues({ cloudProvider }) });
    setFieldErrors({});
    setSubmitError("");
    setResult(null);
    setRegionMenuOpen(false);
    submitAbortRef.current?.abort();
    reviewAbortRef.current?.abort();
    setReviewResult(null);
    setReviewError("");
  }, [automation, cloudProvider, definition]);

  useEffect(() => {
    if (!isPullRequestReview) return;
    githubAppAbortRef.current?.abort();
    const controller = new AbortController();
    githubAppAbortRef.current = controller;
    setGitHubAppLoading(true);
    setGitHubAppError("");
    void getGitHubAppConfig(controller.signal)
      .then((config) => {
        if (githubAppAbortRef.current !== controller) return;
        setGitHubAppConfig(config);
      })
      .catch((error) => {
        if (controller.signal.aborted || githubAppAbortRef.current !== controller) return;
        setGitHubAppError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => {
        if (githubAppAbortRef.current === controller) {
          githubAppAbortRef.current = null;
          setGitHubAppLoading(false);
        }
      });
  }, [isPullRequestReview]);

  const refreshGitHubAppRepositories = () => {
    githubAppRepositoriesAbortRef.current?.abort();
    const controller = new AbortController();
    githubAppRepositoriesAbortRef.current = controller;
    setGitHubAppRepositoriesLoading(true);
    setGitHubAppRepositoriesError("");
    void getGitHubAppRepositories(controller.signal)
      .then((result) => {
        if (githubAppRepositoriesAbortRef.current !== controller) return;
        setGitHubAppRepositories(result.repositories);
        setGitHubAppReviewSettings({
          reviewSettingsConfigured: result.reviewSettingsConfigured,
          reviewSettingsReason: result.reviewSettingsReason,
        });
      })
      .catch((error) => {
        if (controller.signal.aborted || githubAppRepositoriesAbortRef.current !== controller) return;
        setGitHubAppRepositoriesError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => {
        if (githubAppRepositoriesAbortRef.current === controller) {
          githubAppRepositoriesAbortRef.current = null;
          setGitHubAppRepositoriesLoading(false);
        }
      });
  };

  useEffect(() => {
    if (!isPullRequestReview || githubAppConfig?.configured !== true) return;
    refreshGitHubAppRepositories();
  }, [githubAppConfig?.configured, isPullRequestReview]);

  const toggleRepositoryReview = async (repository: GitHubAppRepository) => {
    if (githubAppReviewSettings?.reviewSettingsConfigured !== true || updatingRepository) return;
    const nextRepositories = githubAppRepositories.map((item) => (
      item.fullName === repository.fullName
        ? { ...item, reviewEnabled: !item.reviewEnabled }
        : item
    ));
    const enabledRepositories = nextRepositories
      .filter((item) => item.reviewEnabled)
      .map((item) => item.fullName);
    const controller = new AbortController();
    setUpdatingRepository(repository.fullName);
    setGitHubAppRepositoriesError("");
    try {
      const saved = await updateGitHubAppReviewRepositories(enabledRepositories, controller.signal);
      const savedLookup = new Set(saved.map((item) => item.toLowerCase()));
      setGitHubAppRepositories((current) => current.map((item) => ({
        ...item,
        reviewEnabled: savedLookup.has(item.fullName.toLowerCase()),
      })));
    } catch (error) {
      setGitHubAppRepositoriesError(error instanceof Error ? error.message : String(error));
    } finally {
      setUpdatingRepository("");
    }
  };

  const updateField = (name: FormFieldName, value: string) => {
    setForm((current) => ({ ...current, [name]: value }));
    if (fieldErrors[name]) {
      setFieldErrors((current) => ({ ...current, [name]: "" }));
    }
  };

  const blurField = (name: FieldName) => {
    const required = (!isPullRequestReview && name === "token")
      || name === "pullRequestUrl"
      || definition.fields.find((field) => field.name === name)?.required === true;
    const value = name === "pullRequestUrl" ? pullRequestUrl : form[name as FormFieldName];
    const error = validateField(name, value, required);
    setFieldErrors((current) => ({ ...current, [name]: error }));
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isPullRequestReview) return;
    const errors: Partial<Record<FieldName, string>> = {};
    for (const field of definition.fields) {
      const error = validateField(field.name, form[field.name], field.required);
      if (error) errors[field.name] = error;
    }
    if (!isPullRequestReview) {
      const tokenError = validateField("token", form.token, true);
      if (tokenError) {
        errors.token = tokenError;
      }
    }
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;

    submitAbortRef.current?.abort();
    const controller = new AbortController();
    submitAbortRef.current = controller;
    setSubmitting(true);
    setSubmitError("");
    setResult(null);
    try {
      const nextResult = await definition.submit(
        form,
        { cloudProvider },
        controller.signal,
      );
      if (submitAbortRef.current !== controller) return;
      setResult(nextResult);
      setForm((current) => ({ ...current, token: "" }));
    } catch (error) {
      if (controller.signal.aborted || submitAbortRef.current !== controller) return;
      setSubmitError(error instanceof Error ? error.message : String(error));
    } finally {
      if (submitAbortRef.current === controller) {
        submitAbortRef.current = null;
        setSubmitting(false);
      }
    }
  };

  const stopComposingSubmit = (event: KeyboardEvent<HTMLFormElement>) => {
    if (event.key === "Enter" && (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229)) {
      event.preventDefault();
    }
  };

  const startReview = async () => {
    const errors: Partial<Record<FieldName, string>> = {};
    const pullRequestError = validateField("pullRequestUrl", pullRequestUrl, true);
    if (pullRequestError) errors.pullRequestUrl = pullRequestError;
    if (!pullRequestError) {
      const repository = repositoryFromGitHubPullRequestUrl(pullRequestUrl);
      const installedRepository = githubAppRepositories.find((item) => (
        item.fullName.toLowerCase() === repository.toLowerCase()
      ));
      if (!installedRepository) {
        errors.pullRequestUrl = "PR URL 所属仓库尚未安装 GitHub App";
      } else if (!installedRepository.reviewEnabled) {
        errors.pullRequestUrl = `请先在下方开启 ${installedRepository.fullName} 的评审`;
      }
    }
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;

    reviewAbortRef.current?.abort();
    const controller = new AbortController();
    reviewAbortRef.current = controller;
    setReviewSubmitting(true);
    setReviewError("");
    setReviewResult(null);
    try {
      const nextResult = await startGitHubPullRequestReview(
        {
          pullRequestUrl: pullRequestUrl.trim(),
        },
        controller.signal,
      );
      if (reviewAbortRef.current !== controller) return;
      setReviewResult(nextResult);
      setForm((current) => ({ ...current, token: "" }));
      onOpenSandboxSession?.(nextResult.sessionId);
    } catch (error) {
      if (controller.signal.aborted || reviewAbortRef.current !== controller) return;
      setReviewError(error instanceof Error ? error.message : String(error));
    } finally {
      if (reviewAbortRef.current === controller) {
        reviewAbortRef.current = null;
        setReviewSubmitting(false);
      }
    }
  };

  const field = (
    fieldDefinition: AutomationFieldDefinition,
  ) => {
    const { name, label, placeholder, help, required } = fieldDefinition;
    const isRepository = name === "repository";
    return (
      <div className="github-field" key={name}>
        <div className="github-field-label-row">
          <label htmlFor={`github-${name}`}>
            <span>{label}</span>
            {requiredMark(form[name], required)}
          </label>
          {isRepository ? (
            <a className="github-field-action" href="https://github.com/" target="_blank" rel="noreferrer">
              https://github.com/
              <ExternalIcon />
            </a>
          ) : null}
        </div>
        <input
          id={`github-${name}`}
          value={form[name]}
          onChange={(event) => updateField(name, event.target.value)}
          onBlur={() => blurField(name)}
          placeholder={placeholder}
          required={required}
          aria-invalid={Boolean(fieldErrors[name])}
          aria-describedby={`github-${name}-help${fieldErrors[name] ? ` github-${name}-error` : ""}`}
        />
        <span id={`github-${name}-help`} className="github-field-help">
          {isRepository && configuredRepository
            ? isPullRequestReview
              ? `将使用 GitHub App 校验 ${configuredRepository} 的 Pull Request`
              : `将为 ${configuredRepository} 添加 PR 自动评审配置`
            : help}
        </span>
        {fieldErrors[name] ? <span id={`github-${name}-error`} className="github-field-error" role="alert">{fieldErrors[name]}</span> : null}
      </div>
    );
  };

  return (
    <div className="github-integration-page">
      <header className="github-integration-header">
        <button type="button" className="github-back" onClick={onBack} aria-label="返回自动化列表">
          <BackIcon />
        </button>
        <GitHubLogo className="github-integration-logo" />
        <div>
          <h1>{definition.title}</h1>
          <p>{definition.subtitle}</p>
        </div>
      </header>

      <div className="github-integration-layout">
        <section id={`github-panel-${automation}`} className="github-section-panel">
          <div className="github-panel-heading">
            <p>{definition.panel}</p>
          </div>
          <form className="github-release-form" onSubmit={onSubmit} onKeyDown={stopComposingSubmit} noValidate>
            {!isPullRequestReview ? (
              <div className="github-field-grid">
                {definition.fields.map(field)}
                <div className="github-field">
                  <label id="github-region-label">
                    <span>地域</span>
                    {requiredMark(form.region, true)}
                  </label>
                  <div
                    className="pp-network-region github-region-picker"
                    onKeyDown={(event) => {
                      if (event.key === "Escape") setRegionMenuOpen(false);
                    }}
                  >
                    <button
                      type="button"
                      className="pp-region-trigger"
                      aria-labelledby="github-region-label"
                      aria-haspopup="listbox"
                      aria-expanded={regionMenuOpen}
                      onClick={() => setRegionMenuOpen((open) => !open)}
                    >
                      <span>{selectedRegion?.label ?? form.region}</span>
                      <ChevronIcon className={`pp-region-chevron${regionMenuOpen ? " is-open" : ""}`} />
                    </button>
                    {regionMenuOpen ? (
                      <>
                        <div className="menu-scrim" onClick={() => setRegionMenuOpen(false)} />
                        <div className="pp-region-menu" role="listbox" aria-label="地域">
                          {regionOptions.map((region) => {
                            const selected = region.value === form.region;
                            return (
                              <button
                                key={region.value}
                                type="button"
                                role="option"
                                aria-selected={selected}
                                className={`pp-region-option${selected ? " is-selected" : ""}`}
                                onClick={() => {
                                  updateField("region", region.value);
                                  setRegionMenuOpen(false);
                                }}
                              >
                                <span>{region.label}</span>
                                {selected ? <CheckIcon /> : null}
                              </button>
                            );
                          })}
                        </div>
                      </>
                    ) : null}
                  </div>
                  <span className="github-field-help">
                    {definition.regionHelp}
                  </span>
                </div>
              </div>
            ) : null}

            {isPullRequestReview ? (
              <>
                <div className={`github-app-card${githubAppConfig?.configured ? " is-ready" : ""}`}>
                  <div>
                    <strong>GitHub App 授权</strong>
                    <span>
                      {githubAppLoading
                        ? "正在检查中心服务配置..."
                        : githubAppConfig?.configured
                          ? `安装 ${githubAppName} 到目标仓库后，可在下方开启自动评审。`
                          : githubAppError || githubAppConfig?.reason || "管理员未配置 GitHub App。"}
                    </span>
                  </div>
                  <a className="github-app-install-link" href={githubAppInstallUrl} target="_blank" rel="noreferrer">
                    安装 GitHub App
                    <ExternalIcon />
                  </a>
                </div>

                <section className="github-app-repositories" aria-labelledby="github-app-repositories-title">
                  <div className="github-app-repositories-header">
                    <div>
                      <h2 id="github-app-repositories-title">已安装仓库</h2>
                      <p>只有开启评审的仓库会响应 GitHub webhook 自动触发。</p>
                    </div>
                    <button
                      type="button"
                      onClick={refreshGitHubAppRepositories}
                      disabled={!githubAppConfig?.configured || githubAppRepositoriesLoading}
                    >
                      {githubAppRepositoriesLoading ? "刷新中..." : "刷新"}
                    </button>
                  </div>
                  {githubAppRepositoriesError ? (
                    <div className="github-submit-message is-error" role="alert">{githubAppRepositoriesError}</div>
                  ) : null}
                  {githubAppReviewSettings?.reviewSettingsConfigured === false && !githubAppRepositoriesError ? (
                    <div className="github-submit-message is-error" role="alert">
                      {githubAppReviewSettings.reviewSettingsReason || "管理员未配置 Studio 持久化存储，无法保存启用评审设置。"}
                    </div>
                  ) : null}
                  {githubAppRepositoriesLoading && githubAppRepositories.length === 0 ? (
                    <div className="github-app-repository-empty">正在读取 GitHub App 安装仓库...</div>
                  ) : null}
                  {!githubAppRepositoriesLoading && githubAppRepositories.length === 0 && !githubAppRepositoriesError ? (
                    <div className="github-app-repository-empty">GitHub App 尚未安装到任何仓库。</div>
                  ) : null}
                  {githubAppRepositories.length > 0 ? (
                    <div className="github-app-repository-list">
                      {githubAppRepositories.map((repository) => {
                        const busy = updatingRepository === repository.fullName;
                        const disabled = githubAppReviewSettings?.reviewSettingsConfigured !== true || Boolean(updatingRepository);
                        return (
                          <div className="github-app-repository-row" key={repository.fullName}>
                            <div className="github-app-repository-main">
                              <a href={repository.htmlUrl} target="_blank" rel="noreferrer" title={repository.fullName}>
                                {repository.fullName}
                                <ExternalIcon />
                              </a>
                              <span>{repository.private ? "Private" : "Public"} · Installation {repository.installationId}</span>
                            </div>
                            <button
                              type="button"
                              className={`github-review-switch${repository.reviewEnabled ? " is-on" : ""}`}
                              role="switch"
                              aria-checked={repository.reviewEnabled}
                              disabled={disabled}
                              onClick={() => { void toggleRepositoryReview(repository); }}
                            >
                              <span>{busy ? "保存中" : repository.reviewEnabled ? "已启用" : "未启用"}</span>
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  ) : null}
                </section>
              </>
            ) : (
              <>
                <div className="github-field github-token-field">
                  <div className="github-token-label-row">
                    <label htmlFor="github-token">
                      <span>GitHub Token</span>
                      {requiredMark(form.token, true)}
                    </label>
                    <a
                      className="github-field-action"
                      href="https://github.com/settings/personal-access-tokens/new?name=VeADK%20Studio&description=Create%20a%20GitHub%20automation%20pull%20request&contents=write&pull_requests=write&workflows=write"
                      target="_blank"
                      rel="noreferrer"
                    >
                      创建 GitHub Token
                      <ExternalIcon />
                    </a>
                  </div>
                  <div className="github-token-input">
                    <input
                      id="github-token"
                      type={showToken ? "text" : "password"}
                      value={form.token}
                      onChange={(event) => updateField("token", event.target.value)}
                      onBlur={() => blurField("token")}
                      autoComplete="off"
                      required
                      placeholder="需要 Contents、Pull requests、Workflows 写权限"
                      aria-invalid={Boolean(fieldErrors.token)}
                      aria-describedby={`github-token-help${fieldErrors.token ? " github-token-error" : ""}`}
                    />
                    <button
                      type="button"
                      onClick={() => setShowToken((current) => !current)}
                      aria-label={showToken ? "隐藏 Token" : "显示 Token"}
                      title={showToken ? "隐藏 Token" : "显示 Token"}
                    >
                      <EyeIcon hidden={showToken} />
                    </button>
                  </div>
                  <span id="github-token-help" className="github-field-help">此处 Token 用于创建配置 PR；它不是 Sandbox 的通用必填项，且不会保存在浏览器或写入 PR</span>
                  {fieldErrors.token ? <span id="github-token-error" className="github-field-error" role="alert">{fieldErrors.token}</span> : null}
                </div>

                {submitError ? <div className="github-submit-message is-error" role="alert">{submitError}</div> : null}
                {result ? (
                  <div className="github-submit-message is-success github-result-message" role="status">
                    <div>
                      <strong>配置 PR #{result.number} 已创建</strong>
                      <span>合并后，后续同仓库 PR 会自动触发评审。</span>
                    </div>
                    <a className="github-result-link" href={result.url} target="_blank" rel="noreferrer">
                      查看配置 PR
                      <ExternalIcon />
                    </a>
                  </div>
                ) : null}

                <div className="github-form-actions">
                  <div className="github-secrets-note">
                    <div className="github-secrets-header">
                      <strong>合并配置 PR 前，请在目标仓库添加运行时密钥</strong>
                      {repositorySecretsUrl ? (
                        <a className="github-secrets-link" href={repositorySecretsUrl} target="_blank" rel="noreferrer">
                          打开 Secrets 设置
                          <ExternalIcon />
                        </a>
                      ) : null}
                    </div>
                    <span className="github-secrets-path">路径：Settings → Secrets and variables → Actions → Repository secrets</span>
                    <ul>
                      {secrets.map((secret) => {
                        const [name, ...descriptionParts] = secret.split("：");
                        return (
                          <li key={secret}>
                            <code>{name}</code>
                            {descriptionParts.length ? <span>{descriptionParts.join("：")}</span> : null}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                  <button type="submit" disabled={submitting}>
                    {submitting ? "提交 PR 中…" : definition.submitLabel}
                  </button>
                </div>
              </>
            )}
          </form>
          {isPullRequestReview ? (
            <section className="github-review-now" aria-labelledby="github-review-now-title">
              <div className="github-review-now-copy">
                <h2 id="github-review-now-title">立即评审一个 PR</h2>
              </div>
              <div className="github-field">
                <div className="github-field-label-row">
                  <label htmlFor="github-pull-request-url">
                    <span>Pull Request URL</span>
                    {requiredMark(pullRequestUrl, true)}
                  </label>
                  <span className="github-field-note">会自动识别 PR 所属仓库</span>
                </div>
                <input
                  id="github-pull-request-url"
                  value={pullRequestUrl}
                  onChange={(event) => {
                    setPullRequestUrl(event.target.value);
                    if (fieldErrors.pullRequestUrl) {
                      setFieldErrors((current) => ({ ...current, pullRequestUrl: "" }));
                    }
                  }}
                  onBlur={() => setFieldErrors((current) => ({
                    ...current,
                    pullRequestUrl: validateField("pullRequestUrl", pullRequestUrl, true),
                  }))}
                  placeholder="https://github.com/owner/repository/pull/123"
                  aria-invalid={Boolean(fieldErrors.pullRequestUrl)}
                  aria-describedby={fieldErrors.pullRequestUrl ? "github-pull-request-url-error" : undefined}
                />
                {fieldErrors.pullRequestUrl ? <span id="github-pull-request-url-error" className="github-field-error" role="alert">{fieldErrors.pullRequestUrl}</span> : null}
                {!fieldErrors.pullRequestUrl && reviewRepository ? (
                  <span className="github-field-help">
                    {installedReviewRepository?.reviewEnabled
                      ? `将使用 GitHub App 评审 ${installedReviewRepository.fullName}`
                      : installedReviewRepository
                        ? `请先在下方开启 ${installedReviewRepository.fullName} 的评审`
                        : `PR URL 所属仓库 ${reviewRepository} 尚未安装 GitHub App`}
                  </span>
                ) : null}
                {!fieldErrors.pullRequestUrl && !reviewRepository && enabledReviewRepositories.length > 0 ? (
                  <span className="github-field-help">
                    已启用仓库：{enabledReviewRepositories.map((repository) => repository.fullName).join("、")}
                  </span>
                ) : null}
              </div>
              {reviewError ? <div className="github-submit-message is-error" role="alert">{reviewError}</div> : null}
              {reviewResult ? (
                <div className="github-submit-message is-success" role="status">
                  <span>已发起评审，Session {reviewResult.sessionId} 正在运行。</span>
                </div>
              ) : null}
              <div className="github-review-now-actions">
                <button type="button" onClick={startReview} disabled={reviewSubmitting}>
                  {reviewSubmitting ? "发起评审中…" : "立即发起评审"}
                </button>
              </div>
            </section>
          ) : null}
        </section>
      </div>
    </div>
  );
}
