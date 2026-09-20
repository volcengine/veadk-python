import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Button } from "../../components/primitives/Button";
import { Textarea } from "../../components/primitives/Textarea";
import {
  getSkillDocument,
  saveSkillDocument,
  type SkillDocument,
  type SkillDocumentTarget,
} from "../../adk/skillDocuments";
import { SkillManagementApiError } from "../../adk/skills";
import "./SkillDocumentEditor.css";

export function SkillDocumentEditor({
  target,
  onClose,
  onSaved,
}: {
  target: SkillDocumentTarget;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation("workspaceTools");
  const [record, setDocument] = useState<SkillDocument | null>(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [revision, setRevision] = useState(0),
    [discard, setDiscard] = useState(false);
  const id = useId(),
    dialog = useRef<HTMLElement>(null),
    lock = useRef(false),
    mounted = useRef(true);
  const state = useRef({ dirty: false, onClose });
  state.current = {
    dirty: record !== null && content !== record.content,
    onClose,
  };
  const saveController = useRef<AbortController | null>(null);
  function close() {
    if (lock.current) return;
    if (state.current.dirty) setDiscard(true);
    else state.current.onClose();
  }
  useEffect(() => {
    mounted.current = true;
    const previous =
      window.document.activeElement instanceof HTMLElement
        ? window.document.activeElement
        : null;
    const overflow = window.document.body.style.overflow;
    window.document.body.style.overflow = "hidden";
    dialog.current?.querySelector<HTMLButtonElement>("button")?.focus();
    function key(event: KeyboardEvent) {
      if (event.isComposing) return;
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      }
      if (event.key !== "Tab") return;
      const nodes = Array.from(
        dialog.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]),textarea:not([disabled]),[tabindex="0"]',
        ) ?? [],
      );
      if (!nodes.length) return;
      if (event.shiftKey && window.document.activeElement === nodes[0]) {
        event.preventDefault();
        nodes[nodes.length - 1]?.focus();
      } else if (
        !event.shiftKey &&
        window.document.activeElement === nodes[nodes.length - 1]
      ) {
        event.preventDefault();
        nodes[0].focus();
      }
    }
    window.addEventListener("keydown", key);
    return () => {
      mounted.current = false;
      saveController.current?.abort();
      window.removeEventListener("keydown", key);
      window.document.body.style.overflow = overflow;
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void getSkillDocument({ ...target, signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) {
          setDocument(value);
          setContent(value.content);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setError("documentLoadFailed");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [target, revision]);
  async function save() {
    if (
      lock.current ||
      !record?.canUpdate ||
      content === record.content ||
      !content.trim()
    )
      return;
    lock.current = true;
    setBusy(true);
    setError("");
    const controller = new AbortController();
    saveController.current = controller;
    try {
      await saveSkillDocument({
        ...target,
        content,
        baseVersion: record.baseVersion,
        signal: controller.signal,
      });
      if (mounted.current) {
        onSaved();
        onClose();
      }
    } catch (reason) {
      if (mounted.current)
        setError(
          reason instanceof SkillManagementApiError && reason.status === 409
            ? "documentConflict"
            : reason instanceof SkillManagementApiError && reason.status === 403
              ? "accessDenied"
              : "documentSaveFailed",
        );
    } finally {
      lock.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  return createPortal(
    <div className="mpa-skill-editor-backdrop">
      <section
        className="mpa-skill-editor"
        role="dialog"
        aria-modal="true"
        aria-labelledby={id}
        ref={dialog}
      >
        <header>
          <h2 id={id}>{target.name} · SKILL.md</h2>
          <Button variant="ghost" disabled={busy} onClick={close}>
            {t("agentTopology.close")}
          </Button>
        </header>
        <p className="mpa-skill-editor-hint">
          {t("agentTopology.documentEditHint")}
        </p>
        {loading ? (
          <p role="status">{t("agentTopology.documentLoading")}</p>
        ) : record ? (
          <>
            <p>
              {record.baseVersion} ·{" "}
              {t(
                record.canUpdate
                  ? "agentTopology.documentWritable"
                  : "agentTopology.documentReadOnly",
              )}
            </p>
            <Textarea
              aria-label="SKILL.md"
              value={content}
              readOnly={!record.canUpdate}
              disabled={busy}
              maxLength={262144}
              spellCheck={false}
              onChange={(event) => setContent(event.currentTarget.value)}
            />
          </>
        ) : null}
        {error && <p role="alert">{t(`agentTopology.${error}`)}</p>}
        {discard && (
          <div role="alert">
            <p>{t("agentTopology.discardDocument")}</p>
            <Button variant="outline" onClick={() => setDiscard(false)}>
              {t("agentTopology.keepEditing")}
            </Button>
            <Button variant="secondary" onClick={onClose}>
              {t("agentTopology.discardChanges")}
            </Button>
          </div>
        )}
        <footer>
          {!record && !loading && (
            <Button
              variant="outline"
              onClick={() => setRevision((value) => value + 1)}
            >
              {t("agentTopology.refresh")}
            </Button>
          )}
          {record?.canUpdate && (
            <Button
              loading={busy}
              disabled={
                loading || content === record.content || !content.trim()
              }
              onClick={() => void save()}
            >
              {t("agentTopology.saveDocument")}
            </Button>
          )}
        </footer>
      </section>
    </div>,
    window.document.body,
  );
}
