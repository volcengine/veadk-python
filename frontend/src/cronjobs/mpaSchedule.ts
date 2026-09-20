import type { MpaCronTask } from "../adk/mpaCronTasks";

export const scheduleTypes = [
  "Once",
  "Interval",
  "Daily",
  "Weekly",
  "Monthly",
  "Cron",
] as const;
export const runStatuses = [
  "Queued",
  "Running",
  "Succeeded",
  "Failed",
  "TimedOut",
  "Cancelled",
  "Skipped",
] as const;
export function taskStatus(task: MpaCronTask): string {
  return task.runningAt ? "Running" : task.lastRunStatus || "Pending";
}
export function formatTime(
  value: unknown,
  locale: string,
  zone?: string,
): string {
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value)))
    return "—";
  return new Intl.DateTimeFormat(locale, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: zone,
  }).format(new Date(value));
}
export function scheduleText(
  task: MpaCronTask,
  label: (key: string) => string,
  locale: string,
): string {
  const s = task.schedule;
  const zone = typeof s.timezone === "string" ? s.timezone : "Asia/Shanghai";
  const type = s.type;
  const value =
    type === "Once"
      ? formatTime(s.runAt, locale, zone)
      : type === "Interval"
        ? `${s.intervalSeconds} ${label("seconds")}`
        : type === "Cron"
          ? String(s.cronExpression)
          : `${s.time}${type === "Weekly" ? ` · ${String(s.weekdays)}` : type === "Monthly" ? ` · ${String(s.monthDays)}` : ""}`;
  return `${label(type)} · ${value} (${zone})`;
}
export function monthDays(month: Date): Date[] {
  const start = new Date(month.getFullYear(), month.getMonth(), 1);
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
  return Array.from(
    { length: 42 },
    (_, i) =>
      new Date(start.getFullYear(), start.getMonth(), start.getDate() + i),
  );
}
const parts = (date: Date, zone: string) =>
  Object.fromEntries(
    new Intl.DateTimeFormat("en-US", {
      timeZone: zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(date)
      .map((p) => [p.type, p.value]),
  );
// Convert wall time using candidate offsets on both sides of a possible DST transition.
function wallTimes(
  y: number,
  m: number,
  d: number,
  h: number,
  min: number,
  zone: string,
): number[] {
  const wall = Date.UTC(y, m - 1, d, h, min);
  const candidates = new Set<number>();
  for (const delta of [-86400000, 0, 86400000]) {
    const base = wall + delta;
    const p = parts(new Date(base), zone);
    const offset =
      Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute) - base;
    const at = wall - offset;
    const actual = parts(new Date(at), zone);
    if (
      +actual.year === y &&
      +actual.month === m &&
      +actual.day === d &&
      +actual.hour === h &&
      +actual.minute === min
    )
      candidates.add(at);
  }
  return [...candidates];
}
export function calendarTimes(
  task: MpaCronTask,
  day: Date,
): { at: number; count: number; nextOnly: boolean } | null {
  const start = day.getTime();
  const end = new Date(
    day.getFullYear(),
    day.getMonth(),
    day.getDate() + 1,
  ).getTime();
  const s = task.schedule;
  const zone = String(s.timezone || "Asia/Shanghai");
  const created = Date.parse(task.createdAt || "") || -Infinity;
  const within = (at: number) => at >= Math.max(start, created) && at < end;
  if (s.type === "Once") {
    const at = Date.parse(String(s.runAt));
    return within(at) ? { at, count: 1, nextOnly: false } : null;
  }
  if (!task.enabled) return null;
  if (s.type === "Interval") {
    const anchor = Date.parse(String(s.anchorAt || task.nextRunAt));
    const step = Number(s.intervalSeconds) * 1000;
    if (!Number.isFinite(anchor) || !Number.isFinite(step) || step < 30000)
      return null;
    const at =
      anchor +
      Math.max(0, Math.ceil((Math.max(start, created) - anchor) / step)) * step;
    return within(at)
      ? { at, count: Math.ceil((end - at) / step), nextOnly: false }
      : null;
  }
  let time = String(s.time);
  let weekdays = s.weekdays as number[] | undefined;
  let dates = s.monthDays as number[] | undefined;
  if (s.type === "Cron") {
    const f = String(s.cronExpression).trim().split(/\s+/);
    if (
      f.length !== 5 ||
      !/^\d+$/.test(f[0]) ||
      +f[0] > 59 ||
      !/^\d+$/.test(f[1]) ||
      +f[1] > 23 ||
      f[3] !== "*" ||
      !/^(\*|\d+(,\d+)*)$/.test(f[2]) ||
      !/^(\*|\d+(,\d+)*)$/.test(f[4]) ||
      (f[2] !== "*" && f[4] !== "*")
    ) {
      const at = Date.parse(task.nextRunAt || "");
      return within(at) ? { at, count: 1, nextOnly: true } : null;
    }
    time = `${f[1]}:${f[0]}`;
    dates = f[2] === "*" ? undefined : f[2].split(",").map(Number);
    weekdays =
      f[4] === "*"
        ? undefined
        : f[4].split(",").map((n) => (+n === 0 ? 7 : +n));
  }
  const [h, min] = time.split(":").map(Number);
  if (!Number.isFinite(h) || !Number.isFinite(min)) return null;
  const found: number[] = [];
  for (let delta = -1; delta <= 1; delta++) {
    const p = parts(new Date(start + delta * 86400000), zone);
    const y = +p.year,
      m = +p.month,
      d = +p.day;
    const weekday = new Date(Date.UTC(y, m - 1, d)).getUTCDay() || 7;
    if (
      (weekdays && !weekdays.includes(weekday)) ||
      (dates && !dates.includes(d))
    )
      continue;
    found.push(...wallTimes(y, m, d, h, min, zone).filter(within));
  }
  const unique = [...new Set(found)].sort((a, b) => a - b);
  return unique.length
    ? { at: unique[0], count: unique.length, nextOnly: false }
    : null;
}
