export function sandboxCreateErrorKind(error: unknown): string {
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
