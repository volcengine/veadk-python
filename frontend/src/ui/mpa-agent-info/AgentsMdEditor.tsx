import { useEffect, useRef, useState } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { useTranslation } from "react-i18next";
import { ModalLayout } from "../../components/layouts/ModalLayout";
import { Button } from "../../components/primitives/Button";
import { Textarea } from "../../components/primitives/Textarea";
import { ScrollArea } from "../../components/primitives/ScrollArea";
import { TextShimmer } from "../text-shimmer/TextShimmer";
import {
  AgentsMdError,
  requestAgentsMdDocument,
  type AgentsMdDocument,
  type AgentsMdTarget,
} from "../../adk/agentsMd";
import "../../components/composites/ModalButton/ModalButton.css";
import "./AgentsMdEditor.css";

export function AgentsMdEditor({
  target,
  onClose,
  onSaved,
}: {
  target: AgentsMdTarget;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation("workspaceTools");
  const [record, setRecord] = useState<AgentsMdDocument | null>(null);
  const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [uncertain, setUncertain] = useState(false);
  const [confirmation, setConfirmation] = useState<
    "close" | "reload" | "clear" | null
  >(null);
  const saveRequest = useRef<AbortController | null>(null);
  const composing = useRef(false);
  const dirty = record !== null && content !== record.content;
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    void requestAgentsMdDocument(target, controller.signal)
      .then((value) => {
        if (controller.signal.aborted) return;
        setRecord(value);
        setContent(value.content);
        setUncertain(false);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(errorKey(reason, false));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [target.runtimeId, target.region, reload]);
  useEffect(() => () => saveRequest.current?.abort(), []);

  function close() {
    if (saveRequest.current || composing.current) return;
    if (dirty) setConfirmation("close");
    else onClose();
  }
  async function save(confirmed = false) {
    if (
      saveRequest.current ||
      composing.current ||
      !record ||
      !dirty ||
      uncertain ||
      loading ||
      content.length > 40000
    )
      return;
    if (!content && !confirmed) {
      setConfirmation("clear");
      return;
    }
    const controller = new AbortController();
    saveRequest.current = controller;
    setBusy(true);
    setError("");
    try {
      await requestAgentsMdDocument(target, controller.signal, {
        content,
        revision: record.revision,
      });
      if (!controller.signal.aborted) {
        onSaved();
        onClose();
      }
    } catch (reason: unknown) {
      if (!controller.signal.aborted) {
        const unknown =
          !(reason instanceof AgentsMdError) || reason.status >= 500;
        setUncertain(unknown);
        setError(unknown ? "agentsMdSaveUncertain" : errorKey(reason, true));
      }
    } finally {
      if (saveRequest.current === controller) saveRequest.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  function confirm() {
    const action = confirmation;
    setConfirmation(null);
    if (action === "close") onClose();
    else if (action === "reload") setReload((value) => value + 1);
    else if (action === "clear") void save(true);
  }
  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <Dialog.Portal>
        <Dialog.Backdrop className="studio-modal-button__backdrop" />
        <Dialog.Popup
          className="studio-modal-button__popup"
          render={
            <ModalLayout
              title={<Dialog.Title render={<span />}>AGENTS.md</Dialog.Title>}
              topGlow={false}
              onClose={close}
              closeLabel={t("agentTopology.close")}
              footer={
                <>
                  {error && (
                    <Button
                      variant="outline"
                      disabled={busy || loading}
                      onClick={() =>
                        dirty
                          ? setConfirmation("reload")
                          : setReload((value) => value + 1)
                      }
                    >
                      {t("agentTopology.refresh")}
                    </Button>
                  )}
                  <Button variant="outline" disabled={busy} onClick={close}>
                    {t("agentTopology.close")}
                  </Button>
                  <Button
                    loading={busy}
                    disabled={
                      !record ||
                      !dirty ||
                      loading ||
                      uncertain ||
                      content.length > 40000
                    }
                    onClick={() => void save()}
                  >
                    {t("agentTopology.saveAgentsMd")}
                  </Button>
                </>
              }
            >
              <ScrollArea className="studio-modal-button__body">
                <div className="mpa-agents-md-editor-body">
                  <p>{t("agentTopology.agentsMdEditHint")}</p>
                  {loading ? (
                    <TextShimmer as="p">
                      {t("agentTopology.agentsMdLoading")}
                    </TextShimmer>
                  ) : (
                    record && (
                      <Textarea
                        aria-label="AGENTS.md"
                        value={content}
                        disabled={busy}
                        rows={9}
                        spellCheck={false}
                        maxLength={40000}
                        onCompositionStart={() => {
                          composing.current = true;
                        }}
                        onCompositionEnd={() => {
                          composing.current = false;
                        }}
                        onChange={(event) => {
                          setContent(event.currentTarget.value);
                          setConfirmation(null);
                        }}
                      />
                    )
                  )}
                  {content.length > 40000 && (
                    <p role="alert">{t("agentTopology.agentsMdTooLong")}</p>
                  )}
                  {error && <p role="alert">{t(`agentTopology.${error}`)}</p>}
                  {confirmation && (
                    <div role="alert">
                      <p>
                        {t(
                          `agentTopology.${confirmation === "clear" ? "agentsMdClearConfirm" : "discardDocument"}`,
                        )}
                      </p>
                      <div className="mpa-agents-md-confirm-actions">
                        <Button
                          variant="outline"
                          onClick={() => setConfirmation(null)}
                        >
                          {t("agentTopology.keepEditing")}
                        </Button>
                        <Button onClick={confirm}>
                          {t("agentTopology.confirmDocument")}
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              </ScrollArea>
            </ModalLayout>
          }
        />
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function errorKey(reason: unknown, saving: boolean): string {
  if (reason instanceof AgentsMdError) {
    if ([401, 403].includes(reason.status)) return "accessDenied";
    if ([404, 405, 501].includes(reason.status))
      return "agentsMdEditUnsupported";
    if (reason.status === 409) return "agentsMdConflict";
    if (reason.status === 422) return "agentsMdTooLong";
  }
  return saving ? "documentSaveFailed" : "agentsMdLoadFailed";
}
