interface SessionCapabilitySummary {
  tools: Array<{ custom: boolean }>;
  skills: Array<{ custom: boolean }>;
}

/** Use the capability-aware runner only when this session adds an overlay. */
export function requiresSessionCapabilityRunner(
  capabilities: SessionCapabilitySummary | null,
): boolean {
  return Boolean(
    capabilities &&
      [...capabilities.tools, ...capabilities.skills].some((item) => item.custom),
  );
}
