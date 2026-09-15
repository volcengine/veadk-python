import { useEffect, useRef, useState, type SVGProps } from "react";

import {
  disconnectGitLabOAuth,
  getGitLabAppConfig,
  getGitLabOAuthAuthorizationUrl,
  getGitLabProjects,
  getGitLabReviewRecords,
  projectFromGitLabMergeRequestUrl,
  startGitLabMergeRequestReview,
  updateGitLabReviewProject,
  type GitLabAppConfig,
  type GitLabProject,
  type GitLabReviewRecord,
  type GitLabReviewRecordStatus,
  type GitLabReviewRecordTrigger,
  type GitLabReviewResult,
} from "../adk/gitlabIntegration";
import "./GitHubIntegration.css";

interface GitLabIntegrationProps {
  onBack: () => void;
  onOpenSandboxSession?: (id: string) => void;
}

const REVIEW_PAGE_SIZE = 10;

function ExternalIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M6.5 4H4a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M9 3h4v4M8.5 7.5 13 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function BackIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path d="m9.8 3.5-4.5 4.5 4.5 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function GitLabLogo(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" {...props}>
      <path d="m22.54 9.64-.03-.08-2.2-6.81a.76.76 0 0 0-1.43-.08l-2.1 4.31H7.22l-2.1-4.31a.76.76 0 0 0-1.43.08l-2.2 6.81-.03.08a5.15 5.15 0 0 0 1.7 5.79l.01.01.02.01 8.81 6.58 8.81-6.58.02-.01.01-.01a5.15 5.15 0 0 0 1.7-5.79ZM12 20.08 8.65 8.59h6.7L12 20.08Z" />
    </svg>
  );
}

function reviewRecordStatusText(status: GitLabReviewRecordStatus): string {
  if (status === "started") return "进行中";
  if (status === "completed") return "已完成";
  if (status === "ignored") return "已忽略";
  return "失败";
}

function reviewRecordTriggerText(trigger: GitLabReviewRecordTrigger): string {
  return trigger === "webhook" ? "自动触发" : "手动发起";
}

function reviewRecordTime(value: string): string {
  const time = new Date(value);
  if (Number.isNaN(time.getTime())) return value;
  return time.toLocaleString();
}

function reviewRecordReasonText(record: GitLabReviewRecord): string {
  if (record.reason === "project-review-disabled") return "项目未启用";
  if (record.reason === "merge-request-not-reviewable") return "MR 不满足评审条件";
  return record.reason;
}

function paginationText(page: number, pageSize: number, count: number, hasNext: boolean): string {
  const start = (page - 1) * pageSize + 1;
  const end = (page - 1) * pageSize + count;
  return hasNext ? `${start}-${end}` : `${start}-${end} / ${end}`;
}

