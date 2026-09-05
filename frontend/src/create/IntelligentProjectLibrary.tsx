import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { createT } from "./i18n";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { Tooltip } from "@openai/apps-sdk-ui/components/Tooltip";
import type { IntelligentDevelopmentReleaseRef } from "../blocks";
import { localeCompatibleBackendText } from "../i18n/locales";
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

function formatVersionTime(value: string, locale: string, unknownLabel: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return unknownLabel;
  return new Intl.DateTimeFormat(locale, {
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
    ...(version.environment ? { environment: version.environment } : {}),
  };
}

export function migrationOptimizationUnavailableReason(
  origin: IntelligentDevelopmentProject["origin"],
  versions: Pick<IntelligentDevelopmentVersion, "migrationFramework">[],
  unavailableLabel = createT("common.notSupported"),
): string {
  if (origin !== "migration") return "";
  const framework = versions
    .map((version) => version.migrationFramework?.trim().toLowerCase() ?? "")
    .find(Boolean);
  return framework === "any" || framework === "dify" ? "" : unavailableLabel;
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
  origin?: IntelligentDevelopmentProject["origin"];
  title?: string;
  description?: string;
  emptyTitle?: string;
  emptyDescription?: string;
  initialProjectId?: string;
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
  origin = "intelligent-development",
  title,
  description,
  emptyTitle,
  emptyDescription,
  initialProjectId,
}: IntelligentProjectLibraryProps) {
  const { t, i18n } = useTranslation("create");
  const locale = i18n.resolvedLanguage || i18n.language;
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
  const appliedInitialProjectId = useRef("");
  const storageEnabled = capabilities?.projectStorageEnabled === true;

  useEffect(() => {
    if (!storageEnabled) return;
    const controller = new AbortController();
    setProjectsLoading(true);
    setProjectsError("");
    const request = origin === "intelligent-development"
      ? fetchIntelligentDevelopmentProjects(controller.signal)
      : fetchIntelligentDevelopmentProjects(controller.signal, origin);
    void request
      .then((items) => {
        if (!controller.signal.aborted) setProjects(items);
      })
      .catch((cause) => {
        if (!controller.signal.aborted) {
          setProjectsError(
            cause instanceof Error ? cause.message : t("projectLibrary.errors.projects"),
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setProjectsLoading(false);
      });
    return () => controller.abort();
  }, [origin, projectsRefresh, storageEnabled, t]);

  useEffect(() => {
    if (
      initialProjectId
      && appliedInitialProjectId.current !== initialProjectId
      && projects.some((project) => project.projectId === initialProjectId)
    ) {
      appliedInitialProjectId.current = initialProjectId;
      setSelectedProjectId(initialProjectId);
    }
  }, [initialProjectId, projects]);

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
              : t("projectLibrary.errors.versions"),
          }));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setVersionsLoading("");
      });
    return () => controller.abort();
  }, [selectedProjectId, storageEnabled, versionsRefresh, t]);

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
        text: cause instanceof Error ? cause.message : t("projectLibrary.errors.source"),
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
        baseLabel: formatVersionTime(selected[0].createdAt, locale, t("projectLibrary.unknownTime")),
        targetLabel: formatVersionTime(selected[1].createdAt, locale, t("projectLibrary.unknownTime")),
      });
      setBrowserDelivery(target);
    } catch (cause) {
      setFeedback({
        kind: "error",
        text: cause instanceof Error ? cause.message : t("projectLibrary.errors.versions"),
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
      setFeedback({ kind: "status", text: t("projectLibrary.sourceDownloaded") });
    } catch (cause) {
      setFeedback({
        kind: "error",
        text: cause instanceof Error ? cause.message : t("projectLibrary.errors.download"),
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
        text: cause instanceof Error ? cause.message : t("projectLibrary.errors.prepareDeployment"),
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
        cause instanceof Error ? cause.message : t("projectLibrary.errors.deleteVersion"),
      );
    } finally {
      setBusyAction("");
    }
  }

  return (
    <>
      <section
        className="ic-panel ic-projects-panel"
        aria-labelledby={`${origin}-projects-title`}
      >
        <div className="ic-projects-heading">
          <span className="ic-project-icon-wrap"><ProjectArchiveIcon /></span>
          <div>
            <h2 id={`${origin}-projects-title`}>
              {title ?? t("projectLibrary.title")}
            </h2>
            <p>{description ?? t("projectLibrary.description")}</p>
          </div>
          {projects.length > 0 ? (
            <Tooltip compact content={t("projectLibrary.refresh")}>
              <button
                type="button"
                className={`ic-refresh ic-icon-button${projectsLoading ? " is-loading" : ""}`}
                onClick={() => setProjectsRefresh((value) => value + 1)}
                disabled={projectsLoading}
                aria-label={t("projectLibrary.refresh")}
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
              {t("projectLibrary.checkingStorage")}
            </TextShimmer>
          </div>
        ) : capabilities === null ? (
          <div className="ic-project-state" role="alert">
            <strong>{t("projectLibrary.unavailableTitle")}</strong>
            <span>{t("projectLibrary.storageCheckError")}</span>
          </div>
        ) : !storageEnabled ? (
          <div className="ic-project-state" role="alert">
            <strong>{t("projectLibrary.unavailableTitle")}</strong>
            <span>
              {localeCompatibleBackendText(capabilities.projectStorageReason, locale)
                || localeCompatibleBackendText(capabilities.reason, locale)
                || t("projectLibrary.storageNotConfigured")}
            </span>
          </div>
        ) : projectsLoading && projects.length === 0 ? (
          <div className="ic-project-state" role="status" aria-live="polite">
            <TextShimmer as="span" duration={2.2} spread={16}>
              {origin === "migration" ? t("projectLibrary.loadingMigrated") : t("projectLibrary.loadingSaved")}
            </TextShimmer>
          </div>
        ) : projectsError && projects.length === 0 ? (
          <div className="ic-project-state" role="alert">
            <strong>
              {origin === "migration" ? t("projectLibrary.errors.migrated") : t("projectLibrary.errors.saved")}
            </strong>
            <span>{projectsError}</span>
            <button
              type="button"
              className="ic-secondary ic-state-action"
              onClick={() => setProjectsRefresh((value) => value + 1)}
            >{t("common.retry")}</button>
          </div>
        ) : projects.length === 0 ? (
          <div className="ic-project-state">
            <strong>
              {emptyTitle ?? (origin === "migration"
                ? t("projectLibrary.empty.migratedTitle")
                : t("projectLibrary.empty.savedTitle"))}
            </strong>
            <span>
              {emptyDescription ?? (origin === "migration"
                ? t("projectLibrary.empty.migratedDescription")
                : t("projectLibrary.empty.savedDescription"))}
            </span>
          </div>
        ) : (
          <div className="ic-project-list" aria-busy={projectsLoading || undefined}>
            {projectsError ? (
              <div className="ic-inline-error" role="alert">
                <span>{projectsError}</span>
                <button
                  type="button"
                  onClick={() => setProjectsRefresh((value) => value + 1)}
                >{t("common.retry")}</button>
              </div>
            ) : null}
            {projects.map((project) => {
              const expanded = selectedProjectId === project.projectId;
              const projectVersions = versions[project.projectId] ?? [];
              const versionError = versionsError[project.projectId] ?? "";
              const projectComparison = compareSelection?.projectId === project.projectId
                ? compareSelection
                : null;
              const optimizationUnavailableReason =
                migrationOptimizationUnavailableReason(origin, projectVersions, t("common.notSupported"));
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
                          {t("projectLibrary.projectSummary", {
                            count: project.versionCount,
                            time: formatVersionTime(project.updatedAt, locale, t("projectLibrary.unknownTime")),
                          })}
                        </span>
                      </span>
                    </button>
                    {expanded && projectVersions.length >= 2 ? (
                      <div className="ic-project-compare-actions">
                        {projectComparison ? (
                          <>
                            <span aria-live="polite">
                              {t("projectLibrary.compare.selected", { count: projectComparison.versionIds.length })}
                            </span>
                            <button
                              type="button"
                              className="ic-version-action"
                              onClick={() => setCompareSelection(null)}
                              disabled={Boolean(busyAction)}
                            >{t("common.cancel")}</button>
                            <button
                              type="button"
                              className="ic-version-compare-primary"
                              onClick={() => void viewVersionComparison(project, projectVersions)}
                              disabled={projectComparison.versionIds.length !== 2 || Boolean(busyAction)}
                            >
                              {busyAction === `compare:${project.projectId}` ? t("common.loading") : t("projectLibrary.compare.view")}
                            </button>
                          </>
                        ) : (
                          <button
                            type="button"
                            className="ic-version-compare-trigger"
                            onClick={() => startVersionComparison(project, projectVersions)}
                            disabled={Boolean(busyAction)}
                          >{t("projectLibrary.compare.start")}</button>
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
                          >{t("common.retry")}</button>
                        </div>
                      ) : null}
                      {versionsLoading === project.projectId
                        && projectVersions.length === 0 ? (
                          <TextShimmer as="p" duration={2.2} spread={16}>
                            {t("projectLibrary.loadingVersions")}
                          </TextShimmer>
                        ) : versionError && projectVersions.length === 0 ? (
                          <div className="ic-version-error" role="alert">
                            <span>{versionError}</span>
                            <button
                              type="button"
                              onClick={() => setVersionsRefresh((value) => value + 1)}
                            >{t("common.retry")}</button>
                          </div>
                        ) : projectVersions.length === 0 ? (
                          <p className="ic-version-empty">{t("projectLibrary.empty.noVersions")}</p>
                        ) : (
                          <ul className="ic-version-list">
                            {projectVersions.map((version, index) => {
                              const versionSummary = version.intentSummary
                                || version.validationSummary
                                || t("projectLibrary.noVersionDescription");
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
                                      <span>{isCompareSelected ? t("projectLibrary.compare.selectedLabel") : t("projectLibrary.compare.select")}</span>
                                    </label>
                                  ) : null}
                                  <div className="ic-version-copy">
                                    <div>
                                      <strong>
                                        {index === 0
                                          ? t("projectLibrary.latestVersion")
                                          : formatVersionTime(version.createdAt, locale, t("projectLibrary.unknownTime"))}
                                      </strong>
                                      <span className={`ic-version-status${version.verified ? " is-verified" : ""}`}>
                                        {version.verified ? t("projectLibrary.verified") : t("projectLibrary.pendingVerification")}
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
                                      {t("projectLibrary.versionSummary", {
                                        time: formatVersionTime(version.createdAt, locale, t("projectLibrary.unknownTime")),
                                        count: version.fileCount,
                                      })}
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
                                        ? t("common.loading")
                                        : t("projectLibrary.viewSource")}
                                    </button>
                                    <button
                                      type="button"
                                      className="ic-version-action"
                                      onClick={() => void downloadVersion(version)}
                                      disabled={Boolean(busyAction)}
                                    >
                                      {busyAction === `download:${version.versionId}`
                                        ? t("projectLibrary.downloading")
                                        : t("projectLibrary.download")}
                                    </button>
                                    <button
                                      type="button"
                                      className="ic-version-action"
                                      onClick={() => void deployVersion(version)}
                                      disabled={Boolean(busyAction)}
                                    >
                                      {busyAction === `deploy:${version.versionId}`
                                        ? t("intelligent.actions.preparing")
                                        : t("common.deploy")}
                                    </button>
                                    {optimizationUnavailableReason ? (
                                      <Tooltip
                                        compact
                                        content={optimizationUnavailableReason}
                                      >
                                        <span
                                          className="ic-disabled-action-tooltip"
                                          tabIndex={0}
                                          aria-label={t("projectLibrary.optimizeUnavailable")}
                                        >
                                          <button
                                            type="button"
                                            className="ic-version-action"
                                            disabled
                                          >{t("projectLibrary.optimize")}</button>
                                        </span>
                                      </Tooltip>
                                    ) : (
                                      <button
                                        type="button"
                                        className="ic-version-action"
                                        onClick={() => selectBaseVersion(
                                          project,
                                          version.versionId,
                                          version.versionId === project.latestVersionId
                                            ? t("projectLibrary.latestVersion")
                                            : formatVersionTime(version.createdAt, locale, t("projectLibrary.unknownTime")),
                                        )}
                                        disabled={creating || Boolean(busyAction)}
                                      >{t("projectLibrary.optimize")}</button>
                                    )}
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
                                      {t("common.delete")}
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
          title={t("projectLibrary.delete.title")}
          description={deleteTarget.project.versionCount === 1
            ? t("projectLibrary.delete.onlyVersion", { name: deleteTarget.project.name })
            : t("projectLibrary.delete.description")}
          error={deleteError}
          confirmLabel={t("projectLibrary.delete.confirm")}
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
