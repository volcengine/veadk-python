import { useEffect, useMemo, useState } from "react";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { Tooltip } from "@openai/apps-sdk-ui/components/Tooltip";
import type { IntelligentDevelopmentReleaseRef } from "../blocks";
import {
  deleteIntelligentDevelopmentVersion,
  fetchIntelligentDevelopmentProjects,
  fetchIntelligentDevelopmentVersions,
  fetchIntelligentDevelopmentVersionSource,
  type IntelligentDevelopmentProject,
  type IntelligentDevelopmentVersion,
} from "../adk/intelligentDevelopment";
import { CodeBrowserDialog } from "../ui/CodeBrowserDialog";
import { SourceRefreshIcon } from "../ui/icons/SourceWorkspaceIcons";
import { StudioConfirmDialog } from "../ui/StudioConfirmDialog";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
import type {
  IntelligentCreateBaseVersion,
  IntelligentDevelopmentCapabilities,
} from "./IntelligentCreate";

function ProjectArchiveIcon() {
  return (
    <svg
      className="ic-project-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M4.5 7.5h15v11h-15z" />
      <path d="M7 7.5V5h10v2.5M9 11h6" />
    </svg>
  );
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`ic-chevron${expanded ? " is-expanded" : ""}`}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="m5.5 3.5 4 4-4 4" />
    </svg>
  );
}

function CompareCheckIcon() {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="m3.5 8.2 2.7 2.7 6.3-6.1" />
    </svg>
  );
}

