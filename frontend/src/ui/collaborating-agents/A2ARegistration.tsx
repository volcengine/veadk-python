import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Button,
  FormLabel,
  InputWithTailIcon,
  Select,
  Textarea,
} from "../../components/primitives";
import {
  createA2aCenterAgent,
  getRuntimes,
  requestA2aRuntimeEndpoints,
  type CloudRuntime,
} from "../../adk/client";
import {
  createdAgent,
  parseRegistrationCard,
  type CenterRegistration,
  runtimeEndpoints,
  type RuntimeEndpoint,
} from "../../adk/a2aSpace";
import { CollaboratorApiError } from "../../adk/collaboratingAgents";
import { TextShimmer } from "../text-shimmer/TextShimmer";

type Form =
  | { source: "Runtime"; runtimeId: string; networkType: "public" | "private" }
  | { source: "Standard"; importType: "json"; json: string }
  | { source: "Standard"; importType: "url"; cardUrl: string };
type Props = {
  runtimeId: string;
  region: string;
  spaceId: string;
  spaceName?: string;
  projectName: string;
  onCreated: (id: string) => void;
  onCancel: () => void;
  onUncertain: () => void;
  onBusy: (busy: boolean) => void;
};
export function A2ARegistration({
  runtimeId,
  region,
  spaceId,
  spaceName,
  projectName,
  onCreated,
  onCancel,
  onUncertain,
  onBusy,
}: Props) {
  const { t } = useTranslation("collaboratingAgents");
  const id = useId();
  const [form, setForm] = useState<Form>({
    source: "Runtime",
    runtimeId: "",
    networkType: "public",
  });
  const [error, setError] = useState("");
  const [showCard, setShowCard] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [runtimes, setRuntimes] = useState<CloudRuntime[]>([]);
  const [nextToken, setNextToken] = useState("");
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState(false);
  const [endpointData, setEndpointData] = useState<{
    runtimeId: string;
    endpoints: RuntimeEndpoint[];
  } | null>(null);
  const [endpointLoading, setEndpointLoading] = useState(false);
  const [endpointError, setEndpointError] = useState(false);
  const [endpointRetry, setEndpointRetry] = useState(0);
  const pending = useRef<AbortController | null>(null);
  const listing = useRef<AbortController | null>(null);
  const composing = useRef(false);
  const errorElement = useRef<HTMLParagraphElement>(null);
  const sourceRuntimeId =
    form.source === "Runtime" &&
    runtimes.some((item) => item.runtimeId === form.runtimeId)
      ? form.runtimeId
      : "";
  const endpoints =
    endpointData?.runtimeId === sourceRuntimeId ? endpointData.endpoints : [];
  const selectedEndpoint =
    form.source === "Runtime"
      ? endpoints.find((item) => item.networkType === form.networkType)
      : undefined;
  const endpointReady =
    !!selectedEndpoint && !endpointLoading && !endpointError;
  useEffect(() => {
    document.getElementById(`${id}-source`)?.focus();
  }, [id]);
  useEffect(() => {
    setEndpointData(null);
    setEndpointError(false);
    if (!/^r-[A-Za-z0-9_-]{1,100}$/.test(sourceRuntimeId)) {
      setEndpointLoading(false);
      return;
    }
    const controller = new AbortController();
    setEndpointLoading(true);
    void requestA2aRuntimeEndpoints(
      runtimeId,
      region,
      sourceRuntimeId,
      controller.signal,
    )
      .then((response) => runtimeEndpoints(response, sourceRuntimeId))
      .then((items) => {
        if (controller.signal.aborted) return;
        setEndpointData({ runtimeId: sourceRuntimeId, endpoints: items });
        setForm((current) =>
          current.source === "Runtime" &&
          current.runtimeId === sourceRuntimeId &&
          items.length > 0 &&
          !items.some((item) => item.networkType === current.networkType)
            ? { ...current, networkType: items[0].networkType }
            : current,
        );
      })
      .catch(() => {
        if (!controller.signal.aborted) setEndpointError(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setEndpointLoading(false);
      });
    return () => controller.abort();
  }, [sourceRuntimeId, runtimeId, region, endpointRetry]);
  useEffect(() => {
    if (error) errorElement.current?.focus();
  }, [error]);
  async function loadRuntimes(token = "") {
    listing.current?.abort();
    const controller = new AbortController();
    listing.current = controller;
    setListLoading(true);
    setListError(false);
    try {
      const page = await getRuntimes({
        region,
        nextToken: token,
        signal: controller.signal,
      });
      if (!controller.signal.aborted) {
        setRuntimes((current) =>
          token
            ? [
                ...new Map(
                  [...current, ...page.runtimes].map((item) => [
                    item.runtimeId,
                    item,
                  ]),
                ).values(),
              ]
            : page.runtimes,
        );
        setNextToken(page.nextToken);
      }
    } catch {
      if (!controller.signal.aborted) setListError(true);
    } finally {
      if (!controller.signal.aborted) setListLoading(false);
    }
  }
  useEffect(() => {
    void loadRuntimes();
    return () => {
      listing.current?.abort();
      pending.current?.abort();
    };
  }, [region]);
  async function submit() {
    if (pending.current || uncertain || composing.current) return;
    if (form.source === "Runtime" && !endpointReady) {
      setError("registration.endpointRequired");
      return;
    }
    let payload: CenterRegistration;
    try {
      const base = { targetRuntimeId: runtimeId, spaceId, projectName };
      payload =
        form.source === "Runtime"
          ? { ...base, ...form }
          : form.importType === "url"
            ? { ...base, ...form }
            : {
                ...base,
                source: "Standard",
                importType: "json",
                agentCard: parseRegistrationCard(form.json),
              };
    } catch {
      setError("registration.invalidCard");
      return;
    }
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    onBusy(true);
    setError("");
    try {
      const identifier = await createA2aCenterAgent(
        region,
        payload,
        controller.signal,
      ).then(createdAgent);
      if (!controller.signal.aborted) onCreated(identifier);
    } catch (reason: unknown) {
      if (!controller.signal.aborted) {
        const unknown =
          !(reason instanceof CollaboratorApiError) || reason.status >= 500;
        if (unknown) {
          setUncertain(true);
          onUncertain();
        }
        setError(
          reason instanceof CollaboratorApiError &&
            reason.reason === "runtime_already_registered"
            ? "registration.runtimeExists"
            : unknown
              ? "registration.uncertain"
              : reason.status === 422 || reason.status === 413
                ? "registration.invalid"
                : reason.status === 401 || reason.status === 403
                  ? "center.forbidden"
                  : "registration.failed",
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
  function cancel() {
    if (pending.current) {
      pending.current.abort();
      onUncertain();
      onBusy(false);
    }
    onCancel();
  }
  return (
    <form
      className="collaborators-form"
      aria-label={t("registration.open")}
      onCompositionStart={() => {
        composing.current = true;
      }}
      onCompositionEnd={() => {
        composing.current = false;
      }}
      onKeyDown={(event) => {
        if (
          event.key === "Enter" &&
          (event.nativeEvent.isComposing ||
            event.nativeEvent.keyCode === 229 ||
            composing.current)
        )
          event.preventDefault();
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
      <p>
        {t("registration.destination")}:{" "}
        {spaceName || t("center.nameUnavailable")}
      </p>
      <FormLabel htmlFor={`${id}-source`}>{t("registration.source")}</FormLabel>
      <Select
        id={`${id}-source`}
        aria-label={t("registration.source")}
        value={form.source}
        disabled={busy || uncertain}
        options={[
          { value: "Runtime", label: t("registration.runtime") },
          { value: "Standard", label: t("registration.standard") },
        ]}
        onChange={(event) => {
          setError("");
          setShowCard(false);
          setForm(
            event.target.value === "Runtime"
              ? { source: "Runtime", runtimeId: "", networkType: "public" }
              : { source: "Standard", importType: "json", json: "" },
          );
        }}
      />
      {form.source === "Runtime" ? (
        <>
          <FormLabel htmlFor={`${id}-known`} required>
            {t("registration.knownRuntime")}
          </FormLabel>
          <Select
            id={`${id}-known`}
            aria-label={t("registration.knownRuntime")}
            required
            value={
              runtimes.some((item) => item.runtimeId === form.runtimeId)
                ? form.runtimeId
                : ""
            }
            disabled={busy || uncertain || runtimes.length === 0}
            options={[
              { value: "", label: t("registration.chooseRuntime") },
              ...runtimes.map((item) => ({
                value: item.runtimeId,
                label: `${item.name} | ${item.runtimeId}`,
              })),
            ]}
            onChange={(event) => {
              setError("");
              setForm({ ...form, runtimeId: event.target.value });
            }}
          />
          {listLoading && <TextShimmer as="span">{t("loading")}</TextShimmer>}
          {listError && (
            <p role="alert">
              {t("registration.runtimeListFailed")}{" "}
              <Button
                variant="ghost"
                size="compact"
                disabled={listLoading}
                onClick={() => void loadRuntimes()}
              >
                {t("refresh")}
              </Button>
            </p>
          )}
          {!listLoading && !listError && runtimes.length === 0 && (
            <div role="status">
              {t("registration.noRuntimes")}{" "}
              <Button
                variant="ghost"
                size="compact"
                disabled={busy || uncertain}
                onClick={() => void loadRuntimes()}
              >
                {t("refresh")}
              </Button>
            </div>
          )}
          {nextToken && (
            <Button
              variant="ghost"
              size="compact"
              disabled={listLoading}
              onClick={() => void loadRuntimes(nextToken)}
            >
              {t("center.next")}
            </Button>
          )}
          <FormLabel htmlFor={`${id}-network`}>
            {t("registration.network")}
          </FormLabel>
          <Select
            id={`${id}-network`}
            aria-label={t("registration.network")}
            value={form.networkType}
            disabled={busy || uncertain || !endpointReady}
            options={endpoints.map((item) => ({
              value: item.networkType,
              label: t(`registration.${item.networkType}`),
              description: item.url,
            }))}
            onChange={(event) =>
              setForm({
                ...form,
                networkType:
                  event.target.value === "private" ? "private" : "public",
              })
            }
          />
          {endpointLoading && (
            <TextShimmer as="span">
              {t("registration.endpointsLoading")}
            </TextShimmer>
          )}
          {endpointError && (
            <div role="alert">
              {t("registration.endpointsFailed")}{" "}
              <Button
                variant="ghost"
                size="compact"
                disabled={busy || uncertain}
                onClick={() => setEndpointRetry((value) => value + 1)}
              >
                {t("refresh")}
              </Button>
            </div>
          )}
          {!endpointLoading &&
            !endpointError &&
            endpointData?.runtimeId === sourceRuntimeId &&
            endpoints.length === 0 && <p>{t("registration.noEndpoints")}</p>}
          {selectedEndpoint && (
            <p className="collaborators-address">{selectedEndpoint.url}</p>
          )}
        </>
      ) : (
        <>
          <FormLabel htmlFor={`${id}-method`}>
            {t("registration.importType")}
          </FormLabel>
          <Select
            id={`${id}-method`}
            aria-label={t("registration.importType")}
            value={form.importType}
            disabled={busy || uncertain}
            options={[
              { value: "json", label: "JSON" },
              { value: "url", label: "URL" },
            ]}
            onChange={(event) => {
              setError("");
              setShowCard(false);
              setForm(
                event.target.value === "url"
                  ? { source: "Standard", importType: "url", cardUrl: "" }
                  : { source: "Standard", importType: "json", json: "" },
              );
            }}
          />
          {form.importType === "json" ? (
            <>
              <FormLabel htmlFor={`${id}-card`} required>
                {t("registration.cardJson")}
              </FormLabel>
              {showCard ? (
                <Textarea
                  id={`${id}-card`}
                  aria-label={t("registration.cardJson")}
                  aria-invalid={
                    error === "registration.invalidCard" || undefined
                  }
                  aria-describedby={error ? `${id}-error` : undefined}
                  value={form.json}
                  rows={7}
                  required
                  maxLength={120000}
                  spellCheck={false}
                  autoComplete="off"
                  disabled={busy || uncertain}
                  onChange={(event) =>
                    setForm({ ...form, json: event.target.value })
                  }
                />
              ) : (
                <InputWithTailIcon
                  className="collaborators-input"
                  tailIcon={null}
                  id={`${id}-card`}
                  aria-label={t("registration.cardJson")}
                  aria-invalid={
                    error === "registration.invalidCard" || undefined
                  }
                  aria-describedby={error ? `${id}-error` : undefined}
                  type="password"
                  value={form.json}
                  required
                  maxLength={120000}
                  autoComplete="new-password"
                  spellCheck={false}
                  disabled={busy || uncertain}
                  onChange={(event) =>
                    setForm({ ...form, json: event.target.value })
                  }
                />
              )}
              <Button
                variant="ghost"
                size="compact"
                aria-controls={`${id}-card`}
                aria-pressed={showCard}
                disabled={busy || uncertain}
                onClick={() => setShowCard((value) => !value)}
              >
                {t(showCard ? "hideSecret" : "showSecret")}
              </Button>
            </>
          ) : (
            <>
              <FormLabel htmlFor={`${id}-url`} required>
                {t("registration.cardUrl")}
              </FormLabel>
              <InputWithTailIcon
                className="collaborators-input"
                tailIcon={null}
                id={`${id}-url`}
                aria-label={t("registration.cardUrl")}
                type="url"
                value={form.cardUrl}
                required
                maxLength={4096}
                disabled={busy || uncertain}
                onChange={(event) =>
                  setForm({ ...form, cardUrl: event.target.value })
                }
              />
            </>
          )}
        </>
      )}
      {error && (
        <p role="alert" ref={errorElement} tabIndex={-1} id={`${id}-error`}>
          {t(error)}
        </p>
      )}
      {busy && (
        <TextShimmer as="span">{t("registration.creating")}</TextShimmer>
      )}
      <div className="collaborators-actions">
        <Button
          type="submit"
          disabled={
            busy || uncertain || (form.source === "Runtime" && !endpointReady)
          }
        >
          {t("registration.submit")}
        </Button>
        <Button variant="ghost" onClick={cancel}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}
