import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { listMpaRuns } from "../adk/client";
import type { MpaCronTask, MpaRunPage, MpaRuntime } from "../adk/mpaCronTasks";
import { DialogShell } from "../ui/SandboxControls";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
import { formatTime, scheduleText } from "./mpaSchedule";
import { MpaIcon } from "./MpaTaskIcons";
export function mpaErrorKey(error: unknown): string {
  const message = error instanceof Error ? error.message : "";
  return (
    (
      {
        MPA_HTTP_401: "mpa.authRequired",
        MPA_HTTP_403: "mpa.forbidden",
        MPA_HTTP_404: "mpa.unsupported",
        MPA_HTTP_409: "mpa.manage.conflict",
        MPA_HTTP_422: "mpa.manage.invalid",
        MPA_INVALID_RESPONSE: "mpa.invalidResponse",
      } as Record<string, string>
    )[message] || "mpa.loadFailed"
  );
}
export function MpaTaskDetail({
  task,
  runtime,
  onClose,
}: {
  task: MpaCronTask;
  runtime: MpaRuntime;
  onClose: () => void;
}) {
  const { t, i18n } = useTranslation("cronjobs");
  const label = (key: string) => t(`mpa.manage.${key}`);
  const [offset, setOffset] = useState(0),
    [refresh, setRefresh] = useState(0),
    [page, setPage] = useState<MpaRunPage | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setPage(null);
    void listMpaRuns(runtime, task.id, offset, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setPage(data);
      })
      .catch((e) => {
        if (!controller.signal.aborted) setError(mpaErrorKey(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [runtime.runtimeId, runtime.region, task.id, offset, refresh]);
  return (
    <DialogShell
      open
      title={task.name}
      icon={<MpaIcon kind="detail" />}
      className="mpa-dialog mpa-detail"
      onClose={onClose}
    >
      <div className="sandbox-control-body">
        <dl className="mpa-details">
          <dt>{label("agent")}</dt>
          <dd>{task.agentId || "—"}</dd>
          <dt>{label("schedule")}</dt>
          <dd>{scheduleText(task, label, i18n.language)}</dd>
          <dt>{t("mpa.columns.next")}</dt>
          <dd>{formatTime(task.nextRunAt, i18n.language)}</dd>
          <dt>{label("prompt")}</dt>
          <dd className="mpa-prompt">{task.prompt}</dd>
        </dl>
        <div className="mpa-history-title">
          <h3>{label("history")}</h3>
          <button
            className="cw-btn cw-btn-ghost"
            disabled={loading}
            onClick={() => setRefresh((n) => n + 1)}
          >
            {t("mpa.refresh")}
          </button>
        </div>
        {error && (
          <p className="cw-error-text" role="alert">
            {t(error)}
          </p>
        )}
        {loading && <TextShimmer>{t("mpa.loading")}</TextShimmer>}
        {page && (
          <>
            <div className="mpa-cron-table">
              <table>
                <thead>
                  <tr>
                    {["lastRun", "lastStatus", "duration", "result"].map(
                      (k) => (
                        <th key={k}>{label(k)}</th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((run) => (
                    <tr key={run.id}>
                      <td>
                        {formatTime(
                          run.startedAt || run.scheduledAt,
                          i18n.language,
                        )}
                      </td>
                      <td>{label(run.status)}</td>
                      <td>
                        {run.durationMs == null ? "—" : `${run.durationMs} ms`}
                      </td>
                      <td>{run.errorMessage || run.sessionId || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {page.items.length === 0 && <p>{label("noRuns")}</p>}
            <nav className="mpa-cron-pages">
              <span>{t("mpa.total", { total: page.total })}</span>
              <button
                className="cw-btn cw-btn-ghost"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - 20))}
              >
                {t("mpa.previous")}
              </button>
              <button
                className="cw-btn cw-btn-ghost"
                disabled={!page.hasMore}
                onClick={() => setOffset(page.nextOffset!)}
              >
                {t("mpa.next")}
              </button>
            </nav>
          </>
        )}
      </div>
    </DialogShell>
  );
}
