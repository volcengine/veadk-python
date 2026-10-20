import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Checkbox } from "@openai/apps-sdk-ui/components/Checkbox";
import { useTranslation } from "react-i18next";
import {
  SANDBOX_DISPLAY_NAME_MAX_LENGTH,
  type SandboxAgentKind,
} from "../adk/sandbox";
import { SandboxAgentIcon } from "./icons/SandboxAgentIcons";

export type SandboxLaunchState = "confirm" | "loading" | "error";

export interface SandboxLaunchDialogProps {
  open: boolean;
  state: SandboxLaunchState;
  agentKind?: "codex" | SandboxAgentKind;
  error?: string;
  persistentEnabled?: boolean;
  persistentReason?: string;
  persistentRequired?: boolean;
  storageMode?: "snapshot" | "disk";
  diskGbDefault?: number;
  diskGbMin?: number;
  diskGbMax?: number;
  onCancel: () => void;
  onConfirm: (displayName: string, persistent: boolean, diskGb?: number) => void;
}

export function SandboxLaunchDialog({
  open,
  state,
  agentKind = "codex",
  error,
  persistentEnabled = true,
  persistentReason = "",
  persistentRequired = false,
  storageMode = "snapshot",
  diskGbDefault = 10,
  diskGbMin = 5,
  diskGbMax = 100,
  onCancel,
  onConfirm,
}: SandboxLaunchDialogProps) {
  const { t } = useTranslation("sandbox");
  const agentLabel = agentKind === "codex"
    ? "Codex"
    : agentKind === "deepseek-harness"
      ? "DeepSeek Harness"
      : agentKind === "openclaw" ? "OpenClaw" : "Hermes";
  const defaultDisplayName = agentKind === "codex"
    ? t("launch.defaultName")
    : t("launch.namedDefault", { agent: agentLabel });
  const dialogRef = useRef<HTMLFormElement>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);
  const composingRef = useRef(false);
  const onCancelRef = useRef(onCancel);
  const [displayName, setDisplayName] = useState(defaultDisplayName);
  const [persistent, setPersistent] = useState(true);
  const [diskGb, setDiskGb] = useState(diskGbDefault);
  onCancelRef.current = onCancel;

  useEffect(() => {
    if (!open) return;
    setDisplayName(defaultDisplayName);
    setPersistent(persistentRequired || persistentEnabled);
    setDiskGb(diskGbDefault);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusFrame = window.requestAnimationFrame(() => {
      nameInputRef.current?.focus();
      nameInputRef.current?.select();
    });
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancelRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const controls = dialogRef.current?.querySelectorAll<HTMLElement>(
        "input:not(:disabled), button:not(:disabled)",
      );
      if (!controls?.length) return;
      const first = controls[0];
      const last = controls[controls.length - 1];
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
      window.cancelAnimationFrame(focusFrame);
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [defaultDisplayName, diskGbDefault, open, persistentEnabled, persistentRequired]);

  if (!open) return null;

  const loading = state === "loading";
  const validDisplayName = displayName.trim();
  const validDiskGb = Number.isInteger(diskGb) && diskGb >= diskGbMin && diskGb <= diskGbMax;
  const title = loading
    ? t("launch.creatingTitle", { agent: agentLabel })
    : state === "error"
      ? t("launch.failedTitle")
      : t("launch.createTitle", { agent: agentLabel });

  return createPortal(
    <div
      className="sandbox-dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !loading) onCancel();
      }}
    >
      <form
        ref={dialogRef}
        className="sandbox-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="sandbox-dialog-title"
        aria-describedby={state === "confirm" ? undefined : "sandbox-dialog-description"}
        onSubmit={(event) => {
          event.preventDefault();
          if (
            !loading &&
            !composingRef.current &&
            validDisplayName &&
            (storageMode !== "disk" || validDiskGb)
          ) {
            onConfirm(
              validDisplayName,
              storageMode === "disk" ? true : persistent,
              storageMode === "disk" ? diskGb : undefined,
            );
          }
        }}
      >
        <div className="sandbox-dialog-visual" aria-hidden="true">
          <span className="sandbox-dialog-orbit" />
          <span className="sandbox-dialog-icon">
            {loading ? (
              <span className="sandbox-spinner" />
            ) : (
              <SandboxAgentIcon kind={agentKind} />
            )}
          </span>
        </div>
        <div className="sandbox-dialog-copy">
          <h2 id="sandbox-dialog-title">{title}</h2>
          {state === "error" ? (
            <p id="sandbox-dialog-description" className="sandbox-dialog-error" role="alert">
              {error || t("launch.fallbackError")}
            </p>
          ) : loading ? (
            <p id="sandbox-dialog-description" aria-live="polite">
              {t("launch.creatingDescription", { agent: agentLabel })}
            </p>
          ) : null}
          <label className="sandbox-dialog-field">
            <span className="sandbox-dialog-field-label">
              <span>{t("launch.name")}</span>
              <span aria-hidden="true">
                {displayName.length}/{SANDBOX_DISPLAY_NAME_MAX_LENGTH}
              </span>
            </span>
            <input
              ref={nameInputRef}
              type="text"
              required
              value={displayName}
              maxLength={SANDBOX_DISPLAY_NAME_MAX_LENGTH}
              disabled={loading}
              placeholder={defaultDisplayName}
              autoComplete="off"
              onChange={(event) => setDisplayName(event.target.value)}
              onCompositionStart={() => {
                composingRef.current = true;
              }}
              onCompositionEnd={() => {
                composingRef.current = false;
              }}
              onKeyDown={(event) => {
                const { nativeEvent } = event;
                if (
                  event.key === "Enter" &&
                  (composingRef.current ||
                    nativeEvent.isComposing ||
                    nativeEvent.keyCode === 229)
                ) {
                  event.preventDefault();
                }
              }}
            />
          </label>
          {storageMode === "disk" ? (
            <label className="sandbox-dialog-field sandbox-dialog-disk-field">
              <span className="sandbox-dialog-field-label">
                <span>{t("launch.storageSize")}</span>
                <span>GiB</span>
              </span>
              <input
                type="number"
                required
                min={diskGbMin}
                max={diskGbMax}
                step={1}
                value={diskGb}
                disabled={loading}
                onChange={(event) => setDiskGb(event.currentTarget.valueAsNumber)}
              />
              <span className="sandbox-dialog-field-help">
                {t("launch.storageHelp", { min: diskGbMin, max: diskGbMax })}
              </span>
            </label>
          ) : (
            <div
              className="sandbox-dialog-persistence"
              role="group"
              aria-describedby="sandbox-persistence-description"
            >
              <Checkbox
                id="sandbox-persistence"
                className="sandbox-dialog-persistence-control"
                checked={persistent}
                disabled={loading || !persistentEnabled || persistentRequired}
                onCheckedChange={setPersistent}
                label={t("launch.persistent")}
              />
              <p
                id="sandbox-persistence-description"
                className={`sandbox-dialog-persistence-description${
                  persistent ? "" : " is-warning"
                }`}
                role={persistent ? undefined : "status"}
              >
                {!persistentEnabled
                  ? persistentReason || t("launch.persistenceUnsupported")
                  : persistent
                  ? t("launch.persistentHelp")
                  : t("launch.temporaryHelp")}
              </p>
            </div>
          )}
        </div>
        <footer className="sandbox-dialog-actions">
          <button ref={cancelButtonRef} type="button" onClick={onCancel}>
            {loading ? t("launch.cancelCreation") : t("common.cancel")}
          </button>
          {!loading && (
            <button
              type="submit"
              className="is-primary"
              disabled={!validDisplayName || (storageMode === "disk" && !validDiskGb)}
            >
              {state === "error" ? t("launch.retry") : t("launch.confirm")}
            </button>
          )}
        </footer>
      </form>
    </div>,
    document.body,
  );
}
