import { useRef, useState } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { useTranslation } from "react-i18next";
import { decideSkillReview } from "../adk/skills";
import { normalizeSkillError, SkillErrorDetails } from "../ui/skills/SkillErrorDetails";
import type { ReviewApplication, ReviewDecision } from "./reviewModel";

export function ReviewDecisionDialog({ application, decision, onClose, onDecided }: {
  application: ReviewApplication;
  decision: ReviewDecision;
  onClose: () => void;
  onDecided: (application: ReviewApplication) => void;
}) {
  const { t } = useTranslation("reviews");
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState(application.status === "approving" ? application.comment || "" : "");
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState<Error | null>(null);
  const reasonRequired = decision === "returned";
  const invalid = reasonRequired && !reason.trim();
  const previousFocus = useRef(document.activeElement instanceof HTMLElement ? document.activeElement : null);
  const submit = async () => {
    if (busyRef.current) return;
    setTouched(true);
    if (invalid) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      const updated = await decideSkillReview({ id: application.id, region: application.region, decision, reason: reason.trim(), comment: comment.trim() });
      onDecided(updated);
    } catch (failure) {
      setError(normalizeSkillError(failure, t("decision.failed")));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };
  return (
    <Dialog.Root open onOpenChange={(open) => { if (!open && !busyRef.current) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Backdrop className="review-backdrop" />
        <Dialog.Popup className="confirm-box review-decision" finalFocus={() => previousFocus.current?.isConnected ? previousFocus.current : document.getElementById("review-skill-tab")}>
          <Dialog.Title className="confirm-title">{t(reasonRequired ? "decision.returnTitle" : "decision.approveTitle")}</Dialog.Title>
          <Dialog.Description className="confirm-text">{t(reasonRequired ? "decision.returnDescription" : "decision.approveDescription", {name: application.name, version: application.version})}</Dialog.Description>
          {reasonRequired ? <div className="review-decision__field">
            <label className="cw-label" htmlFor="review-return-reason">{t("decision.reason")}</label>
            <textarea id="review-return-reason" className="cw-input" rows={4} maxLength={256} required disabled={busy}
              value={reason} onChange={(event) => setReason(event.target.value)} onBlur={() => setTouched(true)}
              aria-invalid={touched && invalid} aria-describedby="review-return-help" />
            <span id="review-return-help" className={touched && invalid ? "cw-error-text" : "cw-help"} role={touched && invalid ? "alert" : undefined}>
              {t(touched && invalid ? "decision.reasonRequired" : "decision.reasonHelp")}
            </span>
          </div> : null}
          <div className="review-decision__field">
            <label className="cw-label" htmlFor="review-decision-comment">{t("decision.comment")}</label>
            <textarea id="review-decision-comment" className="cw-input" rows={3} maxLength={256} disabled={busy || application.status === "approving"}
              value={comment} onChange={(event) => setComment(event.target.value)} aria-describedby="review-comment-help" />
            <span id="review-comment-help" className="cw-help">{t("decision.commentHelp")}</span>
          </div>
          {error ? <div role="alert" className="review-decision__error"><SkillErrorDetails error={error} /></div> : null}
          <div className="confirm-actions">
            <Button color="secondary" variant="outline" size="md" pill={false} disabled={busy} onClick={onClose}>{t("actions.cancel")}</Button>
            <Button color="primary" size="md" pill={false} disabled={busy || invalid} onClick={() => void submit()}>
              {t(busy ? "decision.saving" : reasonRequired ? "actions.confirmReturn" : "actions.confirmApprove")}
            </Button>
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
