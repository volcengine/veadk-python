export const UNKNOWN_RESOURCE_SOURCE = "未知来源";

export function formatResourceSource(
  value: string | null | undefined,
): string {
  return value?.trim() || UNKNOWN_RESOURCE_SOURCE;
}
