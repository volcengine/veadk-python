import { useRef, useState } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { useTranslation } from "react-i18next";
import { SourceCloseIcon } from "../ui/icons/SourceWorkspaceIcons";
import type { ReviewApplication, ReviewPerson, ReviewStatus } from "./reviewModel";
import { ReviewScoreHistory } from "./ReviewScore";
import "./ReviewCenter.css";

export function ReviewStatusLabel({ status }: { status: ReviewStatus }) {
  const { t } = useTranslation("reviews");
  return <span className={`review-status is-${status}`}><span aria-hidden="true" />{t(`status.${status}`)}</span>;
}

export function ReviewerIdentity({ person, fallback, compact = false }: {
  person?: ReviewPerson; fallback?: string; compact?: boolean;
}) {
  const { t } = useTranslation("reviews");
  const [failedImage, setFailedImage] = useState("");
  const name = person?.name || fallback || t("detail.unknownReviewer");
  const avatar = person?.avatarUrl;
  return <span className={`review-person${compact ? " is-compact" : ""}`}>
    {avatar && avatar !== failedImage ? <img className="review-person__avatar" src={avatar} alt="" referrerPolicy="no-referrer" onError={() => setFailedImage(avatar)} />
      : <span className="review-person__avatar is-fallback" aria-hidden="true">{Array.from(name)[0]}</span>}
    <span className="review-person__text"><span>{name}</span>{!compact && person?.email ? <span className="review-person__email">{person.email}</span> : null}</span>
  </span>;
}

export function ReviewOutcome({ application }: { application: ReviewApplication }) {
  const { t, i18n } = useTranslation("reviews");
  return <div className="review-outcome">
    <ReviewStatusLabel status={application.status} />
    {application.reviewer || application.reviewedBy || application.reviewedAt ? <dl className="review-outcome__facts">
      {application.reviewer || application.reviewedBy ? <div><dt>{t(`detail.${application.status === "returned" ? "returnedBy" : application.status === "approved" ? "approvedBy" : "reviewer"}`)}</dt><dd><ReviewerIdentity person={application.reviewer} fallback={application.reviewedBy} /></dd></div> : null}
      {application.reviewedAt ? <div><dt>{t("detail.reviewedAt")}</dt><dd><time dateTime={application.reviewedAt}>{new Date(application.reviewedAt).toLocaleString(i18n.language, {hour12: false})}</time></dd></div> : null}
    </dl> : null}
    {application.reason ? <div className="review-outcome__message is-returned"><strong>{t("decision.reason")}</strong><p>{application.reason}</p></div> : null}
    {application.comment ? <div className="review-outcome__message"><strong>{t("detail.comment")}</strong><p>{application.comment}</p></div> : null}
    {application.status === "pending" ? <p className="review-outcome__hint">{t("detail.pendingHint")}</p> : null}
    {application.status === "approving" ? <p className="review-outcome__hint">{t("detail.approvingHint")}</p> : null}
  </div>;
}

export function ReviewHistoryList({ applications }: { applications: readonly ReviewApplication[] }) {
  const { t, i18n } = useTranslation("reviews");
  if (!applications.length) return <p className="review-outcome__hint">{t("detail.noHistory")}</p>;
  return <ol className="review-source-history">
    {[...applications].sort((left, right) => right.submittedAt.localeCompare(left.submittedAt)).map((application) => <li key={application.id}>
      <div className="review-source-history__submission"><strong>{application.version}</strong><span>{t("detail.submitted", {name: application.author})}</span><time dateTime={application.submittedAt}>{new Date(application.submittedAt).toLocaleString(i18n.language, {hour12: false})}</time></div>
      <ReviewOutcome application={application} />
      <ReviewScoreHistory application={application} />
    </li>)}
  </ol>;
}

export function ReviewHistoryDialog({ name, applications, onClose }: {
  name: string; applications: readonly ReviewApplication[]; onClose: () => void;
}) {
  const { t } = useTranslation("reviews");
  const previousFocus = useRef(document.activeElement instanceof HTMLElement ? document.activeElement : null);
  return <Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
    <Dialog.Portal>
      <Dialog.Backdrop className="review-backdrop" />
      <Dialog.Popup className="review-drawer" finalFocus={() => previousFocus.current?.isConnected ? previousFocus.current : null}>
        <header className="review-drawer__header">
          <div><Dialog.Title>{t("detail.history")}</Dialog.Title><Dialog.Description>{name}</Dialog.Description></div>
          <Dialog.Close className="review-icon-button" aria-label={t("actions.close")}><SourceCloseIcon /></Dialog.Close>
        </header>
        <div className="review-drawer__body"><ReviewHistoryList applications={applications} /></div>
      </Dialog.Popup>
    </Dialog.Portal>
  </Dialog.Root>;
}
