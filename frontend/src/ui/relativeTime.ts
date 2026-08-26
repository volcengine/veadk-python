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
): string {
  if (value === undefined || value === "") return "—";
  const timestamp = timestampFrom(value);
  if (!Number.isFinite(timestamp)) return "—";

  const elapsedSeconds = Math.floor(Math.max(0, nowMs - timestamp) / 1000);
  if (elapsedSeconds < 60) return `${elapsedSeconds} 秒前`;
  const elapsedMinutes = Math.floor(elapsedSeconds / 60);
  if (elapsedMinutes < 60) return `${elapsedMinutes} 分钟前`;
  const elapsedHours = Math.floor(elapsedMinutes / 60);
  if (elapsedHours < 24) return `${elapsedHours} 小时前`;
  const elapsedDays = Math.floor(elapsedHours / 24);
  if (elapsedDays < 30) return `${elapsedDays} 天前`;
  const elapsedMonths = Math.floor(elapsedDays / 30);
  if (elapsedMonths < 12) return `${elapsedMonths} 个月前`;
  return `${Math.floor(elapsedMonths / 12)} 年前`;
}
