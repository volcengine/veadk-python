import { AgentReviewCenter } from "../agent-reviews/AgentReviewCenter";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { useTranslation } from "react-i18next";
import type { StudioRole } from "../adk/client";
import { getSkillReviewFiles, listSkillReviews, type ManagedSkillFile } from "../adk/skills";
import { cloudRegionOptions, defaultCloudRegion, formatCloudRegion, type CloudProvider } from "../adk/cloudProvider";
import { normalizeSkillError, SkillErrorDetails } from "../ui/skills/SkillErrorDetails";
import {
  ResourceDataTable, ResourceFilterSelect, ResourceLoadingState,
  ResourcePageHeader, ResourcePageShell, ResourceTabs, ResourceToolbar,
  type ResourceDataTableColumn,
} from "../ui/ResourceCollection";
import { SidebarDocumentIcon } from "../ui/icons/SidebarIcons";
import { SourceCloseIcon } from "../ui/icons/SourceWorkspaceIcons";
import { filterReviewApplications, type ReviewApplication, type ReviewKind, type ReviewStatus, type ReviewDecision } from "./reviewModel";
import { ReviewDecisionDialog } from "./ReviewDecisionDialog";
import { ReviewOutcome, ReviewerIdentity, ReviewStatusLabel } from "./ReviewOutcome";
import { ReviewScoreDetails, ReviewScoreLabel } from "./ReviewScore";
import { reviewScoreSummary, scoreInProgress, type ReviewScoreResponse } from "./scoreModel";
import "./ReviewCenter.css";

const SkillFileTree = lazy(() => import("../ui/skills/SkillFileTree").then((module) => ({ default: module.SkillFileTree })));

