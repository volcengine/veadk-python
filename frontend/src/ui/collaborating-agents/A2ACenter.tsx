import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button, FormLabel, Select } from "../../components/primitives";
import { requestCollaborators } from "../../adk/client";
import { CollaboratorApiError } from "../../adk/collaboratingAgents";
import {
  registryPage,
  spaceBinding,
  type RegistryPage,
  type RegistryItem,
  type SpaceBinding,
} from "../../adk/a2aSpace";
import { TextShimmer } from "../text-shimmer/TextShimmer";

import { A2AAliasEditor } from "./A2AAliasEditor";
import { A2ARegistration } from "./A2ARegistration";
import { A2ASpaceCreation } from "./A2ASpaceCreation";
import { A2AMemberActions, A2ASpaceDeletion } from "./A2AResourceActions";

type Target = { runtimeId: string; region: string };
export function A2ACenter({ runtimeId, region }: Target) {
  const { t } = useTranslation("collaboratingAgents");
  const id = useId();
  const [binding, setBinding] = useState<SpaceBinding | null>(null);
  const [spaces, setSpaces] = useState<RegistryPage | null>(null);
  const [agents, setAgents] = useState<RegistryPage | null>(null);
  const [selected, setSelected] = useState("");
  const [loading, setBusy] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [registrationOpen, setRegistrationOpen] = useState(false);
  const [created, setCreated] = useState("");
  const registrationTrigger = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef(false);
  const [creationOpen, setCreationOpen] = useState(false);
  const [creatingSpace, setCreatingSpace] = useState(false);
  const [newSpace, setNewSpace] = useState<RegistryItem | null>(null);
  const [spaceCreated, setSpaceCreated] = useState(false);
  const [spaceUncertain, setSpaceUncertain] = useState(false);
  const creationTrigger = useRef<HTMLButtonElement>(null);
  const creationReturnFocus = useRef(false);
  const refreshTrigger = useRef<HTMLButtonElement>(null);
  const [resourceBusy, setResourceBusy] = useState(false);
  const [resourceNotice, setResourceNotice] = useState("");
  const resourceReturnFocus = useRef(false);
  const busy = loading || registering || creatingSpace || resourceBusy;
  useEffect(() => {
    if (!busy && resourceReturnFocus.current) {
      refreshTrigger.current?.focus();
      resourceReturnFocus.current = false;
    }
  }, [busy, resourceNotice]);
  useEffect(() => {
    if (creationOpen) creationReturnFocus.current = true;
    else if (!busy && creationReturnFocus.current) {
      (creationTrigger.current?.disabled
        ? refreshTrigger.current
        : creationTrigger.current
      )?.focus();
      creationReturnFocus.current = false;
    }
  }, [creationOpen, busy]);
  useEffect(() => {
    if (registrationOpen) returnFocus.current = true;
    else if (!busy && returnFocus.current) {
      (registrationTrigger.current?.disabled
        ? refreshTrigger.current
        : registrationTrigger.current
      )?.focus();
      returnFocus.current = false;
    }
  }, [registrationOpen, busy]);
  const [error, setError] = useState("");
  const [uncertain, setUncertain] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);
  const pending = useRef<AbortController | null>(null);

  async function perform(
    work: (signal: AbortSignal) => Promise<() => void>,
    mutation = false,
  ) {
    if (pending.current && !pending.current.signal.aborted) return;
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setError("");
    try {
      const apply = await work(controller.signal);
      if (!controller.signal.aborted) apply();
    } catch (reason: unknown) {
      if (!controller.signal.aborted) {
        if (mutation) setUncertain(true);
        setError(
          mutation
            ? "center.refreshRequired"
            : reason instanceof CollaboratorApiError &&
                [401, 403].includes(reason.status)
              ? "center.forbidden"
              : reason instanceof CollaboratorApiError && reason.status === 404
                ? "unsupported"
                : "center.failed",
        );
      }
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        if (!controller.signal.aborted) setBusy(false);
      }
    }
  }
  function call(suffix: string, signal: AbortSignal, init: RequestInit = {}) {
    return requestCollaborators(runtimeId, region, `/registry/${suffix}`, {
      ...init,
      signal,
    });
  }
  async function reload(
    preferred = newSpace?.Id === selected ? newSpace : null,
  ) {
    setRegistrationOpen(false);
    setCreationOpen(false);
    await perform(async (signal) => {
      const saved = await call("binding", signal).then(spaceBinding);
      if (signal.aborted) return () => {};
      setBinding(saved);
      setUncertain(false);
      setDisconnecting(false);
      setAgents(null);
      const page = await call("spaces?page=1", signal).then(registryPage);
      if (signal.aborted) return () => {};
      const chosen = preferred?.Id ?? saved.space_id ?? page.items[0]?.Id ?? "";
      setSpaces(page);
      setSelected(chosen);
      const list = chosen
        ? await call(
            `agents?space_id=${encodeURIComponent(chosen)}&page=1`,
            signal,
          ).then(registryPage)
        : null;
      return () => {
        setBinding(saved);
        setSpaceUncertain(false);
        setSpaces(page);
        setSelected(chosen);
        setAgents(list);
        setUncertain(false);
        setDisconnecting(false);
      };
    });
  }
  useEffect(() => {
    void reload();
    return () => pending.current?.abort();
  }, [runtimeId, region]);
  function choose(value: string) {
    setDisconnecting(false);
    setResourceNotice("");
    setRegistrationOpen(false);
    setCreationOpen(false);
    setCreated("");
    setSelected(value);
    setAgents(null);
    void perform(async (signal) => {
      const page = await call(
        `agents?space_id=${encodeURIComponent(value)}&page=1`,
        signal,
      ).then(registryPage);
      return () => setAgents(page);
    });
  }
  function save(spaceId: string | null) {
    if (
      !binding ||
      uncertain ||
      (spaceId === null && binding.space_id !== selected)
    )
      return;
    void perform(async (signal) => {
      const saved = await call("binding", signal, {
        method: "PUT",
        body: JSON.stringify({ space_id: spaceId, revision: binding.revision }),
      }).then(spaceBinding);
      return () => {
        setBinding(saved);
        setDisconnecting(false);
      };
    }, true);
  }
  function page(kind: "spaces" | "agents", value: number) {
    void perform(async (signal) => {
      const result = await call(
        `${kind}?page=${value}${kind === "agents" ? `&space_id=${encodeURIComponent(selected)}` : ""}`,
        signal,
      ).then(registryPage);
      return () => {
        if (kind === "spaces") setSpaces(result);
        else setAgents(result);
      };
    });
  }
  function pagination(kind: "spaces" | "agents", result: RegistryPage | null) {
    if (!result || result.total <= result.page_size) return null;
    return (
      <div
        className="collaborators-actions"
        aria-label={t(`center.${kind}Pages`)}
      >
        <Button
          variant="ghost"
          size="compact"
          disabled={busy || result.page <= 1}
          onClick={() => page(kind, result.page - 1)}
        >
          {t("center.previous")}
        </Button>
        <span>
          {result.page} / {Math.ceil(result.total / result.page_size)}
        </span>
        <Button
          variant="ghost"
          size="compact"
          disabled={busy || result.page * result.page_size >= result.total}
          onClick={() => page(kind, result.page + 1)}
        >
          {t("center.next")}
        </Button>
      </div>
    );
  }
  const options =
    spaces?.items.map((item) => ({
      value: item.Id,
      label: item.Name || t("center.nameUnavailable"),
    })) ?? [];
  if (newSpace && !options.some((item) => item.value === newSpace.Id))
    options.push({
      value: newSpace.Id,
      label: newSpace.Name || t("center.nameUnavailable"),
    });
  const selectedSpace =
    spaces?.items.find((item) => item.Id === selected) ??
    (newSpace?.Id === selected ? newSpace : null);
  const destination = selectedSpace?.Name || t("center.nameUnavailable");
  const boundSpaceName =
    binding?.space_name ||
    spaces?.items.find((item) => item.Id === binding?.space_id)?.Name ||
    (newSpace?.Id === binding?.space_id ? newSpace?.Name : null) ||
    t("center.nameUnavailable");
  if (selected && !options.some((item) => item.value === selected))
    options.unshift({ value: selected, label: t("center.nameUnavailable") });
  return (
    <div className="collaborators">
      <p className="collaborators-context">
        {runtimeId} | {region}
      </p>
      {busy && <TextShimmer as="span">{t("loading")}</TextShimmer>}
      {error && <p role="alert">{t(error)}</p>}
      {resourceNotice && <p role="status">{t(resourceNotice)}</p>}
      {uncertain && !registrationOpen && !creationOpen && (
        <p role="alert">
          {t(
            spaceUncertain
              ? "spaceCreation.uncertain"
              : "center.refreshRequired",
          )}
        </p>
      )}
      <section
        className="collaborators-section"
        aria-label={t("center.bindingTitle")}
      >
        <h4>{t("center.bindingTitle")}</h4>
        <p className="collaborators-help">{t("center.help")}</p>
        {binding && (
          <p role="status">
            {t("center.current")}:{" "}
            {binding.space_id ? boundSpaceName : t("center.notConnected")}
          </p>
        )}
        {spaces && !spaces.items.length && !error && !newSpace && (
          <p>{t("center.noSpaces")}</p>
        )}
        <div className="collaborators-selector-row">
          {spaces && options.length > 0 && (
            <div className="collaborators-space-field">
              <FormLabel htmlFor={`${id}-space`}>{t("center.space")}</FormLabel>
              <Select
                id={`${id}-space`}
                aria-label={t("center.space")}
                value={selected}
                options={options}
                disabled={busy}
                onChange={(event) => choose(event.target.value)}
              />
            </div>
          )}
          <Button
            variant="outline"
            ref={creationTrigger}
            disabled={
              busy ||
              uncertain ||
              creationOpen ||
              registrationOpen ||
              !!error ||
              !binding ||
              !spaces
            }
            onClick={() => {
              setRegistrationOpen(false);
              setSpaceCreated(false);
              setCreationOpen(true);
            }}
          >
            {t("spaceCreation.open")}
          </Button>
        </div>
        {selected && (
          <div className="collaborators-actions">
            <A2ASpaceDeletion
              key={`${runtimeId}:${region}:${selected}`}
              runtimeId={runtimeId}
              region={region}
              spaceId={selected}
              name={destination}
              disabled={
                busy || uncertain || creationOpen || registrationOpen || !!error
              }
              blocked={
                binding?.space_id === selected
                  ? "bound"
                  : !agents
                    ? "loading"
                    : agents.total || agents.items.length
                      ? "nonempty"
                      : undefined
              }
              onBusy={setResourceBusy}
              onUncertain={() => setUncertain(true)}
              onDone={() => {
                resourceReturnFocus.current = true;
                setResourceNotice("spaceDeletion.deleted");
                setNewSpace(null);
                setSpaceCreated(false);
                setSelected("");
                setAgents(null);
                void reload(null);
              }}
            />
          </div>
        )}
        {pagination("spaces", spaces)}
        {spaceCreated && newSpace && (
          <p role="status">
            {t("spaceCreation.created")}: {newSpace.Name}
          </p>
        )}
        {creationOpen && (
          <A2ASpaceCreation
            runtimeId={runtimeId}
            region={region}
            onBusy={setCreatingSpace}
            onUncertain={() => {
              setUncertain(true);
              setSpaceUncertain(true);
            }}
            onCancel={() => {
              setCreationOpen(false);
              setCreatingSpace(false);
            }}
            onCreated={(space) => {
              setDisconnecting(false);
              setNewSpace(space);
              setSelected(space.Id);
              setAgents(null);
              setSpaceCreated(true);
              setCreationOpen(false);
              setCreatingSpace(false);
              void reload(space);
            }}
          />
        )}
        <div className="collaborators-actions">
          {selected && (
            <Button
              disabled={
                busy ||
                uncertain ||
                creationOpen ||
                registrationOpen ||
                !binding ||
                binding.space_id === selected ||
                !agents ||
                !!error
              }
              onClick={() => save(selected)}
            >
              {t("center.connect")}
            </Button>
          )}
          {binding?.space_id && binding.space_id === selected && (
            <Button
              variant="outline"
              disabled={busy || uncertain || creationOpen || registrationOpen}
              onClick={() => setDisconnecting(true)}
            >
              {t("center.disconnect")}
            </Button>
          )}
        </div>
        {disconnecting && binding?.space_id === selected && (
          <div role="group" aria-label={t("center.disconnectConfirm")}>
            <p>{t("center.disconnectConfirm")}</p>
            <div className="collaborators-actions">
              <Button
                disabled={busy || uncertain || creationOpen || registrationOpen}
                onClick={() => save(null)}
              >
                {t("center.disconnect")}
              </Button>
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() => setDisconnecting(false)}
              >
                {t("cancel")}
              </Button>
            </div>
          </div>
        )}
      </section>
      <section
        className="collaborators-section collaborators-members"
        aria-label={t("center.membersTitle")}
      >
        <header className="collaborators-section-header">
          <h4>{t("center.membersTitle")}</h4>
          <div className="collaborators-actions">
            {selected && (
              <Button
                size="compact"
                disabled={
                  busy ||
                  uncertain ||
                  registrationOpen ||
                  creationOpen ||
                  !!error ||
                  !spaces
                }
                ref={registrationTrigger}
                onClick={() => {
                  setCreated("");
                  setRegistrationOpen(true);
                }}
              >
                {t("registration.open")}
              </Button>
            )}
            <Button
              variant="outline"
              size="compact"
              disabled={busy}
              ref={refreshTrigger}
              onClick={() => void reload()}
            >
              {t("refresh")}
            </Button>
          </div>
        </header>
        {selected && (
          <p className="collaborators-context">
            {t("center.viewing")}: {destination}
          </p>
        )}
        {created && (
          <p role="status">
            {t("registration.created")}: {created}
          </p>
        )}
        {registrationOpen && (
          <div className="collaborators-registration collaborators-reveal">
            <A2ARegistration
              key={`${runtimeId}:${region}:${selected}`}
              runtimeId={runtimeId}
              region={region}
              spaceId={selected}
              spaceName={destination}
              projectName={selectedSpace?.ProjectName ?? "default"}
              onBusy={setRegistering}
              onUncertain={() => setUncertain(true)}
              onCancel={() => {
                setRegistrationOpen(false);
                setRegistering(false);
              }}
              onCreated={(identifier) => {
                setCreated(identifier);
                setRegistrationOpen(false);
                setRegistering(false);
                void perform(async (signal) => {
                  const list = await call(
                    `agents?space_id=${encodeURIComponent(selected)}&page=1`,
                    signal,
                  ).then(registryPage);
                  return () => setAgents(list);
                });
              }}
            />
          </div>
        )}
        {agents && !agents.items.length && !error && (
          <p>{t("center.noAgents")}</p>
        )}
        {agents?.items.map((item) => (
          <section key={item.Id} className="collaborators-item">
            <div className="collaborators-section-header">
              <strong>{item.Name}</strong>
              <A2AMemberActions
                key={`${runtimeId}:${region}:${selected}:${item.Id}`}
                runtimeId={runtimeId}
                region={region}
                spaceId={selected}
                item={item}
                disabled={
                  busy ||
                  uncertain ||
                  registrationOpen ||
                  creationOpen ||
                  !!error
                }
                onBusy={setResourceBusy}
                onUncertain={() => setUncertain(true)}
                onDone={() => {
                  resourceReturnFocus.current = true;
                  setResourceNotice("member.unregistered");
                  void perform(async (signal) => {
                    const list = await call(
                      `agents?space_id=${encodeURIComponent(selected)}&page=1`,
                      signal,
                    ).then(registryPage);
                    return () => setAgents(list);
                  });
                }}
              />
            </div>
            <span className="collaborators-context">
              {item.Id} |{" "}
              {item.Status === "running"
                ? t("center.running")
                : t("center.unavailable")}
            </span>
            <A2AAliasEditor
              key={`alias:${runtimeId}:${region}:${selected}:${item.Id}`}
              runtimeId={runtimeId}
              region={region}
              spaceId={selected}
              agentId={item.Id}
              alias={item.Alias ?? null}
              revision={item.AliasRevision ?? 0}
              available={item.AliasAvailable === true}
              disabled={
                busy || uncertain || registrationOpen || creationOpen || !!error
              }
              onBusy={setResourceBusy}
              onRefresh={() => {
                void reload();
              }}
              onSaved={(record) =>
                setAgents((current) =>
                  current
                    ? {
                        ...current,
                        items: current.items.map((member) =>
                          member.Id === item.Id
                            ? {
                                ...member,
                                Alias: record.alias,
                                AliasRevision: record.revision,
                              }
                            : member,
                        ),
                      }
                    : current,
                )
              }
            />
            {item.Description && (
              <details>
                <summary>{t("description")}</summary>
                <p>{item.Description}</p>
              </details>
            )}
          </section>
        ))}
        {pagination("agents", agents)}
      </section>
    </div>
  );
}
