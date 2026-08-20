import { useEffect, useMemo, useState, type FormEvent, type SVGProps } from "react";
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

function githubRepoLabel(url: string): string {
  const trimmed = url.trim();
  if (!trimmed) return "GitHub 仓库";
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

function errorDetailFromUnknown(error: unknown): GithubCicdPipelineErrorDetail {
  if (error instanceof GithubCicdPipelineError) return error.detail;
  if (error instanceof Error) return { message: error.message };
  return { message: String(error || "同步 GitHub 代码失败") };
}

function deliveryStatusLabel(result: GithubCicdPipelineResult): string {
  if (result.status === "cicd-bound") return "已挂载";
  if (result.status === "bound") return "已绑定";
  if (result.status === "succeeded") return "已同步";
  return result.status || "已创建";
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
        if (!cancelled) setError(errorDetailFromUnknown(caught));
      })
      .finally(() => {
        if (!cancelled) setLoadingBinding(false);
      });
    return () => {
      cancelled = true;
    };
  }, [onBindingChange, runtimeId]);

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

  const repoLabel = useMemo(() => githubRepoLabel(githubUrl), [githubUrl]);
  const resultGithub = result?.github;
  const resultRepo =
    resultGithub?.owner && resultGithub.repo
      ? `${resultGithub.owner}/${resultGithub.repo}`
      : resultGithub?.repo ?? repoLabel;
  const resultBranch = resultGithub?.branch ?? normalizeBranch(baseBranch);
  const resultRuntimeId = result?.runtimeId;
  const isCicdMode = mode === "cicd";
  const credentialProviderLabel =
    cloudProvider === "byteplus" ? "BytePlus" : "火山";
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
      ? "挂载持续交付"
      : pendingCicdSelected
        ? "已选择，部署时挂载"
        : "部署时挂载持续交付"
    : "同步代码";

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
      setError(errorDetailFromUnknown(caught));
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
          <div className="pp-github-cicd-tabs" role="tablist" aria-label="GitHub 交付模式">
            <button
              type="button"
              className={mode === "source" ? "is-active" : ""}
              role="tab"
              aria-selected={mode === "source"}
              onClick={() => setMode("source")}
            >
              GitHub 代码同步
            </button>
            <button
              type="button"
              role="tab"
              className={mode === "cicd" ? "is-active" : ""}
              aria-selected={mode === "cicd"}
              onClick={() => setMode("cicd")}
            >
              挂载持续交付
            </button>
          </div>
        ) : (
          <span>GitHub 交付</span>
        )}
        {(submitting || loadingBinding) && (
          <span className="pp-github-cicd-status" role="status">
            <SpinnerIcon className="pp-ic spin" />
            {loadingBinding ? "读取中" : "执行中"}
          </span>
        )}
      </div>
      {showSetup && (
        <p className="pp-github-cicd-copy">
          {isCicdMode
            ? runtimeId
              ? "写入 AgentKit Runtime GitHub Actions workflow，后续 GitHub 提交会更新绑定 Runtime。"
              : "首次部署成功后初始化目标分支，后续 GitHub 提交会更新绑定 Runtime。"
            : "Studio 会直接 push 到目标分支；该分支由 Studio 管理，远端冲突时同步会失败。Runtime 仍由部署按钮发布。"}
        </p>
      )}

      {showSetup && (
        <form className="pp-github-cicd-form" onSubmit={handleSubmit}>
          <label className="pp-github-cicd-field">
            <span>GitHub URL</span>
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
            <span>Token</span>
            <input
              type="password"
              value={githubToken}
              placeholder="repo 或 contents write 权限"
              disabled={disabled || submitting}
              autoComplete="off"
              onChange={(event) => {
                setPendingCicdSelected(false);
                setGithubToken(event.currentTarget.value);
              }}
            />
          </label>
          <label className="pp-github-cicd-field">
            <span>目标分支</span>
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
                  placeholder="用于写入 GitHub Actions Secret"
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
                  placeholder="用于写入 GitHub Actions Secret"
                  disabled={disabled || submitting}
                  autoComplete="off"
                  onChange={(event) => {
                    setPendingCicdSelected(false);
                    setVolcengineSecretKey(event.currentTarget.value);
                  }}
                />
              </label>
              <label className="pp-github-cicd-field">
                <span>{credentialProviderLabel} Session Token</span>
                <input
                  type="password"
                  value={volcengineSessionToken}
                  placeholder="临时凭证可选"
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
                同步中…
              </>
            ) : (
              submitLabel
            )}
          </button>
        </form>
      )}

      {pendingCicdSelected && !result && (
        <p className="pp-github-cicd-bound-note">
          已选择挂载持续交付。点击部署后，Studio 会等待 Runtime 创建完成并初始化 GitHub 目标分支，初始化成功后才完成部署流程。
        </p>
      )}

      {result && (
        <div className="pp-github-cicd-result" role="status">
          <div className="pp-github-cicd-result-head">
            <strong>
              {result.cicd?.enabled
                ? result.runtimeId
                  ? "已挂载持续交付"
                  : "已选择挂载持续交付"
                : resultRuntimeId
                  ? "已绑定 GitHub"
                  : "代码已同步"}
            </strong>
            <span>{deliveryStatusLabel(result)}</span>
          </div>
          <dl className="pp-github-cicd-result-grid">
            <div>
              <dt>仓库</dt>
              <dd>{resultRepo}</dd>
            </div>
            <div>
              <dt>分支</dt>
              <dd>{resultBranch}</dd>
            </div>
            {resultRuntimeId && (
              <div>
                <dt>Runtime</dt>
                <dd>{resultRuntimeId}</dd>
              </div>
            )}
            {resultGithub?.commitSha && (
              <div>
                <dt>Commit</dt>
                <dd>{resultGithub.commitSha.slice(0, 12)}</dd>
              </div>
            )}
            {result.cicd?.workflowPath && (
              <div>
                <dt>Workflow</dt>
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
                查看 PR
              </a>
            )}
          </div>
          {resultRuntimeId && (
            <p className="pp-github-cicd-bound-note">
              {result.cicd?.enabled
                ? "目标分支提交会触发 Runtime 持续交付。"
                : "更新并发布时会先同步当前源码到这个分支。"}
            </p>
          )}
        </div>
      )}

      {error && (
        <div className="pp-github-cicd-error" role="alert">
          <strong>创建失败</strong>
          <p>{error.message}</p>
          {(error.phase || error.runtimeId || error.logPath) && (
            <dl>
              {error.phase && (
                <div>
                  <dt>阶段</dt>
                  <dd>{error.phase}</dd>
                </div>
              )}
              {error.runtimeId && (
                <div>
                  <dt>Runtime</dt>
                  <dd>{error.runtimeId}</dd>
                </div>
              )}
              {error.logPath && (
                <div>
                  <dt>日志</dt>
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
