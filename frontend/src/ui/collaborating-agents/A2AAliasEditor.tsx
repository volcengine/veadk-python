import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Button,
  FormLabel,
  InputWithTailIcon,
} from "../../components/primitives";
import { requestCollaborators } from "../../adk/client";
import { aliasRecord, type AliasRecord } from "../../adk/a2aSpace";
import { CollaboratorApiError } from "../../adk/collaboratingAgents";

type Props = {
  runtimeId: string;
  region: string;
  spaceId: string;
  agentId: string;
  alias: string | null;
  revision: number;
  available: boolean;
  disabled: boolean;
  onBusy: (value: boolean) => void;
  onSaved: (value: AliasRecord) => void;
  onRefresh: () => void;
};
export function A2AAliasEditor(props: Props) {
  const { t } = useTranslation("collaboratingAgents");
  const id = useId();
  const [editing, setEditing] = useState(false);
  const [saved, setSaved] = useState<AliasRecord>({
    alias: props.alias,
    revision: props.revision,
  });
  const [value, setValue] = useState(props.alias ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const pending = useRef<AbortController | null>(null);
  const composing = useRef(false);
  const form = useRef<HTMLFormElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const restoreFocus = useRef(false);
  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => {
    setSaved({ alias: props.alias, revision: props.revision });
    setValue(props.alias ?? "");
    setUncertain(false);
    setError("");
  }, [props.alias, props.revision]);
  useEffect(() => {
    if (editing) {
      restoreFocus.current = true;
      form.current?.querySelector("input")?.focus();
    } else if (restoreFocus.current && !busy && !props.disabled) {
      trigger.current?.focus();
      restoreFocus.current = false;
    }
  }, [editing, busy, props.disabled]);
  function close() {
    if (pending.current) {
      pending.current.abort();
      pending.current = null;
      setBusy(false);
      props.onBusy(false);
      setUncertain(true);
      setError("alias.failed");
    }
    setEditing(false);
    trigger.current?.focus();
  }
  async function submit() {
    if (
      pending.current ||
      uncertain ||
      composing.current ||
      props.disabled ||
      !props.available
    )
      return;
    const alias = value.normalize("NFKC").trim();
    if (alias.length > 80 || (alias && !/^[\p{L}\p{N} ._-]+$/u.test(alias))) {
      setError("alias.invalid");
      return;
    }
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    props.onBusy(true);
    setError("");
    try {
      const record = await requestCollaborators(
        props.runtimeId,
        props.region,
        `/registry/aliases/${encodeURIComponent(props.agentId)}`,
        {
          method: "PUT",
          signal: controller.signal,
          body: JSON.stringify({
            space_id: props.spaceId,
            alias: alias || null,
            revision: saved.revision,
          }),
        },
      ).then(aliasRecord);
      if (controller.signal.aborted) return;
      setSaved(record);
      setValue(record.alias ?? "");
      setEditing(false);
      props.onSaved(record);
      trigger.current?.focus();
    } catch (reason: unknown) {
      if (controller.signal.aborted) return;
      const code =
        reason instanceof CollaboratorApiError ? reason.reason : undefined;
      setError(
        code === "alias_conflict"
          ? "alias.conflict"
          : code === "revision_conflict"
            ? "alias.revisionConflict"
            : code === "invalid_alias"
              ? "alias.invalid"
              : "alias.failed",
      );
      setUncertain(code !== "alias_conflict" && code !== "invalid_alias");
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        if (!controller.signal.aborted) {
          setBusy(false);
          props.onBusy(false);
        }
      }
    }
  }
  return (
    <div>
      <div className="collaborators-actions">
        <span>
          {t("alias.label")}: {saved.alias || t("alias.empty")}
        </span>
        <Button
          ref={trigger}
          variant="outline"
          disabled={props.disabled || !props.available || editing}
          onClick={() => {
            setValue(saved.alias ?? "");
            setEditing(true);
          }}
        >
          {t("alias.edit")}
        </Button>
      </div>
      {!props.available && (
        <p className="collaborators-help">{t("alias.unavailable")}</p>
      )}
      {editing && (
        <form
          ref={form}
          className="collaborators-form collaborators-reveal"
          onCompositionStart={() => {
            composing.current = true;
          }}
          onCompositionEnd={() => {
            composing.current = false;
          }}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              (composing.current || event.nativeEvent.isComposing)
            )
              event.preventDefault();
            if (event.key === "Escape" && !composing.current) {
              event.preventDefault();
              close();
            }
          }}
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <FormLabel htmlFor={id}>{t("alias.label")}</FormLabel>
          <InputWithTailIcon
            tailIcon={null}
            id={id}
            className="collaborators-input"
            value={value}
            maxLength={80}
            disabled={busy || uncertain}
            aria-invalid={!!error}
            aria-describedby={`${id}-help ${id}-error`}
            onChange={(event) => setValue(event.target.value)}
          />
          <p id={`${id}-help`} className="collaborators-help">
            {t("alias.help")}
          </p>
          {error && (
            <p id={`${id}-error`} role="alert">
              {t(error)}
            </p>
          )}
          <div className="collaborators-actions">
            <Button
              type="submit"
              disabled={busy || uncertain || props.disabled}
            >
              {t(busy ? "saving" : "save")}
            </Button>
            <Button type="button" variant="outline" onClick={close}>
              {t("cancel")}
            </Button>
            {uncertain && (
              <Button type="button" variant="outline" onClick={props.onRefresh}>
                {t("refresh")}
              </Button>
            )}
          </div>
        </form>
      )}
    </div>
  );
}
