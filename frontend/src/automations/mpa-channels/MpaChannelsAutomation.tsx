import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  getRuntimes,
  RuntimeListError,
  type CloudRuntime,
  type RuntimeScope,
  type StudioRole,
} from "../../adk/client";
import { formatRelativeTimeLabel } from "../../ui/relativeTime";
import { DeploymentSelect } from "../../ui/DeploymentSelect";
import { RuntimeChannels } from "../../ui/RuntimeChannels";
import { TextShimmer } from "../../ui/text-shimmer/TextShimmer";
import { MpaChannelsIcon } from "./MpaChannelsIcon";
import "../../ui/ProjectPreview.css";
import "./MpaChannelsAutomation.css";

interface MpaChannelsAutomationProps {
  role: StudioRole;
  runtimeScope: RuntimeScope;
  onBack: () => void;
}

const runtimeKey = (runtime: CloudRuntime) =>
  `${runtime.region}:${runtime.runtimeId}`;

export function MpaChannelsAutomation({
  role,
  runtimeScope,
  onBack,
}: MpaChannelsAutomationProps) {
  const { t } = useTranslation("automations");
  const authorized = role === "admin" || role === "super_admin";
  return (
    <div className="mpa-channels-page">
      <header className="mpa-channels-header">
        <button
          type="button"
          className="mpa-channels-back"
          aria-label={t("backToAutomations")}
          onClick={onBack}
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
            <path d="m14 6-6 6 6 6" />
          </svg>
        </button>
        <MpaChannelsIcon className="mpa-channels-icon" />
        <div>
          <h1>{t("cards.mpa-channels.name")}</h1>
          <p>{t("cards.mpa-channels.description")}</p>
        </div>
      </header>
      <div className="mpa-channels-scroll">
        {authorized ? (
          <MpaChannelSelector
            key={`${role}:${runtimeScope}`}
            runtimeScope={runtimeScope}
          />
        ) : (
          <p className="mpa-channels-notice" role="status">
            {t("mpaChannels.unauthorized")}
          </p>
        )}
      </div>
    </div>
  );
}

function MpaChannelSelector({ runtimeScope }: { runtimeScope: RuntimeScope }) {
  const { t, i18n } = useTranslation("automations");
  const [runtimes, setRuntimes] = useState<CloudRuntime[]>([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [query, setQuery] = useState("");
  const [nextToken, setNextToken] = useState("");
  const [loading, setLoading] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<"unauthorized" | "loadFailed" | null>(
    null,
  );
  const request = useRef<AbortController | null>(null);
  const failedCursor = useRef("");

  async function loadPage(cursor = "") {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError(null);
    failedCursor.current = cursor;
    try {
      const page = await getRuntimes({
        agentCategory: "mpa",
        scope: runtimeScope,
        region: "all",
        pageSize: 100,
        nextToken: cursor || undefined,
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      // Older filtered list responses may omit category metadata.
      const items = page.runtimes.filter(
        (runtime) =>
          runtime.runtimeId &&
          runtime.region &&
          (runtime.agentCategory === "mpa" ||
            runtime.agentCategory === undefined),
      );
      setRuntimes((current) => [
        ...new Map(
          (cursor ? [...current, ...items] : items).map((runtime) => [
            runtimeKey(runtime),
            runtime,
          ]),
        ).values(),
      ]);
      if (!cursor)
        setSelectedKey((current) =>
          items.some((runtime) => runtimeKey(runtime) === current)
            ? current
            : "",
        );
      setNextToken(page.nextToken);
      setLoaded(true);
    } catch (cause) {
      if (controller.signal.aborted) return;
      const denied =
        cause instanceof RuntimeListError &&
        (cause.status === 401 || cause.status === 403);
      setError(denied ? "unauthorized" : "loadFailed");
      if (denied) {
        setRuntimes([]);
        setSelectedKey("");
        setNextToken("");
        setLoaded(false);
        failedCursor.current = "";
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  useEffect(() => {
    void loadPage();
    return () => request.current?.abort();
    // The parent remounts the selector whenever role or scope changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selected = runtimes.find(
    (runtime) => runtimeKey(runtime) === selectedKey,
  );
  const keyword = query.trim().toLocaleLowerCase();
  const options = runtimes
    .filter((runtime) =>
      `${runtime.name} ${runtime.runtimeId} ${runtime.region}`
        .toLocaleLowerCase()
        .includes(keyword),
    )
    .map((runtime) => {
      const createdAt = formatRelativeTimeLabel(
        runtime.createdAt,
        Date.now(),
        i18n.resolvedLanguage || i18n.language,
      );
      return {
        value: runtimeKey(runtime),
        label: runtime.name || runtime.runtimeId,
        description:
          runtime.description?.trim() || t("mpaChannels.noDescription"),
        metadata: `${t("mpaChannels.optionMetadata", {
          creator: runtime.author?.trim() || t("mpaChannels.unknownCreator"),
          createdAt,
        })}\n${runtime.region} · ${runtime.runtimeId}`,
      };
    });

  return (
    <div className="mpa-channels-content">
      <section
        className="mpa-channels-picker"
        aria-label={t("mpaChannels.selectAgent")}
      >
        <div className="mpa-channels-picker-heading">
          <h2>{t("mpaChannels.selectAgent")}</h2>
          <button
            type="button"
            className="mpa-channels-action"
            disabled={loading}
            onClick={() => void loadPage()}
          >
            {t("mpaChannels.refresh")}
          </button>
        </div>
        <DeploymentSelect
          ariaLabel={t("mpaChannels.selectAgent")}
          placeholder={t("mpaChannels.chooseAgent")}
          value={selectedKey}
          valueLabel={selected?.name || selected?.runtimeId}
          options={options}
          disabled={!runtimes.length}
          searchValue={query}
          searchPlaceholder={t("mpaChannels.search")}
          emptyMessage={t("mpaChannels.noMatches")}
          onSearchChange={setQuery}
          onChange={setSelectedKey}
        />
        {selected && (
          <p className="mpa-channels-target">
            {selected.region} · {selected.runtimeId}
          </p>
        )}
        {loading && (
          <TextShimmer as="p" role="status">
            {t("mpaChannels.loading")}
          </TextShimmer>
        )}
        {error && (
          <div className="mpa-channels-error" role="alert">
            <p>{t(`mpaChannels.${error}`)}</p>
            <button
              type="button"
              className="mpa-channels-action"
              onClick={() => void loadPage(failedCursor.current)}
            >
              {t("mpaChannels.retry")}
            </button>
          </div>
        )}
        {!loading && !error && loaded && !runtimes.length && !nextToken && (
          <p role="status">{t("mpaChannels.empty")}</p>
        )}
        {nextToken && (
          <div className="mpa-channels-pagination">
            <p>{t("mpaChannels.moreAvailable")}</p>
            <button
              type="button"
              className="mpa-channels-action"
              disabled={loading}
              onClick={() => void loadPage(nextToken)}
            >
              {t("mpaChannels.loadMore")}
            </button>
          </div>
        )}
      </section>
      {selected ? (
        <RuntimeChannels
          key={runtimeKey(selected)}
          runtimeId={selected.runtimeId}
          region={selected.region}
          showHeader={false}
        />
      ) : loaded && runtimes.length > 0 ? (
        <p className="mpa-channels-notice" role="status">
          {t("mpaChannels.chooseHint")}
        </p>
      ) : null}
    </div>
  );
}
