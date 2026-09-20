import { useEffect, useRef, useState } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { useTranslation } from "react-i18next";
import { ModalLayout } from "../../components/layouts/ModalLayout";
import { Button } from "../../components/primitives/Button";
import { Textarea } from "../../components/primitives/Textarea";
import {
  getMpaCreationConfig,
  startMpaCreation,
  getMpaCreation,
  cancelMpaCreation,
  type MpaCreationInput,
  type MpaCreationTask,
  type MpaCreationConfig,
} from "../../adk/mpaCreation";
import "../../components/composites/ModalButton/ModalButton.css";
import "./MpaCreateDialog.css";

function initial(region: string): {
  input: MpaCreationInput;
  taskId?: string;
  submitted?: boolean;
} {
  try {
    const saved = JSON.parse(
      sessionStorage.getItem(`mpa-create:${region}`) || "null",
    );
    if (
      saved?.input?.region === region &&
      typeof saved.input.requestId === "string" &&
      typeof saved.input.agentId === "string"
    )
      return saved;
  } catch {
    /* A fresh form is safe when browser storage is unavailable. */
  }
  const id = crypto.randomUUID();
  return {
    input: {
      region,
      requestId: id,
      agentId: `mi-${id.replace(/-/g, "").slice(0, 24)}`,
      description: "",
    },
  };
}

