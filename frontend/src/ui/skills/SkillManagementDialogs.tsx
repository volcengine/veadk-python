import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { SkillSpaceRef } from "../../create/skills/skillspace";
import {
  createSkillSpace,
  updateSkillSpace,
  uploadSkillArchive,
  validateSkillArchive,
} from "../../adk/skills";
import {
  SkillConfigSelect,
  type SkillConfigOption,
} from "./SkillConfigSelect";
import { normalizeSkillError, SkillErrorDetails } from "./SkillErrorDetails";

function DialogFrame({
  title,
  children,
  onClose,
  className = "",
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  className?: string;
}) {
  const { t } = useTranslation("skills");
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="skill-dialog-backdrop" onMouseDown={onClose}>
      <section className={`skill-dialog${className ? ` ${className}` : ""}`} role="dialog" aria-modal="true" aria-label={title} onMouseDown={(event) => event.stopPropagation()}>
        <header><h2>{title}</h2><button ref={closeRef} type="button" onClick={onClose} aria-label={t("management.close")}>{t("management.close")}</button></header>
        {children}
      </section>
    </div>
  );
}

export function CreateSkillSpaceDialog({
  region: initialRegion,
  regionOptions,
  onClose,
  onCreated,
}: {
  region: string;
  regionOptions: SkillConfigOption[];
  onClose: () => void;
  onCreated: (space: SkillSpaceRef) => void;
}) {
  const { t } = useTranslation("skills");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [region, setRegion] = useState(initialRegion);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const submit = async () => {
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await createSkillSpace({
        name: name.trim(),
        description: description.trim() || undefined,
        region,
      });
      onCreated({ ...created, region: created.region || region });
    } catch (reason) {
      setError(normalizeSkillError(reason, t("management.createSpaceFailed")));
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <DialogFrame title={t("management.createSpaceTitle")} onClose={onClose}>
      <div className="skill-dialog__body">
        <label><span>{t("management.name")}</span><input autoFocus value={name} maxLength={128} onChange={(event) => setName(event.target.value)} /></label>
        <SkillConfigSelect
          label={t("management.region")}
          value={region}
          options={regionOptions}
          onChange={setRegion}
          required
        />
        <label><span>{t("management.optionalDescription")}</span><textarea value={description} maxLength={1024} onChange={(event) => setDescription(event.target.value)} /></label>
        {error ? <div className="skill-inline-error"><SkillErrorDetails error={error} /></div> : null}
      </div>
      <footer><button type="button" className="skill-button" onClick={onClose}>{t("management.cancel")}</button><button type="button" className="skill-button skill-button--primary" disabled={!name.trim() || submitting} onClick={() => void submit()}>{submitting ? t("management.creating") : t("management.create")}</button></footer>
    </DialogFrame>
  );
}

export function EditSkillSpaceDialog({
  space,
  region,
  onClose,
  onUpdated,
}: {
  space: SkillSpaceRef;
  region: string;
  onClose: () => void;
  onUpdated: (space: SkillSpaceRef) => void;
}) {
  const { t } = useTranslation("skills");
  const [name, setName] = useState(space.name);
  const [description, setDescription] = useState(space.description || "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const submit = async () => {
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await updateSkillSpace({
        spaceId: space.id,
        name: name.trim(),
        description: description.trim() || undefined,
        region,
      });
      onUpdated({ ...space, ...updated, skillCount: space.skillCount });
    } catch (reason) {
      setError(normalizeSkillError(reason, t("management.updateSpaceFailed")));
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <DialogFrame title={t("management.editSpaceTitle")} onClose={onClose}>
      <div className="skill-dialog__body">
        <label><span>{t("management.name")}</span><input autoFocus value={name} maxLength={128} onChange={(event) => setName(event.target.value)} /></label>
        <label><span>{t("management.optionalDescription")}</span><textarea value={description} maxLength={1024} onChange={(event) => setDescription(event.target.value)} /></label>
        {error ? <div className="skill-inline-error"><SkillErrorDetails error={error} /></div> : null}
      </div>
      <footer><button type="button" className="skill-button" onClick={onClose}>{t("management.cancel")}</button><button type="button" className="skill-button skill-button--primary" disabled={!name.trim() || submitting} onClick={() => void submit()}>{submitting ? t("management.saving") : t("management.save")}</button></footer>
    </DialogFrame>
  );
}

export function UploadSkillDialog({ space, region, onClose, onUploaded }: { space: SkillSpaceRef; region: string; onClose: () => void; onUploaded: () => void }) {
  const { t, i18n } = useTranslation("skills");
  const [file, setFile] = useState<File | null>(null);
  const [validation, setValidation] = useState<{ name: string; fileCount: number } | null>(null);
  const [validating, setValidating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [dragging, setDragging] = useState(false);
  const validationRequest = useRef(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const selectFile = async (selected: File | null) => {
    const request = validationRequest.current + 1;
    validationRequest.current = request;
    setFile(selected);
    setValidation(null);
    setError(null);
    setValidating(Boolean(selected));
    if (!selected) return;
    try {
      const result = await validateSkillArchive(selected);
      if (validationRequest.current === request) {
        setValidation({ name: result.name, fileCount: result.files.length });
      }
    } catch (reason) {
      if (validationRequest.current === request) {
        setError(normalizeSkillError(reason, t("management.archiveValidationFailed")));
      }
    } finally {
      if (validationRequest.current === request) setValidating(false);
    }
  };
  const upload = async () => {
    if (!file || !validation) return;
    setSubmitting(true);
    setError(null);
    try {
      await uploadSkillArchive({ spaceId: space.id, region, project: space.projectName, file });
      onUploaded();
    } catch (reason) {
      setError(normalizeSkillError(reason, t("management.uploadFailed")));
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <DialogFrame title={t("management.uploadTitle", { name: space.name })} className="skill-upload-dialog" onClose={onClose}>
      <div className="skill-dialog__body">
        <input
          ref={fileInputRef}
          className="skill-upload-dialog__input"
          type="file"
          accept=".zip,application/zip"
          onChange={(event) => void selectFile(event.target.files?.[0] || null)}
        />
        <button
          type="button"
          className={`skill-upload-dropzone${dragging ? " is-dragging" : ""}`}
          onClick={() => fileInputRef.current?.click()}
          onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
          onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; setDragging(true); }}
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
          }}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            void selectFile(event.dataTransfer.files?.[0] || null);
          }}
        >
          <strong>{file ? file.name : t("management.dropzone")}</strong>
          <span>{file ? t("fileTree.bytes", { value: new Intl.NumberFormat(i18n.resolvedLanguage).format(file.size) }) : t("management.chooseLocalFile")}</span>
        </button>
        <p>{t("management.archiveHelp")}</p>
        {validating ? <div className="skill-inline-notice">{t("management.validating")}</div> : null}
        {validation ? <div className="skill-inline-notice">{t("management.validationPassed", { name: validation.name, count: validation.fileCount })}</div> : null}
        {error ? <div className="skill-inline-error"><SkillErrorDetails error={error} /></div> : null}
      </div>
      <footer><button type="button" className="skill-button" onClick={onClose}>{t("management.cancel")}</button><button type="button" className="skill-button skill-button--primary" disabled={!file || !validation || validating || submitting} onClick={() => void upload()}>{submitting ? t("management.uploading") : t("management.upload")}</button></footer>
    </DialogFrame>
  );
}
