import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { getManagedSkillFiles, type ManagedSkillFile } from "../../adk/skills";
import { listSkillVersions, uploadSkillVersion, type SkillVersionsResult } from "../../adk/skillVersions";
import type { SkillSpaceRef, SkillSpaceSkill } from "../../create/skills/skillspace";
import { latestSourceReviews, type ReviewApplication } from "../../reviews/reviewModel";
import { ReviewHistoryList, ReviewOutcome, ReviewStatusLabel } from "../../reviews/ReviewOutcome";
import { SkillErrorDetails, normalizeSkillError } from "./SkillErrorDetails";
import { SkillFileTree } from "./SkillFileTree";
import "./SkillVersionsDialog.css";

export interface SkillVersionsDialogProps {
  skill: SkillSpaceSkill;
  space: SkillSpaceRef;
  region: string;
  reviews: ReviewApplication[];
  onClose: () => void;
  onChanged: () => void;
  onSubmitReview?: (version: string) => Promise<void>;
}

export function SkillVersionsDialog({
  skill, space, region, reviews, onClose, onChanged, onSubmitReview,
}: SkillVersionsDialogProps) {
  const { t, i18n } = useTranslation("ui");
  const [result, setResult] = useState<SkillVersionsResult | null>(null);
  const [selectedVersion, setSelectedVersion] = useState(skill.version);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [actionError, setActionError] = useState<Error | null>(null);
  const [files, setFiles] = useState<ManagedSkillFile[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [filesError, setFilesError] = useState<Error | null>(null);
  const [revision, setRevision] = useState(0);
  const [fileRevision, setFileRevision] = useState(0);
  const [busy, setBusy] = useState<"upload" | "submit" | null>(null);
  const dialog = useRef<HTMLElement>(null);
  const uploadInput = useRef<HTMLInputElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const actionLock = useRef(false);
  const mounted = useRef(true);
  const callbacks = useRef({ onClose, busy });
  callbacks.current = { onClose, busy };
  const selected = result?.items.find((item) => item.version === selectedVersion);
  const applications = useMemo(() => latestSourceReviews(reviews), [reviews]);
  const application = applications.get(`${skill.skillId}:${selectedVersion}`);
  const previousApplications = reviews.filter((item) => item.sourceSkillId === skill.skillId
    && item.version === selectedVersion && item.id !== application?.id);
  const canSubmit = Boolean(onSubmitReview && result?.canUpdate && selected
    && ["running", "ready"].includes(selected.status.toLowerCase())
    && (!application || application.status === "returned"));

  useEffect(() => {
    mounted.current = true;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButton.current?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        if (!callbacks.current.busy) callbacks.current.onClose();
      }
      if (event.key !== "Tab") return;
      const controls = Array.from(dialog.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]):not([type="file"]), a[href], summary, [tabindex="0"]',
      ) || []);
      const first = controls[0];
      const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", handleKey);
    return () => {
      mounted.current = false;
      document.removeEventListener("keydown", handleKey);
      if (previous?.isConnected) previous.focus();
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setLoadError(null);
    void listSkillVersions({ spaceId: space.id, skillId: skill.skillId, region, signal: controller.signal })
      .then((value) => {
        if (controller.signal.aborted) return;
        setResult(value);
        setSelectedVersion((previous) => value.items.some((item) => item.version === previous)
          ? previous : value.items[0]?.version || "");
      }).catch((error: unknown) => {
        if (!controller.signal.aborted) setLoadError(normalizeSkillError(error, t("skillCenter.versions.loadFailed")));
      }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [space.id, skill.skillId, region, revision, t]);

  useEffect(() => {
    if (!selectedVersion || !selected) return;
    let active = true;
    setFilesLoading(true);
    setFilesError(null);
    setFiles([]);
    void getManagedSkillFiles({ spaceId: space.id, skillId: skill.skillId, region, version: selectedVersion })
      .then((value) => { if (active) setFiles(value); })
      .catch((error: unknown) => { if (active) setFilesError(normalizeSkillError(error, t("skillCenter.versions.filesFailed"))); })
      .finally(() => { if (active) setFilesLoading(false); });
    return () => { active = false; };
  }, [space.id, skill.skillId, region, selectedVersion, Boolean(selected), fileRevision, t]);

  async function upload(file: File) {
    if (actionLock.current) return;
    actionLock.current = true;
    setBusy("upload");
    setActionError(null);
    try {
      const created = await uploadSkillVersion({ spaceId: space.id, skillId: skill.skillId, region, file });
      if (!mounted.current) return;
      setSelectedVersion(created.version);
      setRevision((value) => value + 1);
      onChanged();
    } catch (error) {
      if (mounted.current) setActionError(normalizeSkillError(error, t("skillCenter.versions.uploadFailed")));
    } finally {
      actionLock.current = false;
      if (mounted.current) setBusy(null);
    }
  }

  async function submit() {
    if (!canSubmit || !onSubmitReview || actionLock.current) return;
    actionLock.current = true;
    setBusy("submit");
    setActionError(null);
    try { await onSubmitReview(selectedVersion); }
    catch (error) {
      if (mounted.current) setActionError(normalizeSkillError(error, t("skillCenter.versions.submitFailed")));
    } finally {
      actionLock.current = false;
      if (mounted.current) setBusy(null);
    }
  }

  function dateLabel(value: string): string {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString(i18n.resolvedLanguage || i18n.language);
  }

  return (
    <div className="skill-detail-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !busy) onClose();
    }}>
      <section className="skill-detail-dialog skill-versions" role="dialog" aria-modal="true" aria-labelledby="skill-versions-title" ref={dialog}>
        <header className="skill-detail-head">
          <div className="skill-detail-heading"><div>
            <h2 id="skill-versions-title">{t("skillCenter.versions.title")}</h2>
            <p title={skill.skillName}>{skill.skillName}</p>
          </div></div>
          <div className="skill-detail-actions">
            <button type="button" disabled={loading || Boolean(busy)} onClick={() => setRevision((value) => value + 1)}>{t("skillCenter.versions.refresh")}</button>
            {result?.canUpdate ? <button type="button" disabled={Boolean(busy)} onClick={() => uploadInput.current?.click()}>
              {t(busy === "upload" ? "skillCenter.versions.uploading" : "skillCenter.versions.upload")}
            </button> : null}
            <button type="button" ref={closeButton} disabled={Boolean(busy)} onClick={onClose}>{t("skillCenter.versions.close")}</button>
          </div>
          <input className="skill-versions__file-input" ref={uploadInput} type="file" accept=".zip,application/zip" aria-label={t("skillCenter.versions.upload")} onChange={(event) => {
            const file = event.target.files?.[0]; event.target.value = ""; if (file) void upload(file);
          }} />
        </header>
        {actionError ? <div className="skill-versions__notice" role="alert"><SkillErrorDetails error={actionError} /></div> : null}
        {result?.canUpdate ? <p className="skill-versions__hint">{t("skillCenter.versions.hint")}</p> : null}
        <div className="skill-versions__body">
          <div className="skill-versions__history" aria-busy={loading}>
            {loading && !result ? <p role="status">{t("skillCenter.versions.loading")}</p> : null}
            {loadError ? <div role="alert"><SkillErrorDetails error={loadError} /><button className="cw-btn cw-btn-ghost" type="button" onClick={() => setRevision((value) => value + 1)}>{t("skillCenter.versions.retry")}</button></div> : null}
            {!loading && !loadError && !result?.items.length ? <p>{t("skillCenter.versions.empty")}</p> : null}
            <div className="skill-versions__list" role="list" aria-label={t("skillCenter.versions.title")}>
              {result?.items.map((item) => <div key={item.version} role="listitem">
                <button type="button" className={`skill-versions__version${selectedVersion === item.version ? " is-active" : ""}`} aria-pressed={selectedVersion === item.version} onClick={() => setSelectedVersion(item.version)}>
                  <span className="skill-versions__version-title"><strong>{item.sourceVersion || item.version}</strong>{item.isCurrent ? <span>{t("skillCenter.versions.current")}</span> : null}</span>
                  <time dateTime={item.createdAt}>{dateLabel(item.createdAt)}</time>
                  {applications.get(`${skill.skillId}:${item.version}`) ? <ReviewStatusLabel status={applications.get(`${skill.skillId}:${item.version}`)!.status} /> : <span>{t(space.isShared ? "skillCenter.versions.shared" : "skillCenter.versions.notSubmitted")}</span>}
                </button>
              </div>)}
            </div>
          </div>
          <div className="skill-versions__detail">
            {selected ? <>
              <div className="skill-versions__summary">
                <div><h3>{selected.sourceVersion || selected.version}</h3><p title={selected.description}>{selected.description}</p>{selected.author || skill.author ? <p className="skill-versions__author">{t("skillCenter.authorName", {name: selected.author || skill.author})}</p> : null}</div>
                {onSubmitReview && result?.canUpdate ? <button type="button" className="cw-btn cw-btn-primary" disabled={!canSubmit || Boolean(busy)} onClick={() => void submit()}>
                  {t(busy === "submit" ? "skillCenter.versions.submitting" : "skillCenter.versions.submit")}
                </button> : null}
              </div>
              {selected.error ? <p className="skill-versions__notice" role="alert">{selected.error}</p> : null}
              {!["running", "ready"].includes(selected.status.toLowerCase()) ? <p role="status">{t("skillCenter.versions.processing", { status: selected.status })}</p> : null}
              {application ? <ReviewOutcome application={application} /> : null}
              {previousApplications.length ? <details className="skill-versions__review-history"><summary>{t("skillCenter.versions.history")}</summary><ReviewHistoryList applications={previousApplications} /></details> : null}
              <div className="skill-versions__files">
                {filesLoading ? <p role="status">{t("skillCenter.versions.filesLoading")}</p> : filesError ? <div role="alert"><SkillErrorDetails error={filesError} /><button className="cw-btn cw-btn-ghost" type="button" onClick={() => setFileRevision((value) => value + 1)}>{t("skillCenter.versions.retry")}</button></div> : files.length ? <SkillFileTree key={selectedVersion} files={files} /> : <p>{t("skillCenter.versions.filesEmpty")}</p>}
              </div>
            </> : null}
          </div>
        </div>
      </section>
    </div>
  );
}
