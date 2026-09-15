import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Menu } from "@openai/apps-sdk-ui/components/Menu";
import { listMpaCronTasks, requestMpaTask } from "../adk/client";
import type {
  MpaCronTask,
  MpaCronTaskPage,
  MpaRuntime,
  TaskFields,
} from "../adk/mpaCronTasks";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
import { DialogShell } from "../ui/SandboxControls";
import { MpaTaskEditor } from "./MpaTaskEditor";
import { MpaTaskDetail, mpaErrorKey } from "./MpaTaskDetail";
import { MpaIcon } from "./MpaTaskIcons";
import {
  calendarTimes,
  formatTime,
  monthDays,
  runStatuses,
  scheduleText,
  taskStatus,
} from "./mpaSchedule";
import "../create/CustomCreate.css";
import "../ui/ProjectPreview.css";
import "./MpaCronTasks.css";

export function MpaCronTasks({ runtime }: { runtime?: MpaRuntime }) {
  const { t } = useTranslation("cronjobs");
  return runtime ? (
    <RuntimeTasks
      key={`${runtime.region}:${runtime.runtimeId}`}
      runtime={runtime}
    />
  ) : (
    <p role="status">{t("mpa.selectRuntime")}</p>
  );
}
function RuntimeTasks({ runtime }: { runtime: MpaRuntime }) {
  const { t, i18n } = useTranslation("cronjobs");
  const label = (key: string) => t(`mpa.manage.${key}`);
  const [draftQuery, setDraftQuery] = useState(""),
    [query, setQuery] = useState(""),
    [index, setIndex] = useState(0),
    [refresh, setRefresh] = useState(0);
  const [page, setPage] = useState<MpaCronTaskPage | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [view, setView] = useState("list"),
    [status, setStatus] = useState("all"),
    [month, setMonth] = useState(() => new Date());
  const [editor, setEditor] = useState<{
      task?: MpaCronTask;
      copy: boolean;
    } | null>(null),
    [detail, setDetail] = useState<MpaCronTask | null>(null),
    [deleting, setDeleting] = useState<MpaCronTask | null>(null);
  const [busy, setBusy] = useState(false),
    [writeError, setWriteError] = useState("");
  const locked = useRef(false),
    composing = useRef(false);
  const lifetime = useRef(new AbortController());
  const tokens = useRef(new Map<string, string>());
  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => controller.abort();
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setPage(null);
    void (async () => {
      const first = await listMpaCronTasks(
        runtime,
        0,
        query,
        controller.signal,
      );
      const items = [...first.items];
      let current = first;
      let offset = 0;
      while (current.hasMore) {
        if (controller.signal.aborted) return;
        if (
          current.nextOffset === null ||
          current.nextOffset <= offset ||
          items.length > 100000
        )
          throw new Error("MPA_INVALID_RESPONSE");
        offset = current.nextOffset;
        current = await listMpaCronTasks(
          runtime,
          offset,
          query,
          controller.signal,
        );
        items.push(...current.items);
      }
      if (!controller.signal.aborted)
        setPage({
          ...first,
          items: [...new Map(items.map((task) => [task.id, task])).values()],
          hasMore: false,
          nextOffset: null,
        });
    })()
      .catch((e) => {
        if (!controller.signal.aborted) setError(mpaErrorKey(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [runtime.runtimeId, runtime.region, query, refresh]);
  const filtered = useMemo(
    () =>
      page?.items.filter(
        (task) => status === "all" || taskStatus(task) === status,
      ) || [],
    [page, status],
  );
  const days = useMemo(() => monthDays(month), [month]);
  const calendar = useMemo(
    () =>
      days.map((day) => ({
        day,
        tasks: filtered.flatMap((task) => {
          const entry = calendarTimes(task, day);
          return entry ? [{ task, ...entry }] : [];
        }),
      })),
    [days, filtered],
  );
  const visible = filtered.slice(index, index + 10);
  function token(key: string) {
    let value = tokens.current.get(key);
    if (!value) {
      value = crypto.randomUUID();
      tokens.current.set(key, value);
    }
    return value;
  }
  async function mutate(
    kind: "create" | "edit" | "delete" | "run" | "toggle",
    task?: MpaCronTask,
    fields?: TaskFields,
  ) {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setWriteError("");
    setNotice("");
    const operation = lifetime.current;
    const key =
      kind === "create" ? JSON.stringify(fields) : `${kind}:${task?.id}`;
    try {
      const suffix = task
        ? `/${encodeURIComponent(task.id)}${kind === "run" ? "/run" : ""}`
        : "";
      if (
        (kind === "edit" || kind === "toggle") &&
        (!Number.isInteger(task?.version) || Number(task?.version) < 1)
      )
        throw new Error("MPA_INVALID_RESPONSE");
      const payload =
        kind === "delete"
          ? undefined
          : kind === "run"
            ? { clientToken: token(key), mode: "Force" }
            : kind === "create"
              ? { ...fields, clientToken: token(key) }
              : {
                  ...(kind === "toggle" ? { enabled: !task!.enabled } : fields),
                  expectedVersion: task!.version,
                };
      const result = await requestMpaTask(
        runtime,
        kind === "delete" ? "DELETE" : "POST",
        suffix,
        payload,
        operation.signal,
      );
      if (
        kind === "delete"
          ? result.removed !== true
          : kind === "run"
            ? !result.run
            : !result.task
      )
        throw new Error("MPA_INVALID_RESPONSE");
      tokens.current.delete(key);
      if (!operation.signal.aborted) {
        setEditor(null);
        setDeleting(null);
        setDetail(null);
        setNotice(label(kind === "run" ? "queued" : "saved"));
        setIndex(0);
        setRefresh((n) => n + 1);
      }
    } catch (e) {
      if (!operation.signal.aborted) setWriteError(t(mpaErrorKey(e)));
    } finally {
      locked.current = false;
      if (!operation.signal.aborted) setBusy(false);
    }
  }
  function openEditor(task?: MpaCronTask, copy = false) {
    setWriteError("");
    setEditor({ task, copy });
  }
  return (
    <section className="mpa-cron" aria-label={t("mpa.title")}>
      <div className="mpa-cron-target">
        <strong>{runtime.name}</strong>
        <span>
          {runtime.runtimeId} · {runtime.region}
        </span>
      </div>
      <div className="mpa-cron-heading">
        <div className="mpa-segment" role="group" aria-label={label("view")}>
          {["list", "calendar"].map((mode) => (
            <button
              key={mode}
              aria-pressed={view === mode}
              onClick={() => setView(mode)}
            >
              {label(mode)}
            </button>
          ))}
        </div>
        <button
          className="cw-btn cw-btn-primary mpa-create"
          disabled={busy}
          onClick={() => openEditor()}
        >
          <MpaIcon kind="plus" />
          {label("create")}
        </button>
      </div>
      <div className="mpa-toolbar">
        <form
          className="mpa-cron-search"
          onSubmit={(e) => {
            e.preventDefault();
            if (composing.current) return;
            setIndex(0);
            setQuery(draftQuery);
            setRefresh((n) => n + 1);
          }}
        >
          <input
            aria-label={t("mpa.search")}
            placeholder={t("mpa.search")}
            type="search"
            maxLength={200}
            value={draftQuery}
            onChange={(e) => setDraftQuery(e.target.value)}
            onCompositionStart={() => {
              composing.current = true;
            }}
            onCompositionEnd={() => {
              composing.current = false;
            }}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                (composing.current ||
                  e.nativeEvent.isComposing ||
                  e.keyCode === 229)
              )
                e.preventDefault();
            }}
          />
          <button
            className="cw-btn cw-btn-ghost"
            disabled={loading}
            type="submit"
          >
            {t("mpa.search")}
          </button>
          <button
            className="cw-btn cw-btn-ghost"
            disabled={loading}
            type="button"
            onClick={() => setRefresh((n) => n + 1)}
          >
            {t("mpa.refresh")}
          </button>
        </form>
        {page?.overview && (
          <div className="mpa-cron-overview">
            <span>{label("overview")}</span>
            <span>
              {t("mpa.successRate")}{" "}
              <strong>{Math.round(page.overview.successRate * 100)}%</strong>
            </span>
            <span>
              {t("mpa.executionCount")}{" "}
              <strong>{page.overview.executionCount}</strong>
            </span>
          </div>
        )}
      </div>
      {error && (
        <p role="alert" className="mpa-cron-error">
          {t(error)}
        </p>
      )}
      {writeError && !editor && !deleting && (
        <p role="alert" className="mpa-cron-error">
          {writeError}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {loading && (
        <div className="mpa-state" role="status">
          <TextShimmer>{t("mpa.loading")}</TextShimmer>
        </div>
      )}
      {!loading && !error && page && (
        <>
          {view === "list" ? (
            <>
              <div
                className="mpa-cron-table"
                tabIndex={0}
                role="region"
                aria-label={t("mpa.title")}
              >
                <table>
                  <thead>
                    <tr>
                      <th>{label("name")}</th>
                      <th>{label("lastRun")}</th>
                      <th>{label("schedule")}</th>
                      <th>
                        <Menu>
                          <Menu.Trigger>
                            <button
                              className="mpa-status-filter"
                              aria-label={label("lastStatus")}
                            >
                              {label(status === "all" ? "lastStatus" : status)}
                              <MpaIcon kind="filter" />
                            </button>
                          </Menu.Trigger>
                          <Menu.Content side="bottom" align="start">
                            {["all", "Pending", ...runStatuses].map((value) => (
                              <Menu.Item
                                key={value}
                                onSelect={() => {
                                  setStatus(value);
                                  setIndex(0);
                                }}
                              >
                                {label(value)}
                              </Menu.Item>
                            ))}
                          </Menu.Content>
                        </Menu>
                      </th>
                      <th>{label("agent")}</th>
                      <th>{label("actions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((task) => (
                      <tr key={task.id}>
                        <td>
                          <button
                            className="mpa-task-link"
                            title={task.name}
                            onClick={() => setDetail(task)}
                          >
                            {task.name}
                          </button>
                        </td>
                        <td>{formatTime(task.lastRunAt, i18n.language)}</td>
                        <td>{scheduleText(task, label, i18n.language)}</td>
                        <td>
                          <span
                            className={`mpa-status mpa-status-${taskStatus(task)}`}
                          >
                            {label(taskStatus(task))}
                          </span>
                        </td>
                        <td>{task.agentId || "—"}</td>
                        <td>
                          <div className="mpa-actions">
                            <button
                              role="switch"
                              aria-checked={task.enabled}
                              aria-label={`${label("enabled")} ${task.name}`}
                              disabled={busy}
                              className="mpa-switch"
                              onClick={() => void mutate("toggle", task)}
                            >
                              <span />
                            </button>
                            <button
                              className="mpa-icon-button"
                              title={label("run")}
                              aria-label={`${label("run")} ${task.name}`}
                              disabled={
                                busy ||
                                taskStatus(task) === "Running" ||
                                taskStatus(task) === "Queued"
                              }
                              onClick={() => void mutate("run", task)}
                            >
                              <MpaIcon kind="play" />
                            </button>
                            <Menu>
                              <Menu.Trigger>
                                <button
                                  className="mpa-icon-button"
                                  disabled={busy}
                                  aria-label={`${label("actions")} ${task.name}`}
                                >
                                  <MpaIcon kind="more" />
                                </button>
                              </Menu.Trigger>
                              <Menu.Content
                                side="bottom"
                                align="end"
                                minWidth={148}
                              >
                                {(
                                  ["detail", "edit", "copy", "delete"] as const
                                ).map((action) => (
                                  <Menu.Item
                                    key={action}
                                    onSelect={() => {
                                      if (action === "detail") setDetail(task);
                                      else if (action === "delete") {
                                        setWriteError("");
                                        setDeleting(task);
                                      } else
                                        openEditor(task, action === "copy");
                                    }}
                                  >
                                    <MpaIcon kind={action} />
                                    <span>{label(action)}</span>
                                  </Menu.Item>
                                ))}
                              </Menu.Content>
                            </Menu>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {filtered.length === 0 && (
                  <div className="mpa-state" role="status">
                    {t("mpa.empty")}
                  </div>
                )}
              </div>
              <nav className="mpa-cron-pages" aria-label={t("mpa.pagination")}>
                <span>{t("mpa.total", { total: filtered.length })}</span>
                <button
                  className="cw-btn cw-btn-ghost"
                  disabled={index === 0}
                  onClick={() => setIndex(Math.max(0, index - 10))}
                >
                  {t("mpa.previous")}
                </button>
                <button
                  className="cw-btn cw-btn-ghost"
                  disabled={index + 10 >= filtered.length}
                  onClick={() => setIndex(index + 10)}
                >
                  {t("mpa.next")}
                </button>
              </nav>
            </>
          ) : (
            <>
              <div className="mpa-calendar-bar">
                <strong>
                  {new Intl.DateTimeFormat(i18n.language, {
                    year: "numeric",
                    month: "long",
                  }).format(month)}
                </strong>
                <span>
                  {label("calendarZone")}{" "}
                  {Intl.DateTimeFormat().resolvedOptions().timeZone}
                </span>
                <button
                  className="cw-btn cw-btn-ghost"
                  onClick={() =>
                    setMonth(
                      new Date(month.getFullYear(), month.getMonth() - 1, 1),
                    )
                  }
                >
                  {label("prevMonth")}
                </button>
                <button
                  className="cw-btn cw-btn-ghost"
                  onClick={() => setMonth(new Date())}
                >
                  {label("today")}
                </button>
                <button
                  className="cw-btn cw-btn-ghost"
                  onClick={() =>
                    setMonth(
                      new Date(month.getFullYear(), month.getMonth() + 1, 1),
                    )
                  }
                >
                  {label("nextMonth")}
                </button>
              </div>
              <div className="mpa-calendar">
                {days.slice(0, 7).map((d) => (
                  <div className="mpa-calendar-weekday" key={d.toISOString()}>
                    {new Intl.DateTimeFormat(i18n.language, {
                      weekday: "short",
                    }).format(d)}
                  </div>
                ))}
                {calendar.map(({ day, tasks }) => (
                  <div
                    key={day.toISOString()}
                    className={`mpa-calendar-day ${day.getMonth() !== month.getMonth() ? "is-outside" : ""}`}
                  >
                    <time dateTime={day.toISOString()}>{day.getDate()}</time>
                    {tasks.map(({ task, at, count, nextOnly }) => (
                      <button
                        key={task.id}
                        className="mpa-calendar-task"
                        onClick={() => setDetail(task)}
                        title={`${task.name} · ${scheduleText(task, label, i18n.language)}`}
                      >
                        <span>
                          {new Intl.DateTimeFormat(i18n.language, {
                            hour: "2-digit",
                            minute: "2-digit",
                          }).format(at)}{" "}
                          {task.name}
                        </span>
                        {count > 1 && <small> × {count}</small>}
                        {nextOnly && <small>{label("nextOnly")}</small>}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
              <p>{label("calendarHint")}</p>
            </>
          )}
        </>
      )}
      {editor && (
        <MpaTaskEditor
          defaultAgentId={runtime.runtimeId}
          task={editor.task}
          copy={editor.copy}
          busy={busy}
          error={writeError}
          onClose={() => setEditor(null)}
          onSave={(fields) =>
            void mutate(
              editor.task && !editor.copy ? "edit" : "create",
              editor.copy ? undefined : editor.task,
              fields,
            )
          }
        />
      )}
      {detail && (
        <MpaTaskDetail
          key={detail.id}
          runtime={runtime}
          task={detail}
          onClose={() => setDetail(null)}
        />
      )}
      {deleting && (
        <DialogShell
          open
          title={label("delete")}
          icon={<MpaIcon kind="delete" />}
          busy={busy}
          onClose={() => setDeleting(null)}
        >
          <div className="sandbox-control-body">
            <p>{t("mpa.manage.deleteConfirm", { name: deleting.name })}</p>
            {writeError && (
              <p role="alert" className="cw-error-text">
                {writeError}
              </p>
            )}
          </div>
          <footer className="sandbox-control-actions">
            <button
              className="cw-btn cw-btn-ghost"
              disabled={busy}
              onClick={() => setDeleting(null)}
            >
              {label("cancel")}
            </button>
            <button
              className="cw-btn cw-btn-primary"
              disabled={busy}
              onClick={() => void mutate("delete", deleting)}
            >
              {label("delete")}
            </button>
          </footer>
        </DialogShell>
      )}
    </section>
  );
}