function formatVersionTime(value: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function releaseFromVersion(
  version: IntelligentDevelopmentVersion,
): IntelligentDevelopmentReleaseRef {
  return {
    sessionId: version.sourceSessionId,
    projectId: version.projectId,
    versionId: version.versionId,
    parentVersionId: version.parentVersionId,
    artifactSha256: version.artifactSha256,
    validationReportSha256: version.validationReportSha256,
    agentName: version.agentName,
    entryPoint: version.entryPoint,
    fileCount: version.fileCount,
    artifactSize: version.artifactSize,
    validatedAt: version.validatedAt,
    gateSummary: version.gateSummary,
    deployable: true,
    verified: version.verified,
    validationSummary: version.validationSummary,
  };
}

interface IntelligentProjectLibraryProps {
  capabilities: IntelligentDevelopmentCapabilities | null;
  capabilitiesLoading: boolean;
  creating: boolean;
  selectedBaseVersionId?: string;
  onSelectBaseVersion: (base: IntelligentCreateBaseVersion) => void;
  onClearBaseVersion: () => void;
  onDownload: (delivery: IntelligentDevelopmentReleaseRef) => Promise<void>;
  onDeploy: (delivery: IntelligentDevelopmentReleaseRef) => void;
}

export function IntelligentProjectLibrary({
  capabilities,
  capabilitiesLoading,
  creating,
  selectedBaseVersionId,
  onSelectBaseVersion,
  onClearBaseVersion,
  onDownload,
  onDeploy,
}: IntelligentProjectLibraryProps) {
  const [projects, setProjects] = useState<IntelligentDevelopmentProject[]>([]);
  const [projectsLoading, setProjectsLoading] = useState(true);
  const [projectsError, setProjectsError] = useState("");
  const [projectsRefresh, setProjectsRefresh] = useState(0);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [versions, setVersions] = useState<
    Record<string, IntelligentDevelopmentVersion[]>
  >({});
  const [versionsLoading, setVersionsLoading] = useState("");
  const [versionsError, setVersionsError] = useState<Record<string, string>>({});
  const [versionsRefresh, setVersionsRefresh] = useState(0);
  const [busyAction, setBusyAction] = useState("");
  const [feedback, setFeedback] = useState<{
    kind: "error" | "status";
    text: string;
  } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{
    project: IntelligentDevelopmentProject;
    version: IntelligentDevelopmentVersion;
  } | null>(null);
  const [deleteError, setDeleteError] = useState("");
  const [browserDelivery, setBrowserDelivery] =
    useState<IntelligentDevelopmentReleaseRef | null>(null);
  const [browserComparison, setBrowserComparison] = useState<{
    base: IntelligentDevelopmentReleaseRef;
    baseLabel: string;
    targetLabel: string;
  } | null>(null);
  const [compareSelection, setCompareSelection] = useState<{
    projectId: string;
    versionIds: string[];
  } | null>(null);
  const storageEnabled = capabilities?.projectStorageEnabled === true;

  useEffect(() => {
    if (!storageEnabled) return;
    const controller = new AbortController();
    setProjectsLoading(true);
    setProjectsError("");
    void fetchIntelligentDevelopmentProjects(controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) setProjects(items);
      })
      .catch((cause) => {
        if (!controller.signal.aborted) {
          setProjectsError(
            cause instanceof Error ? cause.message : "无法读取已保存项目。",
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setProjectsLoading(false);
      });
    return () => controller.abort();
  }, [projectsRefresh, storageEnabled]);

  useEffect(() => {
    if (!selectedProjectId || !storageEnabled) return;
    const controller = new AbortController();
    setVersionsLoading(selectedProjectId);
    setVersionsError((current) => ({ ...current, [selectedProjectId]: "" }));
    void fetchIntelligentDevelopmentVersions(selectedProjectId, controller.signal)
      .then((items) => {
        if (!controller.signal.aborted) {
          setVersions((current) => ({ ...current, [selectedProjectId]: items }));
        }
      })
      .catch((cause) => {
        if (!controller.signal.aborted) {
          setVersionsError((current) => ({
            ...current,
            [selectedProjectId]: cause instanceof Error
              ? cause.message
              : "无法读取项目版本。",
          }));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setVersionsLoading("");
      });
    return () => controller.abort();
  }, [selectedProjectId, storageEnabled, versionsRefresh]);

  const browserProject = useMemo(() => ({
    name: browserDelivery?.agentName ?? "Agent",
    files: browserDelivery?.files ?? [],
  }), [browserDelivery]);

  function selectBaseVersion(
    project: IntelligentDevelopmentProject,
    versionId: string,
    versionLabel: string,
  ) {
    onSelectBaseVersion({
      projectId: project.projectId,
      versionId,
      projectName: project.name,
      versionLabel,
    });
    setFeedback(null);
  }

  async function viewVersion(version: IntelligentDevelopmentVersion) {
    const action = `view:${version.versionId}`;
    if (busyAction) return;
    setBusyAction(action);
    setFeedback(null);
    try {
      setBrowserComparison(null);
      setBrowserDelivery(await fetchIntelligentDevelopmentVersionSource(version));
    } catch (cause) {
      setFeedback({
        kind: "error",
        text: cause instanceof Error ? cause.message : "无法读取项目源码。",
      });
    } finally {
      setBusyAction("");
    }
  }

  function startVersionComparison(
    project: IntelligentDevelopmentProject,
    projectVersions: IntelligentDevelopmentVersion[],
  ) {
    const target = projectVersions.find(
      (version) => version.versionId === project.latestVersionId,
    ) ?? projectVersions[0];
    const base = projectVersions.find(
      (version) => version.versionId === target?.parentVersionId,
    ) ?? projectVersions.find((version) => version.versionId !== target?.versionId);
    setCompareSelection({
      projectId: project.projectId,
      versionIds: base && target ? [base.versionId, target.versionId] : [],
    });
    setFeedback(null);
  }

  function toggleCompareVersion(projectId: string, versionId: string) {
    setCompareSelection((current) => {
      if (!current || current.projectId !== projectId) return current;
      const selected = current.versionIds.includes(versionId);
      return {
        ...current,
        versionIds: selected
          ? current.versionIds.filter((item) => item !== versionId)
          : current.versionIds.length < 2
            ? [...current.versionIds, versionId]
            : current.versionIds,
      };
    });
  }

  async function viewVersionComparison(
    project: IntelligentDevelopmentProject,
    projectVersions: IntelligentDevelopmentVersion[],
  ) {
    if (busyAction || compareSelection?.projectId !== project.projectId) return;
    const selected = projectVersions
      .filter((version) => compareSelection.versionIds.includes(version.versionId))
      .sort((left, right) => (
        new Date(left.createdAt).getTime() - new Date(right.createdAt).getTime()
        || left.versionId.localeCompare(right.versionId)
      ));
    if (selected.length !== 2) return;
    const action = `compare:${project.projectId}`;
    setBusyAction(action);
    setFeedback(null);
    try {
      const [base, target] = await Promise.all([
        fetchIntelligentDevelopmentVersionSource(selected[0]),
        fetchIntelligentDevelopmentVersionSource(selected[1]),
      ]);
      setBrowserComparison({
        base,
        baseLabel: formatVersionTime(selected[0].createdAt),
        targetLabel: formatVersionTime(selected[1].createdAt),
      });
      setBrowserDelivery(target);
    } catch (cause) {
      setFeedback({
        kind: "error",
        text: cause instanceof Error ? cause.message : "无法读取项目版本。",
      });
    } finally {
      setBusyAction("");
    }
  }

  async function downloadVersion(version: IntelligentDevelopmentVersion) {
    const action = `download:${version.versionId}`;
    if (busyAction) return;
    setBusyAction(action);
    setFeedback(null);
    try {
      await onDownload(releaseFromVersion(version));
      setFeedback({ kind: "status", text: "源码已下载。" });
    } catch (cause) {
      setFeedback({
        kind: "error",
        text: cause instanceof Error ? cause.message : "下载源码失败。",
      });
    } finally {
      setBusyAction("");
    }
  }

  async function deployVersion(version: IntelligentDevelopmentVersion) {
    const action = `deploy:${version.versionId}`;
    if (busyAction) return;
    setBusyAction(action);
    setFeedback(null);
    try {
      onDeploy(await fetchIntelligentDevelopmentVersionSource(version));
    } catch (cause) {
      setFeedback({
        kind: "error",
        text: cause instanceof Error ? cause.message : "无法准备部署源码。",
      });
      setBusyAction("");
    }
  }

  async function confirmDelete() {
    if (!deleteTarget || busyAction) return;
    const { project, version } = deleteTarget;
    setBusyAction(`delete:${version.versionId}`);
    setDeleteError("");
    try {
      const { projectDeleted } = await deleteIntelligentDevelopmentVersion(
        project.projectId,
        version.versionId,
      );
      if (selectedBaseVersionId === version.versionId) onClearBaseVersion();
      setDeleteTarget(null);
      if (compareSelection?.versionIds.includes(version.versionId)) {
        setCompareSelection(null);
      }
      if (projectDeleted) setSelectedProjectId("");
      setProjectsRefresh((value) => value + 1);
      setVersionsRefresh((value) => value + 1);
    } catch (cause) {
      setDeleteError(
        cause instanceof Error ? cause.message : "删除项目版本失败。",
      );
    } finally {
      setBusyAction("");
    }
  }

  return (
    <>
      <section className="ic-panel ic-projects-panel" aria-labelledby="saved-projects-title">
        <div className="ic-projects-heading">
          <span className="ic-project-icon-wrap"><ProjectArchiveIcon /></span>
          <div>
            <h2 id="saved-projects-title">已保存项目</h2>
            <p>选择已有版本继续优化，或查看、下载和部署源码。</p>
          </div>
          {projects.length > 0 ? (
            <Tooltip compact content="刷新项目列表">
              <button
                type="button"
                className={`ic-refresh ic-icon-button${projectsLoading ? " is-loading" : ""}`}
                onClick={() => setProjectsRefresh((value) => value + 1)}
                disabled={projectsLoading}
                aria-label="刷新项目列表"
                aria-busy={projectsLoading}
              >
                <SourceRefreshIcon />
              </button>
            </Tooltip>
          ) : null}
        </div>

        {capabilitiesLoading ? (
          <div className="ic-project-state" role="status" aria-live="polite">
            <TextShimmer as="span" duration={2.2} spread={16}>
              正在检查项目存储…
            </TextShimmer>
          </div>
        ) : capabilities === null ? (
          <div className="ic-project-state" role="alert">
            <strong>暂时无法读取项目</strong>
            <span>无法确认项目存储状态，请稍后重试。</span>
          </div>
        ) : !storageEnabled ? (
          <div className="ic-project-state" role="alert">
            <strong>暂时无法读取项目</strong>
            <span>
              {capabilities.projectStorageReason
                || capabilities.reason
                || "项目存储尚未配置。"}
            </span>
          </div>
        ) : projectsLoading && projects.length === 0 ? (
          <div className="ic-project-state" role="status" aria-live="polite">
            <TextShimmer as="span" duration={2.2} spread={16}>
              正在读取已保存项目…
            </TextShimmer>
          </div>
        ) : projectsError && projects.length === 0 ? (
          <div className="ic-project-state" role="alert">
            <strong>无法读取已保存项目</strong>
            <span>{projectsError}</span>
            <button
              type="button"
              className="ic-secondary ic-state-action"
              onClick={() => setProjectsRefresh((value) => value + 1)}
            >重试</button>
          </div>
        ) : projects.length === 0 ? (
          <div className="ic-project-state">
            <strong>还没有已保存的项目</strong>
            <span>完成首次构建后，源码会自动保存在这里。</span>
          </div>
        ) : (
          <div className="ic-project-list" aria-busy={projectsLoading || undefined}>
            {projectsError ? (
              <div className="ic-inline-error" role="alert">
                <span>{projectsError}</span>
                <button
                  type="button"
                  onClick={() => setProjectsRefresh((value) => value + 1)}
                >重试</button>
              </div>
            ) : null}
            {projects.map((project) => {
              const expanded = selectedProjectId === project.projectId;
              const projectVersions = versions[project.projectId] ?? [];
              const versionError = versionsError[project.projectId] ?? "";
              const projectComparison = compareSelection?.projectId === project.projectId
                ? compareSelection
                : null;
              return (
                <article
                  className={`ic-project${expanded ? " is-expanded" : ""}`}
                  key={project.projectId}
                >
                  <div className="ic-project-summary">
                    <button
                      type="button"
                      className="ic-project-disclosure"
                      aria-expanded={expanded}
                      aria-controls={`versions-${project.projectId}`}
                      onClick={() => setSelectedProjectId(
                        expanded ? "" : project.projectId,
                      )}
                    >
                      <ChevronIcon expanded={expanded} />
                      <span className="ic-project-copy">
                        <strong title={project.name}>{project.name}</strong>
                        <span>
                          {project.versionCount} 个版本 · 更新于 {formatVersionTime(project.updatedAt)}
                        </span>
                      </span>
                    </button>
                    {expanded && projectVersions.length >= 2 ? (
                      <div className="ic-project-compare-actions">
                        {projectComparison ? (
                          <>
                            <span aria-live="polite">
                              已选择 {projectComparison.versionIds.length}/2
                            </span>
                            <button
                              type="button"
                              className="ic-version-action"
                              onClick={() => setCompareSelection(null)}
                              disabled={Boolean(busyAction)}
                            >取消</button>
                            <button
                              type="button"
                              className="ic-version-compare-primary"
                              onClick={() => void viewVersionComparison(project, projectVersions)}
                              disabled={projectComparison.versionIds.length !== 2 || Boolean(busyAction)}
                            >
                              {busyAction === `compare:${project.projectId}` ? "读取中…" : "查看对比"}
                            </button>
                          </>
                        ) : (
                          <button
                            type="button"
                            className="ic-version-compare-trigger"
                            onClick={() => startVersionComparison(project, projectVersions)}
                            disabled={Boolean(busyAction)}
                          >对比版本</button>
                        )}
                      </div>
                    ) : null}
                  </div>

                  {expanded ? (
                    <div
                      className="ic-version-region"
                      id={`versions-${project.projectId}`}
                      aria-busy={versionsLoading === project.projectId || undefined}
                    >
                      {versionError && projectVersions.length > 0 ? (
                        <div className="ic-version-error" role="alert">
                          <span>{versionError}</span>
                          <button
                            type="button"
                            onClick={() => setVersionsRefresh((value) => value + 1)}
                          >重试</button>
                        </div>
                      ) : null}
                      {versionsLoading === project.projectId
                        && projectVersions.length === 0 ? (
                          <TextShimmer as="p" duration={2.2} spread={16}>
                            正在读取项目版本…
                          </TextShimmer>
                        ) : versionError && projectVersions.length === 0 ? (
                          <div className="ic-version-error" role="alert">
                            <span>{versionError}</span>
                            <button
                              type="button"
                              onClick={() => setVersionsRefresh((value) => value + 1)}
                            >重试</button>
                          </div>
                        ) : projectVersions.length === 0 ? (
                          <p className="ic-version-empty">这个项目还没有可用版本。</p>
                        ) : (
                          <ul className="ic-version-list">
                            {projectVersions.map((version, index) => {
                              const versionSummary = version.intentSummary
                                || version.validationSummary
                                || "暂无版本描述";
                              const isCompareSelected = projectComparison
                                ?.versionIds.includes(version.versionId) === true;
                              const isCompareDisabled = Boolean(busyAction)
                                || (!isCompareSelected
                                  && (projectComparison?.versionIds.length ?? 0) >= 2);
                              return (
                                <li
                                  key={version.versionId}
                                  className={[
                                    projectComparison ? "is-comparing" : "",
                                    isCompareSelected ? "is-compare-selected" : "",
                                  ].filter(Boolean).join(" ") || undefined}
                                >
                                  {projectComparison ? (
                                    <label className={`ic-version-compare-check${
                                      isCompareSelected ? " is-selected" : ""
                                    }${isCompareDisabled ? " is-disabled" : ""}`}>
                                      <input
                                        type="checkbox"
                                        checked={isCompareSelected}
                                        onChange={() => toggleCompareVersion(project.projectId, version.versionId)}
                                        disabled={isCompareDisabled}
                                      />
                                      <span className="ic-version-compare-box" aria-hidden="true">
                                        {isCompareSelected ? <CompareCheckIcon /> : null}
                                      </span>
                                      <span>{isCompareSelected ? "已选择" : "选择"}</span>
                                    </label>
                                  ) : null}
                                  <div className="ic-version-copy">
                                    <div>
                                      <strong>
                                        {index === 0
                                          ? "最新版本"
                                          : formatVersionTime(version.createdAt)}
                                      </strong>
                                      <span className={`ic-version-status${version.verified ? " is-verified" : ""}`}>
                                        {version.verified ? "已验证" : "待确认"}
                                      </span>
                                    </div>
                                    <Tooltip
                                      content={versionSummary}
                                      contentClassName="ic-version-tooltip"
                                      maxWidth={420}
                                      interactive
                                    >
                                      <p
                                        className="ic-version-description"
                                        tabIndex={0}
                                      >
                                        {versionSummary}
                                      </p>
                                    </Tooltip>
                                    <span>
                                      {formatVersionTime(version.createdAt)} · {version.fileCount} 个文件
                                    </span>
                                  </div>
                                  <div className="ic-version-actions">
                                    <button
                                      type="button"
                                      className="ic-version-action"
                                      onClick={() => void viewVersion(version)}
                                      disabled={Boolean(busyAction)}
                                    >
                                      {busyAction === `view:${version.versionId}`
                                        ? "读取中…"
                                        : "查看源码"}
                                    </button>
                                    <button
                                      type="button"
                                      className="ic-version-action"
                                      onClick={() => void downloadVersion(version)}
                                      disabled={Boolean(busyAction)}
                                    >
                                      {busyAction === `download:${version.versionId}`
                                        ? "下载中…"
                                        : "下载"}
                                    </button>
                                    <button
                                      type="button"
                                      className="ic-version-action"
                                      onClick={() => void deployVersion(version)}
                                      disabled={Boolean(busyAction)}
                                    >
                                      {busyAction === `deploy:${version.versionId}`
                                        ? "准备中…"
                                        : "部署"}
                                    </button>
                                    <button
                                      type="button"
                                      className="ic-version-action"
                                      onClick={() => selectBaseVersion(
                                        project,
                                        version.versionId,
                                        version.versionId === project.latestVersionId
                                          ? "最新版本"
                                          : formatVersionTime(version.createdAt),
                                      )}
                                      disabled={creating || Boolean(busyAction)}
                                    >去优化</button>
                                    <Button
                                      type="button"
                                      className="ic-version-delete"
                                      color="danger"
                                      variant="ghost"
                                      size="sm"
                                      pill={false}
                                      onClick={() => {
                                        setDeleteError("");
                                        setDeleteTarget({ project, version });
                                      }}
                                      disabled={Boolean(busyAction)}
                                    >
                                      删除
                                    </Button>
                                  </div>
                                </li>
                              );
                            })}
                          </ul>
                        )}
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        )}
        {feedback ? (
          <p
            className={`ic-notice${feedback.kind === "error" ? " is-error" : ""}`}
            role={feedback.kind === "error" ? "alert" : "status"}
            aria-live={feedback.kind === "error" ? "assertive" : "polite"}
          >
            {feedback.text}
          </p>
        ) : null}
      </section>

      <CodeBrowserDialog
        project={browserProject}
        open={browserDelivery !== null}
        comparison={browserComparison ? {
          baseProject: {
            name: browserComparison.base.agentName,
            files: browserComparison.base.files ?? [],
          },
          baseLabel: browserComparison.baseLabel,
          targetLabel: browserComparison.targetLabel,
        } : undefined}
        onClose={() => {
          setBrowserDelivery(null);
          setBrowserComparison(null);
        }}
        onChange={() => undefined}
        readOnly
      />
      {deleteTarget ? (
        <StudioConfirmDialog
          title="删除这个版本？"
          description={deleteTarget.project.versionCount === 1
            ? `“${deleteTarget.project.name}”只有这一个版本，删除后项目也会移除。此操作无法撤销。`
            : "该版本的源码和验证记录将永久删除，其他版本不受影响。"}
          error={deleteError}
          confirmLabel="删除版本"
          variant="danger"
          busy={busyAction === `delete:${deleteTarget.version.versionId}`}
          onCancel={() => {
            if (!busyAction) setDeleteTarget(null);
          }}
          onConfirm={() => void confirmDelete()}
        />
      ) : null}
    </>
  );
}
