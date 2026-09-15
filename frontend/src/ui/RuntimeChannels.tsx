import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@openai/apps-sdk-ui/components/Button";
import { Select } from "../components/primitives/Select/Select";
import { Radio } from "../components/primitives/Radio/Radio";
import {
  channelRequest,
  ChannelApiError,
  type ChannelCapabilities,
  type ChannelDiagnostics,
  type ChannelPermission,
  type ChannelScope,
  type FeishuBinding,
} from "../adk/client";
import { TextShimmer } from "./text-shimmer/TextShimmer";
import {
  authorizeWecom,
  WecomAuthorizationError,
} from "../adk/wecomAuthorization";
import { SourceCloseIcon } from "./icons/SourceWorkspaceIcons";
import "./RuntimeChannels.css";

const providers = ["feishu", "wecom", "dingtalk"] as const;
type Provider = (typeof providers)[number];
type ConfigurationMethod = "quick" | "manual";

export function RuntimeChannels(props: { runtimeId: string; region: string }) {
  const { t } = useTranslation("ui");
  const [provider, setProvider] = useState<Provider>("feishu");
  const id = useId();
  const tabs = useRef<Array<HTMLButtonElement | null>>([]);
  return (
    <div className="message-channels">
      <div className="message-channels-header">
        <h2>{t("channels.workspaceTitle")}</h2>
        <p>{t("channels.workspaceDescription")}</p>
      </div>
      <div
        className="message-channels-tabs"
        role="tablist"
        aria-label={t("channels.workspaceTitle")}
      >
        {providers.map((value, index) => (
          <button
            key={value}
            ref={(node) => {
              tabs.current[index] = node;
            }}
            type="button"
            role="tab"
            id={`${id}-${value}`}
            aria-controls={`${id}-panel`}
            aria-selected={provider === value}
            tabIndex={provider === value ? 0 : -1}
            onClick={() => setProvider(value)}
            onKeyDown={(event) => {
              let next: number;
              if (event.key === "ArrowRight")
                next = (index + 1) % providers.length;
              else if (event.key === "ArrowLeft")
                next = (index + providers.length - 1) % providers.length;
              else if (event.key === "Home") next = 0;
              else if (event.key === "End") next = providers.length - 1;
              else return;
              event.preventDefault();
              setProvider(providers[next]);
              tabs.current[next]?.focus();
            }}
          >
            {t(`channels.provider_${value}`)}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id={`${id}-panel`}
        aria-labelledby={`${id}-${provider}`}
        tabIndex={0}
      >
        <ProviderChannel
          key={`${props.region}:${props.runtimeId}:${provider}`}
          {...props}
          provider={provider}
        />
      </div>
    </div>
  );
}

function ChannelStatus({
  label,
  value,
  complete,
  description,
}: {
  label: string;
  value: string;
  complete: boolean;
  description: string;
}) {
  return (
    <div className="runtime-channels-status-card">
      <dt>{label}</dt>
      <dd>
        <span
          className={`runtime-channels-status-value${complete ? " is-complete" : ""}`}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="9" />
            {complete ? <path d="m8 12 3 3 5-6" /> : <path d="M12 7v5l3 2" />}
          </svg>
          {value}
        </span>
        <p>{description}</p>
      </dd>
    </div>
  );
}

const terminal = new Set(["BOUND", "FAILED", "EXPIRED"]);
const scopes: ChannelScope[] = [
  "group_sender",
  "group",
  "group_topic_sender",
  "group_topic",
];
function ProviderChannel({
  runtimeId,
  region,
  provider,
}: {
  runtimeId: string;
  region: string;
  provider: Provider;
}) {
  const { t } = useTranslation("ui");
  const ep = useMemo(() => ({ runtimeId, region }), [runtimeId, region]);
  const methodId = useId();
  const [method, setMethod] = useState<ConfigurationMethod>("quick");
  const [capability, setCapability] = useState<ChannelCapabilities | null>(
    null,
  );
  const [diagnostics, setDiagnostics] = useState<ChannelDiagnostics | null>(
    null,
  );
  const [groups, setGroups] = useState<ChannelPermission[]>([]);
  const [pairingRequested, setPairingRequested] = useState(false);
  const [binding, setBinding] = useState<FeishuBinding | null>(null);
  const [botId, setBotId] = useState("");
  const [secret, setSecret] = useState("");
  const [authorizing, setAuthorizing] = useState(false);
  const [wecomPairingComplete, setWecomPairingComplete] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [chatId, setChatId] = useState("");
  const [scope, setScope] = useState<ChannelScope>("group_sender");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const alive = useRef(true);
  const operation = useRef<AbortController | null>(null);
  const polling = useRef<AbortController | null>(null);
  const authorizationWaiting = useRef(false);
  const storageKey = `mpa-${provider}-binding:${region}:${runtimeId}`;
  const fail = (value: unknown) => {
    if (!alive.current) return;
    if (value instanceof WecomAuthorizationError) {
      const key =
        (
          {
            WINDOW_BLOCKED: "wecomPopupBlocked",
            CANCELLED: "wecomAuthCancelled",
            AUTH_TIMEOUT: "wecomAuthTimeout",
            INVALID_RESULT: "wecomInvalidResult",
          } as Record<string, string>
        )[value.code] || "wecomAuthFailed";
      setError(t(`channels.${key}`));
      return;
    }
    const status = value instanceof ChannelApiError ? value.status : 0;
    if (status === 409) setUncertain(true);
    setError(
      t(
        `channels.${status === 409 ? "uncertain" : status === 404 ? "unsupported" : status === 401 || status === 403 ? "unauthorized" : status === 503 ? "configurationError" : "requestFailed"}`,
      ),
    );
  };
  async function refresh(signal: AbortSignal) {
    const [diag, permissions] = await Promise.all([
      channelRequest<ChannelDiagnostics>(ep, `/${provider}/diagnostics`, {
        signal,
      }),
      provider === "feishu"
        ? channelRequest<{ permissions: ChannelPermission[] }>(
            ep,
            "/chat-permissions?channel=feishu",
            { signal },
          )
        : Promise.resolve({ permissions: [] }),
    ]);
    if (!signal.aborted && alive.current) {
      setDiagnostics(diag);
      setGroups(permissions.permissions);
    }
  }
  useEffect(() => {
    alive.current = true;
    try {
      sessionStorage.removeItem(storageKey);
    } catch {
      /* Legacy resume hints are optional and are never read. */
    }
    return () => {
      alive.current = false;
      operation.current?.abort();
      polling.current?.abort();
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setCapability(null);
    setBinding(null);
    setPairingRequested(false);
    setWecomPairingComplete(false);
    polling.current?.abort();
    void (async () => {
      try {
        const caps = await channelRequest<ChannelCapabilities>(
          ep,
          "/capabilities",
          { signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        if (
          !caps.serverSideBinding ||
          !(caps.channels ?? ["feishu"]).includes(provider)
        )
          throw new ChannelApiError(404);
        setCapability(caps);
        await refresh(controller.signal);
      } catch (value) {
        if (!controller.signal.aborted) fail(value);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
    // Remounted by AgentWorkspace when the Runtime changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ep, reload]);
  useEffect(() => {
    if (method !== "quick" || !binding || terminal.has(binding.status) || busy)
      return;
    const controller = new AbortController();
    polling.current = controller;
    const timer = window.setTimeout(
      () => {
        void channelRequest<FeishuBinding>(
          ep,
          `/${provider}/bindings/${encodeURIComponent(binding.id)}`,
          { signal: controller.signal },
        )
          .then(async (value) => {
            if (controller.signal.aborted) return;
            setBinding(value);
            if (value.lastErrorCode === "REGISTRATION_UNCERTAIN")
              setUncertain(true);
            if (value.status === "BOUND") await refresh(controller.signal);
          })
          .catch((value) => {
            if (!controller.signal.aborted) fail(value);
          });
      },
      Math.max(1, binding.pollAfterSeconds) * 1000,
    );
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [binding, ep, busy, reload, method]);
  async function perform(action: (signal: AbortSignal) => Promise<void>) {
    if (operation.current) return;
    const controller = new AbortController();
    operation.current = controller;
    setBusy(true);
    setError("");
    polling.current?.abort();
    try {
      await action(controller.signal);
    } catch (value) {
      if (!controller.signal.aborted) fail(value);
    } finally {
      if (operation.current === controller) {
        operation.current = null;
        if (alive.current) setBusy(false);
      }
    }
  }
  function begin(retry = false) {
    void perform(async (signal) => {
      setPairingRequested(true);
      if (!retry) setBinding(null);
      const value = await channelRequest<FeishuBinding>(
        ep,
        retry && binding
          ? `/${provider}/bindings/${encodeURIComponent(binding.id)}/retry`
          : `/${provider}/bindings`,
        { method: "POST", body: "{}", signal },
      );
      if (!signal.aborted) {
        setBinding(value);
        if (value.lastErrorCode === "REGISTRATION_UNCERTAIN")
          setUncertain(true);
        if (value.status === "BOUND") await refresh(signal);
      }
    });
  }
  function beginWecom() {
    void perform(async (signal) => {
      setPairingRequested(true);
      setWecomPairingComplete(false);
      setAuthorizing(true);
      authorizationWaiting.current = true;
      try {
        const credentials = await authorizeWecom(signal);
        if (signal.aborted) return;
        authorizationWaiting.current = false;
        setAuthorizing(false);
        await channelRequest(ep, "/wecom/bindings", {
          method: "POST",
          body: JSON.stringify(credentials),
          signal,
        });
        if (!signal.aborted) {
          setWecomPairingComplete(true);
          setSecret("");
          setBotId("");
          await refresh(signal);
        }
      } finally {
        if (alive.current && !signal.aborted) {
          authorizationWaiting.current = false;
          setAuthorizing(false);
        }
      }
    });
  }
  const manualSupported =
    provider === "wecom" ||
    !!capability?.credentialBindingChannels?.includes(provider);
  const pendingBinding = !!binding && !terminal.has(binding.status);
  const credentialDisabled = busy || loading || uncertain || pendingBinding;
  const methodDisabled = loading || (busy && !authorizing);
  function changeMethod(next: ConfigurationMethod) {
    if (
      next === method ||
      loading ||
      (operation.current && !authorizationWaiting.current)
    )
      return;
    operation.current?.abort();
    operation.current = null;
    authorizationWaiting.current = false;
    polling.current?.abort();
    setBusy(false);
    setAuthorizing(false);
    setBinding(null);
    setPairingRequested(false);
    setWecomPairingComplete(false);
    setBotId("");
    setSecret("");
    setError("");
    setMethod(next);
  }
  const safeUrl = (value: string | undefined) => {
    try {
      const url = new URL(value || "");
      return url.protocol === "https:" ? url.href : undefined;
    } catch {
      return undefined;
    }
  };
  const wecomAuthorizationActions = provider === "wecom" && capability && (
    <>
      <Button
        color="primary"
        size="sm"
        disabled={busy || loading || uncertain || !capability.bindingReady}
        onClick={beginWecom}
      >
        {t(diagnostics?.configured ? "channels.newQr" : "channels.wecomScan")}
      </Button>
      {authorizing && (
        <>
          <span role="status">{t("channels.wecomAuthorizing")}</span>
          <Button
            color="secondary"
            variant="outline"
            size="sm"
            onClick={() => {
              operation.current?.abort();
              authorizationWaiting.current = false;
              setAuthorizing(false);
            }}
          >
            {t("channels.cancelAuthorization")}
          </Button>
        </>
      )}
    </>
  );
  return (
    <section
      className="runtime-channels"
      aria-label={t(`channels.provider_${provider}`)}
      aria-busy={loading || busy}
    >
      <div className="runtime-channels-heading">
        <h3>
          {t("channels.providerBindingTitle", {
            name: t(`channels.provider_${provider}`),
          })}
        </h3>
        <Button
          color="secondary"
          variant="outline"
          size="sm"
          disabled={busy || loading}
          onClick={() => setReload((value) => value + 1)}
        >
          {t("channels.refresh")}
        </Button>
      </div>
      {loading && (
        <p role="status">
          <TextShimmer>{t("channels.loading")}</TextShimmer>
        </p>
      )}
      {error && (
        <div className="aw-integration-error" role="alert">
          <span>{error}</span>
          <Button
            color="secondary"
            variant="outline"
            size="sm"
            disabled={busy || loading}
            onClick={() => setReload((value) => value + 1)}
          >
            {t("common.retry")}
          </Button>
        </div>
      )}
      {capability && (
        <>
          <div className="runtime-channels-binding-summary">
            <span
              className={`runtime-channels-badge${diagnostics?.configured ? " is-bound" : ""}`}
            >
              {t(
                diagnostics?.configured
                  ? "channels.connected"
                  : "channels.notBound",
              )}
            </span>
            <p>
              {diagnostics?.configured
                ? t("channels.bound", {
                    name: diagnostics.appName || diagnostics.appId,
                  })
                : t("channels.providerUnbound", {
                    name: t(`channels.provider_${provider}`),
                  })}
            </p>
          </div>
          {!capability.bindingReady && (
            <p role="alert">{t("channels.keyRequired")}</p>
          )}
          {diagnostics && (
            <dl className="runtime-channels-diagnostics">
              <ChannelStatus
                label={t("channels.gateway")}
                value={t(
                  diagnostics.gatewayConfigured
                    ? "channels.configured"
                    : "channels.missing",
                )}
                complete={diagnostics.gatewayConfigured}
                description={t("channels.gatewayDescription")}
              />
              <ChannelStatus
                label={t("channels.route")}
                value={t(
                  diagnostics.routeConfigured
                    ? "channels.configured"
                    : "channels.missing",
                )}
                complete={diagnostics.routeConfigured}
                description={t("channels.routeDescription")}
              />
              <ChannelStatus
                label={t("channels.delivery")}
                value={t(`channels.delivery_${diagnostics.deliveryHealth}`, {
                  defaultValue: t("channels.delivery_not_observed"),
                })}
                complete={diagnostics.deliveryHealth === "delivered"}
                description={t("channels.deliveryDescription")}
              />
            </dl>
          )}
          {!!diagnostics?.missingConfiguration.length && (
            <p role="alert">
              {t("channels.missingConfig", {
                fields: diagnostics.missingConfiguration.join(", "),
              })}
            </p>
          )}
          <fieldset className="runtime-channels-methods">
            <legend>{t("channels.configurationMethod")}</legend>
            <div>
              {(["quick", "manual"] as const).map((value) => (
                <Radio
                  key={value}
                  name={`${methodId}-method`}
                  value={value}
                  checked={method === value}
                  disabled={methodDisabled}
                  label={t(`channels.${value}Setup`)}
                  onChange={() => changeMethod(value)}
                />
              ))}
            </div>
          </fieldset>
          <p>
            {t(
              method === "quick"
                ? "channels.qrGuidance"
                : "channels.manualGuidance",
              {
                name: t(`channels.provider_${provider}`),
              },
            )}
          </p>
          {method === "manual" && diagnostics?.configured && (
            <p>{t("channels.manualReplacement")}</p>
          )}
          {method === "manual" && !manualSupported && (
            <p>
              {t("channels.manualUpgrade", {
                name: t(`channels.provider_${provider}`),
              })}
            </p>
          )}
          {method === "manual" && manualSupported && (
            <form
              className="runtime-channels-form"
              data-channel-binding
              onSubmit={(event) => {
                event.preventDefault();
                if (
                  !botId.trim() ||
                  !secret.trim() ||
                  credentialDisabled ||
                  !capability.bindingReady
                )
                  return;
                void perform(async (signal) => {
                  await channelRequest(
                    ep,
                    provider === "wecom"
                      ? "/wecom/bindings"
                      : `/${provider}/bindings/manual`,
                    {
                      method: "POST",
                      body: JSON.stringify(
                        provider === "wecom"
                          ? { botId: botId.trim(), secret: secret.trim() }
                          : provider === "feishu"
                            ? {
                                appId: botId.trim(),
                                appSecret: secret.trim(),
                              }
                            : {
                                clientId: botId.trim(),
                                clientSecret: secret.trim(),
                              },
                      ),
                      signal,
                    },
                  );
                  if (!signal.aborted) {
                    setSecret("");
                    setBotId("");
                    await refresh(signal);
                  }
                });
              }}
            >
              <label>
                {t(
                  provider === "wecom"
                    ? "channels.wecomBotId"
                    : provider === "feishu"
                      ? "channels.feishuAppId"
                      : "channels.dingtalkClientId",
                )}
                <input
                  name={
                    provider === "wecom"
                      ? "botId"
                      : provider === "feishu"
                        ? "appId"
                        : "clientId"
                  }
                  value={botId}
                  required
                  autoComplete="off"
                  disabled={credentialDisabled}
                  onChange={(event) => setBotId(event.target.value)}
                  onKeyDown={(event) => {
                    if (
                      event.key === "Enter" &&
                      (event.nativeEvent.isComposing ||
                        event.nativeEvent.keyCode === 229)
                    )
                      event.preventDefault();
                  }}
                />
              </label>
              <label>
                {t(
                  provider === "wecom"
                    ? "channels.wecomSecret"
                    : provider === "feishu"
                      ? "channels.feishuAppSecret"
                      : "channels.dingtalkClientSecret",
                )}
                <input
                  name="secret"
                  type="password"
                  value={secret}
                  required
                  autoComplete="new-password"
                  disabled={credentialDisabled}
                  onChange={(event) => setSecret(event.target.value)}
                  onKeyDown={(event) => {
                    if (
                      event.key === "Enter" &&
                      (event.nativeEvent.isComposing ||
                        event.nativeEvent.keyCode === 229)
                    )
                      event.preventDefault();
                  }}
                />
              </label>
              <Button
                color="primary"
                size="sm"
                type="submit"
                disabled={
                  credentialDisabled ||
                  !capability.bindingReady ||
                  !botId.trim() ||
                  !secret.trim() ||
                  uncertain
                }
              >
                {t("channels.bindCredentials")}
              </Button>
            </form>
          )}
          {uncertain && <p role="alert">{t("channels.uncertain")}</p>}
          <div className="runtime-channels-actions">
            {method === "quick" && wecomAuthorizationActions}
            {method === "quick" && provider !== "wecom" && (
              <Button
                color="primary"
                size="sm"
                disabled={
                  busy ||
                  loading ||
                  !capability.bindingReady ||
                  uncertain ||
                  (!!binding && !terminal.has(binding.status))
                }
                onClick={() => begin()}
              >
                {t(
                  binding || diagnostics?.configured || pairingRequested
                    ? "channels.newQr"
                    : "channels.bind",
                )}
              </Button>
            )}
            {diagnostics?.configured && (
              <Button
                color="danger"
                variant="outline"
                size="sm"
                disabled={busy}
                onClick={() => {
                  if (window.confirm(t("channels.confirmUnbind")))
                    void perform(async (signal) => {
                      await channelRequest(
                        ep,
                        `?channel=${provider}&appId=${encodeURIComponent(diagnostics.appId || "")}`,
                        { method: "DELETE", signal },
                      );
                      if (!signal.aborted) {
                        setBinding(null);
                        setPairingRequested(false);
                        setWecomPairingComplete(false);
                        setUncertain(false);
                        await refresh(signal);
                      }
                    });
                }}
              >
                {t("channels.unbind")}
              </Button>
            )}
          </div>
          {method === "quick" && (binding || pairingRequested) && (
            <div
              className="runtime-channels-binding-progress"
              role="status"
              aria-live="polite"
            >
              <h3>{t("channels.pairingTitle")}</h3>
              {provider === "feishu" && (
                <p>{t("channels.feishuPairingDescription")}</p>
              )}
              {provider === "wecom" && (
                <p>{t("channels.wecomPairingDescription")}</p>
              )}
              {provider === "wecom" && wecomPairingComplete && (
                <p>{t("channels.status_BOUND")}</p>
              )}
              {!binding && busy && (
                <p>
                  <TextShimmer>
                    {t(
                      provider === "wecom"
                        ? authorizing
                          ? "channels.wecomAuthorizing"
                          : "channels.status_REGISTERING"
                        : "channels.generatingQr",
                    )}
                  </TextShimmer>
                </p>
              )}
              {binding && (
                <>
                  {binding.status !== "PENDING" && (
                    <p>{t(`channels.status_${binding.status}`)}</p>
                  )}
                  {!terminal.has(binding.status) && (
                    <>
                      {safeUrl(binding.qrCodeImage) && (
                        <img
                          className="runtime-channels-qr"
                          src={safeUrl(binding.qrCodeImage)}
                          alt={t("channels.qrAlt")}
                          referrerPolicy="no-referrer"
                        />
                      )}
                    </>
                  )}
                  {binding.lastErrorCode && (
                    <p>
                      {binding.lastErrorCode === "REGISTRATION_UNCERTAIN"
                        ? t("channels.uncertain")
                        : t("channels.bindingFailed")}
                    </p>
                  )}
                  {binding.status === "FAILED" &&
                    binding.lastErrorCode !== "REGISTRATION_UNCERTAIN" && (
                      <Button
                        color="secondary"
                        variant="outline"
                        size="sm"
                        disabled={busy}
                        onClick={() => begin(true)}
                      >
                        {t("common.retry")}
                      </Button>
                    )}
                </>
              )}
            </div>
          )}
          {provider === "feishu" && (
            <section
              className="runtime-channels-permissions"
              aria-label={t("channels.groupsTitle")}
            >
              <div className="runtime-channels-heading">
                <h3>{t("channels.groupsTitle")}</h3>
                <span className="runtime-channels-count">{groups.length}</span>
              </div>
              <p>{t("channels.groupsDescription")}</p>
              <form
                className="runtime-channels-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!chatId.trim() || busy) return;
                  void perform(async (signal) => {
                    await channelRequest(ep, "/chat-permissions", {
                      method: "POST",
                      body: JSON.stringify({
                        channel: provider,
                        chatId: chatId.trim(),
                        groupSessionScope: scope,
                      }),
                      signal,
                    });
                    if (!signal.aborted) {
                      setChatId("");
                      await refresh(signal);
                    }
                  });
                }}
              >
                <label>
                  {t("channels.chatId")}
                  <input
                    value={chatId}
                    required
                    disabled={busy}
                    onChange={(event) => setChatId(event.target.value)}
                    onKeyDown={(event) => {
                      if (
                        event.key === "Enter" &&
                        (event.nativeEvent.isComposing ||
                          event.nativeEvent.keyCode === 229)
                      )
                        event.preventDefault();
                    }}
                  />
                </label>
                <label>
                  {t("channels.scope")}
                  <Select
                    style={{ width: "100%", minWidth: 0 }}
                    value={scope}
                    disabled={busy}
                    options={scopes.map((value) => ({
                      value,
                      label: t(`channels.scope_${value}`),
                    }))}
                    onChange={(event) =>
                      setScope(event.target.value as ChannelScope)
                    }
                  />
                </label>
                <Button
                  color="primary"
                  size="sm"
                  type="submit"
                  disabled={busy || !chatId.trim()}
                >
                  {t("channels.saveGroup")}
                </Button>
              </form>
              {!groups.length && (
                <p className="runtime-channels-empty">
                  {t("channels.noGroups")}
                </p>
              )}
              <ul className="runtime-channels-groups">
                {groups.map((group) => (
                  <li key={group.chatId}>
                    <span>
                      {group.chatName || group.chatId} ·{" "}
                      {t(
                        `channels.scope_${group.groupSessionScope || "group"}`,
                      )}
                    </span>
                    <Button
                      color="danger"
                      variant="ghost"
                      size="sm"
                      className="runtime-channels-remove-group"
                      disabled={busy}
                      aria-label={t("channels.removeGroup", {
                        name: group.chatName || group.chatId,
                      })}
                      onClick={() =>
                        void perform(async (signal) => {
                          await channelRequest(
                            ep,
                            `/chat-permissions?channel=${provider}&chat_id=${encodeURIComponent(group.chatId)}`,
                            { method: "DELETE", signal },
                          );
                          await refresh(signal);
                        })
                      }
                    >
                      <SourceCloseIcon />
                    </Button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </section>
  );
}
