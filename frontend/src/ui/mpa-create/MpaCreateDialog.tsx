import { useEffect, useRef, useState } from "react";
import { Alert } from "@openai/apps-sdk-ui/components/Alert";
import { Dialog } from "@base-ui/react/dialog";
import { useTranslation } from "react-i18next";
import { ModalLayout } from "../../components/layouts/ModalLayout";
import { Button } from "../../components/primitives/Button";
import { Textarea } from "../../components/primitives/Textarea";
import {
  getMpaCreationConfig,
  checkMpaCreationName,
  startMpaCreation,
  listMpaCreations,
  getMpaCreation,
  cancelMpaCreation,
  type MpaCreationInput,
  type MpaCreationTask,
  type MpaCreationConfig,
  MpaCreationRequestError,
} from "../../adk/mpaCreation";
import "../../components/composites/ModalButton/ModalButton.css";
import "./MpaCreateDialog.css";
import { MpaCreationFailure } from "./MpaCreationFailure";
import "../ProjectPreview.css";
import { runtimeNameProblem } from "../../create/runtimeName";
import type { CloudProvider } from "../../adk/cloudProvider";
import { validOpenViking, validPgTarget } from "../../adk/mpaCreationResources";
import { ResourcePicker, useDeploymentResourceList } from "../DeploymentResources";

const PG_CONSOLE_URL =
  "https://console.volcengine.com/aidap/region:aidap+cn-beijing/";
const OPENVIKING_CONSOLE_URL =
  "https://console.volcengine.com/vikingdb/openviking/region:openviking+cn-beijing/ov-6689fabdf032294/context-management?accountId=default&userId=default&projectName=default";

function defaultMaximumInstances(cloudProvider: CloudProvider): number {
  return cloudProvider === "byteplus" ? 10 : 20;
}

function freshInput(region: string, cloudProvider: CloudProvider): MpaCreationInput {
  return {
    region,
    requestId: crypto.randomUUID(),
    name: "",
    description: "",
    maxInstance: defaultMaximumInstances(cloudProvider),
  };
}

function withoutTosCredentials(input: MpaCreationInput): MpaCreationInput {
  const clean = { ...input };
  Reflect.deleteProperty(clean, "tosAccessKey");
  Reflect.deleteProperty(clean, "tosSecretKey");
  return clean;
}

function cleanInput(input: MpaCreationInput): MpaCreationInput {
  const clean = withoutTosCredentials(input);
  for (const key of Object.keys(clean) as Array<keyof MpaCreationInput>) {
    if (clean[key] === undefined || clean[key] === "") delete clean[key];
  }
  return clean;
}

function initial(region: string, cloudProvider: CloudProvider): {
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
      typeof saved.input.requestId === "string"
    ) {
      if (saved.submitted || saved.taskId) {
        return { ...saved, input: withoutTosCredentials(saved.input) };
      }
      const draft: MpaCreationInput = {
        ...saved.input,
        name: typeof saved.input.name === "string" ? saved.input.name : "",
        maxInstance: saved.input.maxInstance ?? defaultMaximumInstances(cloudProvider),
      };
      delete draft.agentId;
      delete draft.runtimeImage;
      delete draft.workerImage;
      return { ...saved, input: withoutTosCredentials(draft) };
    }
  } catch {
    /* A fresh form is safe when browser storage is unavailable. */
  }
  return { input: freshInput(region, cloudProvider) };
}

