import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { getReviewScore, retryReviewScore } from "../adk/reviewScores";
import { normalizeSkillError, SkillErrorDetails } from "../ui/skills/SkillErrorDetails";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
import type { ReviewApplication } from "./reviewModel";
import { REVIEW_SCORE_DIMENSIONS, scoreInProgress, type ReviewScoreResponse } from "./scoreModel";
import "./ReviewScore.css";

export function ReviewScoreLabel({ score }: { score?: ReviewScoreResponse }) {
  const { t } = useTranslation("reviews");
  return <span className={`review-score-label is-${score?.status || "unscored"}`}>
    {score?.status === "completed"
      ? typeof score.overallScore === "number" ? t("score.points", { score: score.overallScore }) : t("score.insufficient")
      : t(`score.status.${score?.status || "unscored"}`)}
  </span>;
}

export function ReviewScoreDetails({ application, canRetry = false, onScoreChanged }: {
  application: ReviewApplication; canRetry?: boolean;
  onScoreChanged?: (score: ReviewScoreResponse, requested: boolean) => void;
}) {
  const { t, i18n } = useTranslation("reviews");
  const [response, setResponse] = useState<ReviewScoreResponse | undefined>(application.aiReview);
  const [loading, setLoading] = useState(Boolean(application.aiReview));
  const [error, setError] = useState<Error | null>(null);
  const [request, setRequest] = useState({ revision: 0, retry: false });
  const [downloadUrl, setDownloadUrl] = useState("");
  const lastRetryRevision = useRef(-1);
  const onScoreChangedRef = useRef(onScoreChanged);
  onScoreChangedRef.current = onScoreChanged;
  const { id, region } = application;
  const hasScore = Boolean(application.aiReview);

  useEffect(() => {
    if (!hasScore && request.revision === 0) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let inFlight = false;
    let active = true;
    const load = async (retry: boolean, initial = false) => {
      if (inFlight || controller.signal.aborted) return;
      if (!initial && document.visibilityState === "hidden") return;
      inFlight = true;
      if (initial) setLoading(true);
      setError(null);
      try {
        const result = await (retry ? retryReviewScore : getReviewScore)({ id, region, signal: controller.signal });
        if (controller.signal.aborted) return;
        setResponse(result);
        onScoreChangedRef.current?.(result, retry);
        active = scoreInProgress(result);
        if (active && document.visibilityState !== "hidden") timer = setTimeout(() => void load(false), 5000);
      } catch (reason: unknown) {
        if (!controller.signal.aborted) {
          active = false;
          setError(normalizeSkillError(reason, t(retry ? "score.retryFailed" : "score.loadFailed")));
        }
      } finally {
        inFlight = false;
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    const visibilityChanged = () => {
      clearTimeout(timer);
      if (active && document.visibilityState !== "hidden") void load(false);
    };
    const retry = request.retry && lastRetryRevision.current !== request.revision;
    if (retry) lastRetryRevision.current = request.revision;
    void load(retry, true);
    document.addEventListener("visibilitychange", visibilityChanged);
    return () => {
      controller.abort();
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", visibilityChanged);
    };
  }, [id, region, hasScore, request, t]);

  const result = response?.status === "completed" ? response.result : undefined;
  useEffect(() => {
    if (!result) { setDownloadUrl(""); return; }
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }));
    setDownloadUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [result]);

  const requestAgain = (retry: boolean) => setRequest((current) => ({ revision: current.revision + 1, retry }));
  return <section className="review-score" aria-label={t("score.title")}>
    <div className="review-score__header">
      <div aria-live="polite">{loading ? <TextShimmer>{t(request.retry ? "score.starting" : "score.loading")}</TextShimmer> : <ReviewScoreLabel score={response} />}</div>
      <div className="review-score__actions">
        {downloadUrl ? <a className="cw-btn cw-btn-ghost" href={downloadUrl} download={`${id}-score.json`}>{t("score.download")}</a> : null}
        {canRetry && (!response || response.status === "failed" || response.status === "not_requested") ? <button type="button" className="cw-btn cw-btn-ghost" disabled={loading} onClick={() => requestAgain(true)}>{t(response?.status === "failed" ? "score.retry" : "score.start")}</button> : null}
      </div>
    </div>
    <p className="review-score__hint">{t("score.hint")}</p>
    {error ? <div className="review-score__error" role="alert"><SkillErrorDetails error={error} /><button type="button" className="cw-btn cw-btn-ghost" disabled={loading} onClick={() => requestAgain(false)}>{t("score.reload")}</button></div> : null}
    {response?.error ? <div role="alert" className="review-score__error"><details className="review-score__raw-error" open>
      <summary>{t("score.originalError")}</summary><pre>{response.error}</pre>
    </details></div> : response?.status === "failed" ? <p role="alert" className="review-score__error">{t("score.failed")}</p> : null}
    {result ? <>
      {result.riskFlags.length ? <div className="review-score__risks"><h3>{t("score.risks")}</h3><ul>{result.riskFlags.map((risk, index) => <li key={`${index}:${risk.reason}`}><strong>{t(`score.severity.${risk.severity}`)}</strong>{" · "}{risk.reason}</li>)}</ul></div> : null}
      {result.coverage && !result.coverage.complete ? <div className="review-score__coverage"><h3>{t("score.coverage")}</h3><p>{t("score.coverageIncomplete")}</p><p>{t("score.coverageCount", { included: result.coverage.includedFiles, total: result.coverage.totalFiles })}</p><ul>
        {result.coverage.omittedFiles.map((file) => <li key={`omitted:${file.path}`}>{t("score.omittedFile", file)}</li>)}
        {result.coverage.truncatedFiles.map((file) => <li key={`truncated:${file.path}`}>{t("score.truncatedFile", file)}</li>)}
      </ul></div> : null}
      <dl className="review-score__dimensions">{REVIEW_SCORE_DIMENSIONS.map((dimension) => {
        const value = result.dimensions[dimension];
        return <div key={dimension} className={dimension === "safety" && value.score !== null && value.score < 60 ? "is-risk" : undefined}>
          <dt><span>{t(`score.dimensions.${dimension}`)}</span><strong>{value.score === null ? t("score.insufficient") : t("score.points", { score: value.score })}</strong></dt>
          <dd>{value.reason}</dd>
        </div>;
      })}</dl>
      {result.suggestions.length ? <div className="review-score__suggestions"><h3>{t("score.suggestions")}</h3><ul>{result.suggestions.map((suggestion, index) => <li key={`${index}:${suggestion}`}>{suggestion}</li>)}</ul></div> : null}
      <dl className="review-score__metadata">
        <div><dt>{t("score.model")}</dt><dd>{result.modelName}</dd></div>
        <div><dt>{t("score.rubric")}</dt><dd>{result.rubricVersion}</dd></div>
        <div><dt>{t("score.time")}</dt><dd><time dateTime={result.scoredAt}>{new Date(result.scoredAt).toLocaleString(i18n.language, { hour12: false })}</time></dd></div>
      </dl>
    </> : null}
  </section>;
}

export function ReviewScoreHistory({ application }: { application: ReviewApplication }) {
  const { t } = useTranslation("reviews");
  const [expanded, setExpanded] = useState(false);
  const [score, setScore] = useState<ReviewScoreResponse | undefined>(application.aiReview);
  const panelId = useId();
  useEffect(() => setScore(application.aiReview), [application.aiReview]);
  return <div className="review-score-history">
    <button type="button" className="review-score-history__toggle" aria-expanded={expanded} aria-controls={panelId} onClick={() => setExpanded((value) => !value)}>
      <span>{t("score.title")}</span><ReviewScoreLabel score={score} /><span>{t(expanded ? "score.collapse" : "score.expand")}</span>
    </button>
    {expanded ? <div id={panelId}><ReviewScoreDetails key={`${application.region}:${application.id}`} application={application} onScoreChanged={setScore} /></div> : null}
  </div>;
}