function ReviewDetails({ application, cloudProvider, onClose, onDecision, onScoreChanged }: {
  application: ReviewApplication; cloudProvider: CloudProvider; onClose: () => void;
  onDecision: (decision: ReviewDecision) => void;
  onScoreChanged: (score: ReviewScoreResponse, requested: boolean) => void;
}) {
  const { t, i18n } = useTranslation("reviews");
  const [tab, setTab] = useState<"overview" | "files" | "score">("overview");
  const [files, setFiles] = useState<ManagedSkillFile[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [revision, setRevision] = useState(0);
  const previousFocus = useRef(document.activeElement instanceof HTMLElement ? document.activeElement : null);
  useEffect(() => {
    if (tab !== "files") return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    void getSkillReviewFiles({ id: application.id, region: application.region, signal: controller.signal })
      .then((response) => { if (!controller.signal.aborted) setFiles(response.files); })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setError(normalizeSkillError(reason, t("detail.filesFailed"))); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [application.id, application.region, tab, revision, t]);
  const reviewedAt = application.reviewedAt ? new Date(application.reviewedAt).toLocaleString(i18n.language, { hour12: false }) : "—";
  const submittedAt = application.submittedAt ? new Date(application.submittedAt).toLocaleString(i18n.language, { hour12: false }) : "—";
  return (
    <Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Backdrop className="review-backdrop" />
        <Dialog.Popup className="review-drawer" finalFocus={() => previousFocus.current?.isConnected ? previousFocus.current : document.getElementById("review-skill-tab")}>
          <header className="review-drawer__header">
            <div><Dialog.Title>{t("detail.title")}</Dialog.Title><Dialog.Description>{t("detail.versionFixed")}</Dialog.Description></div>
            <Dialog.Close className="review-icon-button" aria-label={t("actions.close")}><SourceCloseIcon /></Dialog.Close>
          </header>
          <div className="review-drawer__identity">
            <span className="review-resource-icon"><SidebarDocumentIcon /></span>
            <div><h2>{application.name}</h2><span>{t("kind.skill")} · {application.version}</span></div>
            <ReviewStatusLabel status={application.status} />
          </div>
          <ResourceTabs className="review-drawer__tabs" idPrefix="review-detail" ariaLabel={t("detail.sections")} value={tab}
            items={[
              { id: "overview", label: t("detail.overview"), panelId: "review-detail-panel" },
              { id: "files", label: t("detail.filesTab"), panelId: "review-detail-panel" },
              { id: "score", label: t("score.title"), panelId: "review-detail-panel" },
            ]} onChange={setTab} />
          <div className="review-drawer__body" id="review-detail-panel" role="tabpanel" aria-labelledby={`review-detail-${tab}-tab`}>
            {tab === "score" ? <ReviewScoreDetails key={`${application.region}:${application.id}`} application={application} canRetry onScoreChanged={onScoreChanged} /> : tab === "files" ? loading ? <ResourceLoadingState /> : error ? (
              <div role="alert"><SkillErrorDetails error={error} /><button type="button" onClick={() => setRevision((value) => value + 1)}>{t("space.retry")}</button></div>
            ) : <div className="review-files"><Suspense fallback={<ResourceLoadingState />}><SkillFileTree files={files} /></Suspense></div> : (
              <>
                <dl className="review-facts">
                  <div><dt>{t("columns.submitter")}</dt><dd>{application.author || t("detail.unknownAuthor")}</dd></div>
                  <div><dt>{t("columns.submittedAt")}</dt><dd>{submittedAt}</dd></div>
                  <div><dt>{t("columns.version")}</dt><dd>{application.version}</dd></div>
                  <div><dt>{t("detail.source")}</dt><dd>{t("detail.source_skill", { name: application.author })}</dd></div>
                  <div><dt>{t("detail.destination")}</dt><dd>{t("detail.destination_skill")}</dd></div>
                  <div><dt>{t("detail.region")}</dt><dd>{formatCloudRegion(application.region, cloudProvider)}</dd></div>
                  <div><dt>{t("detail.visibility")}</dt><dd>{t("detail.shared")}</dd></div>
                </dl>
                <section className="review-detail-section"><h3>{t("detail.description")}</h3><p>{application.description || "—"}</p></section>
                <section className="review-detail-section"><h3>{t("detail.result")}</h3><ReviewOutcome application={application} /></section>
                <section className="review-detail-section review-history">
                  <h3>{t("detail.history")}</h3>
                  <div><span className="review-history__dot" aria-hidden="true" /><p><strong>{t("detail.submitted", { name: application.author })}</strong><span>{submittedAt}</span></p></div>
                  {application.reviewedAt ? <div><span className="review-history__dot" aria-hidden="true" /><p><strong>{t(`detail.${application.status === "approved" ? "approved" : application.status === "returned" ? "returned" : "approving"}`, {name: application.reviewer?.name || application.reviewedBy || t("detail.unknownReviewer")})}</strong><span>{reviewedAt}</span></p></div> : null}
                </section>
              </>
            )}
          </div>
          <footer className="review-drawer__footer">
            {application.status === "pending" ? <Button color="secondary" variant="outline" size="md" pill={false} onClick={() => onDecision("returned")}>{t("actions.return")}</Button> : null}
            {application.status === "pending" || application.status === "approving" ? <Button color="primary" size="md" pill={false} onClick={() => onDecision("approved")}>{t(application.status === "approving" ? "actions.resumeApproval" : "actions.approve")}</Button> : <span>{t(`status.${application.status}`)}</span>}
          </footer>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function ReviewCenterContent({ cloudProvider, onAgentChanged }: { cloudProvider: CloudProvider; onAgentChanged?: () => void }) {
  const { t, i18n } = useTranslation("reviews");
  const [applications, setApplications] = useState<ReviewApplication[]>([]);
  const [agentPendingCount, setAgentPendingCount] = useState<number | null>(null);
  const [kind, setKind] = useState<ReviewKind>("skill");
  const [region, setRegion] = useState<string>(defaultCloudRegion(cloudProvider));
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [revision, setRevision] = useState(0);
  const [status, setStatus] = useState<ReviewStatus | "all">("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<ReviewApplication | null>(null);
  const [decision, setDecision] = useState<{application: ReviewApplication; value: ReviewDecision; fromDetails: boolean} | null>(null);
  const [notice, setNotice] = useState("");
  const openDecision = (application: ReviewApplication, value: ReviewDecision, fromDetails = false) => {
    setSelected(null);
    setNotice("");
    setDecision({application, value, fromDetails});
  };
  useEffect(() => {
    if (kind !== "skill") return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let inFlight = false;
    let scoring = false;
    setLoading(true);
    setError(null);
    const load = async () => {
      if (inFlight || controller.signal.aborted) return;
      inFlight = true;
      try {
        const response = await listSkillReviews({ region, signal: controller.signal });
        if (controller.signal.aborted) return;
        setApplications(response.items);
        setSelected((current) => current ? response.items.find((item) => item.id === current.id) || null : null);
        scoring = response.items.some((item) => scoreInProgress(item.aiReview));
        if (scoring && document.visibilityState !== "hidden") timer = setTimeout(() => void load(), 5000);
      } catch (reason: unknown) {
        if (!controller.signal.aborted) setError(normalizeSkillError(reason, t("space.failed")));
        scoring = false;
      } finally {
        inFlight = false;
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    const visibilityChanged = () => {
      clearTimeout(timer);
      if (scoring && document.visibilityState !== "hidden") void load();
    };
    void load();
    document.addEventListener("visibilitychange", visibilityChanged);
    return () => { controller.abort(); clearTimeout(timer); document.removeEventListener("visibilitychange", visibilityChanged); };
  }, [region, kind, revision, t]);
  const visible = filterReviewApplications(applications, kind, status, query);
  const hasFilters = Boolean(query.trim()) || status !== "all";
  const columns: ResourceDataTableColumn<ReviewApplication>[] = [
    { key: "name", header: t("columns.application"), className: "review-column-name", render: (item) => <div className="review-name"><span className="review-resource-icon"><SidebarDocumentIcon /></span><div><button type="button" title={item.name} onClick={() => setSelected(item)}>{item.name}</button></div></div> },
    { key: "submitter", header: t("columns.submitter"), className: "review-column-submitter", render: (item) => item.author || t("detail.unknownAuthor") },
    { key: "version", header: t("columns.version"), className: "review-column-version", render: (item) => item.version },
    { key: "submitted", header: t("columns.submittedAt"), className: "review-column-time", render: (item) => item.submittedAt ? <time dateTime={item.submittedAt} title={new Date(item.submittedAt).toLocaleString(i18n.language)}>{new Date(item.submittedAt).toLocaleString(i18n.language, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false })}</time> : "—" },
    { key: "status", header: t("columns.status"), className: "review-column-status", render: (item) => <div className="review-table-outcome"><ReviewStatusLabel status={item.status} />{item.reviewer || item.reviewedBy ? <ReviewerIdentity compact person={item.reviewer} fallback={item.reviewedBy} /> : null}</div> },
    { key: "score", header: t("score.title"), className: "review-column-score", render: (item) => <ReviewScoreLabel score={item.aiReview} /> },
    { key: "actions", header: t("columns.actions"), className: "review-column-actions", render: (item) => <div className="review-row-actions"><button type="button" onClick={() => setSelected(item)} aria-label={t("actions.detailsFor", { name: item.name })}>{t("actions.details")}</button>{item.status === "pending" || item.status === "approving" ? <button type="button" onClick={() => openDecision(item, "approved")}>{t(item.status === "approving" ? "actions.resumeApproval" : "actions.approve")}</button> : null}{item.status === "pending" ? <button type="button" onClick={() => openDecision(item, "returned")}>{t("actions.return")}</button> : null}</div> },
  ];
  return (
    <ResourcePageShell className="review-center" aria-label={t("title")}>
      <ResourcePageHeader title={t("title")} />
      <ResourceToolbar>
        <ResourceTabs idPrefix="review" ariaLabel={t("category")} value={kind}
          items={(["skill", "agent"] as const).map((item) => ({ id: item, label: <>{t(`kind.${item}`)}{item === "agent" ? agentPendingCount === null ? null : <span className="review-tab-count">{agentPendingCount}</span> : <span className="review-tab-count">{applications.filter((application) => application.kind === item && (application.status === "pending" || application.status === "approving")).length}</span>}</>, panelId: "review-requests-panel" }))}
          onChange={(next) => { setKind(next); setStatus("all"); setQuery(""); setSelected(null); }} />
      </ResourceToolbar>
      <div className="review-center__panel" id="review-requests-panel" role="tabpanel" aria-labelledby={`review-${kind}-tab`}>
        {kind === "agent" ? <AgentReviewCenter cloudProvider={cloudProvider} onPendingCountChange={setAgentPendingCount} onChanged={onAgentChanged} /> : <>
        {kind === "skill" && error ? <div role="alert"><SkillErrorDetails error={error} /><button type="button" onClick={() => setRevision((value) => value + 1)}>{t("space.retry")}</button></div> : null}
        {notice ? <p role="status" className="review-notice">{notice}</p> : null}
        <ResourceDataTable rows={visible} rowKey={(item) => item.id} columns={columns}
          searchValue={query} onSearchChange={setQuery} searchPlaceholder={t("search")} searchLabel={t("search")}
          toolbarActions={<>
            {kind === "skill" ? <><ResourceFilterSelect id="review-region" ariaLabel={t("detail.region")} value={region} options={cloudRegionOptions(cloudProvider)} onChange={(next) => { setApplications([]); setSelected(null); setRegion(next); }} /><button type="button" disabled={loading} onClick={() => setRevision((value) => value + 1)}>{t("actions.refresh")}</button></> : null}
            <ResourceFilterSelect id="review-status" ariaLabel={t("filterStatus")} value={status} options={(["all", "pending", "approving", "approved", "returned"] as const).map((value) => ({ value, label: t(`status.${value}`) }))} onChange={setStatus} />
          </>}
          emptyLabel={kind === "skill" && loading ? <ResourceLoadingState /> : kind === "skill" && error ? null : <div className="review-empty"><strong>{t(hasFilters ? "empty.filteredTitle" : "empty.title")}</strong><span>{t(hasFilters ? "empty.filteredDescription" : "empty.description")}</span>{hasFilters ? <button type="button" onClick={() => { setQuery(""); setStatus("all"); }}>{t("actions.clearFilters")}</button> : null}</div>} />
        <div className="review-center__count">{t("total", { count: visible.length })}</div>
        </>}
      </div>
      {selected ? <ReviewDetails key={selected.id} application={selected} cloudProvider={cloudProvider} onClose={() => setSelected(null)} onDecision={(value) => openDecision(selected, value, true)} onScoreChanged={(score, requested) => {
        const aiReview = reviewScoreSummary(score);
        setApplications((items) => items.map((item) => item.id === selected.id ? { ...item, aiReview } : item));
        if (requested) setRevision((value) => value + 1);
      }} /> : null}
      {decision ? <ReviewDecisionDialog key={`${decision.application.id}:${decision.value}`} application={decision.application} decision={decision.value}
        onClose={() => { if (decision.fromDetails) setSelected(decision.application); setDecision(null); setRevision((value) => value + 1); }}
        onDecided={(updated) => {
          setApplications((items) => items.map((item) => item.id === updated.id ? updated : item));
          if (decision.fromDetails) setSelected(updated);
          setNotice(t(updated.status === "approved" ? "decision.approved" : "decision.returned", {name: updated.name}));
          setDecision(null);
        }} /> : null}
    </ResourcePageShell>
  );
}

export function ReviewCenter({ role, cloudProvider, onAgentChanged }: { role: StudioRole; cloudProvider: CloudProvider; onAgentChanged?: () => void }) {
  const { t } = useTranslation("reviews");
  if (role !== "admin" && role !== "super_admin") {
    return <ResourcePageShell className="review-center"><ResourcePageHeader title={t("title")} /><p role="status">{t("adminOnly")}</p></ResourcePageShell>;
  }
  return <ReviewCenterContent key={cloudProvider} cloudProvider={cloudProvider} onAgentChanged={onAgentChanged} />;
}
