export const UNKNOWN_RESOURCE_SOURCE = "未知来源";
export const UNKNOWN_RESOURCE_CREATOR = "未知创建者";

export function formatResourceSource(
  value: string | null | undefined,
): string {
  return value?.trim() || UNKNOWN_RESOURCE_SOURCE;
}

export function formatResourceCreator(
  value: string | null | undefined,
): string {
  return value?.trim() || UNKNOWN_RESOURCE_CREATOR;
}
