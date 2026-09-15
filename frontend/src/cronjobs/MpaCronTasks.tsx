import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { listMpaCronTasks } from "../adk/client";
import type { MpaCronTaskPage, MpaRuntime } from "../adk/mpaCronTasks";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
import "./MpaCronTasks.css";

export function MpaCronTasks({ runtime }: { runtime?: MpaRuntime }) {
  const { t } = useTranslation("cronjobs");
  return runtime ? <RuntimeTasks key={`${runtime.region}:${runtime.runtimeId}`} runtime={runtime} />
    : <p role="status">{t("mpa.selectRuntime")}</p>;
}

function RuntimeTasks({ runtime }: { runtime: MpaRuntime }) {
  const { t } = useTranslation("cronjobs");
  const [draftJwt, setDraftJwt] = useState("");
  const [jwt, setJwt] = useState("");
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [page, setPage] = useState<MpaCronTaskPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setError("");
    void listMpaCronTasks(runtime, offset, jwt, controller.signal).then(result => {
      if (!controller.signal.aborted) setPage(result);
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "network");
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [runtime.runtimeId, runtime.region, offset, jwt, refresh]);
  const errorKey = error === "MPA_HTTP_401" ? "mpa.authRequired"
    : error === "MPA_HTTP_403" ? "mpa.forbidden"
      : error === "MPA_HTTP_404" ? "mpa.unsupported"
        : error === "MPA_INVALID_RESPONSE" ? "mpa.invalidResponse" : "mpa.loadFailed";
  function move(next: number) { setPage(null); setOffset(next); }
  return <section className="mpa-cron" aria-label={t("mpa.title")}>
    <div className="mpa-cron-target"><strong>{runtime.name}</strong><span>{runtime.runtimeId} · {runtime.region}</span></div>
    <p>{t("mpa.scope")}</p>
    <form className="mpa-cron-auth" onSubmit={event => {
      event.preventDefault(); setPage(null); setOffset(0); setJwt(draftJwt); setRefresh(value => value + 1);
    }}>
      <label>{t("mpa.jwt")}<input type="password" autoComplete="off" value={draftJwt}
        onChange={event => setDraftJwt(event.target.value)} aria-describedby="mpa-jwt-help" /></label>
      <button className="cw-btn cw-btn-soft" type="submit" disabled={loading}>{t("mpa.apply")}</button>
      <button className="cw-btn cw-btn-ghost" type="button" disabled={loading} onClick={() => setRefresh(value => value + 1)}>{t("mpa.refresh")}</button>
    </form>
    <p id="mpa-jwt-help">{t("mpa.jwtHelp")}</p>
    {error && <p className="mpa-cron-error" role="alert">{t(errorKey)}</p>}
    {loading && <div role="status"><TextShimmer>{t("mpa.loading")}</TextShimmer></div>}
    {!loading && !error && page?.items.length === 0 && <p role="status">{t("mpa.empty")}</p>}
    {page && page.items.length > 0 && <div className="mpa-cron-table" tabIndex={0} role="region" aria-label={t("mpa.title")}>
      <table><thead><tr>{["name", "enabled", "schedule", "next", "last"].map(field => <th key={field} scope="col">{t(`mpa.columns.${field}`)}</th>)}</tr></thead>
        <tbody>{page.items.map(task => <tr key={task.id}>
          <th scope="row"><span>{task.name}</span><small>{task.id}</small></th>
          <td>{t(task.enabled ? "status.enabled" : "status.paused")}</td>
          <td><details><summary>{t(`mpa.schedule.${task.schedule.type}`, {defaultValue: task.schedule.type})}</summary><pre>{JSON.stringify(task.schedule, null, 2)}</pre></details></td>
          <td>{task.nextRunAt || "—"}</td><td>{task.lastRunStatus || "—"}</td>
        </tr>)}</tbody></table>
    </div>}
    {page && <nav className="mpa-cron-pages" aria-label={t("mpa.pagination")}>
      <span>{t("mpa.total", {total: page.total})}</span>
      <button className="cw-btn cw-btn-ghost" disabled={loading || offset === 0} onClick={() => move(Math.max(0, offset - 20))}>{t("mpa.previous")}</button>
      <button className="cw-btn cw-btn-ghost" disabled={loading || !page.hasMore} onClick={() => move(page.nextOffset!)}>{t("mpa.next")}</button>
    </nav>}
  </section>;
}
