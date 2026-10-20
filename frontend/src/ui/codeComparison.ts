import type { ProjectFile } from "../create/project";
import { workspaceToolsT } from "./workspaceToolsI18n";

export type CodeChangeStatus = "added" | "modified" | "deleted";

export interface CodeFileChange {
  path: string;
  status: CodeChangeStatus;
  before: string;
  after: string;
}

export function compareProjectFiles(
  baseFiles: ProjectFile[],
  targetFiles: ProjectFile[],
): CodeFileChange[] {
  const baseByPath = new Map(baseFiles.map((file) => [file.path, file.content]));
  const targetByPath = new Map(targetFiles.map((file) => [file.path, file.content]));
  const paths = new Set([...baseByPath.keys(), ...targetByPath.keys()]);
  const changes: CodeFileChange[] = [];

  for (const path of [...paths].sort((left, right) => left.localeCompare(right))) {
    const before = baseByPath.get(path);
    const after = targetByPath.get(path);
    if (before === after) continue;
    changes.push({
      path,
      status: before === undefined ? "added" : after === undefined ? "deleted" : "modified",
      before: before ?? "",
      after: after ?? "",
    });
  }
  return changes;
}

export function codeChangeLabel(status: CodeChangeStatus): string {
  return workspaceToolsT(`codeBrowser.change.${status}`);
}
