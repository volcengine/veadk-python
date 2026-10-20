import { useEffect, useState } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { useTranslation } from "react-i18next";
import { changeAgentReview, readAgentReview, type AgentReviewApplication, type ReviewPerson } from "../adk/agentReviews";
import { ResourceLoadingState } from "../ui/ResourceCollection";
import { APPLICATION_MESSAGE_LIMIT, REVIEW_TEXT_LIMIT } from "./limits";
import "./agentReviews.css";

function ReviewTextField({ label, value, onChange, limit, disabled, required = false }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  limit: number;
  disabled: boolean;
  required?: boolean;
}) {
  const { t } = useTranslation("agentReviews");
  return <label>{label}
    <textarea aria-label={label} value={value} onChange={(event) => onChange(Array.from(event.target.value).slice(0, limit).join(""))}
      maxLength={limit * 2} disabled={disabled} required={required} rows={3} />
    <span className="agent-review-text-count">{t("textCount", { count: Array.from(value).length, limit })}</span>
  </label>;
}

export function ReviewPersonLabel({ person }: { person: ReviewPerson }) {
  return <span className="agent-review-person" title={person.email || person.name}>
    {person.avatarUrl ? <img src={person.avatarUrl} alt="" referrerPolicy="no-referrer" onError={(event) => { event.currentTarget.hidden = true; }} /> : null}
    <span>{person.name || person.id}</span>
  </span>;
}

