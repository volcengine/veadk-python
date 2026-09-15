import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import {
  developmentRuns,
  DevelopmentRequestError,
  runEnded,
  type DevelopmentRun,
} from "../adk/developmentRuns";
import { Button } from "../components/primitives/Button";
import { ToastProvider, useToast } from "../components/primitives/Toast";

interface Props {
  ownerId: string;
  sessionId: string;
  onOpen: (session: string, signal: AbortSignal) => Promise<void>;
}

function TaskMonitor({ ownerId, sessionId, onOpen }: Props) {
  const { t } = useTranslation("sandbox");
  const toast = useToast();
  const current = useRef({ sessionId, onOpen, toast, t });
  current.current = { sessionId, onOpen, toast, t };
  useEffect(() => {
    if (!ownerId) return;
    const controller = new AbortController();
    const known = new Map<string, DevelopmentRun>();
    const shown = new Map<string, string>();
    const hidden = new Set<string>();
    let timer: ReturnType<typeof setTimeout>;
    const show = (run: DevelopmentRun) => {
      const { toast, t, sessionId, onOpen } = current.current;
      if (controller.signal.aborted) return;
      if (run.sessionId === sessionId) {
        toast.dismiss(run.runId);
        shown.delete(run.runId);
        return;
      }
      if (hidden.has(run.runId) || shown.get(run.runId) === run.state) return;
      shown.set(run.runId, run.state);
      toast.add({
        id: run.runId,
        duration: 0,
        title: t(`taskNotice.${run.state}`),
        description: run.message.slice(0, 80),
        variant:
          run.state === "succeeded"
            ? "success"
            : run.state === "failed"
              ? "error"
              : "info",
        closeLabel: t("taskNotice.hide"),
        onClose: () => hidden.add(run.runId),
        action: (
          <Button
            variant="secondary"
            onClick={() => {
              void onOpen(run.sessionId, controller.signal).catch((error) => {
                if (!controller.signal.aborted)
                  toast.add({
                    id: "task-open-error",
                    variant: "error",
                    description:
                      error instanceof Error ? error.message : String(error),
                  });
              });
            }}
          >
            {t("taskNotice.open")}
          </Button>
        ),
      });
    };
    const poll = async () => {
      try {
        const active = await developmentRuns.active(controller.signal);
        if (controller.signal.aborted) return;
        const ids = new Set(active.map((run) => run.runId));
        for (const previous of known.values()) {
          if (!ids.has(previous.runId) && !runEnded(previous)) {
            let ended: DevelopmentRun;
            try {
              ended = await developmentRuns.get(
                previous.runId,
                controller.signal,
              );
            } catch (error) {
              if (
                error instanceof DevelopmentRequestError &&
                error.status === 404
              ) {
                known.delete(previous.runId);
                shown.delete(previous.runId);
                current.current.toast.dismiss(previous.runId);
                continue;
              }
              throw error;
            }
            if (controller.signal.aborted) return;
            known.set(ended.runId, ended);
            show(ended);
          }
        }
        for (const run of active) {
          known.set(run.runId, run);
          show(run);
        }
        current.current.toast.dismiss("task-connection");
      } catch (error) {
        if (!controller.signal.aborted && known.size)
          current.current.toast.add({
            id: "task-connection",
            duration: 0,
            description: current.current.t("taskNotice.reconnecting"),
          });
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 3000);
      }
    };
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
      current.current.toast.dismiss();
    };
  }, [ownerId]);
  return null;
}

export function DevelopmentTaskNotice(props: Props) {
  const { t } = useTranslation("sandbox");
  return (
    <ToastProvider position="bottom-right" label={t("taskNotice.label")}>
      <TaskMonitor key={`${props.ownerId}:${props.sessionId}`} {...props} />
    </ToastProvider>
  );
}
