export function sandboxCreateErrorKind(error: unknown): string {
  if ((error as Error | undefined)?.name === "AbortError") return "abort";
  if (error instanceof Error && error.name && error.name !== "Error") {
    return error.name;
  }
  return "unknown";
}

export function agentDebugErrorKind(error: unknown): string {
  if ((error as Error | undefined)?.name === "AbortError") return "abort";
  if (error instanceof Error && error.name && error.name !== "Error") {
    return error.name;
  }
  return "unknown";
}

export function agentConnectErrorKind(error: unknown): string {
  if ((error as Error | undefined)?.name === "AbortError") return "abort";
  if (error instanceof Error && error.name && error.name !== "Error") {
    return error.name;
  }
  return "unknown";
}

export function agentMessageErrorKind(error: unknown): string {
  if ((error as Error | undefined)?.name === "AbortError") return "abort";
  if (error instanceof Error && error.name && error.name !== "Error") {
    return error.name;
  }
  return "unknown";
}

export function agentSourceDownloadErrorKind(error: unknown): string {
  if ((error as Error | undefined)?.name === "AbortError") return "abort";
  if (error instanceof Error && error.name && error.name !== "Error") {
    return error.name;
  }
  return "unknown";
}

export function agentDeployErrorKind(error: unknown, phase: string): string {
  if (phase === "build") return "build_failed";
  if ((error as Error | undefined)?.name === "RuntimeProbeError") {
    return "runtime_probe_error";
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return "abort";
  }
  if (error instanceof Error && error.name && error.name !== "Error") {
    return error.name;
  }
  return "unknown";
}

export function telemetryErrorSummary(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error);
  return raw
    .replace(
      /\b((?:app[_-]?)?secret|token|api[_-]?key|password)\b\s*[:=]\s*["']?[^"',\s}]+/gi,
      "$1=<redacted>",
    )
    .slice(0, 300);
}
