import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "../components/primitives/Button/Button";
import { Select } from "../components/primitives/Select/Select";
import {
  channelRequest,
  ChannelApiError,
  type ChannelCapabilities,
} from "../adk/client";
import { listFeishuAccounts, type FeishuAccount } from "../adk/feishuAccounts";
import { TextShimmer } from "./text-shimmer/TextShimmer";

export interface FeishuAccountPanelProps {
  accountId?: string;
  accountMode: "add" | "manage";
  onBound: (appId?: string) => void;
  onDeleted: () => void;
  onBusyChange: (busy: boolean) => void;
}

export function FeishuAccounts({
  runtimeId,
  region,
  capability,
  renderPanel,
}: {
  runtimeId: string;
  region: string;
  capability: ChannelCapabilities;
  renderPanel: (props: FeishuAccountPanelProps) => ReactNode;
}) {
  const { t } = useTranslation("ui");
  const ep = useMemo(() => ({ runtimeId, region }), [runtimeId, region]);
  const [accounts, setAccounts] = useState<FeishuAccount[]>([]);
  const [selected, setSelected] = useState("");
  const [adding, setAdding] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const read = useRef<AbortController | null>(null);
  const write = useRef<AbortController | null>(null);
  const preferred = useRef<string | undefined>(undefined);
  const active = accounts.find((account) => account.appId === selected);
  useEffect(() => {
    const controller = new AbortController();
    read.current = controller;
    setLoading(true);
    setError("");
    void listFeishuAccounts(ep, controller.signal)
      .then((values) => {
        if (controller.signal.aborted) return;
        setAccounts(values);
        const requested = preferred.current;
        setSelected((current) => {
          const candidate = requested ?? current;
          return values.some((account) => account.appId === candidate)
            ? candidate
            : values.length === 1
              ? values[0].appId
              : "";
        });
        preferred.current = undefined;
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setError(
            t(
              reason instanceof ChannelApiError &&
                [401, 403].includes(reason.status)
                ? "channels.unauthorized"
                : "channels.accountsFailed",
            ),
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [ep, reload, t]);
  useEffect(
    () => () => {
      read.current?.abort();
      write.current?.abort();
    },
    [],
  );
  function refresh(appId?: string) {
    preferred.current = appId;
    setAdding(false);
    setReload((value) => value + 1);
  }
  async function toggle() {
    if (!active || busy || write.current) return;
    const controller = new AbortController();
    write.current = controller;
    setBusy(true);
    setError("");
    try {
      await channelRequest(
        ep,
        `/feishu/accounts/${encodeURIComponent(active.appId)}`,
        {
          method: "PATCH",
          body: JSON.stringify({ enabled: !active.enabled }),
          signal: controller.signal,
        },
      );
      if (!controller.signal.aborted) refresh(active.appId);
    } catch (reason) {
      if (!controller.signal.aborted)
        setError(
          t(
            reason instanceof ChannelApiError &&
              [401, 403].includes(reason.status)
              ? "channels.unauthorized"
              : "channels.requestFailed",
          ),
        );
    } finally {
      if (write.current === controller) write.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  return (
    <section
      className="runtime-channels runtime-channels-accounts"
      aria-label={t("channels.accountsTitle")}
      aria-busy={loading || busy}
    >
      <div className="runtime-channels-heading">
        <h3>{t("channels.accountsTitle")}</h3>
        <Button
          variant="outline"
          size="compact"
          disabled={busy || loading}
          onClick={() => refresh(selected)}
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
        <div role="alert" className="aw-integration-error">
          <span>{error}</span>
          <Button
            variant="outline"
            size="compact"
            disabled={busy || loading}
            onClick={() => refresh(selected)}
          >
            {t("common.retry")}
          </Button>
        </div>
      )}
      <div className="runtime-channels-account-actions">
        <label className="runtime-channels-account-select">
          {t("channels.account")}
          <Select
            aria-label={t("channels.account")}
            value={selected}
            disabled={busy || loading || !!error}
            options={[
              { value: "", label: t("channels.selectAccount") },
              ...accounts.map((account) => ({
                value: account.appId,
                label: `${account.appName || account.appId} | ${account.enabled ? t("channels.accountEnabled") : t("channels.accountDisabled")}`,
                description: account.appName ? account.appId : undefined,
              })),
            ]}
            onChange={(event) => {
              setAdding(false);
              setSelected(event.target.value);
            }}
          />
        </label>
        <Button
          size="compact"
          disabled={busy || loading || !!error || !capability.bindingReady}
          onClick={() => setAdding(true)}
        >
          {t("channels.addAccount")}
        </Button>
        {active && !adding && (
          <Button
            variant="outline"
            size="compact"
            disabled={busy || loading || !!error}
            onClick={() => void toggle()}
          >
            {t(
              active.enabled
                ? "channels.disableAccount"
                : "channels.enableAccount",
            )}
          </Button>
        )}
      </div>
      {!loading && !error && !accounts.length && (
        <p role="status">{t("channels.noAccounts")}</p>
      )}
      {!loading && !error && !adding && !selected && accounts.length > 0 && (
        <p role="status">{t("channels.selectAccount")}</p>
      )}
      {!loading && !error && (adding || active) && (
        <div key={adding ? "add" : selected}>
          {adding && (
            <Button
              variant="ghost"
              size="compact"
              disabled={busy}
              onClick={() => setAdding(false)}
            >
              {t("channels.cancelAddAccount")}
            </Button>
          )}
          {renderPanel({
            accountId: adding ? undefined : selected,
            accountMode: adding ? "add" : "manage",
            onBound: refresh,
            onDeleted: () => refresh(""),
            onBusyChange: setBusy,
          })}
        </div>
      )}
    </section>
  );
}
