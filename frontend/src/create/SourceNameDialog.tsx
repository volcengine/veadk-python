import { useId, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@openai/apps-sdk-ui/components/Tooltip";
import { normalizeSourceName, sourceNameError, SOURCE_NAME_MAX_LENGTH } from "../adk/sourceProjectName";
import { DialogShell } from "../ui/SandboxControls";
import { EditArtifactIcon } from "../ui/icons/LibraryIcons";
import { SandboxCheckIcon, SandboxSpinnerIcon } from "../ui/icons/SandboxControlIcons";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
import "./SourceNameDialog.css";

interface SourceNameDialogProps {
  kind: "project" | "version";
  initialName: string;
  busy: boolean;
  error: string;
  onClose: () => void;
  onSave: (name: string) => void;
}

export function SourceNameDialog({ kind, initialName, busy, error, onClose, onSave }: SourceNameDialogProps) {
  const { t } = useTranslation("create");
  const [name, setName] = useState(initialName);
  const [touched, setTouched] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);
  const composing = useRef(false);
  const inputId = useId();
  const helpId = useId();
  const errorId = useId();
  const invalid = sourceNameError(name);
  const normalized = normalizeSourceName(name);
  const unchanged = normalized === normalizeSourceName(initialName);
  const visibleError = touched && invalid
    ? t(`projectLibrary.rename.${invalid}`, { max: SOURCE_NAME_MAX_LENGTH })
    : error;

  function submit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (busy || composing.current || invalid || unchanged) return;
    onSave(normalized);
  }

  return (
    <DialogShell
      open
      title={t(`projectLibrary.rename.${kind}Title`)}
      icon={<EditArtifactIcon />}
      className="source-name-dialog"
      initialFocusRef={nameRef}
      busy={busy}
      onClose={onClose}
    >
      <form onSubmit={submit} noValidate>
        <div className="sandbox-control-body source-name-body">
          <label className="cw-label" htmlFor={inputId}>{t(`projectLibrary.rename.${kind}Label`)}</label>
          <input
            ref={nameRef}
            id={inputId}
            className="cw-input"
            value={name}
            maxLength={SOURCE_NAME_MAX_LENGTH * 4}
            disabled={busy}
            autoComplete="off"
            spellCheck={false}
            aria-invalid={Boolean(touched && invalid) || undefined}
            aria-describedby={`${helpId}${visibleError ? ` ${errorId}` : ""}`}
            onFocus={(event) => event.currentTarget.select()}
            onBlur={() => setTouched(true)}
            onChange={(event) => { setName(event.target.value); setTouched(true); }}
            onCompositionStart={() => { composing.current = true; }}
            onCompositionEnd={() => { composing.current = false; }}
            onKeyDown={(event) => {
              if (composing.current || event.nativeEvent.isComposing || event.keyCode === 229) {
                event.stopPropagation();
                if (event.key === "Enter") event.preventDefault();
              }
            }}
          />
          <p id={helpId} className="cw-help">{t("projectLibrary.rename.hint", { max: SOURCE_NAME_MAX_LENGTH })}</p>
          {visibleError ? <p id={errorId} className="cw-error-text" role="alert">{visibleError}</p> : null}
        </div>
        <footer className="sandbox-control-actions source-name-actions">
          <span className="source-name-count" aria-live="polite">
            {Array.from(normalized).length}/{SOURCE_NAME_MAX_LENGTH}
          </span>
          {busy ? <TextShimmer as="span">{t("projectLibrary.rename.saving")}</TextShimmer> : null}
          <Tooltip compact content={t("projectLibrary.rename.save")}>
            <button
              type="submit"
              className="is-primary source-name-save"
              disabled={busy || Boolean(invalid) || unchanged}
              aria-label={t("projectLibrary.rename.save")}
              aria-busy={busy || undefined}
              title={t("projectLibrary.rename.save")}
            >
              {busy ? <SandboxSpinnerIcon /> : <SandboxCheckIcon />}
            </button>
          </Tooltip>
        </footer>
      </form>
    </DialogShell>
  );
}
