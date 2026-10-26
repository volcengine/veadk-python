import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Button,
  Checkbox,
  FormLabel,
  InputWithTailIcon,
} from "../../components/primitives";
import { createA2aSpace } from "../../adk/client";
import { createdSpace, type RegistryItem } from "../../adk/a2aSpace";
import { CollaboratorApiError } from "../../adk/collaboratingAgents";
import { TextShimmer } from "../text-shimmer/TextShimmer";

type Props = {
  runtimeId: string;
  region: string;
  onCreated: (space: RegistryItem) => void;
  onCancel: () => void;
  onUncertain: () => void;
  onBusy: (busy: boolean) => void;
};
export function A2ASpaceCreation({
  runtimeId,
  region,
  onCreated,
  onCancel,
  onUncertain,
  onBusy,
}: Props) {
  const { t } = useTranslation("collaboratingAgents");
  const id = useId();
  const [name, setName] = useState("");
  const [projectName, setProjectName] = useState("default");
  const [intentEnabled, setIntentEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState("");
  const form = useRef<HTMLFormElement>(null);
  const errorElement = useRef<HTMLParagraphElement>(null);
  const composing = useRef(false);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => {
    form.current?.querySelector("input")?.focus();
    return () => pending.current?.abort();
  }, []);
  useEffect(() => {
    if (error) errorElement.current?.focus();
  }, [error]);
  function cancel() {
    if (pending.current) {
      pending.current.abort();
      onUncertain();
      onBusy(false);
    }
    onCancel();
  }
  async function submit() {
    if (pending.current || uncertain || composing.current) return;
    if (
      [name, projectName].some(
        (text) =>
          !text.trim() ||
          text.trim().length > 128 ||
          /[\u0000-\u001f\u007f]/.test(text),
      )
    ) {
      setError("spaceCreation.invalid");
      return;
    }
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    onBusy(true);
    setError("");
    try {
      const identifier = await createA2aSpace(
        region,
        {
          targetRuntimeId: runtimeId,
          name: name.trim(),
          projectName: projectName.trim(),
          intentEnabled,
        },
        controller.signal,
      ).then(createdSpace);
      if (!controller.signal.aborted)
        onCreated({
          Id: identifier,
          Name: name.trim(),
          ProjectName: projectName.trim(),
        });
    } catch (reason: unknown) {
      if (!controller.signal.aborted) {
        const unknown =
          !(reason instanceof CollaboratorApiError) || reason.status >= 500;
        if (unknown) {
          setUncertain(true);
          onUncertain();
        }
        setError(
          unknown
            ? "spaceCreation.uncertain"
            : reason.status === 401 || reason.status === 403
              ? "spaceCreation.forbidden"
              : reason.status === 422 || reason.status === 413
                ? "spaceCreation.invalid"
                : "spaceCreation.failed",
        );
      }
    } finally {
      if (!controller.signal.aborted) {
        pending.current = null;
        setBusy(false);
        onBusy(false);
      }
    }
  }
  return (
    <form
      ref={form}
      className="collaborators-form collaborators-reveal"
      aria-label={t("spaceCreation.open")}
      onCompositionStart={() => {
        composing.current = true;
      }}
      onCompositionEnd={() => {
        composing.current = false;
      }}
      onKeyDown={(event) => {
        if (
          event.nativeEvent.isComposing ||
          event.nativeEvent.keyCode === 229 ||
          composing.current
        ) {
          if (event.key === "Enter") event.preventDefault();
          return;
        }
        if (event.key === "Escape" && !event.defaultPrevented) {
          event.preventDefault();
          cancel();
        }
      }}
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <FormLabel htmlFor={`${id}-name`} required>
        {t("spaceCreation.name")}
      </FormLabel>
      <InputWithTailIcon
        className="collaborators-input"
        tailIcon={null}
        id={`${id}-name`}
        aria-label={t("spaceCreation.name")}
        required
        maxLength={128}
        value={name}
        disabled={busy || uncertain}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(event) => setName(event.target.value)}
      />
      <FormLabel htmlFor={`${id}-project`} required>
        {t("spaceCreation.project")}
      </FormLabel>
      <InputWithTailIcon
        className="collaborators-input"
        tailIcon={null}
        id={`${id}-project`}
        aria-label={t("spaceCreation.project")}
        required
        maxLength={128}
        value={projectName}
        disabled={busy || uncertain}
        onChange={(event) => setProjectName(event.target.value)}
      />
      <Checkbox
        label={t("spaceCreation.intent")}
        checked={intentEnabled}
        disabled={busy || uncertain}
        onChange={(event) => setIntentEnabled(event.target.checked)}
      />
      <p className="collaborators-help">{t("spaceCreation.intentHelp")}</p>
      {error && (
        <p role="alert" id={`${id}-error`} ref={errorElement} tabIndex={-1}>
          {t(error)}
        </p>
      )}
      {busy && (
        <TextShimmer as="span">{t("spaceCreation.creating")}</TextShimmer>
      )}
      <div className="collaborators-actions">
        <Button type="submit" disabled={busy || uncertain}>
          {t("spaceCreation.submit")}
        </Button>
        <Button variant="ghost" onClick={cancel}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}
