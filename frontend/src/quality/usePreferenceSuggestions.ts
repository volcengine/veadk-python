import { useEffect, useMemo, useRef, useState } from "react";
import { loadQualityAgentContext, QualityRequestError, suggestQualityPreferences, type ComponentSuggestionPreferences, type PreferenceSuggestion, type PreferenceSuggestionField, type PreferenceSuggestions, type QualityAgentContext, type QualityAgentSource } from "../adk/quality";

const OVERALL_FIELDS: PreferenceSuggestionField[] = ["goal", "scenarios", "successCriteria", "unacceptableErrors"];
const COMPONENT_FIELDS: PreferenceSuggestionField[] = ["datasetScenarios", "datasetRequirements", "overallFocus", "toolsFocus", "skillsFocus", "criteria"];
interface FieldState {
  data: PreferenceSuggestion[] | null;
  loading: boolean;
  error: { code: string; diagnostics: string } | null;
}

function mapFields(create: (field: PreferenceSuggestionField) => FieldState) {
  return {
    goal: create("goal"), scenarios: create("scenarios"), successCriteria: create("successCriteria"), unacceptableErrors: create("unacceptableErrors"),
    datasetScenarios: create("datasetScenarios"), datasetRequirements: create("datasetRequirements"), overallFocus: create("overallFocus"),
    toolsFocus: create("toolsFocus"), skillsFocus: create("skillsFocus"), criteria: create("criteria"),
  };
}

function describeError(cause: unknown) {
  return cause instanceof QualityRequestError ? { code: cause.code, diagnostics: cause.diagnostics } : { code: "failed", diagnostics: "" };
}

function prepareAgentContext(source: QualityAgentSource) {
  let request: { controller: AbortController; promise: Promise<QualityAgentContext> } | null = null;
  return {
    load() {
      if (!request) {
        const controller = new AbortController();
        const promise = loadQualityAgentContext(source, controller.signal);
        request = { controller, promise };
        void promise.catch(() => { if (request?.promise === promise) request = null; });
      }
      return request.promise;
    },
    cancel() {
      request?.controller.abort();
      request = null;
    },
  };
}

export function usePreferenceSuggestions(source: QualityAgentSource, language: "zh-CN" | "en-US", enabled: boolean, preferences?: ComponentSuggestionPreferences) {
  const { runtimeId, region, appName, info, infoLoading = false } = source;
  // Published metadata owns the runtime context; editor recovery must not restart generation.
  const draft = runtimeId ? undefined : source.draft;
  const agentSource = useMemo(() => ({ runtimeId, region, appName, info, draft }), [runtimeId, region, appName, info, draft]);
  const preparation = useMemo(() => prepareAgentContext(agentSource), [agentSource]);
  const signature = useMemo(() => preferences ? JSON.stringify(preferences) : "", [preferences]);
  const context = useMemo(() => ({ source: agentSource, language, preferences, signature }), [agentSource, language, preferences, signature]);
  const scope = preferences ? "components" : "overall";
  const requestedFields = preferences ? COMPONENT_FIELDS : OVERALL_FIELDS;
  type SuggestionCache = { context: typeof context; data: Partial<PreferenceSuggestions> };
  const cache = useRef<Partial<Record<"overall" | "components", SuggestionCache>>>({});
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ context: typeof context | null; fields: Record<PreferenceSuggestionField, FieldState> }>(() => ({
    context: null, fields: mapFields(() => ({ data: null, loading: false, error: null })),
  }));

  useEffect(() => {
    if (infoLoading) return;
    // Prepare mounted resources on entry; foreground requests retry and display any failure.
    void preparation.load().catch(() => {});
    return () => preparation.cancel();
  }, [preparation, infoLoading]);

  useEffect(() => {
    if (!enabled) return;
    const previous = cache.current[scope];
    const current: SuggestionCache = previous?.context.source === context.source && previous.context.language === context.language && previous.context.signature === context.signature
      ? previous : { context, data: {} };
    cache.current[scope] = current;
    const missing = requestedFields.filter(field => !current.data[field]);
    setState({ context, fields: mapFields(field => ({ data: current.data[field] ?? null, loading: missing.includes(field), error: null })) });
    if (infoLoading || !missing.length) return;
    const controller = new AbortController();
    function update(field: PreferenceSuggestionField, value: FieldState) {
      if (controller.signal.aborted) return;
      setState(previous => previous.context === context ? { context, fields: { ...previous.fields, [field]: value } } : previous);
    }
    void (async () => {
      try {
        const agent = await preparation.load();
        controller.signal.throwIfAborted();
        await Promise.all(missing.map(async field => {
          try {
            const result = await suggestQualityPreferences({ agent, field, language: context.language, runtimeId: context.source.runtimeId || "", region: context.source.region || "", ...context.preferences }, controller.signal);
            controller.signal.throwIfAborted();
            current.data[field] = result.suggestions;
            update(field, { data: result.suggestions, loading: false, error: null });
          } catch (cause) {
            update(field, { data: null, loading: false, error: describeError(cause) });
          }
        }));
      } catch (cause) {
        for (const field of missing) update(field, { data: null, loading: false, error: describeError(cause) });
      }
    })();
    return () => controller.abort();
  }, [context, enabled, attempt, infoLoading, preparation, scope, requestedFields]);

  const fields = state.context === context ? state.fields : mapFields(field => ({ data: null, loading: enabled && requestedFields.includes(field), error: null }));
  return {
    fields,
    loading: enabled && requestedFields.some(field => fields[field].loading),
    loadAgent: async (signal: AbortSignal) => {
      signal.throwIfAborted();
      const agent = await preparation.load();
      signal.throwIfAborted();
      return agent;
    },
    // Completed fields and Agent metadata survive retries and modal navigation.
    retry: () => { setAttempt(value => value + 1); },
  };
}
