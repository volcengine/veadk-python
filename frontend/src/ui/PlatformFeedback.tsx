import {
  useRef,
  useState,
  type FormEvent,
  type SVGProps,
} from "react";
import type { IssueFeedbackIssue } from "../adk/issueFeedback";
import type { IssueFeedbackModule } from "../adk/issueFeedback";
import "./PlatformFeedback.css";

const MODULE_OPTIONS: { value: IssueFeedbackModule; label: string }[] = [
  { value: "conversation", label: "对话" },
  { value: "agents", label: "智能体" },
  { value: "applications", label: "自动化" },
  { value: "search", label: "搜索" },
  { value: "other", label: "其他" },
];

const ISSUE_OPTIONS: { value: IssueFeedbackIssue; label: string }[] = [
  { value: "page_slow", label: "页面加载慢" },
  { value: "feature_unavailable", label: "功能无法使用" },
  { value: "display_error", label: "页面显示异常" },
  { value: "no_response", label: "操作无响应" },
  { value: "other", label: "其他问题" },
];

const DESCRIPTION_SUGGESTIONS = [
  "点击后没有反应",
  "页面一直处于加载状态",
  "部分内容显示不完整",
  "操作后出现错误提示",
];

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
        <h1>问题反馈</h1>
        <p>告诉我们您在使用 VeADK Studio 时遇到的问题。</p>
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
              <h2 id="feedback-success-title">上报成功，感谢您的反馈</h2>
              <p>AgentKit 团队会尽快查看您提交的问题。</p>
            </div>
          </section>
        ) : (
          <form
            className="platform-feedback-form"
            onSubmit={(event) => void submit(event)}
          >
            <section className="platform-feedback-section">
              <div className="platform-feedback-section-heading">
                <h2>所属模块</h2>
              </div>
              <div className="platform-feedback-pills" aria-label="所属模块">
                {MODULE_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    aria-pressed={module === option.value}
                    onClick={() => setModule(option.value)}
                    disabled={busy}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </section>

            <section className="platform-feedback-section">
              <div className="platform-feedback-suggestions">
                <span>常见问题（可多选）</span>
                <div className="platform-feedback-pills" aria-label="问题类型">
                  {ISSUE_OPTIONS.map((issue) => (
                    <button
                      key={issue.value}
                      type="button"
                      aria-pressed={selectedIssues.has(issue.value)}
                      onClick={() => toggleIssue(issue.value)}
                      disabled={busy}
                    >
                      {issue.label}
                    </button>
                  ))}
                </div>
              </div>
            </section>

            <section className="platform-feedback-section">
              <label className="platform-feedback-field">
                <span>问题描述</span>
                <textarea
                  ref={textareaRef}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="请描述问题发生时的页面、操作和表现"
                  maxLength={4000}
                  rows={6}
                  disabled={busy}
                />
              </label>
              <div className="platform-feedback-suggestions">
                <span>快捷补充</span>
                <div className="platform-feedback-pills" aria-label="问题描述推荐">
                  {DESCRIPTION_SUGGESTIONS.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => applySuggestion(suggestion)}
                      disabled={busy}
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            </section>

            <p className="platform-feedback-privacy" role="alert">
              您的数据将会上报到 AgentKit 团队，请注意隐私保护。
            </p>
            {error && (
              <p className="platform-feedback-error" role="alert">{error}</p>
            )}

            <div className="platform-feedback-actions">
              <button type="submit" disabled={!canSubmit || busy}>
                {busy ? "正在上报…" : "提交反馈"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
