import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ExternalLink, Loader2 } from "lucide-react";
import {
  bindGithubCicdRuntime,
  createGithubCicdPipeline,
  getGithubCicdRuntimeBinding,
  GithubCicdPipelineError,
  type GithubCicdPipelineErrorDetail,
  type GithubCicdPipelineResult,
} from "../adk/client";
import type { AgentProject } from "../create/project";

interface GithubCicdPanelProps {
  project: AgentProject;
  region: string;
  runtimeId?: string;
  disabled?: boolean;
  onBindingChange?: (binding: GithubCicdPipelineResult | null) => void;
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
  return { message: String(error || "创建持续交付失败") };
}

export function GithubCicdPanel({
  project,
  region,
  runtimeId,
  disabled = false,
  onBindingChange,
}: GithubCicdPanelProps) {
  const [githubUrl, setGithubUrl] = useState("");
  const [githubToken, setGithubToken] = useState("");
  const [baseBranch, setBaseBranch] = useState("main");
  const [submitting, setSubmitting] = useState(false);
  const [loadingBinding, setLoadingBinding] = useState(false);
  const [result, setResult] = useState<GithubCicdPipelineResult | null>(null);
  const [error, setError] = useState<GithubCicdPipelineErrorDetail | null>(null);

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

  const repoLabel = useMemo(() => githubRepoLabel(githubUrl), [githubUrl]);
  const resultGithub = result?.github;
  const resultRepo =
    resultGithub?.owner && resultGithub.repo
      ? `${resultGithub.owner}/${resultGithub.repo}`
      : resultGithub?.repo ?? repoLabel;
  const resultBranch = resultGithub?.branch ?? normalizeBranch(baseBranch);
  const resultRuntimeId = result?.runtimeId;
  const canSubmit =
    !disabled &&
    !submitting &&
    githubUrl.trim().length > 0 &&
    githubToken.trim().length > 0 &&
    project.files.length > 0;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setResult(null);
    setError(null);
    try {
      const nextResult = await createGithubCicdPipeline({
        project,
        githubUrl: githubUrl.trim(),
        githubToken,
        baseBranch: normalizeBranch(baseBranch),
        region,
      });
      const boundResult =
        runtimeId && nextResult.pipelineId
          ? await bindGithubCicdRuntime({
              pipelineId: nextResult.pipelineId,
              runtimeId,
              region,
            })
          : nextResult;
      setResult(boundResult);
      onBindingChange?.(boundResult);
      setGithubToken("");
    } catch (caught) {
      setError(errorDetailFromUnknown(caught));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="pp-config-section pp-github-cicd">
      <div className="pp-config-label pp-github-cicd-title">
        <span>GitHub 持续交付</span>
        {(submitting || loadingBinding) && (
          <span className="pp-github-cicd-status" role="status">
            <Loader2 className="pp-ic spin" />
            {loadingBinding ? "读取中" : "执行中"}
          </span>
        )}
      </div>
      <p className="pp-github-cicd-copy">
        提交当前 Agent 源码到 GitHub，并创建或更新 PR。Runtime 仍由部署按钮发布。
      </p>

      <form className="pp-github-cicd-form" onSubmit={handleSubmit}>
        <label className="pp-github-cicd-field">
          <span>GitHub URL</span>
          <input
            value={githubUrl}
            placeholder="https://github.com/org/repo"
            disabled={disabled || submitting}
            autoComplete="off"
            onChange={(event) => setGithubUrl(event.currentTarget.value)}
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
            onChange={(event) => setGithubToken(event.currentTarget.value)}
          />
        </label>
        <label className="pp-github-cicd-field">
          <span>目标分支</span>
          <input
            value={baseBranch}
            placeholder="main"
            disabled={disabled || submitting}
            autoComplete="off"
            onChange={(event) => setBaseBranch(event.currentTarget.value)}
          />
        </label>
        <button type="submit" className="pp-github-cicd-submit" disabled={!canSubmit}>
          {submitting ? (
            <>
              <Loader2 className="pp-ic spin" />
              同步中…
            </>
          ) : (
            result ? "更新 PR" : "创建 PR"
          )}
        </button>
      </form>

      {result && (
        <div className="pp-github-cicd-result" role="status">
          <div className="pp-github-cicd-result-head">
            <strong>{resultRuntimeId ? "已绑定 GitHub" : "PR 已创建"}</strong>
            <span>{result.status ?? "succeeded"}</span>
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
          </dl>
          <div className="pp-github-cicd-links">
            {resultGithub?.pullRequestUrl && (
              <a
                href={resultGithub.pullRequestUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink className="pp-ic" />
                查看 PR
              </a>
            )}
          </div>
          {resultRuntimeId && (
            <p className="pp-github-cicd-bound-note">
              更新并发布时会先同步当前源码到这个 PR。
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
