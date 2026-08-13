export type ComparisonSessionStatus =
  | "not_started"
  | "ready"
  | "stale"
  | "starting"
  | "failed";

export interface ComparisonSessionFailure {
  variantId: string;
  variantName: string;
  stage: "run" | "session";
  message: string;
}

export interface ComparisonSessionState {
  configurationRevision: number;
  activeSessionRevision: number | null;
  pendingSessionRevision: number | null;
  failure: ComparisonSessionFailure | null;
}

export function createComparisonSessionState(): ComparisonSessionState {
  return {
    configurationRevision: 0,
    activeSessionRevision: null,
    pendingSessionRevision: null,
    failure: null,
  };
}

export function comparisonSessionStatus(
  state: ComparisonSessionState,
): ComparisonSessionStatus {
  if (state.pendingSessionRevision !== null) return "starting";
  if (state.failure) return "failed";
  if (state.activeSessionRevision === null) return "not_started";
  if (state.activeSessionRevision !== state.configurationRevision) return "stale";
  return "ready";
}

export function markComparisonConfigurationChanged(
  state: ComparisonSessionState,
  changed: boolean,
): ComparisonSessionState {
  if (!changed) return state;
  const clearsPendingAttempt =
    state.pendingSessionRevision === state.configurationRevision;
  return {
    ...state,
    configurationRevision: state.configurationRevision + 1,
    pendingSessionRevision: clearsPendingAttempt
      ? null
      : state.pendingSessionRevision,
    failure: null,
  };
}

export function beginComparisonSession(
  state: ComparisonSessionState,
): ComparisonSessionState {
  return {
    ...state,
    pendingSessionRevision: state.configurationRevision,
    failure: null,
  };
}

export function completeComparisonSession(
  state: ComparisonSessionState,
  revision: number,
): ComparisonSessionState {
  if (state.pendingSessionRevision !== revision) return state;
  return {
    ...state,
    activeSessionRevision: revision,
    pendingSessionRevision: null,
    failure: null,
  };
}

export function failComparisonSession(
  state: ComparisonSessionState,
  revision: number,
  failure: ComparisonSessionFailure,
): ComparisonSessionState {
  if (state.pendingSessionRevision !== revision) return state;
  return {
    ...state,
    pendingSessionRevision: null,
    failure,
  };
}

export function resetComparisonSessionState(): ComparisonSessionState {
  return createComparisonSessionState();
}
