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
  MpaCreationRequestError,
} from "../../adk/mpaCreation";
import "../../components/composites/ModalButton/ModalButton.css";
import "./MpaCreateDialog.css";
import { validCreationImage } from "../../adk/mpaCreationImages";
import { validOpenViking, validPgTarget } from "../../adk/mpaCreationResources";

const PG_CONSOLE_URL =
  "https://console.volcengine.com/aidap/region:aidap+cn-beijing/";
const OPENVIKING_CONSOLE_URL =
  "https://console.volcengine.com/vikingdb/openviking/region:openviking+cn-beijing/ov-6689fabdf032294/context-management?accountId=default&userId=default&projectName=default";

function freshInput(region: string): MpaCreationInput {
  const id = crypto.randomUUID();
  return {
    region,
    requestId: id,
    agentId: `mi-${id.replace(/-/g, "").slice(0, 24)}`,
    description: "",
  };
}

function initial(region: string): {
  input: MpaCreationInput;
  taskId?: string;
  submitted?: boolean;
  step?: number;
} {
  try {
    const saved = JSON.parse(
      sessionStorage.getItem(`mpa-create:${region}`) || "null",
    );
    if (
      saved?.input?.region === region &&
      typeof saved.input.requestId === "string" &&
      typeof saved.input.agentId === "string"
    ) {
      const suffix = saved.input.requestId.replace(/-/g, "");
      if (
        !saved.submitted &&
        !saved.taskId &&
        /^[0-9a-f]{32}$/.test(suffix) &&
        saved.input.agentId === `mi-${suffix.slice(0, 12)}`
      ) {
        return {
          ...saved,
          input: { ...saved.input, agentId: `mi-${suffix.slice(0, 24)}` },
        };
      }
      return saved;
    }
  } catch {
    /* A fresh form is safe when browser storage is unavailable. */
  }
  return { input: freshInput(region) };
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
  const [openvikingApiKey, setOpenvikingApiKey] = useState("");
  const [step, setStep] = useState(
    saved.submitted || saved.taskId
      ? 2
      : Math.min(2, Math.max(0, saved.step ?? 0)),
  );
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
  const imagesValid =
    validCreationImage(input.runtimeImage) &&
    validCreationImage(input.workerImage);
  const autoPg = config?.postgresMode === "auto";
  const pgValid = autoPg
    ? !input.pgHost && !input.pgPort
    : validPgTarget(input.pgHost, input.pgPort);
  const openvikingValid = validOpenViking(
    input.openvikingUrl,
    input.openvikingResourceId,
    openvikingApiKey,
  );
  useEffect(() => {
    if (submitted || taskId) return;
    try {
      sessionStorage.setItem(
        `mpa-create:${region}`,
        JSON.stringify({ input, step }),
      );
    } catch {
      /* Draft contains nonsecret settings only; storage is optional. */
    }
  }, [input, step, region, submitted, taskId]);
  function persist(id?: string) {
    try {
      sessionStorage.setItem(
        `mpa-create:${region}`,
        JSON.stringify({ input, taskId: id, submitted: true, step: 2 }),
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
        if (!controller.signal.aborted) {
          setConfig(value);
          if (
            value.configured &&
            !saved.submitted &&
            !saved.taskId &&
            !lock.current
          ) {
            setInput((previous) => ({
              ...previous,
              runtimeImage: previous.runtimeImage ?? value.runtimeImage ?? "",
              workerImage: previous.workerImage ?? value.workerImage ?? "",
              pgHost:
                value.postgresMode === "auto"
                  ? ""
                  : (previous.pgHost ?? value.pgHost ?? ""),
              pgPort:
                value.postgresMode === "auto"
                  ? ""
                  : (previous.pgPort ?? value.pgPort ?? ""),
            }));
          }
        }
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
      !imagesValid ||
      !pgValid ||
      !openvikingValid ||
      step !== 2 ||
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
      const value = await startMpaCreation(
        { ...input, openvikingApiKey },
        controller.signal,
      );
      if (!alive.current || controller.signal.aborted) return;
      persist(value.taskId);
      setTaskId(value.taskId);
      setTask(value);
      setRevision((v) => v + 1);
    } catch (reason) {
      if (alive.current && !controller.signal.aborted) {
        if (
          reason instanceof MpaCreationRequestError &&
          (reason.status === 400 || reason.status === 422)
        ) {
          setSubmitted(false);
        }
        setError(
          reason instanceof Error ? reason.message : t(key("creationFailed")),
        );
      }
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
  function startAnotherAgent() {
    if (
      busy ||
      loading ||
      (task?.state !== "failed" && task?.state !== "cancelled")
    )
      return;
    const nextInput: MpaCreationInput = {
      ...freshInput(region),
      runtimeImage: config?.runtimeImage ?? "",
      workerImage: config?.workerImage ?? "",
      pgHost: autoPg ? "" : (config?.pgHost ?? ""),
      pgPort: autoPg ? "" : (config?.pgPort ?? ""),
    };
    try {
      sessionStorage.setItem(
        `mpa-create:${region}`,
        JSON.stringify({ input: nextInput, step: 0 }),
      );
    } catch {
      /* The new in-memory draft remains usable without browser storage. */
    }
    setInput(nextInput);
    setOpenvikingApiKey("");
    setStep(0);
    setTaskId(undefined);
    setSubmitted(false);
    setTask(null);
    setError("");
    setConfirmCancel(false);
    finished.current = false;
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
                <ol
                  className="mpa-create-steps"
                  aria-label={t(key("stepsLabel"))}
                >
                  {(["basics", "postgres", "openviking"] as const).map(
                    (name, index) => (
                      <li
                        key={name}
                        aria-current={step === index ? "step" : undefined}
                      >
                        <span>{index + 1}</span>
                        {t(
                          key(
                            `steps.${name === "postgres" && autoPg ? "autoPostgres" : name}`,
                          ),
                        )}
                      </li>
                    ),
                  )}
                </ol>
                {step === 0 && (
                  <>
                    <p>
                      {t(key("region"))}：{region}
                    </p>
                    <label>
                      {t(key("agentId"))}
                      <input
                        name="agentId"
                        value={input.agentId}
                        pattern="[a-z0-9][a-z0-9_-]{0,63}"
                        maxLength={64}
                        readOnly
                        aria-readonly="true"
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
                          setInput({
                            ...input,
                            description: event.target.value,
                          })
                        }
                      />
                    </label>
                    {(["runtimeImage", "workerImage"] as const).map((field) => (
                      <label key={field}>
                        {t(key(field))}
                        <input
                          name={field}
                          value={
                            submitted
                              ? (task?.images?.[field] ?? input[field] ?? "")
                              : (input[field] ?? "")
                          }
                          maxLength={1024}
                          placeholder={t(key("imageDefault"))}
                          disabled={
                            loading || busy || submitted || !config?.configured
                          }
                          autoComplete="off"
                          spellCheck={false}
                          aria-invalid={!validCreationImage(input[field])}
                          aria-describedby={`mpa-${field}-help`}
                          onChange={(event) =>
                            setInput((previous) => ({
                              ...previous,
                              [field]: event.target.value,
                            }))
                          }
                        />
                        <p
                          id={`mpa-${field}-help`}
                          role={
                            !validCreationImage(input[field])
                              ? "alert"
                              : undefined
                          }
                        >
                          {t(
                            key(
                              validCreationImage(input[field])
                                ? "imageDefault"
                                : "imageInvalid",
                            ),
                          )}
                        </p>
                      </label>
                    ))}
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
                  </>
                )}
                {step === 1 && (
                  <>
                    <p>
                      {t(
                        key(
                          autoPg
                            ? "pgAutoDescription"
                            : config?.postgresLayout === "split-workspaces"
                              ? "pgSplitDescription"
                              : "pgDescription",
                        ),
                      )}
                    </p>
                    <a
                      href={PG_CONSOLE_URL}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {t(key("pgConsole"))}
                    </a>
                    {!autoPg && (
                      <>
                        <label>
                          {t(key("pgHost"))}
                          <input
                            name="pgHost"
                            value={input.pgHost ?? ""}
                            maxLength={255}
                            disabled={busy || submitted}
                            aria-invalid={!pgValid}
                            onChange={(event) =>
                              setInput((previous) => ({
                                ...previous,
                                pgHost: event.target.value,
                              }))
                            }
                          />
                        </label>
                        <label>
                          {t(key("pgPort"))}
                          <input
                            name="pgPort"
                            value={input.pgPort ?? ""}
                            inputMode="numeric"
                            maxLength={5}
                            disabled={busy || submitted}
                            aria-invalid={!pgValid}
                            onChange={(event) =>
                              setInput((previous) => ({
                                ...previous,
                                pgPort: event.target.value,
                              }))
                            }
                          />
                        </label>
                        {!pgValid && <p role="alert">{t(key("pgInvalid"))}</p>}
                        <p>{t(key("pgCredentials"))}</p>
                      </>
                    )}
                  </>
                )}
                {step === 2 && (
                  <>
                    <p>{t(key("openvikingDescription"))}</p>
                    <a
                      href={OPENVIKING_CONSOLE_URL}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {t(key("openvikingConsole"))}
                    </a>
                    <label>
                      {t(key("openvikingUrl"))}
                      <input
                        name="openvikingUrl"
                        value={input.openvikingUrl ?? ""}
                        maxLength={1024}
                        disabled={busy || submitted}
                        autoComplete="off"
                        spellCheck={false}
                        aria-invalid={!openvikingValid}
                        onChange={(event) =>
                          setInput((previous) => ({
                            ...previous,
                            openvikingUrl: event.target.value,
                          }))
                        }
                      />
                    </label>
                    <label>
                      {t(key("openvikingResourceId"))}
                      <input
                        name="openvikingResourceId"
                        value={input.openvikingResourceId ?? ""}
                        maxLength={128}
                        disabled={busy || submitted}
                        autoComplete="off"
                        spellCheck={false}
                        aria-invalid={!openvikingValid}
                        onChange={(event) =>
                          setInput((previous) => ({
                            ...previous,
                            openvikingResourceId: event.target.value,
                          }))
                        }
                      />
                    </label>
                    <label>
                      {t(key("openvikingApiKey"))}
                      <input
                        type="password"
                        name="openvikingApiKey"
                        value={openvikingApiKey}
                        maxLength={512}
                        disabled={
                          busy || running || task?.state === "succeeded"
                        }
                        autoComplete="off"
                        spellCheck={false}
                        onChange={(event) =>
                          setOpenvikingApiKey(event.target.value)
                        }
                      />
                    </label>
                    {!openvikingValid && (
                      <p role="alert">{t(key("openvikingInvalid"))}</p>
                    )}
                    <p>{t(key("openvikingCredentials"))}</p>
                  </>
                )}
                {loading ? (
                  <p role="status">{t(key("checking"))}</p>
                ) : config?.configured ? (
                  <p>{t(key("configured"))}</p>
                ) : (
                  <div role="alert">
                    <p>{t(key("notConfigured"))}</p>
                    <p>
                      {config?.postgresMigrationRequired
                        ? t(key("pgMigrationRequired"))
                        : config?.error}
                    </p>
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
                    {task.state !== "succeeded" && (
                      <p>
                        {t(key(`stages.${task.stage}`), {
                          defaultValue: task.stage,
                        })}
                      </p>
                    )}
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
                {autoPg && !pgValid && (
                  <p role="alert">{t(key("pgModeChanged"))}</p>
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
                    {(task?.state === "failed" ||
                      task?.state === "cancelled") && (
                      <Button
                        variant="outline"
                        disabled={busy || loading}
                        onClick={startAnotherAgent}
                      >
                        {t(key("newAgent"))}
                      </Button>
                    )}
                    {!submitted && step > 0 && (
                      <Button
                        variant="outline"
                        disabled={busy}
                        onClick={() => setStep((previous) => previous - 1)}
                      >
                        {t(key("previousStep"))}
                      </Button>
                    )}
                    {running ? (
                      <Button
                        variant="outline"
                        disabled={busy || task?.state === "cancelling"}
                        onClick={() => setConfirmCancel(true)}
                      >
                        {t(key("cancel"))}
                      </Button>
                    ) : task?.state !== "succeeded" && step < 2 ? (
                      <Button
                        disabled={
                          busy ||
                          (step === 0 && !imagesValid) ||
                          (step === 1 && !pgValid)
                        }
                        onClick={() => setStep((previous) => previous + 1)}
                      >
                        {t(key("next"))}
                      </Button>
                    ) : task?.state !== "succeeded" ? (
                      <Button
                        loading={busy}
                        disabled={
                          loading ||
                          !config?.configured ||
                          !imagesValid ||
                          !pgValid ||
                          !openvikingValid ||
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
