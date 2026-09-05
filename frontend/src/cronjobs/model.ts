import type {
  CronJob,
  CronJobRun,
  CronJobRunStatus,
  CronJobSchedule,
} from "../adk/client";
import { i18n } from "../i18n";

export const CRONJOB_STATUS_LABEL_KEYS: Record<CronJobRunStatus, string> = {
  queued: "status.queued",
  pending: "status.pending",
  running: "status.running",
  retrying: "status.retrying",
  success: "status.success",
  failed: "status.failed",
  cancelled: "status.cancelled",
  skipped: "status.skipped",
};

export const WEEKDAY_KEYS = [
  "weekdays.sunday",
  "weekdays.monday",
  "weekdays.tuesday",
  "weekdays.wednesday",
  "weekdays.thursday",
  "weekdays.friday",
  "weekdays.saturday",
] as const;

export function formatCronJobDate(value?: string): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(i18n.resolvedLanguage, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date).replace(/\//g, "-");
}

export function formatCronJobDuration(run: CronJobRun): string {
  if (!run.startedAt) return "-";
  const start = Date.parse(run.startedAt);
  const end = run.finishedAt ? Date.parse(run.finishedAt) : Date.now();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "-";
  const seconds = Math.max(1, Math.round((end - start) / 1000));
  if (seconds < 60) return i18n.t("cronjobs:duration.seconds", { count: seconds });
  const minutes = Math.floor(seconds / 60);
  return i18n.t("cronjobs:duration.minutesSeconds", {
    minutes,
    seconds: seconds % 60,
  });
}

export function describeCronJobSchedule(schedule: CronJobSchedule): string {
  const zone = schedule.timezone ? ` · ${schedule.timezone}` : "";
  if (schedule.type === "once") {
    return i18n.t("cronjobs:schedule.once", {
      date: formatCronJobDate(schedule.onceAt),
      zone,
    });
  }
  if (schedule.type === "daily") {
    return i18n.t("cronjobs:schedule.daily", { time: schedule.time ?? "-", zone });
  }
  if (schedule.type === "weekly") {
    return i18n.t("cronjobs:schedule.weekly", {
      weekday: i18n.t(`cronjobs:${WEEKDAY_KEYS[schedule.weekday ?? 1]}`),
      time: schedule.time ?? "-",
      zone,
    });
  }
  return i18n.t("cronjobs:schedule.cron", { cron: schedule.cron ?? "-", zone });
}

export function cronJobIsRunning(job: CronJob): boolean {
  return job.latestRun?.status === "queued" || job.latestRun?.status === "running" || job.latestRun?.status === "retrying" || job.latestRun?.status === "pending";
}
