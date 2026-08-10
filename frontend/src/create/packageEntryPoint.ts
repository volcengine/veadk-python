import type { ProjectFile } from "./project";

const CONVENTIONAL_ENTRY_POINTS = [
  "app.py",
  "agentkit_app.py",
  "main.py",
] as const;
const MIGRATION_MANIFEST_PATH = "migration-result.json";

export type PackageEntryPointSource =
  | "manifest"
  | "convention"
  | "single"
  | "ambiguous";

export interface PackageEntryPointResolution {
  entryPoint: string | null;
  source: PackageEntryPointSource;
}

function isSafePythonPath(path: string): boolean {
  if (
    !path ||
    path.startsWith("/") ||
    path.includes("\\") ||
    path.includes("\0") ||
    [...path].some((character) => {
      const code = character.charCodeAt(0);
      return code < 32 || code === 127;
    }) ||
    !path.endsWith(".py")
  ) {
    return false;
  }
  const parts = path.split("/");
  return (
    parts[parts.length - 1] !== "__init__.py" &&
    parts.every((part) => part && part !== "." && part !== "..")
  );
}

export function listPackageEntryPoints(files: ProjectFile[]): string[] {
  const paths = new Set(
    files
      .map((file) => file.path)
      .filter(
        (path) =>
          isSafePythonPath(path),
      ),
  );
  return [...paths].sort((left, right) => {
    const leftRank = CONVENTIONAL_ENTRY_POINTS.indexOf(
      left as (typeof CONVENTIONAL_ENTRY_POINTS)[number],
    );
    const rightRank = CONVENTIONAL_ENTRY_POINTS.indexOf(
      right as (typeof CONVENTIONAL_ENTRY_POINTS)[number],
    );
    if (leftRank >= 0 || rightRank >= 0) {
      if (leftRank < 0) return 1;
      if (rightRank < 0) return -1;
      return leftRank - rightRank;
    }
    return left < right ? -1 : left > right ? 1 : 0;
  });
}

function migrationManifestEntryPoint(
  files: ProjectFile[],
  candidates: string[],
): string | null {
  const manifest = files.find((file) => file.path === MIGRATION_MANIFEST_PATH);
  if (!manifest) return null;

  let parsed: unknown;
  try {
    parsed = JSON.parse(manifest.content);
  } catch {
    throw new Error("migration-result.json 不是有效的 JSON。");
  }
  if (
    !parsed ||
    typeof parsed !== "object" ||
    !("entrypoint" in parsed) ||
    typeof parsed.entrypoint !== "string"
  ) {
    throw new Error("migration-result.json 必须声明字符串类型的 entrypoint。");
  }
  const entryPoint = parsed.entrypoint.trim();
  if (!isSafePythonPath(entryPoint)) {
    throw new Error("manifest 中的 entrypoint 不是安全的 Python 相对路径。");
  }
  if (!candidates.includes(entryPoint)) {
    throw new Error(`manifest 指定的启动入口不存在：${entryPoint}`);
  }
  return entryPoint;
}

export function resolvePackageEntryPoint(
  files: ProjectFile[],
): PackageEntryPointResolution {
  const candidates = listPackageEntryPoints(files);
  if (candidates.length === 0) {
    throw new Error("代码包至少包含一个可执行的 Python 文件。");
  }

  const manifestEntryPoint = migrationManifestEntryPoint(files, candidates);
  if (manifestEntryPoint) {
    return { entryPoint: manifestEntryPoint, source: "manifest" };
  }
  const conventionalEntryPoint = CONVENTIONAL_ENTRY_POINTS.find((path) =>
    candidates.includes(path),
  );
  if (conventionalEntryPoint) {
    return { entryPoint: conventionalEntryPoint, source: "convention" };
  }
  if (candidates.length === 1) {
    return { entryPoint: candidates[0], source: "single" };
  }
  return { entryPoint: null, source: "ambiguous" };
}
