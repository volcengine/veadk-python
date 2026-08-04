import {
  useState,
  type FormEvent,
  type KeyboardEvent,
  type SVGProps,
} from "react";

import {
  createGitHubPullRequest,
  type GitHubPullRequestInput,
  type GitHubPullRequestResult,
} from "../adk/githubIntegration";
import "./GitHubIntegration.css";

interface GitHubIntegrationProps {
  onBack: () => void;
}

type SectionId = "release" | "security" | "history";
type FieldName = keyof GitHubPullRequestInput;

const SECTIONS: Array<{ id: SectionId; label: string }> = [
  { id: "release", label: "持续发布到 AgentKit Runtime" },
  { id: "security", label: "权限与安全" },
  { id: "history", label: "PR 记录" },
];

const INITIAL_FORM: GitHubPullRequestInput = {
  repository: "",
  baseBranch: "main",
  projectPath: ".",
  runtimeName: "",
  runtimeId: "",
  region: "cn-beijing",
  token: "",
};

function BackIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path d="m9.8 3.5-4.5 4.5 4.5 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function RepositoryFlowIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
      <circle cx="7" cy="5" r="2" />
      <circle cx="17" cy="8" r="2" />
      <circle cx="7" cy="19" r="2" />
      <path d="M7 7v10M9 8h4a4 4 0 0 1 4 4v-2" />
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

