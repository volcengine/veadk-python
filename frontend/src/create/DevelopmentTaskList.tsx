import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@openai/apps-sdk-ui/components/Tooltip";
import { localeCompatibleBackendText } from "../i18n/locales";
import { SourceRefreshIcon } from "../ui/icons/SourceWorkspaceIcons";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
import type { DevelopmentTaskSnapshot } from "./DevelopmentTaskNotice";

interface Props {
  ownerId: string;
  snapshot?: DevelopmentTaskSnapshot;
  disabled: boolean;
  onRefresh: () => void;
  onOpen: (sessionId: string, signal: AbortSignal) => Promise<void>;
}

function TaskIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M8 4.5H5.5v15h13v-15H16M8 3.5h8v4H8zM9 12h6M9 16h3" />
    </svg>
  );
}

function TaskArrowIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M5 12h14m-5-5 5 5-5 5" />
    </svg>
  );
}

export function DevelopmentTaskList({
  ownerId,
  snapshot,
  disabled,
  onRefresh,
  onOpen,
}: Props) {
  const { t, i18n } = useTranslation("create");
  const [openingId, setOpeningId] = useState("");
  const [openError, setOpenError] = useState("");
  const opening = useRef<AbortController | null>(null);
  const state = snapshot?.ownerId === ownerId ? snapshot : undefined;
  const runs = [...(state?.runs ?? [])].sort(
    (a, b) => b.createdAt - a.createdAt,
  );
  const loading = state?.loading ?? true;
  const locale = i18n.resolvedLanguage || i18n.language;
  const error =
    localeCompatibleBackendText(state?.error, locale) ||
    (state?.error ? t("intelligent.tasks.loadError") : "");

  useEffect(() => {
    setOpeningId("");
    setOpenError("");
    return () => {
      opening.current?.abort();
      opening.current = null;
    };
  }, [ownerId, disabled]);

  async function open(sessionId: string, runId: string) {
    if (opening.current || disabled) return;
    const controller = new AbortController();
    opening.current = controller;
    setOpeningId(runId);
    setOpenError("");
    try {
      await onOpen(sessionId, controller.signal);
    } catch (cause) {
      if (controller.signal.aborted) return;
      setOpenError(
        localeCompatibleBackendText(
          cause instanceof Error ? cause.message : "",
          locale,
        ) || t("intelligent.tasks.openError"),
      );
    } finally {
      if (opening.current === controller) {
        opening.current = null;
        setOpeningId("");
      }
    }
  }

  function startedAt(value: number) {
    const date = new Date(value * 1000);
    if (!Number.isFinite(date.getTime())) return "";
    return t("intelligent.tasks.startedAt", {
      time: new Intl.DateTimeFormat(locale, {
        month: "numeric",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(date),
    });
  }

  return (
    <section
      className="ic-panel ic-tasks-panel"
      aria-labelledby="intelligent-tasks-title"
    >
      <header className="ic-tasks-heading">
        <h2 id="intelligent-tasks-title">{t("intelligent.tasks.title")}</h2>
        {runs.length > 0 ? (
          <span className="ic-task-count">{runs.length}</span>
        ) : null}
        <button
          type="button"
          className="ic-icon-button ic-refresh"
          onClick={onRefresh}
          disabled={loading || disabled}
          aria-label={t("intelligent.tasks.refresh")}
          title={t("intelligent.tasks.refresh")}
        >
          <SourceRefreshIcon />
        </button>
      </header>
      <p className="ic-tasks-hint">{t("intelligent.tasks.hint")}</p>
      {error ? (
        <div className="ic-inline-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={onRefresh} disabled={loading}>
            {t("common.retry")}
          </button>
        </div>
      ) : null}
      {openError ? (
        <p className="ic-error" role="alert">
          {openError}
        </p>
      ) : null}
      {runs.length ? (
        <ul className="ic-task-list" aria-label={t("intelligent.tasks.title")}>
          {runs.map((run) => (
            <li key={run.runId}>
              <Tooltip content={run.message}>
                <button
                  type="button"
                  className="ic-task"
                  onClick={() => void open(run.sessionId, run.runId)}
                  disabled={disabled || Boolean(openingId)}
                  aria-busy={openingId === run.runId}
                >
                  <span className={`ic-task-status is-${run.state}`}>
                    <span className="ic-task-status-dot" aria-hidden="true" />
                    {t(`intelligent.tasks.states.${run.state}`)}
                  </span>
                  <span className="ic-task-goal">{run.message}</span>
                  <span className="ic-task-footer">
                    <span>{startedAt(run.createdAt)}</span>
                    <span className="ic-task-action">
                      {openingId === run.runId ? (
                        <TextShimmer>
                          {t("intelligent.tasks.opening")}
                        </TextShimmer>
                      ) : (
                        t("intelligent.tasks.open")
                      )}
                      <TaskArrowIcon />
                    </span>
                  </span>
                </button>
              </Tooltip>
            </li>
          ))}
        </ul>
      ) : loading && !error ? (
        <div className="ic-task-empty" role="status">
          <TextShimmer>{t("intelligent.tasks.loading")}</TextShimmer>
        </div>
      ) : !error ? (
        <div className="ic-task-empty">
          <span className="ic-task-empty-icon">
            <TaskIcon />
          </span>
          <strong>{t("intelligent.tasks.empty")}</strong>
          <p>{t("intelligent.tasks.emptyHint")}</p>
        </div>
      ) : null}
    </section>
  );
}
