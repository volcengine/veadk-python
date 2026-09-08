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
  getGitHubPullRequestReviewRecords,
  startGitHubPullRequestReview,
  updateGitHubAppReviewRepository,
  type GitHubAppConfig,
  type GitHubAppRepositoriesResult,
  type GitHubAppRepository,
  type GitHubPullRequestResult,
  type GitHubPullRequestReviewRecord,
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
type GitHubReviewRecordsSettings = GitHubAppReviewSettings;
type ReviewListKind = "repositories" | "records";

const REVIEW_PAGE_SIZE = 10;

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

function reviewRecordStatusText(status: GitHubPullRequestReviewRecord["status"]): string {
  if (status === "started") return "评审中";
  if (status === "completed") return "已完成";
  if (status === "ignored") return "已忽略";
  return "失败";
}

function reviewRecordTriggerText(trigger: GitHubPullRequestReviewRecord["trigger"]): string {
  return trigger === "webhook" ? "自动触发" : "手动发起";
}

function reviewRecordReasonText(record: GitHubPullRequestReviewRecord): string {
  if (!record.reason) return "";
  if (record.status !== "ignored") return record.reason;
  if (record.reason === "repository-review-disabled") return "忽略原因：仓库未开启自动评审";
  if (record.reason === "pull-request-not-reviewable") {
    return "忽略原因：该 PR 事件不需要评审，仅评审新建、更新、重新打开和转为可评审的非 Draft、非 fork PR";
  }
  if (record.reason === "review-settings-unavailable") return "忽略原因：自动评审设置不可用";
  if (record.reason === "unsupported-event") return "忽略原因：不是 Pull Request 事件";
  return `忽略原因：${record.reason}`;
}

function reviewRecordTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function paginationText(page: number, pageSize: number, count: number, hasNextPage: boolean): string {
  if (count === 0) return `第 ${page} 页`;
  const start = (page - 1) * pageSize + 1;
  const end = start + count - 1;
  return `第 ${page} 页 · ${start}-${end}${hasNextPage ? "+" : ""}`;
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
  const [githubAppRepositoriesPage, setGitHubAppRepositoriesPage] = useState(1);
  const [githubAppRepositoriesHasNextPage, setGitHubAppRepositoriesHasNextPage] = useState(false);
  const [githubAppRepositoryQueryInput, setGitHubAppRepositoryQueryInput] = useState("");
  const [githubAppRepositoryQuery, setGitHubAppRepositoryQuery] = useState("");
  const [updatingRepository, setUpdatingRepository] = useState("");
  const [reviewRecords, setReviewRecords] = useState<GitHubPullRequestReviewRecord[]>([]);
  const [reviewRecordsLoading, setReviewRecordsLoading] = useState(isPullRequestReview);
  const [reviewRecordsError, setReviewRecordsError] = useState("");
  const [reviewRecordsSettings, setReviewRecordsSettings] = useState<GitHubReviewRecordsSettings | null>(null);
  const [reviewRecordsPage, setReviewRecordsPage] = useState(1);
  const [reviewRecordsHasNextPage, setReviewRecordsHasNextPage] = useState(false);
  const submitAbortRef = useRef<AbortController | null>(null);
  const reviewAbortRef = useRef<AbortController | null>(null);
  const githubAppAbortRef = useRef<AbortController | null>(null);
  const githubAppRepositoriesAbortRef = useRef<AbortController | null>(null);
  const reviewRecordsAbortRef = useRef<AbortController | null>(null);
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
  const showGitHubAppRepositoriesPagination = githubAppRepositoriesPage > 1
    || githubAppRepositoriesHasNextPage;
  const showReviewRecordsPagination = reviewRecordsPage > 1
    || reviewRecordsHasNextPage;

  useEffect(() => () => {
    submitAbortRef.current?.abort();
    reviewAbortRef.current?.abort();
    githubAppAbortRef.current?.abort();
    githubAppRepositoriesAbortRef.current?.abort();
    reviewRecordsAbortRef.current?.abort();
  }, []);

  useEffect(() => {
    setForm({ ...definition.initialValues({ cloudProvider }) });
    setFieldErrors({});
    setSubmitError("");
    setResult(null);
    setRegionMenuOpen(false);
    submitAbortRef.current?.abort();
    reviewAbortRef.current?.abort();
    reviewRecordsAbortRef.current?.abort();
    setReviewResult(null);
    setReviewError("");
    setReviewRecords([]);
    setReviewRecordsError("");
    setReviewRecordsSettings(null);
    setGitHubAppRepositoriesPage(1);
    setGitHubAppRepositoriesHasNextPage(false);
    setGitHubAppRepositoryQueryInput("");
    setGitHubAppRepositoryQuery("");
    setReviewRecordsPage(1);
    setReviewRecordsHasNextPage(false);
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
        if (!config.configured) {
          setGitHubAppRepositoriesLoading(false);
          setReviewRecordsLoading(false);
        }
      })
      .catch((error) => {
        if (controller.signal.aborted || githubAppAbortRef.current !== controller) return;
        setGitHubAppError(error instanceof Error ? error.message : String(error));
        setGitHubAppRepositoriesLoading(false);
        setReviewRecordsLoading(false);
      })
      .finally(() => {
        if (githubAppAbortRef.current === controller) {
          githubAppAbortRef.current = null;
          setGitHubAppLoading(false);
        }
      });
  }, [isPullRequestReview]);

  const refreshGitHubAppRepositories = (page = githubAppRepositoriesPage, query = githubAppRepositoryQuery) => {
    githubAppRepositoriesAbortRef.current?.abort();
    const controller = new AbortController();
    githubAppRepositoriesAbortRef.current = controller;
    setGitHubAppRepositoriesLoading(true);
    setGitHubAppRepositoriesError("");
    void getGitHubAppRepositories(controller.signal, { page, pageSize: REVIEW_PAGE_SIZE, query })
      .then((result) => {
        if (githubAppRepositoriesAbortRef.current !== controller) return;
        if (result.repositories.length === 0 && result.page > 1) {
          setGitHubAppRepositoriesPage(result.page - 1);
          refreshGitHubAppRepositories(result.page - 1);
          return;
        }
        setGitHubAppRepositories(result.repositories);
        setGitHubAppRepositoriesPage(result.page);
        setGitHubAppRepositoriesHasNextPage(result.hasNextPage);
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

  const refreshReviewRecords = (page = reviewRecordsPage) => {
    reviewRecordsAbortRef.current?.abort();
    const controller = new AbortController();
    reviewRecordsAbortRef.current = controller;
    setReviewRecordsLoading(true);
    setReviewRecordsError("");
    void getGitHubPullRequestReviewRecords(controller.signal, { page, pageSize: REVIEW_PAGE_SIZE })
      .then((result) => {
        if (reviewRecordsAbortRef.current !== controller) return;
        if (result.records.length === 0 && result.page > 1) {
          setReviewRecordsPage(result.page - 1);
          refreshReviewRecords(result.page - 1);
          return;
        }
        setReviewRecords(result.records);
        setReviewRecordsPage(result.page);
        setReviewRecordsHasNextPage(result.hasNextPage);
        setReviewRecordsSettings({
          reviewSettingsConfigured: result.reviewSettingsConfigured,
          reviewSettingsReason: result.reviewSettingsReason,
        });
      })
      .catch((error) => {
        if (controller.signal.aborted || reviewRecordsAbortRef.current !== controller) return;
        setReviewRecordsError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => {
        if (reviewRecordsAbortRef.current === controller) {
          reviewRecordsAbortRef.current = null;
          setReviewRecordsLoading(false);
        }
      });
  };

  useEffect(() => {
    if (!isPullRequestReview || githubAppConfig?.configured !== true) return;
    refreshGitHubAppRepositories(1);
    refreshReviewRecords(1);
  }, [githubAppConfig?.configured, isPullRequestReview]);

  const searchGitHubAppRepositories = () => {
    const query = githubAppRepositoryQueryInput.trim();
    setGitHubAppRepositoryQuery(query);
    setGitHubAppRepositoriesPage(1);
    refreshGitHubAppRepositories(1, query);
  };

  const clearGitHubAppRepositorySearch = () => {
    setGitHubAppRepositoryQueryInput("");
    setGitHubAppRepositoryQuery("");
    setGitHubAppRepositoriesPage(1);
    refreshGitHubAppRepositories(1, "");
  };

  const changeReviewListPage = (kind: ReviewListKind, nextPage: number) => {
    if (nextPage < 1) return;
    if (kind === "repositories") {
      setGitHubAppRepositoriesPage(nextPage);
      refreshGitHubAppRepositories(nextPage, githubAppRepositoryQuery);
      return;
    }
    setReviewRecordsPage(nextPage);
    refreshReviewRecords(nextPage);
  };

  const toggleRepositoryReview = async (repository: GitHubAppRepository) => {
    if (githubAppReviewSettings?.reviewSettingsConfigured !== true || updatingRepository) return;
    const controller = new AbortController();
    setUpdatingRepository(repository.fullName);
    setGitHubAppRepositoriesError("");
    try {
      const saved = await updateGitHubAppReviewRepository(
        {
          repository: repository.fullName,
          reviewEnabled: !repository.reviewEnabled,
        },
        controller.signal,
      );
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
      refreshReviewRecords();
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

                <section className="github-review-section github-app-repositories" aria-labelledby="github-app-repositories-title">
                  <div className="github-review-section-header">
                    <div>
                      <h2 id="github-app-repositories-title">已安装仓库</h2>
                      <p>只有开启评审的仓库会响应 GitHub webhook 自动触发。</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => refreshGitHubAppRepositories()}
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
                  <div className="github-app-repository-search">
                    <input
                      type="search"
                      value={githubAppRepositoryQueryInput}
                      onChange={(event) => setGitHubAppRepositoryQueryInput(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          searchGitHubAppRepositories();
                        }
                      }}
                      placeholder="搜索 owner 或仓库名"
                      aria-label="搜索已安装仓库"
                    />
                    <button
                      type="button"
                      onClick={searchGitHubAppRepositories}
                      disabled={!githubAppConfig?.configured || githubAppRepositoriesLoading}
                    >
                      搜索
                    </button>
                    {githubAppRepositoryQuery ? (
                      <button
                        type="button"
                        onClick={clearGitHubAppRepositorySearch}
                        disabled={githubAppRepositoriesLoading}
                      >
                        清除
                      </button>
                    ) : null}
                  </div>
                  {githubAppRepositoriesLoading && githubAppRepositories.length === 0 ? (
                    <div className="github-app-repository-empty">正在读取 GitHub App 安装仓库...</div>
                  ) : null}
                  {!githubAppRepositoriesLoading && githubAppRepositories.length === 0 && !githubAppRepositoriesError ? (
                    <div className="github-app-repository-empty">
                      {githubAppRepositoryQuery
                        ? `没有匹配 “${githubAppRepositoryQuery}” 的已安装仓库。`
                        : "GitHub App 尚未安装到任何仓库。"}
                    </div>
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
                  {showGitHubAppRepositoriesPagination ? (
                    <div className="github-list-pagination" aria-label="已安装仓库分页">
                      <span>
                        {paginationText(
                          githubAppRepositoriesPage,
                          REVIEW_PAGE_SIZE,
                          githubAppRepositories.length,
                          githubAppRepositoriesHasNextPage,
                        )}
                      </span>
                      <div>
                        <button
                          type="button"
                          onClick={() => changeReviewListPage("repositories", githubAppRepositoriesPage - 1)}
                          disabled={githubAppRepositoriesPage <= 1 || githubAppRepositoriesLoading}
                        >
                          上一页
                        </button>
                        <button
                          type="button"
                          onClick={() => changeReviewListPage("repositories", githubAppRepositoriesPage + 1)}
                          disabled={!githubAppRepositoriesHasNextPage || githubAppRepositoriesLoading}
                        >
                          下一页
                        </button>
                      </div>
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
            <div className="github-pr-review-sections">
              <section className="github-review-section github-review-now" aria-labelledby="github-review-now-title">
                <div className="github-review-section-header">
                  <div>
                    <h2 id="github-review-now-title">立刻评审</h2>
                    <p>输入已安装且已启用仓库的 PR URL，立即创建 Sandbox 评审任务。</p>
                  </div>
                </div>
                <div className="github-review-section-body">
                  <div className="github-field">
                    <input
                      id="github-pull-request-url"
                      aria-label="Pull Request URL"
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
                  <div className="github-review-section-actions">
                    <button type="button" onClick={startReview} disabled={reviewSubmitting}>
                      {reviewSubmitting ? "发起评审中…" : "立即发起评审"}
                    </button>
                  </div>
                </div>
              </section>

              <section className="github-review-section github-review-records" aria-labelledby="github-review-records-title">
                <div className="github-review-section-header">
                  <div>
                    <h2 id="github-review-records-title">评审记录</h2>
                    <p>展示最近自动触发和手动发起的评审任务。</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => refreshReviewRecords()}
                    disabled={!githubAppConfig?.configured || reviewRecordsLoading}
                  >
                    {reviewRecordsLoading ? "刷新中..." : "刷新"}
                  </button>
                </div>
                {reviewRecordsError ? (
                  <div className="github-submit-message is-error" role="alert">{reviewRecordsError}</div>
                ) : null}
                {reviewRecordsSettings?.reviewSettingsConfigured === false && !reviewRecordsError ? (
                  <div className="github-submit-message is-error" role="alert">
                    {reviewRecordsSettings.reviewSettingsReason || "管理员未配置 Studio 持久化存储，无法读取评审记录。"}
                  </div>
                ) : null}
                {reviewRecordsLoading && reviewRecords.length === 0 ? (
                  <div className="github-app-repository-empty">正在读取 PR 评审记录...</div>
                ) : null}
                {!reviewRecordsLoading && reviewRecords.length === 0 && !reviewRecordsError ? (
                  <div className="github-app-repository-empty">暂无 PR 评审记录。</div>
                ) : null}
                {reviewRecords.length > 0 ? (
                  <div className="github-review-record-list">
                    {reviewRecords.map((record) => {
                      const reasonText = reviewRecordReasonText(record);
                      const reviewSessionId = record.status === "completed" ? "" : record.sessionId;
                      return (
                        <div className="github-review-record-row" key={record.id}>
                          <div className="github-review-record-main">
                            <div className="github-review-record-title">
                              <a href={record.pullRequestUrl} target="_blank" rel="noreferrer">
                                {record.repository}#{record.pullRequestNumber}
                                <ExternalIcon />
                              </a>
                              <span className={`github-review-record-status is-${record.status}`}>
                                {reviewRecordStatusText(record.status)}
                              </span>
                            </div>
                            <span>
                              {reviewRecordTriggerText(record.trigger)}
                              {record.action ? ` · ${record.action}` : ""}
                              {" · "}
                              {reviewRecordTime(record.createdAt)}
                              {reasonText ? ` · ${reasonText}` : ""}
                            </span>
                          </div>
                          <div className="github-review-record-actions">
                            {reviewSessionId && onOpenSandboxSession ? (
                              <button type="button" onClick={() => onOpenSandboxSession(reviewSessionId)}>
                                打开 Session
                              </button>
                            ) : null}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : null}
                {showReviewRecordsPagination ? (
                  <div className="github-list-pagination" aria-label="评审记录分页">
                    <span>
                      {paginationText(
                        reviewRecordsPage,
                        REVIEW_PAGE_SIZE,
                        reviewRecords.length,
                        reviewRecordsHasNextPage,
                      )}
                    </span>
                    <div>
                      <button
                        type="button"
                        onClick={() => changeReviewListPage("records", reviewRecordsPage - 1)}
                        disabled={reviewRecordsPage <= 1 || reviewRecordsLoading}
                      >
                        上一页
                      </button>
                      <button
                        type="button"
                        onClick={() => changeReviewListPage("records", reviewRecordsPage + 1)}
                        disabled={!reviewRecordsHasNextPage || reviewRecordsLoading}
                      >
                        下一页
                      </button>
                    </div>
                  </div>
                ) : null}
              </section>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