function validateField(name: FieldName, value: string): string {
  const text = value.trim();
  if (!text) return "此项不能为空";
  if (name === "repository" && !/^(?:https:\/\/github\.com\/)?[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+(?:\.git)?$/.test(text)) {
    return "请输入 owner/repository 或完整 GitHub Repo URL";
  }
  if (name === "baseBranch" && (!/^[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(text) || text.includes(".."))) {
    return "目标分支格式不正确";
  }
  if (name === "projectPath" && (text.startsWith("/") || text.split("/").includes(".."))) {
    return "请输入仓库内的相对目录";
  }
  if (name === "runtimeName" && !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(text)) {
    return "以字母开头，仅支持字母、数字、下划线和连字符";
  }
  if (name === "runtimeId" && !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(text)) {
    return "Runtime ID 格式不正确";
  }
  return "";
}

export function GitHubIntegration({ onBack }: GitHubIntegrationProps) {
  const [activeSection, setActiveSection] = useState<SectionId>("release");
  const [form, setForm] = useState<GitHubPullRequestInput>(INITIAL_FORM);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldName, string>>>({});
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showToken, setShowToken] = useState(false);
  const [result, setResult] = useState<GitHubPullRequestResult | null>(null);

  const updateField = (name: FieldName, value: string) => {
    setForm((current) => ({ ...current, [name]: value }));
    if (fieldErrors[name]) {
      setFieldErrors((current) => ({ ...current, [name]: "" }));
    }
  };

  const blurField = (name: FieldName) => {
    const error = validateField(name, form[name]);
    setFieldErrors((current) => ({ ...current, [name]: error }));
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const errors: Partial<Record<FieldName, string>> = {};
    for (const name of Object.keys(form) as FieldName[]) {
      if (name === "region") continue;
      const error = validateField(name, form[name]);
      if (error) errors[name] = error;
    }
    setFieldErrors(errors);
    if (Object.keys(errors).length) return;

    setSubmitting(true);
    setSubmitError("");
    setResult(null);
    try {
      const nextResult = await createGitHubPullRequest({
        ...form,
        repository: form.repository.trim(),
        baseBranch: form.baseBranch.trim(),
        projectPath: form.projectPath.trim(),
        runtimeName: form.runtimeName.trim(),
        runtimeId: form.runtimeId.trim(),
        token: form.token.trim(),
      });
      setResult(nextResult);
      setForm((current) => ({ ...current, token: "" }));
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : String(error));
    } finally {
      setSubmitting(false);
    }
  };

  const stopComposingSubmit = (event: KeyboardEvent<HTMLFormElement>) => {
    if (event.key === "Enter" && (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229)) {
      event.preventDefault();
    }
  };

  const field = (
    name: Exclude<FieldName, "region" | "token">,
    label: string,
    placeholder: string,
    help: string,
  ) => (
    <div className="github-field">
      <label htmlFor={`github-${name}`}>{label}</label>
      <input
        id={`github-${name}`}
        value={form[name]}
        onChange={(event) => updateField(name, event.target.value)}
        onBlur={() => blurField(name)}
        placeholder={placeholder}
        aria-invalid={Boolean(fieldErrors[name])}
        aria-describedby={`github-${name}-help${fieldErrors[name] ? ` github-${name}-error` : ""}`}
      />
      <span id={`github-${name}-help`} className="github-field-help">{help}</span>
      {fieldErrors[name] ? <span id={`github-${name}-error`} className="github-field-error" role="alert">{fieldErrors[name]}</span> : null}
    </div>
  );

  return (
    <div className="github-integration-page">
      <header className="github-integration-header">
        <button type="button" className="github-back" onClick={onBack} aria-label="返回应用列表">
          <BackIcon />
        </button>
        <div className="github-integration-mark"><RepositoryFlowIcon /></div>
        <div>
          <h1>GitHub 集成</h1>
          <p>用 Pull Request 把持续发布配置安全地加入代码仓库</p>
        </div>
      </header>

      <div className="github-integration-layout">
        <nav className="github-section-tabs" role="tablist" aria-label="GitHub 集成设置">
          {SECTIONS.map((section) => (
            <button
              type="button"
              role="tab"
              key={section.id}
              id={`github-tab-${section.id}`}
              aria-selected={activeSection === section.id}
              aria-controls={`github-panel-${section.id}`}
              className={activeSection === section.id ? "is-active" : ""}
              onClick={() => setActiveSection(section.id)}
            >
              {section.label}
            </button>
          ))}
        </nav>

        <section
          id="github-panel-release"
          role="tabpanel"
          aria-labelledby="github-tab-release"
          hidden={activeSection !== "release"}
          className="github-section-panel"
        >
          <div className="github-panel-heading">
            <h2>持续发布到 AgentKit Runtime</h2>
            <p>提交后将在目标仓库创建发布分支，并发起包含 GitHub Actions 工作流的 PR。</p>
          </div>
          <form className="github-release-form" onSubmit={onSubmit} onKeyDown={stopComposingSubmit} noValidate>
            <div className="github-field-grid">
              {field("repository", "GitHub Repo", "owner/repository", "支持 owner/repository 或完整 github.com URL")}
              {field("baseBranch", "目标分支", "main", "PR 将以此分支为 base")}
              {field("projectPath", "Agent 项目目录", ".", "包含 app.py 的仓库相对目录")}
              {field("runtimeName", "Runtime 名称", "support-agent", "用于 AgentKit 发布配置")}
              {field("runtimeId", "Runtime ID", "rt-xxxxxxxx", "持续更新的目标 AgentKit Runtime")}
              <div className="github-field">
                <label htmlFor="github-region">地域</label>
                <select
                  id="github-region"
                  value={form.region}
                  onChange={(event) => updateField("region", event.target.value)}
                >
                  <option value="cn-beijing">北京</option>
                  <option value="cn-shanghai">上海</option>
                </select>
                <span className="github-field-help">必须与目标 Runtime 所在地域一致</span>
              </div>
            </div>

            <div className="github-field github-token-field">
              <label htmlFor="github-token">GitHub Token</label>
              <div className="github-token-input">
                <input
                  id="github-token"
                  type={showToken ? "text" : "password"}
                  value={form.token}
                  onChange={(event) => updateField("token", event.target.value)}
                  onBlur={() => blurField("token")}
                  autoComplete="off"
                  placeholder="需要仓库 Contents 与 Pull requests 写权限"
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
              <span id="github-token-help" className="github-field-help">Token 仅用于本次提交，不会保存在浏览器或写入 PR</span>
              {fieldErrors.token ? <span id="github-token-error" className="github-field-error" role="alert">{fieldErrors.token}</span> : null}
            </div>

            {submitError ? <div className="github-submit-message is-error" role="alert">{submitError}</div> : null}
            {result ? (
              <div className="github-submit-message is-success" role="status">
                <span>PR #{result.number} 已创建</span>
                <a href={result.url} target="_blank" rel="noreferrer">在 GitHub 查看<ExternalIcon /></a>
              </div>
            ) : null}

            <div className="github-form-actions">
              <p>工作流通过 GitHub Secrets 读取云凭据，不会把凭据提交到仓库。</p>
              <button type="submit" disabled={submitting}>
                {submitting ? "提交 PR 中…" : "确定并提交 PR"}
              </button>
            </div>
          </form>
        </section>

        <section id="github-panel-security" role="tabpanel" aria-labelledby="github-tab-security" hidden={activeSection !== "security"} className="github-section-panel github-info-panel">
          <h2>权限与安全</h2>
          <dl>
            <div><dt>GitHub Token</dt><dd>仅在服务端请求 GitHub API 时驻留内存，请使用最小仓库权限。</dd></div>
            <div><dt>云凭据</dt><dd>工作流只引用 VOLCENGINE_ACCESS_KEY、VOLCENGINE_SECRET_KEY 和可选的 VOLCENGINE_SESSION_TOKEN Secrets。</dd></div>
            <div><dt>变更范围</dt><dd>PR 仅新增或更新 .github/workflows/publish-agentkit.yml，便于合并前审阅。</dd></div>
          </dl>
        </section>

        <section id="github-panel-history" role="tabpanel" aria-labelledby="github-tab-history" hidden={activeSection !== "history"} className="github-section-panel github-info-panel">
          <h2>PR 记录</h2>
          {result ? (
            <div className="github-history-item">
              <div><strong>PR #{result.number}</strong><span>{result.branch}</span></div>
              <a href={result.url} target="_blank" rel="noreferrer">查看 PR<ExternalIcon /></a>
            </div>
          ) : (
            <div className="github-history-empty"><RepositoryFlowIcon /><p>本次访问还没有提交 PR</p></div>
          )}
        </section>
      </div>
    </div>
  );
}