export function MpaCreateDialog({
  region,
  cloudProvider = "volcengine",
  onClose,
  onCreated,
}: {
  region: string;
  cloudProvider?: CloudProvider;
  onClose: () => void;
  onCreated: () => void;
}) {
  const { t } = useTranslation("ui");
  const key = (name: string) => `myAgents.mpaCreate.${name}`;
  const defaultMaximum = defaultMaximumInstances(cloudProvider);
  const [saved] = useState(() => initial(region, cloudProvider));
  const hasBrowserDraft = Boolean(
    saved.step ||
      saved.input.name ||
      saved.input.description ||
      saved.input.agentId ||
      saved.input.pgHost ||
      saved.input.pgPort ||
      saved.input.openvikingUrl ||
      saved.input.openvikingResourceId ||
      saved.input.tosBucket,
  );
  const [input, setInput] = useState(saved.input);
  const [maximumInput, setMaximumInput] = useState(
    String(saved.input.maxInstance ?? defaultMaximum),
  );
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
  const submittedIntent = useRef(submitted);
  submittedIntent.current = submitted;
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
  const serverRecoveryAttempted = useRef(false);
  const created = useRef(onCreated);
  created.current = onCreated;
  const running = task?.state === "running" || task?.state === "cancelling";
  const legacyRequest =
    submitted && input.name === undefined && Boolean(input.agentId);
  const nameError = legacyRequest
    ? null
    : runtimeNameProblem((input.name ?? "").trim(), (problem) =>
        t(`validation.runtimeName.${problem}`, { ns: "create" }),
      );
  const nameValid = !nameError;
  const legacyScaling = submitted && input.maxInstance === undefined;
  const maximumValid =
    legacyScaling ||
    (maximumInput.trim() !== "" &&
      Number.isSafeInteger(Number(maximumInput)) &&
      Number(maximumInput) >= 1);
  const autoPg = config?.postgresMode === "auto";
  const aidbPg =
    (submitted ? input.businessDatabaseName : config?.businessDatabaseName) ===
    "aidb";
  const perAgentPg =
    (submitted
      ? input.businessWorkspaceMode
      : config?.businessWorkspaceMode) === "per-agent";
  const pgValid = autoPg
    ? !input.pgHost && !input.pgPort
    : validPgTarget(input.pgHost, input.pgPort);
  const autoOpenviking = input.openvikingMode === "auto";
  const openvikingValid =
    autoOpenviking ||
    validOpenViking(
      input.openvikingUrl,
      input.openvikingResourceId,
      openvikingApiKey,
    );
  const tosBucket = input.tosBucket?.trim() ?? "";
  const tosValid = !tosBucket || (tosBucket.startsWith("agentkit-platform-") && /^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$/.test(tosBucket));
  const tosLocked =
    busy || (submitted && (!task || running || task.state === "succeeded"));
  const tosList = useDeploymentResourceList(
    step === 2 && !tosLocked ? { kind: "tos-bucket", region, namePrefix: "agentkit-platform-" } : null,
  );
  useEffect(() => {
    if (submitted || taskId) return;
    try {
      sessionStorage.setItem(
        `mpa-create:${region}`,
        JSON.stringify({ input: withoutTosCredentials(input), step }),
      );
    } catch {
      /* Draft contains nonsecret settings only; storage is optional. */
    }
  }, [input, step, region, submitted, taskId]);
  function persist(id?: string) {
    try {
      sessionStorage.setItem(
        `mpa-create:${region}`,
        JSON.stringify({
          input: withoutTosCredentials(input),
          taskId: id,
          submitted: true,
          step: 2,
        }),
      );
    } catch {
      /* Server identity still makes retries idempotent. */
    }
  }
  function restoreTask(value: MpaCreationTask) {
    const restoredInput: MpaCreationInput = cleanInput({
      requestId: value.requestId,
      agentId: value.agentId,
      name: value.name,
      description: value.description ?? "",
      maxInstance: value.maxInstance ?? defaultMaximum,
      region: value.region,
      runtimeImage: value.runtimeImage,
      workerImage: value.workerImage,
      pgHost: value.pgHost,
      pgPort: value.pgPort,
      openvikingUrl: value.openvikingUrl,
      openvikingResourceId: value.openvikingResourceId,
      openvikingMode: value.openvikingMode,
      businessWorkspaceMode: value.businessWorkspaceMode,
      businessDatabaseName: value.businessDatabaseName,
      tosBucket: value.tosBucket,
    });
    setInput(restoredInput);
    setMaximumInput(String(restoredInput.maxInstance ?? defaultMaximum));
    setStep(2);
    setSubmitted(true);
    setTaskId(value.taskId);
    setTask(value);
    try {
      sessionStorage.setItem(
        `mpa-create:${region}`,
        JSON.stringify({
          input: restoredInput,
          taskId: value.taskId,
          submitted: true,
          step: 2,
        }),
      );
    } catch {
      /* Server task storage remains the source of truth. */
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
    if (
      serverRecoveryAttempted.current ||
      taskId ||
      saved.taskId ||
      (hasBrowserDraft && !submitted && !saved.submitted)
    )
      return;
    serverRecoveryAttempted.current = true;
    const controller = new AbortController();
    void listMpaCreations(region, controller.signal)
      .then((value) => {
        if (controller.signal.aborted || !alive.current) return;
        const restored =
          value.tasks.find((item) => item.requestId === input.requestId) ??
          value.tasks.find((item) => item.state !== "succeeded");
        if (restored) restoreTask(restored);
      })
      .catch(() => {
        /* Local task recovery is best-effort; config loading still drives errors. */
      });
    return () => controller.abort();
  }, [
    hasBrowserDraft,
    input.requestId,
    region,
    saved.submitted,
    saved.taskId,
    submitted,
    taskId,
  ]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    void getMpaCreationConfig(region, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) {
          setConfig(value);
          if (
            value.configured &&
            !submittedIntent.current &&
            !saved.submitted &&
            !saved.taskId &&
            !lock.current
          ) {
            setInput((previous) => ({
              ...previous,
              ...(value.businessDatabaseName === "aidb"
                ? { businessDatabaseName: "aidb" as const }
                : {}),
              ...(value.businessWorkspaceMode === "per-agent"
                ? { businessWorkspaceMode: "per-agent" as const }
                : {}),
              ...(value.openvikingMode === "auto"
                ? {
                    openvikingMode: "auto" as const,
                    openvikingUrl: undefined,
                    openvikingResourceId: undefined,
                  }
                : {}),
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
  }, [region, revision, cloudProvider, t]);
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
  function creationError(reason: unknown): string {
    if (
      reason instanceof MpaCreationRequestError &&
      (reason.code === "runtimeNameTaken" ||
        reason.code === "runtimeNameCheckFailed")
    )
      return t(key(reason.code));
    return reason instanceof Error ? reason.message : t(key("creationFailed"));
  }
  function taskErrorKey(value: MpaCreationTask): string {
    if (value.latestDiagnostic?.category === "configuration_changed")
      return "configurationChanged";
    return value.error || "creationFailed";
  }
  async function nextStep() {
    if (lock.current || !nameValid || !maximumValid) return;
    if (step !== 0 || submitted || input.businessDatabaseName !== "aidb") {
      setStep((previous) => previous + 1);
      return;
    }
    if (loading || !config?.configured) return;
    lock.current = true;
    setBusy(true);
    setError("");
    const controller = new AbortController();
    action.current = controller;
    try {
      const result = await checkMpaCreationName(
        {
          requestId: input.requestId,
          agentId: input.agentId,
          name: input.name?.trim(),
          region,
        },
        controller.signal,
      );
      if (!alive.current || controller.signal.aborted) return;
      if (!result.available) {
        setError(t(key("runtimeNameTaken")));
        return;
      }
      setStep(1);
    } catch (reason) {
      if (alive.current && !controller.signal.aborted)
        setError(creationError(reason));
    } finally {
      lock.current = false;
      if (alive.current) setBusy(false);
    }
  }
  async function submit() {
    if (
      lock.current ||
      !config?.configured ||
      !nameValid ||
      !maximumValid ||
      !pgValid ||
      !openvikingValid ||
      !tosValid ||
      step !== 2 ||
      running ||
      task?.state === "succeeded"
    )
      return;
    lock.current = true;
    setBusy(true);
    const wasSubmitted = submitted;
    setSubmitted(true);
    setError("");
    persist(taskId);
    const controller = new AbortController();
    action.current = controller;
    try {
      const value = await startMpaCreation(
        {
          ...input,
          ...(legacyScaling ? {} : { maxInstance: Number(maximumInput) }),
          ...(input.name === undefined ? {} : { name: input.name.trim() }),
          openvikingApiKey,
        },
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
          (reason.status === 400 ||
            reason.status === 422 ||
            (!wasSubmitted &&
              (reason.code === "runtimeNameTaken" ||
                reason.code === "runtimeNameCheckFailed")))
        ) {
          setSubmitted(false);
        }
        setError(creationError(reason));
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
    const nextInput: MpaCreationInput = {
      ...freshInput(region, cloudProvider),
      ...(config?.businessDatabaseName === "aidb"
        ? { businessDatabaseName: "aidb" as const }
        : {}),
      ...(config?.businessWorkspaceMode === "per-agent"
        ? { businessWorkspaceMode: "per-agent" as const }
        : {}),
      ...(config?.openvikingMode === "auto"
        ? { openvikingMode: "auto" as const }
        : {}),
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
    setMaximumInput(String(defaultMaximum));
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
                        <button
                          type="button"
                          disabled={
                            busy ||
                            (index > step &&
                              !submitted &&
                              (!nameValid ||
                                !maximumValid ||
                                (index === 2 && !pgValid)))
                          }
                          onClick={() => setStep(index)}
                        >
                          <span>{index + 1}</span>
                          {t(
                            key(
                              `steps.${name === "postgres" && autoPg ? "autoPostgres" : name}`,
                            ),
                          )}
                        </button>
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
                      {t(key("name"))}
                      <input
                        name="name"
                        placeholder={t(key("namePlaceholder"))}
                        value={input.name ?? input.agentId ?? ""}
                        maxLength={64}
                        disabled={busy || submitted}
                        required
                        autoComplete="off"
                        aria-invalid={Boolean(nameError)}
                        aria-describedby="mpa-name-help"
                        onChange={(event) => {
                          setInput({ ...input, name: event.target.value });
                          setError("");
                        }}
                      />
                      <p
                        id="mpa-name-help"
                        role={nameError ? "alert" : undefined}
                      >
                        {nameError || t(key("nameHelp"))}
                      </p>
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

                    {!legacyScaling && (
                      <label>
                        {t(key("maxInstance"))}
                        <input
                          name="maxInstance"
                          type="number"
                          min={1}
                          max={Number.MAX_SAFE_INTEGER}
                          step={1}
                          value={maximumInput}
                          disabled={busy || submitted}
                          required
                          aria-invalid={!maximumValid}
                          aria-describedby="mpa-maximum-help"
                          onChange={(event) => {
                            const value = event.target.value;
                            setMaximumInput(value);
                            setInput({ ...input, maxInstance: Number(value) });
                          }}
                        />
                        <p
                          id="mpa-maximum-help"
                          role={maximumValid ? undefined : "alert"}
                        >
                          {t(
                            key(
                              maximumValid
                                ? "maxInstanceHelp"
                                : "maxInstanceInvalid",
                            ),
                            { maximum: defaultMaximum },
                          )}
                        </p>
                      </label>
                    )}

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
                            ? aidbPg
                              ? "pgAidbDescription"
                              : perAgentPg
                                ? "pgPerAgentDescription"
                                : "pgAutoDescription"
                            : config?.postgresLayout === "split-workspaces"
                              ? "pgSplitDescription"
                              : "pgDescription",
                        ),
                      )}
                    </p>
                    <a
                      href={
                        cloudProvider === "byteplus"
                          ? "https://console.byteplus.com/aidap/"
                          : PG_CONSOLE_URL
                      }
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {t(
                        key(
                          cloudProvider === "byteplus"
                            ? "pgConsoleByteplus"
                            : "pgConsole",
                        ),
                      )}
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
                    <p>
                      {t(
                        key(
                          autoOpenviking
                            ? cloudProvider === "byteplus"
                              ? "openvikingAutoByteplusDescription"
                              : "openvikingAutoDescription"
                            : "openvikingDescription",
                        ),
                      )}
                    </p>
                    <a
                      href={
                        cloudProvider === "byteplus"
                          ? "https://console.byteplus.com/vikingdb/"
                          : autoOpenviking
                            ? "https://console.volcengine.com/vikingdb/openviking/region:openviking+cn-beijing/"
                            : OPENVIKING_CONSOLE_URL
                      }
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {t(
                        key(
                          cloudProvider === "byteplus"
                            ? "openvikingConsoleByteplus"
                            : "openvikingConsole",
                        ),
                      )}
                    </a>
                    {autoOpenviking ? (
                      <p>
                        {t(
                          key(
                            cloudProvider === "byteplus"
                              ? "openvikingAutoByteplusRequirements"
                              : "openvikingAutoBilling",
                          ),
                        )}
                      </p>
                    ) : (
                      <>
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
                    <fieldset className="mpa-create-tos">
                      <legend>{t(key("tosTitle"))}</legend>
                      <p>{t(key("tosDescription"))}</p>
                      <div>
                        <span>{t(key("tosBucket"))}</span>
                        <ResourcePicker
                          ariaLabel={t(key("tosBucket"))}
                          value={tosBucket}
                          valueLabel={tosBucket}
                          valueField="name"
                          state={tosList}
                          disabled={tosLocked}
                          onChange={(resource) => setInput((previous) => ({
                            ...previous, tosBucket: resource.name,
                          }))}
                        />
                      </div>
                      {tosBucket && (
                        <Button variant="outline" disabled={tosLocked}
                          onClick={() => setInput((previous) => ({ ...previous, tosBucket: "" }))}>
                          {t(key("tosDisable"))}
                        </Button>
                      )}
                      {!tosValid && <p role="alert">{t(key("tosInvalid"))}</p>}
                      <p>{t(key("tosCredentials"))}</p>
                    </fieldset>
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
                    {task.state === "failed" ? (
                      <MpaCreationFailure
                        key={`${task.taskId}:${JSON.stringify(task.latestDiagnostic)}`}
                        task={task}
                      />
                    ) : task.state === "cancelled" ? (
                      task.error === "runtimeNameTaken" ? (
                        <Alert
                          color="danger"
                          variant="soft"
                          description={t(key(task.error))}
                        />
                      ) : (
                        <p>{t(key(taskErrorKey(task)))}</p>
                      )
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
                {error && (
                  <Alert color="danger" variant="soft" description={error} />
                )}
                {running && <p>{t(key("background"))}</p>}
                {submitted && <p>{t(key("newAgentDescription"))}</p>}
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
                    {submitted && (
                      <Button
                        variant="outline"
                        disabled={busy || loading}
                        onClick={startAnotherAgent}
                      >
                        {t(key("newAgent"))}
                      </Button>
                    )}
                    {step > 0 && (
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
                          (step === 0 && (!nameValid || !maximumValid)) ||
                          (step === 1 && !pgValid)
                        }
                        onClick={() => void nextStep()}
                        loading={busy}
                      >
                        {t(key("next"))}
                      </Button>
                    ) : task?.state !== "succeeded" ? (
                      <Button
                        loading={busy}
                        disabled={
                          loading ||
                          !config?.configured ||
                          !nameValid ||
                          !maximumValid ||
                          !pgValid ||
                          !openvikingValid ||
                          !tosValid
                        }
                        onClick={() => void submit()}
                      >
                        {t(key(task || submitted ? "retry" : "submit"))}
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