export function MpaCreateDialog({
  region,
  onClose,
  onCreated,
}: {
  region: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const { t } = useTranslation("ui");
  const key = (name: string) => `myAgents.mpaCreate.${name}`;
  const [saved] = useState(() => initial(region));
  const [input, setInput] = useState(saved.input);
  const [taskId, setTaskId] = useState(saved.taskId);
  const [submitted, setSubmitted] = useState(
    Boolean(saved.submitted || saved.taskId),
  );
  const [task, setTask] = useState<MpaCreationTask | null>(null);
  const [config, setConfig] = useState<MpaCreationConfig | null>(null);
  const [loading, setLoading] = useState(true),
    [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0),
    [confirmCancel, setConfirmCancel] = useState(false);
  const lock = useRef(false),
    finished = useRef(false),
    alive = useRef(true);
  const action = useRef<AbortController | null>(null);
  const created = useRef(onCreated);
  created.current = onCreated;
  const running = task?.state === "running" || task?.state === "cancelling";
  function persist(id?: string) {
    try {
      sessionStorage.setItem(
        `mpa-create:${region}`,
        JSON.stringify({ input, taskId: id, submitted: true }),
      );
    } catch {
      /* Server identity still makes retries idempotent. */
    }
  }
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      action.current?.abort();
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    void getMpaCreationConfig(region, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setConfig(value);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(t(key("loadFailed")));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [region, revision, t]);
  useEffect(() => {
    if (!taskId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function poll() {
      try {
        const value = await getMpaCreation(taskId!, controller.signal);
        if (controller.signal.aborted) return;
        setTask(value);
        setError("");
        if (value.state === "succeeded" && !finished.current) {
          finished.current = true;
          try {
            sessionStorage.removeItem(`mpa-create:${region}`);
          } catch {
            /* Optional browser recovery cache. */
          }
          created.current();
        }
        if (value.state !== "running" && value.state !== "cancelling") return;
      } catch {
        if (controller.signal.aborted) return;
        setError(t(key("pollFailed")));
      }
      timer = setTimeout(poll, 2000);
    }
    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [taskId, region, revision, t]);
  async function submit() {
    if (
      lock.current ||
      !config?.configured ||
      running ||
      task?.state === "succeeded"
    )
      return;
    lock.current = true;
    setBusy(true);
    setSubmitted(true);
    setError("");
    persist(taskId);
    const controller = new AbortController();
    action.current = controller;
    try {
      const value = await startMpaCreation(input, controller.signal);
      if (!alive.current || controller.signal.aborted) return;
      persist(value.taskId);
      setTaskId(value.taskId);
      setTask(value);
      setRevision((v) => v + 1);
    } catch (reason) {
      if (alive.current && !controller.signal.aborted)
        setError(
          reason instanceof Error ? reason.message : t(key("creationFailed")),
        );
    } finally {
      lock.current = false;
      if (alive.current) setBusy(false);
    }
  }
  async function cancel() {
    if (!taskId || lock.current) return;
    setConfirmCancel(false);
    lock.current = true;
    setBusy(true);
    const controller = new AbortController();
    action.current = controller;
    try {
      const value = await cancelMpaCreation(taskId, controller.signal);
      if (alive.current && !controller.signal.aborted) setTask(value);
    } catch {
      if (alive.current && !controller.signal.aborted)
        setError(t(key("cancelFailed")));
    } finally {
      lock.current = false;
      if (alive.current) setBusy(false);
    }
  }
  return (
    <>
      <Dialog.Root
        open
        onOpenChange={(open) => {
          if (!open && !busy) {
            if (confirmCancel) setConfirmCancel(false);
            else onClose();
          }
        }}
      >
        <Dialog.Portal>
          <Dialog.Backdrop className="studio-modal-button__backdrop mpa-create-backdrop" />
          <Dialog.Popup
            className="mpa-create-popup"
            aria-label={t(key("title"))}
          >
            <ModalLayout
              className="mpa-create-dialog"
              title={t(key("title"))}
              topGlow={false}
              footer={null}
              onClose={() => {
                if (!busy) onClose();
              }}
              closeLabel={t(key("close"))}
            >
              <div className="mpa-create-body">
                <p>
                  {t(key("region"))}：{region}
                </p>
                <label>
                  {t(key("agentId"))}
                  <input
                    value={input.agentId}
                    pattern="[a-z0-9][a-z0-9_-]{0,63}"
                    maxLength={64}
                    disabled={busy || submitted}
                    onChange={(event) =>
                      setInput({ ...input, agentId: event.target.value })
                    }
                  />
                </label>
                <label>
                  {t(key("description"))}
                  <Textarea
                    className="mpa-create-description"
                    value={input.description}
                    maxLength={512}
                    disabled={busy || submitted}
                    onChange={(event) =>
                      setInput({ ...input, description: event.target.value })
                    }
                  />
                </label>
                <section
                  className="mpa-create-plan"
                  aria-label={t(key("plan"))}
                >
                  <strong>{t(key("plan"))}</strong>
                  <ul>
                    <li>{t(key("sharedResources"))}</li>
                    <li>{t(key("agentResources"))}</li>
                    <li>{t(key("readiness"))}</li>
                  </ul>
                </section>
                {loading ? (
                  <p role="status">{t(key("checking"))}</p>
                ) : config?.configured ? (
                  <p>{t(key("configured"))}</p>
                ) : (
                  <div role="alert">
                    <p>{t(key("notConfigured"))}</p>
                    <p>{config?.error}</p>
                    <Button
                      variant="outline"
                      onClick={() => setRevision((v) => v + 1)}
                    >
                      {t(key("reload"))}
                    </Button>
                  </div>
                )}
                {task && (
                  <section aria-live="polite">
                    <strong>{t(key(`states.${task.state}`))}</strong>
                    {task.state !== "succeeded" && <p>
                      {t(key(`stages.${task.stage}`), {
                        defaultValue: task.stage,
                      })}
                    </p>}
                    {task.state === "failed" || task.state === "cancelled" ? (
                      <p>{t(key(task.error || "creationFailed"))}</p>
                    ) : null}
                    {task.result?.runtime_id && (
                      <p>Runtime ID：{task.result.runtime_id}</p>
                    )}
                    {task.result?.skill_space_id && (
                      <p>
                        {t(key("skillSpace"))}：{task.result.skill_space_id}
                      </p>
                    )}
                  </section>
                )}
                {error && <p role="alert">{error}</p>}
                {running && <p>{t(key("background"))}</p>}
                {confirmCancel ? (
                  <section
                    role="alertdialog"
                    aria-label={t(key("cancel"))}
                    className="mpa-create-plan"
                  >
                    <p>{t(key("cancelDescription"))}</p>
                    <div className="mpa-create-actions">
                      <Button
                        autoFocus
                        variant="outline"
                        onClick={() => setConfirmCancel(false)}
                      >
                        {t(key("back"))}
                      </Button>
                      <Button onClick={() => void cancel()}>
                        {t(key("confirmCancel"))}
                      </Button>
                    </div>
                  </section>
                ) : (
                  <div className="mpa-create-actions">
                    <Button variant="outline" disabled={busy} onClick={onClose}>
                      {t(key("close"))}
                    </Button>
                    {running ? (
                      <Button
                        variant="outline"
                        disabled={busy || task?.state === "cancelling"}
                        onClick={() => setConfirmCancel(true)}
                      >
                        {t(key("cancel"))}
                      </Button>
                    ) : task?.state !== "succeeded" ? (
                      <Button
                        loading={busy}
                        disabled={
                          loading ||
                          !config?.configured ||
                          !/^[a-z0-9][a-z0-9_-]{0,63}$/.test(input.agentId)
                        }
                        onClick={() => void submit()}
                      >
                        {t(key(task ? "retry" : "submit"))}
                      </Button>
                    ) : null}
                  </div>
                )}
              </div>
            </ModalLayout>
          </Dialog.Popup>
        </Dialog.Portal>
      </Dialog.Root>
    </>
  );
}
