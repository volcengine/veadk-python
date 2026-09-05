import {
  useRef,
  useState,
  type FormEvent,
  type SVGProps,
} from "react";
import { useTranslation } from "react-i18next";
import type { IssueFeedbackIssue } from "../adk/issueFeedback";
import type { IssueFeedbackModule } from "../adk/issueFeedback";
import "./PlatformFeedback.css";

const MODULE_OPTIONS: IssueFeedbackModule[] = [
  "conversation",
  "agents",
  "applications",
  "search",
  "other",
];

const ISSUE_OPTIONS: IssueFeedbackIssue[] = [
  "page_slow",
  "feature_unavailable",
  "display_error",
  "no_response",
  "other",
];

const DESCRIPTION_SUGGESTIONS = ["noResponse", "loading", "incomplete", "error"] as const;

interface PlatformFeedbackProps {
  initialModule: IssueFeedbackModule;
  onSubmit: (feedback: {
    module: IssueFeedbackModule;
    issues: IssueFeedbackIssue[];
    description: string;
  }) => Promise<void>;
}

function CheckIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="m5 12.5 4.2 4.2L19 7" />
    </svg>
  );
}

export function PlatformFeedback({
  initialModule,
  onSubmit,
}: PlatformFeedbackProps) {
  const { t } = useTranslation("feedback");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [selectedIssues, setSelectedIssues] = useState<Set<IssueFeedbackIssue>>(
    () => new Set(),
  );
  const [module, setModule] = useState<IssueFeedbackModule>(initialModule);
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const toggleIssue = (issue: IssueFeedbackIssue) => {
    setSelectedIssues((current) => {
      const next = new Set(current);
      if (next.has(issue)) next.delete(issue);
      else next.add(issue);
      return next;
    });
  };

  const applySuggestion = (suggestion: string) => {
    setDescription((current) => {
      if (!current.trim()) return suggestion;
      if (current.includes(suggestion)) return current;
      return `${current.trimEnd()}\n${suggestion}`;
    });
    textareaRef.current?.focus();
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy || submitted) return;
    setBusy(true);
    setError("");
    try {
      await onSubmit({
        module,
        issues: [...selectedIssues],
        description: description.trim(),
      });
      setSubmitted(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const canSubmit = selectedIssues.size > 0 || description.trim().length > 0;

  return (
    <div className="platform-feedback-page">
      <header className="platform-feedback-header">
        <h1>{t("title")}</h1>
        <p>{t("page.description")}</p>
      </header>

      <div className="platform-feedback-scroll">
        {submitted ? (
          <section
            className="platform-feedback-success"
            aria-labelledby="feedback-success-title"
            aria-live="polite"
            role="status"
          >
            <span className="platform-feedback-success-icon" aria-hidden="true">
              <CheckIcon />
            </span>
            <div>
              <h2 id="feedback-success-title">{t("success.title")}</h2>
              <p>{t("success.description")}</p>
            </div>
          </section>
        ) : (
          <form
            className="platform-feedback-form"
            onSubmit={(event) => void submit(event)}
          >
            <section className="platform-feedback-section">
              <div className="platform-feedback-section-heading">
                <h2>{t("page.module")}</h2>
              </div>
              <div className="platform-feedback-pills" aria-label={t("page.module")}>
                {MODULE_OPTIONS.map((option) => (
                  <button
                    key={option}
                    type="button"
                    aria-pressed={module === option}
                    onClick={() => setModule(option)}
                    disabled={busy}
                  >
                    {t(`page.modules.${option}`)}
                  </button>
                ))}
              </div>
            </section>

            <section className="platform-feedback-section">
              <div className="platform-feedback-suggestions">
                <span>{t("page.commonIssuesMultiple")}</span>
                <div className="platform-feedback-pills" aria-label={t("page.issueTypes")}>
                  {ISSUE_OPTIONS.map((issue) => (
                    <button
                      key={issue}
                      type="button"
                      aria-pressed={selectedIssues.has(issue)}
                      onClick={() => toggleIssue(issue)}
                      disabled={busy}
                    >
                      {t(`page.issues.${issue}`)}
                    </button>
                  ))}
                </div>
              </div>
            </section>

            <section className="platform-feedback-section">
              <label className="platform-feedback-field">
                <span>{t("descriptionLabel")}</span>
                <textarea
                  ref={textareaRef}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder={t("page.descriptionPlaceholder")}
                  maxLength={4000}
                  rows={6}
                  disabled={busy}
                />
              </label>
              <div className="platform-feedback-suggestions">
                <span>{t("page.quickAdd")}</span>
                <div className="platform-feedback-pills" aria-label={t("page.suggestionsLabel")}>
                  {DESCRIPTION_SUGGESTIONS.map((suggestionKey) => {
                    const suggestion = t(`page.suggestions.${suggestionKey}`);
                    return (
                    <button
                      key={suggestionKey}
                      type="button"
                      onClick={() => applySuggestion(suggestion)}
                      disabled={busy}
                    >
                      {suggestion}
                    </button>
                    );
                  })}
                </div>
              </div>
            </section>

            <p className="platform-feedback-privacy" role="alert">
              {t("page.privacy")}
            </p>
            {error && (
              <p className="platform-feedback-error" role="alert">{error}</p>
            )}

            <div className="platform-feedback-actions">
              <button type="submit" disabled={!canSubmit || busy}>
                {busy ? t("submitting") : t("submit")}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
