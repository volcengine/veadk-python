function timestampFrom(value: string | number): number {
  if (typeof value === "number") {
    return value < 1_000_000_000_000 ? value * 1000 : value;
  }

  const trimmed = value.trim();
  const numeric = Number(trimmed);
  if (/^\d+(?:\.\d+)?$/.test(trimmed)) {
    return numeric < 1_000_000_000_000 ? numeric * 1000 : numeric;
  }
  return Date.parse(trimmed);
}

export function formatRelativeTimeLabel(
  value: string | number | undefined,
  nowMs = Date.now(),
  locale = "zh-CN",
): string {
  if (value === undefined || value === "") return "—";
  const timestamp = timestampFrom(value);
  if (!Number.isFinite(timestamp)) return "—";

  const elapsedSeconds = Math.floor(Math.max(0, nowMs - timestamp) / 1000);
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: "always" });
  const relative = (amount: number, unit: Intl.RelativeTimeFormatUnit, zhUnit: string) =>
    locale.toLowerCase().startsWith("zh")
      ? `${amount} ${zhUnit}前`
      : formatter.format(-amount, unit);
  if (elapsedSeconds < 60) return relative(elapsedSeconds, "second", "秒");
  const elapsedMinutes = Math.floor(elapsedSeconds / 60);
  if (elapsedMinutes < 60) return relative(elapsedMinutes, "minute", "分钟");
  const elapsedHours = Math.floor(elapsedMinutes / 60);
  if (elapsedHours < 24) return relative(elapsedHours, "hour", "小时");
  const elapsedDays = Math.floor(elapsedHours / 24);
  if (elapsedDays < 30) return relative(elapsedDays, "day", "天");
  const elapsedMonths = Math.floor(elapsedDays / 30);
  if (elapsedMonths < 12) return relative(elapsedMonths, "month", "个月");
  return relative(Math.floor(elapsedMonths / 12), "year", "年");
}
