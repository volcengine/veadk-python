import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type SVGProps,
} from "react";
import { useTranslation } from "react-i18next";

import {
  type GitHubPullRequestResult,
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

function validateField(
  name: FieldName,
  value: string,
  required: boolean,
): string {
  const text = value.trim();
  if (!text) return required ? "github.validation.required" : "";
  if (name === "repository" && !/^(?:https:\/\/github\.com\/)?[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+(?:\.git)?$/.test(text)) {
    return "github.validation.repository";
  }
  if (name === "baseBranch" && (!/^[A-Za-z0-9][A-Za-z0-9._/-]*$/.test(text) || text.includes(".."))) {
    return "github.validation.baseBranch";
  }
  if (name === "projectPath" && (text.startsWith("/") || text.split("/").includes(".."))) {
    return "github.validation.projectPath";
  }
  if (name === "runtimeName") {
    return runtimeNameProblem(text, (key) => `github.validation.runtimeName.${key}`) ?? "";
  }
  if (name === "runtimeId" && !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(text)) {
    return "github.validation.runtimeId";
  }
  if (name === "sandboxToolId" && !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(text)) {
    return "github.validation.sandboxToolId";
  }
  if (name === "modelName" && !/^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/.test(text)) {
    return "github.validation.modelName";
  }
  if (name === "modelBaseUrl") {
    try {
      const url = new URL(text);
      if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash) {
        return "github.validation.modelBaseUrlSafe";
      }
    } catch {
      return "github.validation.modelBaseUrl";
    }
  }
  return "";
}

export function GitHubIntegration({
  automation,
  cloudProvider,
  onBack,
}: GitHubIntegrationProps) {
  const { t } = useTranslation("automations");
  const definition = getGitHubAutomation(automation);
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
  const submitAbortRef = useRef<AbortController | null>(null);

  useEffect(() => () => submitAbortRef.current?.abort(), []);

  useEffect(() => {
    setForm({ ...definition.initialValues({ cloudProvider }) });
    setFieldErrors({});
    setSubmitError("");
    setResult(null);
    setRegionMenuOpen(false);
    submitAbortRef.current?.abort();
  }, [automation, cloudProvider, definition]);

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

  const field = (
    fieldDefinition: AutomationFieldDefinition,
  ) => {
    const { name, placeholder, required } = fieldDefinition;
    const fieldKey = `cards.${automation}.fields.${name}`;
    return (
      <div className="github-field" key={name}>
        <label htmlFor={`github-${name}`}>
          <span>{t(`${fieldKey}.label`)}</span>
          <span className={`github-field-requirement${required ? " is-required" : ""}`}>
            {required ? t("github.required") : t("github.optional")}
          </span>
        </label>
        <input
          id={`github-${name}`}
          value={form[name]}
          onChange={(event) => updateField(name, event.target.value)}
          onBlur={() => blurField(name)}
          placeholder={t(`${fieldKey}.placeholder`, { defaultValue: placeholder })}
          required={required}
          aria-invalid={Boolean(fieldErrors[name])}
          aria-describedby={`github-${name}-help${fieldErrors[name] ? ` github-${name}-error` : ""}`}
        />
        <span id={`github-${name}-help`} className="github-field-help">{t(`${fieldKey}.help`)}</span>
        {fieldErrors[name] ? <span id={`github-${name}-error`} className="github-field-error" role="alert">{t(fieldErrors[name])}</span> : null}
      </div>
    );
  };

  return (
    <div className="github-integration-page">
      <header className="github-integration-header">
        <button type="button" className="github-back" onClick={onBack} aria-label={t("backToAutomations")}>
          <BackIcon />
        </button>
        <GitHubLogo className="github-integration-logo" />
        <div>
          <h1>{t(`cards.${automation}.title`)}</h1>
          <p>{t(`cards.${automation}.subtitle`)}</p>
        </div>
      </header>

      <div className="github-integration-layout">
        <section id={`github-panel-${automation}`} className="github-section-panel">
          <div className="github-panel-heading">
            <p>{t(`cards.${automation}.panel`)}</p>
          </div>
          <form className="github-release-form" onSubmit={onSubmit} onKeyDown={stopComposingSubmit} noValidate>
            <div className="github-field-grid">
              {definition.fields.map(field)}
              <div className="github-field">
                <label id="github-region-label">
                  <span>{t("github.region")}</span>
                  <span className="github-field-requirement is-required">{t("github.required")}</span>
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
                      <div className="pp-region-menu" role="listbox" aria-label={t("github.region")}>
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
                  {t(`cards.${automation}.regionHelp`)}
                </span>
              </div>
            </div>

            <div className="github-field github-token-field">
              <div className="github-token-label-row">
                <label htmlFor="github-token">
                  <span>{t("github.tokenLabel")}</span>
                  <span className="github-field-requirement is-required">{t("github.required")}</span>
                </label>
                <a
                  href="https://github.com/settings/personal-access-tokens/new?name=VeADK%20Studio&description=Create%20a%20GitHub%20automation%20pull%20request&contents=write&pull_requests=write"
                  target="_blank"
                  rel="noreferrer"
                >
                  {t("github.getToken")}
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
                  placeholder={t("github.tokenPlaceholder")}
                  aria-invalid={Boolean(fieldErrors.token)}
                  aria-describedby={`github-token-help${fieldErrors.token ? " github-token-error" : ""}`}
                />
                <button
                  type="button"
                  onClick={() => setShowToken((current) => !current)}
                  aria-label={showToken ? t("github.hideToken") : t("github.showToken")}
                  title={showToken ? t("github.hideToken") : t("github.showToken")}
                >
                  <EyeIcon hidden={showToken} />
                </button>
              </div>
              <span id="github-token-help" className="github-field-help">{t("github.tokenHelp")}</span>
              {fieldErrors.token ? <span id="github-token-error" className="github-field-error" role="alert">{t(fieldErrors.token)}</span> : null}
            </div>

            {submitError ? <div className="github-submit-message is-error" role="alert">{submitError}</div> : null}
            {result ? (
              <div className="github-submit-message is-success" role="status">
                <span>{t("github.prCreated", { number: result.number })}</span>
                <a href={result.url} target="_blank" rel="noreferrer">{t("github.viewOnGitHub")}<ExternalIcon /></a>
              </div>
            ) : null}

            <div className="github-form-actions">
              <div className="github-secrets-note">
                <strong>{t("github.secretsHeading")}</strong>
                {secrets.map((secret) => (
                  <span key={secret}>{secret}</span>
                ))}
              </div>
              <button type="submit" disabled={submitting}>
                {submitting ? t("github.submitting") : t(`cards.${automation}.submitLabel`)}
              </button>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
