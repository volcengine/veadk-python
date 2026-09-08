import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import type { ArtifactLibraryItem } from "./artifactLibraryModel";
import { CloseLibraryIcon } from "./icons/LibraryIcons";

export interface ArtifactMetadataUpdate {
  name: string;
  description: string;
  tags: string[];
}

interface ArtifactEditDialogProps {
  artifact: ArtifactLibraryItem;
  busy: boolean;
  error: string;
  onClose: () => void;
  onSave: (update: ArtifactMetadataUpdate) => void;
}

const MAX_NAME_LENGTH = 180;
const MAX_DESCRIPTION_LENGTH = 500;
const MAX_TAGS = 10;
const MAX_TAG_LENGTH = 32;

function parseTags(value: string): string[] {
  return Array.from(new Set(
    value
      .split(/[,，]/)
      .map((tag) => tag.trim())
      .filter(Boolean),
  ));
}

export function ArtifactEditDialog({
  artifact,
  busy,
  error,
  onClose,
  onSave,
}: ArtifactEditDialogProps) {
  const { t } = useTranslation("workspaceTools");
  const [name, setName] = useState(artifact.name);
  const [description, setDescription] = useState(artifact.description ?? "");
  const [tags, setTags] = useState((artifact.tags ?? []).join("，"));
  const [validationError, setValidationError] = useState("");
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef<HTMLElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const busyRef = useRef(busy);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    busyRef.current = busy;
    onCloseRef.current = onClose;
  }, [busy, onClose]);

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    document.body.style.overflow = "hidden";
    nameRef.current?.focus();
    nameRef.current?.select();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busyRef.current) {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )).filter((element) => element.getClientRects().length > 0);
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedName = name.trim();
    const normalizedTags = parseTags(tags);
    if (!normalizedName) {
      setValidationError(t("artifactEdit.nameRequired"));
      nameRef.current?.focus();
      return;
    }
    if (normalizedTags.length > MAX_TAGS) {
      setValidationError(t("artifactEdit.tooManyTags", { max: MAX_TAGS }));
      return;
    }
    if (normalizedTags.some((tag) => tag.length > MAX_TAG_LENGTH)) {
      setValidationError(t("artifactEdit.tagTooLong", { max: MAX_TAG_LENGTH }));
      return;
    }
    setValidationError("");
    onSave({
      name: normalizedName,
      description: description.trim(),
      tags: normalizedTags,
    });
  };

  const visibleError = validationError || error;

  return createPortal(
    <div
      className="artifact-edit-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onClose();
      }}
    >
      <section
        ref={dialogRef}
        className="artifact-edit-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        aria-busy={busy || undefined}
      >
        <header className="artifact-edit-dialog__header">
          <div>
            <h2 id={titleId}>{t("artifactEdit.title")}</h2>
            <p id={descriptionId}>{t("artifactEdit.subtitle")}</p>
          </div>
          <button type="button" onClick={onClose} disabled={busy} aria-label={t("artifactEdit.close")}>
            <CloseLibraryIcon />
          </button>
        </header>
        <form onSubmit={submit}>
          <div className="artifact-edit-dialog__body">
            <label className="artifact-edit-field">
              <span>{t("artifactEdit.name")}</span>
              <input
                ref={nameRef}
                value={name}
                maxLength={MAX_NAME_LENGTH}
                disabled={busy}
                aria-invalid={Boolean(visibleError) || undefined}
                onChange={(event) => {
                  setName(event.target.value);
                  setValidationError("");
                }}
              />
            </label>
            <label className="artifact-edit-field">
              <span>{t("artifactEdit.description")}</span>
              <textarea
                value={description}
                maxLength={MAX_DESCRIPTION_LENGTH}
                disabled={busy}
                rows={4}
                placeholder={t("artifactEdit.descriptionPlaceholder")}
                onChange={(event) => setDescription(event.target.value)}
              />
              <small>{description.length}/{MAX_DESCRIPTION_LENGTH}</small>
            </label>
            <label className="artifact-edit-field">
              <span>{t("artifactEdit.tags")}</span>
              <input
                value={tags}
                disabled={busy}
                placeholder={t("artifactEdit.tagsPlaceholder", { max: MAX_TAGS })}
                onChange={(event) => {
                  setTags(event.target.value);
                  setValidationError("");
                }}
              />
            </label>
            {visibleError ? (
              <div className="artifact-edit-error" role="alert">{visibleError}</div>
            ) : null}
          </div>
          <footer className="artifact-edit-dialog__actions">
            <button type="button" onClick={onClose} disabled={busy}>{t("artifactEdit.cancel")}</button>
            <button type="submit" className="is-primary" disabled={busy}>
              {busy ? t("artifactEdit.saving") : t("artifactEdit.save")}
            </button>
          </footer>
        </form>
      </section>
    </div>,
    document.body,
  );
}
