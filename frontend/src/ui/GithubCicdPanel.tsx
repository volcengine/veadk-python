import { useEffect, useMemo, useState, type FormEvent, type SVGProps } from "react";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import {
  bindGithubCicdRuntime,
  createGithubCicdPipeline,
  createGithubDeliveryCicdPipeline,
  getGithubCicdRuntimeBinding,
  GithubCicdPipelineError,
  type GithubCicdPipelineErrorDetail,
  type GithubCicdPipelineResult,
} from "../adk/client";
import type { CloudProvider } from "../adk/cloudProvider";
import type { AgentProject } from "../create/project";

interface GithubCicdPanelProps {
  project: AgentProject;
  region: string;
  cloudProvider: CloudProvider;
  runtimeId?: string;
  binding?: GithubCicdPipelineResult | null;
  disabled?: boolean;
  showSetup?: boolean;
  onPendingCicdChange?: (config: PendingGithubCicdConfig | null) => void;
  onBindingChange?: (binding: GithubCicdPipelineResult | null) => void;
}

type DeliveryMode = "source" | "cicd";

export interface PendingGithubCicdConfig {
  githubUrl: string;
  githubToken: string;
  baseBranch: string;
  volcengineAccessKey: string;
  volcengineSecretKey: string;
  volcengineSessionToken?: string;
  cloudProvider: CloudProvider;
  pipelineId?: string;
}

function githubRepoLabel(url: string, t: TFunction): string {
  const trimmed = url.trim();
  if (!trimmed) return t("githubCicd.repository");
  const match = trimmed.match(
    /github\.com[:/](?<owner>[^/\s]+)\/(?<repo>[^/\s#?]+?)(?:\.git)?(?:[/?#].*)?$/,
  );
  if (!match?.groups) return trimmed;
  return `${match.groups.owner}/${match.groups.repo}`;
}

function normalizeBranch(value: string): string {
  const trimmed = value.trim();
  return trimmed || "main";
}

function errorDetailFromUnknown(error: unknown, t: TFunction): GithubCicdPipelineErrorDetail {
  if (error instanceof GithubCicdPipelineError) return error.detail;
  if (error instanceof Error) return { message: error.message };
  return { message: String(error || t("githubCicd.syncFailed")) };
}

function deliveryStatusLabel(result: GithubCicdPipelineResult, t: TFunction): string {
  if (result.status === "cicd-bound") return t("githubCicd.status.mounted");
  if (result.status === "bound") return t("githubCicd.status.bound");
  if (result.status === "succeeded") return t("githubCicd.status.synced");
  return result.status || t("githubCicd.status.created");
}

function ExternalLinkIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M6.2 3.8H4.3A1.8 1.8 0 0 0 2.5 5.6v6.1a1.8 1.8 0 0 0 1.8 1.8h6.1a1.8 1.8 0 0 0 1.8-1.8V9.8" />
      <path d="M8.7 2.5h4.8v4.8" />
      <path d="m13.1 2.9-6 6" />
    </svg>
  );
}

function SpinnerIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <circle
        cx="8"
        cy="8"
        r="5.5"
        stroke="currentColor"
        strokeWidth="1.7"
        opacity="0.24"
      />
      <path
        d="M13.5 8A5.5 5.5 0 0 0 8 2.5"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function GithubCicdPanel({
  project,
  region,
  cloudProvider,
  runtimeId,
  binding,
  disabled = false,
  showSetup = true,
  onPendingCicdChange,
  onBindingChange,
}: GithubCicdPanelProps) {
  const { t } = useTranslation("ui");
  const [githubUrl, setGithubUrl] = useState("");
  const [githubToken, setGithubToken] = useState("");
  const [baseBranch, setBaseBranch] = useState("main");
  const [volcengineAccessKey, setVolcengineAccessKey] = useState("");
  const [volcengineSecretKey, setVolcengineSecretKey] = useState("");
  const [volcengineSessionToken, setVolcengineSessionToken] = useState("");
  const [mode, setMode] = useState<DeliveryMode>("source");
  const [submitting, setSubmitting] = useState(false);
  const [loadingBinding, setLoadingBinding] = useState(false);
  const [result, setResult] = useState<GithubCicdPipelineResult | null>(null);
  const [error, setError] = useState<GithubCicdPipelineErrorDetail | null>(null);
  const [pendingCicdSelected, setPendingCicdSelected] = useState(false);

  useEffect(() => {
    if (binding?.pipelineId || binding?.runtimeId || binding?.status) {
      setResult(binding);
    }
  }, [binding]);

  useEffect(() => {
    let cancelled = false;
    if (!runtimeId) {
      setResult(null);
      onBindingChange?.(null);
      return;
    }
    setLoadingBinding(true);
    getGithubCicdRuntimeBinding(runtimeId)
      .then((binding) => {
        if (cancelled) return;
        setResult(binding);
        onBindingChange?.(binding);
      })
      .catch((caught) => {
        if (!cancelled) setError(errorDetailFromUnknown(caught, t));
      })
      .finally(() => {
        if (!cancelled) setLoadingBinding(false);
      });
    return () => {
      cancelled = true;
    };
  }, [onBindingChange, runtimeId, t]);

  useEffect(() => {
    if (!onPendingCicdChange) return;
    if (runtimeId || mode !== "cicd" || !showSetup) {
      onPendingCicdChange(null);
      setPendingCicdSelected(false);
      return;
    }
    const nextUrl = githubUrl.trim();
    const nextToken = githubToken.trim();
    const nextAccessKey = volcengineAccessKey.trim();
    const nextSecretKey = volcengineSecretKey.trim();
    if (
      !nextUrl ||
      !nextToken ||
      !nextAccessKey ||
      !nextSecretKey ||
      project.files.length === 0
    ) {
      onPendingCicdChange(null);
      setPendingCicdSelected(false);
      return;
    }
    onPendingCicdChange({
      githubUrl: nextUrl,
      githubToken,
      baseBranch: normalizeBranch(baseBranch),
      volcengineAccessKey: nextAccessKey,
      volcengineSecretKey,
      volcengineSessionToken: volcengineSessionToken.trim(),
      pipelineId: result?.pipelineId,
      cloudProvider,
    });
  }, [
    baseBranch,
    cloudProvider,
    githubToken,
    githubUrl,
    mode,
    onPendingCicdChange,
    project.files.length,
    result?.pipelineId,
    runtimeId,
    showSetup,
    volcengineAccessKey,
    volcengineSecretKey,
    volcengineSessionToken,
  ]);

  const repoLabel = useMemo(() => githubRepoLabel(githubUrl, t), [githubUrl, t]);
  const resultGithub = result?.github;
  const resultRepo =
    resultGithub?.owner && resultGithub.repo
      ? `${resultGithub.owner}/${resultGithub.repo}`
      : resultGithub?.repo ?? repoLabel;
  const resultBranch = resultGithub?.branch ?? normalizeBranch(baseBranch);
  const resultRuntimeId = result?.runtimeId;
  const isCicdMode = mode === "cicd";
  const credentialProviderLabel =
    cloudProvider === "byteplus" ? "BytePlus" : t("githubCicd.volcengine");
  const readonlyBinding = !showSetup && Boolean(runtimeId);
  const canSubmit =
    showSetup &&
    !disabled &&
    !submitting &&
    githubUrl.trim().length > 0 &&
    githubToken.trim().length > 0 &&
    (isCicdMode
      ? volcengineAccessKey.trim().length > 0 &&
        volcengineSecretKey.trim().length > 0 &&
        (Boolean(runtimeId) || project.files.length > 0)
      : project.files.length > 0);
  const submitLabel = isCicdMode
    ? runtimeId
      ? t("githubCicd.mountDelivery")
      : pendingCicdSelected
        ? t("githubCicd.selectedForDeployment")
        : t("githubCicd.mountOnDeploy")
    : t("githubCicd.syncCode");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setResult(null);
    setError(null);
    try {
      if (isCicdMode && !runtimeId) {
        onPendingCicdChange?.({
          githubUrl: githubUrl.trim(),
          githubToken,
          baseBranch: normalizeBranch(baseBranch),
          volcengineAccessKey: volcengineAccessKey.trim(),
          volcengineSecretKey,
          volcengineSessionToken: volcengineSessionToken.trim(),
          cloudProvider,
        });
        setPendingCicdSelected(true);
        return;
      }
      const nextResult = isCicdMode && runtimeId
        ? await createGithubDeliveryCicdPipeline({
            githubUrl: githubUrl.trim(),
            githubToken,
            baseBranch: normalizeBranch(baseBranch),
            runtimeName: project.name,
            runtimeId: runtimeId ?? "",
            region,
            cloudProvider,
            projectPath: ".",
            volcengineAccessKey: volcengineAccessKey.trim(),
            volcengineSecretKey,
            volcengineSessionToken: volcengineSessionToken.trim(),
          })
        : await createGithubCicdPipeline({
            project,
            githubUrl: githubUrl.trim(),
            githubToken,
            baseBranch: normalizeBranch(baseBranch),
            region,
            cloudProvider,
          });
      const boundResult =
        !isCicdMode && runtimeId && nextResult.pipelineId
          ? await bindGithubCicdRuntime({
              pipelineId: nextResult.pipelineId,
              runtimeId,
              region,
              cloudProvider,
            })
          : nextResult;
      setResult(boundResult);
      onBindingChange?.(boundResult);
      if (isCicdMode && !runtimeId && boundResult.pipelineId) {
        onPendingCicdChange?.({
          githubUrl: githubUrl.trim(),
          githubToken,
          baseBranch: normalizeBranch(baseBranch),
          volcengineAccessKey: volcengineAccessKey.trim(),
          volcengineSecretKey,
          volcengineSessionToken: volcengineSessionToken.trim(),
          pipelineId: boundResult.pipelineId,
          cloudProvider,
        });
      }
      if (!isCicdMode || runtimeId) {
        setGithubToken("");
        setVolcengineAccessKey("");
        setVolcengineSecretKey("");
        setVolcengineSessionToken("");
      }
    } catch (caught) {
      setError(errorDetailFromUnknown(caught, t));
    } finally {
      setSubmitting(false);
    }
  }

  if (readonlyBinding && !loadingBinding && !result) {
    return null;
  }

  return (
    <section className="pp-config-section pp-github-cicd">
      <div className="pp-config-label pp-github-cicd-title">
        {showSetup ? (
          <div className="pp-github-cicd-tabs" role="tablist" aria-label={t("githubCicd.deliveryMode")}>
            <button
              type="button"
              className={mode === "source" ? "is-active" : ""}
              role="tab"
              aria-selected={mode === "source"}
              onClick={() => setMode("source")}
            >
              {t("githubCicd.sourceSync")}
            </button>
            <button
              type="button"
              role="tab"
              className={mode === "cicd" ? "is-active" : ""}
              aria-selected={mode === "cicd"}
              onClick={() => setMode("cicd")}
            >
              {t("githubCicd.mountDelivery")}
            </button>
          </div>
        ) : (
          <span>{t("githubCicd.delivery")}</span>
        )}
        {(submitting || loadingBinding) && (
          <span className="pp-github-cicd-status" role="status">
            <SpinnerIcon className="pp-ic spin" />
            {loadingBinding ? t("githubCicd.loading") : t("githubCicd.running")}
          </span>
        )}
      </div>
      {showSetup && (
        <p className="pp-github-cicd-copy">
          {isCicdMode
            ? runtimeId
              ? t("githubCicd.runtimeDeliveryHint")
              : t("githubCicd.initialDeliveryHint")
            : t("githubCicd.sourceSyncHint")}
        </p>
      )}

      {showSetup && (
        <form className="pp-github-cicd-form" onSubmit={handleSubmit}>
          <label className="pp-github-cicd-field">
            <span>{t("githubCicd.githubUrl")}</span>
            <input
              value={githubUrl}
              placeholder="https://github.com/org/repo"
              disabled={disabled || submitting}
              autoComplete="off"
              onChange={(event) => {
                setPendingCicdSelected(false);
                setGithubUrl(event.currentTarget.value);
              }}
            />
          </label>
          <label className="pp-github-cicd-field">
            <span>{t("githubCicd.token")}</span>
            <input
              type="password"
              value={githubToken}
              placeholder={t("githubCicd.tokenPlaceholder")}
              disabled={disabled || submitting}
              autoComplete="off"
              onChange={(event) => {
                setPendingCicdSelected(false);
                setGithubToken(event.currentTarget.value);
              }}
            />
          </label>
          <label className="pp-github-cicd-field">
            <span>{t("githubCicd.targetBranch")}</span>
            <input
              value={baseBranch}
              placeholder="main"
              disabled={disabled || submitting}
              autoComplete="off"
              onChange={(event) => {
                setPendingCicdSelected(false);
                setBaseBranch(event.currentTarget.value);
              }}
            />
          </label>
          {isCicdMode && (
            <>
              <label className="pp-github-cicd-field">
                <span>{credentialProviderLabel} AK</span>
                <input
                  type="password"
                  value={volcengineAccessKey}
                  placeholder={t("githubCicd.actionsSecretPlaceholder")}
                  disabled={disabled || submitting}
                  autoComplete="off"
                  onChange={(event) => {
                    setPendingCicdSelected(false);
                    setVolcengineAccessKey(event.currentTarget.value);
                  }}
                />
              </label>
              <label className="pp-github-cicd-field">
                <span>{credentialProviderLabel} SK</span>
                <input
                  type="password"
                  value={volcengineSecretKey}
                  placeholder={t("githubCicd.actionsSecretPlaceholder")}
                  disabled={disabled || submitting}
                  autoComplete="off"
                  onChange={(event) => {
                    setPendingCicdSelected(false);
                    setVolcengineSecretKey(event.currentTarget.value);
                  }}
                />
              </label>
              <label className="pp-github-cicd-field">
                <span>{t("githubCicd.sessionToken", { provider: credentialProviderLabel })}</span>
                <input
                  type="password"
                  value={volcengineSessionToken}
                  placeholder={t("githubCicd.sessionTokenPlaceholder")}
                  disabled={disabled || submitting}
                  autoComplete="off"
                  onChange={(event) => {
                    setPendingCicdSelected(false);
                    setVolcengineSessionToken(event.currentTarget.value);
                  }}
                />
              </label>
            </>
          )}
          <button type="submit" className="pp-github-cicd-submit" disabled={!canSubmit}>
            {submitting ? (
              <>
                <SpinnerIcon className="pp-ic spin" />
                {t("githubCicd.syncing")}
              </>
            ) : (
              submitLabel
            )}
          </button>
        </form>
      )}

      {pendingCicdSelected && !result && (
        <p className="pp-github-cicd-bound-note">
          {t("githubCicd.pendingHint")}
        </p>
      )}

      {result && (
        <div className="pp-github-cicd-result" role="status">
          <div className="pp-github-cicd-result-head">
            <strong>
              {result.cicd?.enabled
                ? result.runtimeId
                  ? t("githubCicd.result.deliveryMounted")
                  : t("githubCicd.result.deliverySelected")
                : resultRuntimeId
                  ? t("githubCicd.result.githubBound")
                  : t("githubCicd.result.codeSynced")}
            </strong>
            <span>{deliveryStatusLabel(result, t)}</span>
          </div>
          <dl className="pp-github-cicd-result-grid">
            <div>
              <dt>{t("githubCicd.repository")}</dt>
              <dd>{resultRepo}</dd>
            </div>
            <div>
              <dt>{t("githubCicd.branch")}</dt>
              <dd>{resultBranch}</dd>
            </div>
            {resultRuntimeId && (
              <div>
                <dt>{t("githubCicd.runtime")}</dt>
                <dd>{resultRuntimeId}</dd>
              </div>
            )}
            {resultGithub?.commitSha && (
              <div>
                <dt>{t("githubCicd.commit")}</dt>
                <dd>{resultGithub.commitSha.slice(0, 12)}</dd>
              </div>
            )}
            {result.cicd?.workflowPath && (
              <div>
                <dt>{t("githubCicd.workflow")}</dt>
                <dd>{result.cicd.workflowPath}</dd>
              </div>
            )}
          </dl>
          <div className="pp-github-cicd-links">
            {resultGithub?.pullRequestUrl && (
              <a
                href={resultGithub.pullRequestUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLinkIcon className="pp-ic" />
                {t("githubCicd.viewPr")}
              </a>
            )}
          </div>
          {resultRuntimeId && (
            <p className="pp-github-cicd-bound-note">
              {result.cicd?.enabled
                ? t("githubCicd.result.deliveryHint")
                : t("githubCicd.result.boundHint")}
            </p>
          )}
        </div>
      )}

      {error && (
        <div className="pp-github-cicd-error" role="alert">
          <strong>{t("githubCicd.createFailed")}</strong>
          <p>{error.message}</p>
          {(error.phase || error.runtimeId || error.logPath) && (
            <dl>
              {error.phase && (
                <div>
                  <dt>{t("githubCicd.phase")}</dt>
                  <dd>{error.phase}</dd>
                </div>
              )}
              {error.runtimeId && (
                <div>
                  <dt>{t("githubCicd.runtime")}</dt>
                  <dd>{error.runtimeId}</dd>
                </div>
              )}
              {error.logPath && (
                <div>
                  <dt>{t("githubCicd.log")}</dt>
                  <dd>{error.logPath}</dd>
                </div>
              )}
            </dl>
          )}
        </div>
      )}
    </section>
  );
}