export function GitLabIntegration({ onBack, onOpenSandboxSession }: GitLabIntegrationProps) {
  const [config, setConfig] = useState<GitLabAppConfig | null>(null);
  const [configError, setConfigError] = useState("");
  const [configLoading, setConfigLoading] = useState(true);
  const [projects, setProjects] = useState<GitLabProject[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [projectsError, setProjectsError] = useState("");
  const [reviewSettings, setReviewSettings] = useState<{ reviewSettingsConfigured: boolean; reviewSettingsReason: string } | null>(null);
  const [projectsPage, setProjectsPage] = useState(1);
  const [projectsHasNextPage, setProjectsHasNextPage] = useState(false);
  const [projectQueryInput, setProjectQueryInput] = useState("");
  const [projectQuery, setProjectQuery] = useState("");
  const [updatingProject, setUpdatingProject] = useState<number | null>(null);
  const [mergeRequestUrl, setMergeRequestUrl] = useState("");
  const [reviewSubmitting, setReviewSubmitting] = useState(false);
  const [reviewError, setReviewError] = useState("");
  const [reviewResult, setReviewResult] = useState<GitLabReviewResult | null>(null);
  const [reviewRecords, setReviewRecords] = useState<GitLabReviewRecord[]>([]);
  const [reviewRecordsLoading, setReviewRecordsLoading] = useState(true);
  const [reviewRecordsError, setReviewRecordsError] = useState("");
  const [reviewRecordsPage, setReviewRecordsPage] = useState(1);
  const [reviewRecordsHasNextPage, setReviewRecordsHasNextPage] = useState(false);
  const [reviewRecordsSettings, setReviewRecordsSettings] = useState<{ reviewSettingsConfigured: boolean; reviewSettingsReason: string } | null>(null);
  const [connectingGitLab, setConnectingGitLab] = useState(false);
  const [disconnectingGitLab, setDisconnectingGitLab] = useState(false);
  const configAbortRef = useRef<AbortController | null>(null);
  const projectsAbortRef = useRef<AbortController | null>(null);
  const recordsAbortRef = useRef<AbortController | null>(null);

  const reviewProject = config
    ? projectFromGitLabMergeRequestUrl(config.baseUrl, mergeRequestUrl)
    : "";
  const accessibleReviewProject = reviewProject
    ? projects.find((project) => project.pathWithNamespace.toLowerCase() === reviewProject.toLowerCase())
    : undefined;
  const showProjectsPagination = projectsPage > 1 || projectsHasNextPage;
  const showRecordsPagination = reviewRecordsPage > 1 || reviewRecordsHasNextPage;
  const gitLabAccessReady = config?.configured === true && config.oauthConnected;

  const refreshProjects = (page = projectsPage, query = projectQuery) => {
    projectsAbortRef.current?.abort();
    const controller = new AbortController();
    projectsAbortRef.current = controller;
    setProjectsLoading(true);
    setProjectsError("");
    void getGitLabProjects(controller.signal, { page, pageSize: REVIEW_PAGE_SIZE, query })
      .then((result) => {
        if (projectsAbortRef.current !== controller) return;
        if (result.projects.length === 0 && result.page > 1) {
          setProjectsPage(result.page - 1);
          refreshProjects(result.page - 1, query);
          return;
        }
        setProjects(result.projects);
        setProjectsPage(result.page);
        setProjectsHasNextPage(result.hasNextPage);
        setReviewSettings({
          reviewSettingsConfigured: result.reviewSettingsConfigured,
          reviewSettingsReason: result.reviewSettingsReason,
        });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || projectsAbortRef.current !== controller) return;
        setProjectsError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => {
        if (projectsAbortRef.current === controller) {
          projectsAbortRef.current = null;
          setProjectsLoading(false);
        }
      });
  };

  const refreshReviewRecords = (page = reviewRecordsPage) => {
    recordsAbortRef.current?.abort();
    const controller = new AbortController();
    recordsAbortRef.current = controller;
    setReviewRecordsLoading(true);
    setReviewRecordsError("");
    void getGitLabReviewRecords(controller.signal, { page, pageSize: REVIEW_PAGE_SIZE })
      .then((result) => {
        if (recordsAbortRef.current !== controller) return;
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
      .catch((error: unknown) => {
        if (controller.signal.aborted || recordsAbortRef.current !== controller) return;
        setReviewRecordsError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => {
        if (recordsAbortRef.current === controller) {
          recordsAbortRef.current = null;
          setReviewRecordsLoading(false);
        }
      });
  };

  useEffect(() => {
    configAbortRef.current?.abort();
    const controller = new AbortController();
    configAbortRef.current = controller;
    setConfigLoading(true);
    setConfigError("");
    void getGitLabAppConfig(controller.signal)
      .then((nextConfig) => {
        if (configAbortRef.current !== controller) return;
        setConfig(nextConfig);
        if (!nextConfig.configured || (nextConfig.oauthConfigured && !nextConfig.oauthConnected)) {
          setProjectsLoading(false);
          setReviewRecordsLoading(false);
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || configAbortRef.current !== controller) return;
        setConfigError(error instanceof Error ? error.message : String(error));
        setProjectsLoading(false);
        setReviewRecordsLoading(false);
      })
      .finally(() => {
        if (configAbortRef.current === controller) {
          configAbortRef.current = null;
          setConfigLoading(false);
        }
      });
    return () => {
      controller.abort();
      projectsAbortRef.current?.abort();
      recordsAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!gitLabAccessReady) return;
    refreshProjects(1, "");
    refreshReviewRecords(1);
  }, [gitLabAccessReady]);

  const searchProjects = () => {
    const query = projectQueryInput.trim();
    setProjectQuery(query);
    setProjectsPage(1);
    refreshProjects(1, query);
  };

  const toggleProjectReview = async (project: GitLabProject) => {
    if (reviewSettings?.reviewSettingsConfigured !== true || updatingProject !== null) return;
    if (!project.reviewEnabled && !gitLabAccessReady) {
      setProjectsError("请先连接 GitLab 后再启用自动评审。");
      return;
    }
    const controller = new AbortController();
    setUpdatingProject(project.projectId);
    setProjectsError("");
    try {
      await updateGitLabReviewProject({
        projectId: project.projectId,
        reviewEnabled: !project.reviewEnabled,
      }, controller.signal);
      setProjects((current) => current.map((item) => (
        item.projectId === project.projectId
          ? { ...item, reviewEnabled: !project.reviewEnabled }
          : item
      )));
    } catch (error) {
      setProjectsError(error instanceof Error ? error.message : String(error));
    } finally {
      setUpdatingProject(null);
    }
  };

  const disconnectGitLab = async () => {
    const controller = new AbortController();
    setDisconnectingGitLab(true);
    setConfigError("");
    try {
      await disconnectGitLabOAuth(controller.signal);
      const nextConfig = await getGitLabAppConfig(controller.signal);
      setConfig(nextConfig);
      setProjects([]);
      setReviewSettings(null);
    } catch (error) {
      setConfigError(error instanceof Error ? error.message : String(error));
    } finally {
      setDisconnectingGitLab(false);
    }
  };

  const connectGitLab = async () => {
    const controller = new AbortController();
    setConnectingGitLab(true);
    setConfigError("");
    try {
      window.location.href = await getGitLabOAuthAuthorizationUrl(controller.signal);
    } catch (error) {
      setConfigError(error instanceof Error ? error.message : String(error));
      setConnectingGitLab(false);
    }
  };

  const startReview = async () => {
    const url = mergeRequestUrl.trim();
    if (!url) {
      setReviewError("请输入 GitLab Merge Request URL。");
      return;
    }
    if (!config?.configured) {
      setReviewError("管理员未配置 GitLab OAuth。");
      return;
    }
    if (!gitLabAccessReady) {
      setReviewError("请先连接 GitLab 后再发起评审。");
      return;
    }
    if (!projectFromGitLabMergeRequestUrl(config.baseUrl, url)) {
      setReviewError("请输入当前 GitLab 实例下的完整 Merge Request URL。");
      return;
    }
    setReviewSubmitting(true);
    setReviewError("");
    setReviewResult(null);
    const controller = new AbortController();
    try {
      const result = await startGitLabMergeRequestReview({ mergeRequestUrl: url }, controller.signal);
      setReviewResult(result);
      refreshReviewRecords(1);
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : String(error));
    } finally {
      setReviewSubmitting(false);
    }
  };

  return (
    <div className="github-integration-page">
      <header className="github-integration-header">
        <button type="button" className="github-back" onClick={onBack} aria-label="返回自动化">
          <BackIcon />
        </button>
        <GitLabLogo className="github-integration-logo" />
        <div>
          <h1>GitLab MR Review</h1>
          <p>通过 GitLab webhook 触发 Sandbox 评审，并将结果写回 Merge Request。</p>
        </div>
      </header>

      <div className="github-integration-layout">
        <section className="github-section-panel">
          <div className="github-panel-heading">
            <p>请先为目标项目开启自动评审，再通过 webhook 或手动 URL 发起 MR 评审。</p>
          </div>

          <div className="github-release-form">
            <div className={`github-app-card${config?.configured ? " is-ready" : ""}`}>
              <div>
                <strong>GitLab 集成配置</strong>
                <span>
                  {configLoading
                    ? "正在检查中心服务配置..."
                    : config?.configured
                      ? config.oauthConnected && config.oauthUser
                        ? `已连接 ${config.oauthUser.gitlabName || config.oauthUser.gitlabUsername} · ${config.baseUrl}`
                        : `当前实例：${config.baseUrl}`
                      : configError || config?.reason || "管理员未配置 GitLab OAuth。"}
                </span>
              </div>
              {config?.oauthConfigured && !config.oauthConnected ? (
                <button
                  type="button"
                  className="github-app-install-link"
                  onClick={() => { void connectGitLab(); }}
                  disabled={connectingGitLab}
                >
                  {connectingGitLab ? "连接中..." : "连接 GitLab"}
                  <ExternalIcon />
                </button>
              ) : config?.oauthConnected ? (
                <button
                  type="button"
                  className="github-app-install-link"
                  onClick={() => { void disconnectGitLab(); }}
                  disabled={disconnectingGitLab}
                >
                  {disconnectingGitLab ? "断开中..." : "断开授权"}
                </button>
              ) : config?.webhookUrl ? (
                <a className="github-app-install-link" href={config.webhookUrl} target="_blank" rel="noreferrer">
                  Webhook
                  <ExternalIcon />
                </a>
              ) : null}
            </div>

            <section className="github-review-section github-app-repositories" aria-labelledby="gitlab-projects-title">
              <div className="github-review-section-header">
                <div>
                  <h2 id="gitlab-projects-title">可访问项目</h2>
                  <p>只有开启评审的项目会响应 GitLab webhook 自动触发。</p>
                </div>
                <button type="button" onClick={() => refreshProjects()} disabled={!gitLabAccessReady || projectsLoading}>
                  {projectsLoading ? "刷新中..." : "刷新"}
                </button>
              </div>
              {projectsError ? <div className="github-submit-message is-error" role="alert">{projectsError}</div> : null}
              {reviewSettings?.reviewSettingsConfigured === false && !projectsError ? (
                <div className="github-submit-message is-error" role="alert">
                  {reviewSettings.reviewSettingsReason || "管理员未配置 Studio 持久化存储，无法保存启用评审设置。"}
                </div>
              ) : null}
              <div className="github-app-repository-search">
                <input
                  type="search"
                  value={projectQueryInput}
                  onChange={(event) => setProjectQueryInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      searchProjects();
                    }
                  }}
                  placeholder="搜索 group 或项目名"
                  aria-label="搜索 GitLab 项目"
                />
                <button type="button" onClick={searchProjects} disabled={!gitLabAccessReady || projectsLoading}>搜索</button>
                {projectQuery ? (
                  <button
                    type="button"
                    onClick={() => {
                      setProjectQueryInput("");
                      setProjectQuery("");
                      setProjectsPage(1);
                      refreshProjects(1, "");
                    }}
                    disabled={projectsLoading || !gitLabAccessReady}
                  >
                    清除
                  </button>
                ) : null}
              </div>
              {!gitLabAccessReady && !configLoading ? (
                <div className="github-app-repository-empty">请先连接 GitLab。</div>
              ) : null}
              {projectsLoading && projects.length === 0 && gitLabAccessReady ? <div className="github-app-repository-empty">正在读取 GitLab 项目...</div> : null}
              {!projectsLoading && projects.length === 0 && !projectsError && gitLabAccessReady ? (
                <div className="github-app-repository-empty">
                  {projectQuery ? `没有匹配 “${projectQuery}” 的 GitLab 项目。` : "GitLab 集成暂无可访问项目。"}
                </div>
              ) : null}
              {projects.length > 0 ? (
                <div className="github-app-repository-list">
                  {projects.map((project) => {
                    const busy = updatingProject === project.projectId;
                    const disabled = reviewSettings?.reviewSettingsConfigured !== true || updatingProject !== null || (!project.reviewEnabled && !gitLabAccessReady);
                    return (
                      <div className="github-app-repository-row" key={`${project.instanceId}:${project.projectId}`}>
                        <div className="github-app-repository-main">
                          <a href={project.webUrl} target="_blank" rel="noreferrer" title={project.pathWithNamespace}>
                            {project.pathWithNamespace}
                            <ExternalIcon />
                          </a>
                          <span>{project.private ? "Private" : "Public"} · Project {project.projectId}{project.permissionsNote ? ` · ${project.permissionsNote}` : ""}{project.reviewBindingStatus && project.reviewBindingStatus !== "active" && project.reviewBindingStatus !== "disabled" ? ` · ${project.reviewBindingReason || "授权失效"}` : ""}</span>
                        </div>
                        <button
                          type="button"
                          className={`github-review-switch${project.reviewEnabled ? " is-on" : ""}`}
                          role="switch"
                          aria-checked={project.reviewEnabled}
                          disabled={disabled}
                          onClick={() => { void toggleProjectReview(project); }}
                        >
                          <span>{busy ? "保存中" : project.reviewEnabled ? "已启用" : "未启用"}</span>
                        </button>
                      </div>
                    );
                  })}
                </div>
              ) : null}
              {showProjectsPagination ? (
                <div className="github-list-pagination" aria-label="GitLab 项目分页">
                  <span>{paginationText(projectsPage, REVIEW_PAGE_SIZE, projects.length, projectsHasNextPage)}</span>
                  <div>
                    <button type="button" onClick={() => { setProjectsPage(projectsPage - 1); refreshProjects(projectsPage - 1, projectQuery); }} disabled={projectsPage <= 1 || projectsLoading}>上一页</button>
                    <button type="button" onClick={() => { setProjectsPage(projectsPage + 1); refreshProjects(projectsPage + 1, projectQuery); }} disabled={!projectsHasNextPage || projectsLoading}>下一页</button>
                  </div>
                </div>
              ) : null}
            </section>
          </div>

          <div className="github-pr-review-sections">
            <section className="github-review-section github-review-now" aria-labelledby="gitlab-review-now-title">
              <div className="github-review-section-header">
                <div>
                  <h2 id="gitlab-review-now-title">立刻评审</h2>
                  <p>输入当前 GitLab 实例下的 MR URL，立即创建 Sandbox 评审任务。</p>
                </div>
              </div>
              <div className="github-review-section-body">
                <div className="github-field">
                  <input
                    aria-label="Merge Request URL"
                    value={mergeRequestUrl}
                    onChange={(event) => setMergeRequestUrl(event.target.value)}
                    placeholder={`${config?.baseUrl || "https://gitlab.example.com"}/group/project/-/merge_requests/123`}
                  />
                  {reviewProject ? (
                    <span className="github-field-help">
                      {accessibleReviewProject
                        ? `将使用 GitLab 授权评审 ${accessibleReviewProject.pathWithNamespace}`
                        : `MR URL 所属项目 ${reviewProject} 不在当前项目列表中`}
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
                  <button type="button" onClick={startReview} disabled={reviewSubmitting || !gitLabAccessReady}>
                    {reviewSubmitting ? "发起评审中..." : "立即发起评审"}
                  </button>
                </div>
              </div>
            </section>

            <section className="github-review-section github-review-records" aria-labelledby="gitlab-review-records-title">
              <div className="github-review-section-header">
                <div>
                  <h2 id="gitlab-review-records-title">评审记录</h2>
                  <p>展示最近自动触发和手动发起的评审任务。</p>
                </div>
                <button type="button" onClick={() => refreshReviewRecords()} disabled={!gitLabAccessReady || reviewRecordsLoading}>
                  {reviewRecordsLoading ? "刷新中..." : "刷新"}
                </button>
              </div>
              {reviewRecordsError ? <div className="github-submit-message is-error" role="alert">{reviewRecordsError}</div> : null}
              {reviewRecordsSettings?.reviewSettingsConfigured === false && !reviewRecordsError ? (
                <div className="github-submit-message is-error" role="alert">
                  {reviewRecordsSettings.reviewSettingsReason || "管理员未配置 Studio 持久化存储，无法读取评审记录。"}
                </div>
              ) : null}
              {reviewRecordsLoading && reviewRecords.length === 0 ? <div className="github-app-repository-empty">正在读取 MR 评审记录...</div> : null}
              {!reviewRecordsLoading && reviewRecords.length === 0 && !reviewRecordsError ? <div className="github-app-repository-empty">暂无 MR 评审记录。</div> : null}
              {reviewRecords.length > 0 ? (
                <div className="github-review-record-list">
                  {reviewRecords.map((record) => {
                    const reasonText = reviewRecordReasonText(record);
                    const reviewSessionId = record.status === "completed" ? "" : record.sessionId;
                    return (
                      <div className="github-review-record-row" key={record.id}>
                        <div className="github-review-record-main">
                          <div className="github-review-record-title">
                            <a href={record.mergeRequestUrl} target="_blank" rel="noreferrer">
                              {record.pathWithNamespace}!{record.mergeRequestIid}
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
              {showRecordsPagination ? (
                <div className="github-list-pagination" aria-label="GitLab 评审记录分页">
                  <span>{paginationText(reviewRecordsPage, REVIEW_PAGE_SIZE, reviewRecords.length, reviewRecordsHasNextPage)}</span>
                  <div>
                    <button type="button" onClick={() => { setReviewRecordsPage(reviewRecordsPage - 1); refreshReviewRecords(reviewRecordsPage - 1); }} disabled={reviewRecordsPage <= 1 || reviewRecordsLoading}>上一页</button>
                    <button type="button" onClick={() => { setReviewRecordsPage(reviewRecordsPage + 1); refreshReviewRecords(reviewRecordsPage + 1); }} disabled={!reviewRecordsHasNextPage || reviewRecordsLoading}>下一页</button>
                  </div>
                </div>
              ) : null}
            </section>
          </div>
        </section>
      </div>
    </div>
  );
}
