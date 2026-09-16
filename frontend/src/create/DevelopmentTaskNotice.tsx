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
  hideNotices?: boolean;
  refreshKey?: number;
  onUpdate?: (snapshot: DevelopmentTaskSnapshot) => void;
}

export interface DevelopmentTaskSnapshot {
  ownerId: string;
  runs: DevelopmentRun[];
  loading: boolean;
  error: string;
}

function TaskMonitor({ ownerId, sessionId, onOpen, hideNotices, refreshKey, onUpdate }: Props) {
  const { t } = useTranslation("sandbox");
  const toast = useToast();
  const known = useRef(new Map<string, DevelopmentRun>());
  const shown = useRef(new Map<string, string>());
  const refresh = useRef<(() => void) | null>(null);
  const current = useRef({ sessionId, onOpen, toast, t, hideNotices, onUpdate });
  current.current = { sessionId, onOpen, toast, t, hideNotices, onUpdate };
  useEffect(() => {
    if (hideNotices) {
      current.current.toast.dismiss();
      shown.current.clear();
      return;
    }
    for (const run of known.current.values()) {
      if (run.sessionId === sessionId) {
        current.current.toast.dismiss(run.runId);
        shown.current.delete(run.runId);
      }
    }
  }, [sessionId, hideNotices]);
  useEffect(() => { refresh.current?.(); }, [refreshKey]);
  useEffect(() => {
    if (!ownerId) return;
    const controller = new AbortController();
    const knownRuns = known.current;
    const shownStates = shown.current;
    const hidden = new Set<string>();
    let timer: ReturnType<typeof setTimeout>;
    let inFlight = false;
    let activeRuns: DevelopmentRun[] = [];
    let lastError = "";
    const publish = (loading: boolean, error = lastError) => {
      lastError = error;
      if (!controller.signal.aborted)
        current.current.onUpdate?.({ ownerId, runs: activeRuns, loading, error });
    };
    const show = (run: DevelopmentRun) => {
      const { toast, t, sessionId, onOpen } = current.current;
      if (controller.signal.aborted) return;
      if (current.current.hideNotices || run.sessionId === sessionId) {
        toast.dismiss(run.runId);
        shownStates.delete(run.runId);
        return;
      }
      if (hidden.has(run.runId) || shownStates.get(run.runId) === run.state) return;
      shownStates.set(run.runId, run.state);
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
    const poll = async (manual = false) => {
      if (inFlight || controller.signal.aborted) return;
      clearTimeout(timer);
      inFlight = true;
      if (manual) publish(true);
      try {
        const active = await developmentRuns.active(controller.signal);
        if (controller.signal.aborted) return;
        activeRuns = active;
        publish(false, "");
        const ids = new Set(active.map((run) => run.runId));
        for (const previous of knownRuns.values()) {
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
                knownRuns.delete(previous.runId);
                shownStates.delete(previous.runId);
                current.current.toast.dismiss(previous.runId);
                continue;
              }
              throw error;
            }
            if (controller.signal.aborted) return;
            knownRuns.set(ended.runId, ended);
            show(ended);
          }
        }
        for (const run of active) {
          knownRuns.set(run.runId, run);
          show(run);
        }
        current.current.toast.dismiss("task-connection");
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof DevelopmentRequestError && [401, 403].includes(error.status)) {
          activeRuns = [];
          knownRuns.clear();
          shownStates.clear();
          current.current.toast.dismiss();
        }
        publish(false, error instanceof Error ? error.message : current.current.t("taskNotice.reconnecting"));
        if (!controller.signal.aborted && knownRuns.size && !current.current.hideNotices)
          current.current.toast.add({
            id: "task-connection",
            duration: 0,
            description: current.current.t("taskNotice.reconnecting"),
          });
      } finally {
        inFlight = false;
        if (!controller.signal.aborted) timer = setTimeout(poll, 3000);
      }
    };
    refresh.current = () => { void poll(true); };
    publish(true);
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
      refresh.current = null;
      current.current.toast.dismiss();
    };
  }, [ownerId]);
  return null;
}

export function DevelopmentTaskNotice(props: Props) {
  const { t } = useTranslation("sandbox");
  return (
    <ToastProvider position="bottom-right" label={t("taskNotice.label")}>
      <TaskMonitor key={props.ownerId} {...props} />
    </ToastProvider>
  );
}
