import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type SVGProps,
} from "react";

import {
  type GitHubPullRequestResult,
} from "../adk/githubIntegration";
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
  onBack: () => void;
}

type FieldName = AutomationFieldName | "region" | "token";

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
  if (name === "sandboxToolId" && !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(text)) {
    return "Sandbox Tool ID 格式不正确";
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
  return "";
}

export function GitHubIntegration({ automation, onBack }: GitHubIntegrationProps) {
  const definition = getGitHubAutomation(automation);
  const [form, setForm] = useState<AutomationFormValues>(() => ({
    ...definition.initialValues,
  }));
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FieldName, string>>>({});
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showToken, setShowToken] = useState(false);
  const [regionMenuOpen, setRegionMenuOpen] = useState(false);
  const [result, setResult] = useState<GitHubPullRequestResult | null>(null);
  const submitAbortRef = useRef<AbortController | null>(null);

  useEffect(() => () => submitAbortRef.current?.abort(), []);

  const updateField = (name: FieldName, value: string) => {
    setForm((current) => ({ ...current, [name]: value }));
    if (fieldErrors[name]) {
      setFieldErrors((current) => ({ ...current, [name]: "" }));
    }
  };

  const blurField = (name: FieldName) => {
    const required = name === "token"
      || definition.fields.find((field) => field.name === name)?.required === true;
    const error = validateField(name, form[name], required);
    setFieldErrors((current) => ({ ...current, [name]: error }));
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const errors: Partial<Record<FieldName, string>> = {};
    for (const field of definition.fields) {
      const error = validateField(field.name, form[field.name], field.required);
      if (error) errors[field.name] = error;
    }
    const tokenError = validateField("token", form.token, true);
    if (tokenError) {
      errors.token = tokenError;
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
      const nextResult = await definition.submit(form, controller.signal);
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

  const field = (
    fieldDefinition: AutomationFieldDefinition,
  ) => {
    const { name, label, placeholder, help, required } = fieldDefinition;
    return (
      <div className="github-field" key={name}>
        <label htmlFor={`github-${name}`}>
          <span>{label}</span>
          <span className={`github-field-requirement${required ? " is-required" : ""}`}>
            {required ? "必填" : "可选"}
          </span>
        </label>
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
        <span id={`github-${name}-help`} className="github-field-help">{help}</span>
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
            <div className="github-field-grid">
              {definition.fields.map(field)}
              <div className="github-field">
                <label id="github-region-label">
                  <span>地域</span>
                  <span className="github-field-requirement is-required">必填</span>
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
                    <span>{form.region === "cn-shanghai" ? "华东 2（上海）" : "华北 2（北京）"}</span>
                    <ChevronIcon className={`pp-region-chevron${regionMenuOpen ? " is-open" : ""}`} />
                  </button>
                  {regionMenuOpen ? (
                    <>
                      <div className="menu-scrim" onClick={() => setRegionMenuOpen(false)} />
                      <div className="pp-region-menu" role="listbox" aria-label="地域">
                        {([
                          { value: "cn-beijing", label: "华北 2（北京）" },
                          { value: "cn-shanghai", label: "华东 2（上海）" },
                        ] as const).map((region) => {
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

            <div className="github-field github-token-field">
              <div className="github-token-label-row">
                <label htmlFor="github-token">
                  <span>GitHub Token</span>
                  <span className="github-field-requirement is-required">必填</span>
                </label>
                <a
                  href="https://github.com/settings/personal-access-tokens/new?name=VeADK%20Studio&description=Create%20a%20GitHub%20automation%20pull%20request&contents=write&pull_requests=write"
                  target="_blank"
                  rel="noreferrer"
                >
                  获取 Token
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
              <div className="github-secrets-note">
                <strong>合并 PR 前，请在仓库的 GitHub Actions Secrets 中配置：</strong>
                {definition.secrets.map((secret) => <span key={secret}>{secret}</span>)}
              </div>
              <button type="submit" disabled={submitting}>
                {submitting ? "提交 PR 中…" : definition.submitLabel}
              </button>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
