const RUNTIME_NAME_PATTERN = /^[A-Za-z0-9_-]+$/;
const RUNTIME_NAME_MIN_LENGTH = 4;
const RUNTIME_NAME_MAX_LENGTH = 64;
const RUNTIME_NAME_SUFFIX_LENGTH = 6;
const DEFAULT_RUNTIME_NAME = "agent-runtime";

/** Convert a root Agent name into a CreateRuntime-compatible default name. */
export function normalizeRuntimeName(rootAgentName: string): string {
  const trimmed = rootAgentName.trim();
  if (!trimmed) return DEFAULT_RUNTIME_NAME;

  let normalized = trimmed
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, RUNTIME_NAME_MAX_LENGTH);

  if (!normalized) return DEFAULT_RUNTIME_NAME;

  if (normalized.length < RUNTIME_NAME_MIN_LENGTH) {
    normalized = `${normalized}-rt`.slice(0, RUNTIME_NAME_MAX_LENGTH);
  }
  return normalized;
}

/** Add a short token while preserving the CreateRuntime length contract. */
export function runtimeNameWithSuffix(
  rootAgentName: string,
  suffix: string,
): string {
  const normalizedSuffix = suffix
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "")
    .slice(0, RUNTIME_NAME_SUFFIX_LENGTH)
    .padEnd(RUNTIME_NAME_SUFFIX_LENGTH, "0");
  const maxBaseLength = RUNTIME_NAME_MAX_LENGTH - normalizedSuffix.length - 1;
  const base = normalizeRuntimeName(rootAgentName)
    .slice(0, maxBaseLength)
    .replace(/[-_]+$/g, "") || "agent";
  return `${base}-${normalizedSuffix}`;
}

/** Generate a low-collision default for one new Runtime deployment. */
export function generateRuntimeName(
  rootAgentName: string,
  random: () => number = Math.random,
): string {
  const value = Math.min(Math.max(random(), 0), 1 - Number.EPSILON);
  const suffix = Math.floor(value * 36 ** RUNTIME_NAME_SUFFIX_LENGTH)
    .toString(36)
    .padStart(RUNTIME_NAME_SUFFIX_LENGTH, "0");
  return runtimeNameWithSuffix(rootAgentName, suffix);
}

/** Resolve the editable Runtime name while preserving older explicit drafts. */
export function resolveRuntimeName(
  rootAgentName: string,
  configuredName?: string,
  customized?: boolean,
): string {
  const usesConfiguredName = customized ?? Boolean(configuredName?.trim());
  return usesConfiguredName ? (configuredName ?? "") : normalizeRuntimeName(rootAgentName);
}

/** Return the CreateRuntime name validation error, or null when valid. */
export function runtimeNameProblem(name: string): string | null {
  if (!name) return "Runtime 名称为必填项";
  if (!RUNTIME_NAME_PATTERN.test(name)) {
    return "Runtime 名称只能包含英文字母、数字、下划线和连字符";
  }
  if (
    name.length < RUNTIME_NAME_MIN_LENGTH ||
    name.length > RUNTIME_NAME_MAX_LENGTH
  ) {
    return "Runtime 名称长度须为 4-64 个字符";
  }
  return null;
}