export function AgentReviewDialog({ runtimeId, region, name, canPublish, onClose, onChanged }: {
  runtimeId: string;
  region: string;
  name: string;
  canPublish: boolean;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { t, i18n } = useTranslation("agentReviews");
  const [application, setApplication] = useState<AgentReviewApplication | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [comment, setComment] = useState("");
  const [reason, setReason] = useState("");
  const [revision, setRevision] = useState(0);
  const [returning, setReturning] = useState(false);
  const [confirmAction, setConfirmAction] = useState<"withdraw" | "unpublish" | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void readAgentReview(runtimeId, region, controller.signal).then((result) => {
      if (!controller.signal.aborted) setApplication(result.application);
    }).catch((value: unknown) => {
      if (!controller.signal.aborted) setError(value instanceof Error ? value.message : String(value));
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [runtimeId, region, revision]);

  async function change(action: "submit" | "publish" | "withdraw" | "unpublish" | "decision", decision?: "approved" | "returned") {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await changeAgentReview(runtimeId, action, {
        region,
        ...(action === "submit" ? { message } : {}),
        ...(action === "publish" || action === "decision" ? { comment } : {}),
        ...(action === "decision" ? { applicationId: application?.id, decision, reason } : {}),
      });
      setApplication(result);
      setComment(""); setReason(""); setReturning(false); setConfirmAction(null);
      onChanged();
    } catch (value: unknown) {
      setError(value instanceof Error ? value.message : String(value));
    } finally {
      setBusy(false);
    }
  }

  const pending = application?.status === "pending";
  const published = Boolean(application?.published);
  const canSubmit = !pending && !published;
  const time = (value: string) => new Date(value).toLocaleString(i18n.language);
  return <Dialog.Root open onOpenChange={(open) => { if (!open && !busy) onClose(); }}>
    <Dialog.Portal><Dialog.Backdrop className="agent-review-backdrop" /><Dialog.Popup className="agent-review-dialog">
      <header className="agent-review-dialog-header">
        <div><Dialog.Title>{name}</Dialog.Title><Dialog.Description>{t("dialogDescription")}</Dialog.Description></div>
        <Dialog.Close className="agent-review-close" disabled={busy} aria-label={t("close")}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" /></svg>
        </Dialog.Close>
      </header>
      <div className="agent-review-dialog-body">
        {loading ? <ResourceLoadingState /> : null}
        {error ? <div className="agent-review-error" role="alert"><p>{error}</p><button type="button" disabled={busy || loading} onClick={() => setRevision((value) => value + 1)}>{t("refresh")}</button></div> : null}
        {!loading && application ? <>
          <dl className="agent-review-facts">
            <div><dt>{t("statusTitle")}</dt><dd>{t(`status.${application.status}`)}{application.status === "approved" && !published ? ` · ${t("private")}` : ""}</dd></div>
            <div><dt>{t("submitter")}</dt><dd><ReviewPersonLabel person={application.submitter} /></dd></div>
            <div><dt>{t("submittedAt")}</dt><dd>{time(application.submittedAt)}</dd></div>
            <div><dt>{t("version")}</dt><dd>{application.agent.version ?? "—"}</dd></div>
            <div><dt>{t("model")}</dt><dd>{application.agent.model || "—"}</dd></div>
            {application.reviewer ? <div><dt>{t(application.status === "returned" ? "returnedBy" : "approvedBy")}</dt><dd><ReviewPersonLabel person={application.reviewer} /></dd></div> : null}
            {application.reviewedAt ? <div><dt>{t("reviewedAt")}</dt><dd>{time(application.reviewedAt)}</dd></div> : null}
          </dl>
          <section><h3>{t("description")}</h3><p>{application.agent.description || "—"}</p></section>
          {application.message ? <section><h3>{t("message")}</h3><p>{application.message}</p></section> : null}
          {application.reason ? <section><h3>{t("reason")}</h3><p>{application.reason}</p></section> : null}
          {application.comment ? <section><h3>{t("comment")}</h3><p>{application.comment}</p></section> : null}
          {application.contentChanged ? <p role="alert" className="agent-review-warning">{t("contentChanged")}</p> : null}
        </> : null}
        {!loading && !error && canSubmit && !canPublish ? <ReviewTextField label={t("message")} value={message} onChange={setMessage} limit={APPLICATION_MESSAGE_LIMIT} disabled={busy} /> : null}
        {!loading && !error && canPublish && (pending || canSubmit) ? <ReviewTextField label={t("comment")} value={comment} onChange={setComment} limit={REVIEW_TEXT_LIMIT} disabled={busy} /> : null}
        {returning ? <ReviewTextField label={t("reasonRequired")} value={reason} onChange={setReason} limit={REVIEW_TEXT_LIMIT} disabled={busy} required /> : null}
        {confirmAction ? <p role="status">{t(`${confirmAction}Confirm`)}</p> : null}
      </div>
      <footer className="agent-review-dialog-footer">
        {busy ? <span role="status">{t("saving")}</span> : null}
        {!loading && (!error || application) ? confirmAction ? <>
          <button type="button" disabled={busy} onClick={() => setConfirmAction(null)}>{t("cancel")}</button>
          <button type="button" disabled={busy} onClick={() => void change(confirmAction)}>{t("confirm")}</button>
        </> : returning ? <>
          <button type="button" disabled={busy} onClick={() => setReturning(false)}>{t("cancel")}</button>
          <button type="button" disabled={busy || !reason.trim()} onClick={() => void change("decision", "returned")}>{t("return")}</button>
        </> : <>
          {published ? <button type="button" disabled={busy} onClick={() => setConfirmAction("unpublish")}>{t("unpublish")}</button> : null}
          {pending ? <button type="button" disabled={busy} onClick={() => setConfirmAction("withdraw")}>{t("withdraw")}</button> : null}
          {pending && canPublish ? <>
            <button type="button" disabled={busy} onClick={() => setReturning(true)}>{t("return")}</button>
            <button type="button" className="is-primary" disabled={busy || application?.contentChanged} onClick={() => void change("decision", "approved")}>{t("approve")}</button>
          </> : null}
          {canSubmit ? <button type="button" className="is-primary" disabled={busy} onClick={() => void change(canPublish ? "publish" : "submit")}>{t(canPublish ? "publish" : "submit")}</button> : null}
        </> : null}
      </footer>
    </Dialog.Popup></Dialog.Portal>
  </Dialog.Root>;
}
