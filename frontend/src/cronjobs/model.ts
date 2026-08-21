import type {
  CronJob,
  CronJobRun,
  CronJobRunStatus,
  CronJobSchedule,
} from "../adk/client";

export const CRONJOB_STATUS_LABELS: Record<CronJobRunStatus, string> = {
  queued: "已排队",
  pending: "准备中",
  running: "执行中",
  retrying: "自动重试中",
  success: "成功",
  failed: "失败",
  cancelled: "已取消",
  skipped: "已跳过",
};

export const WEEKDAY_LABELS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

export function formatCronJobDate(value?: string): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
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
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} 分 ${seconds % 60} 秒`;
}

export function describeCronJobSchedule(schedule: CronJobSchedule): string {
  const zone = schedule.timezone ? ` · ${schedule.timezone}` : "";
  if (schedule.type === "once") {
    return `一次 · ${formatCronJobDate(schedule.onceAt)}${zone}`;
  }
  if (schedule.type === "daily") return `每天 ${schedule.time ?? "-"}${zone}`;
  if (schedule.type === "weekly") {
    return `${WEEKDAY_LABELS[schedule.weekday ?? 1]} ${schedule.time ?? "-"}${zone}`;
  }
  return `Cron ${schedule.cron ?? "-"}${zone}`;
}

export function cronJobIsRunning(job: CronJob): boolean {
  return job.latestRun?.status === "queued" || job.latestRun?.status === "running" || job.latestRun?.status === "retrying" || job.latestRun?.status === "pending";
}
