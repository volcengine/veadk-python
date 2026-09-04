import { workspaceToolsT } from "./workspaceToolsI18n";

export function formatResourceSource(
  value: string | null | undefined,
): string {
  return value?.trim() || workspaceToolsT("resourceMetadata.unknownSource");
}

export function formatResourceCreator(
  value: string | null | undefined,
): string {
  return value?.trim() || workspaceToolsT("resourceMetadata.unknownCreator");
}
