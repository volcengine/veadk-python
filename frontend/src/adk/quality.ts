import { getAgentInfo, getRuntimeAgentInfo, getEnvironmentManifest, studioFetch, type AgentInfo } from "./client";
import { getSkillDetail } from "../create/skills/skillspace";
import { buildQualityAgentContext, qualityEnvironmentContext, type QualityAgentContext } from "./qualityContext";
export type { QualityAgentContext } from "./qualityContext";
import type { AgentDraft } from "../create/types";

export type EvaluationPreference = "trajectory" | "outcome" | "balanced";
export interface EvaluationBrief {
  preference: EvaluationPreference;
  scenario: string;
  requirements: string;
}
export interface EvaluationPreferences {
  name: string;
  goal: string;
  scenarios: string;
  successCriteria: string;
  unacceptableErrors: string;
  preference: EvaluationPreference;
}
export type PreferenceSuggestionField = "goal" | "scenarios" | "successCriteria" | "unacceptableErrors"
  | "datasetScenarios" | "datasetRequirements" | "overallFocus" | "toolsFocus" | "skillsFocus" | "criteria";
export interface PreferenceSuggestion {
  label: string;
  text: string;
}
export type PreferenceSuggestions = Record<PreferenceSuggestionField, PreferenceSuggestion[]>;
export interface DatasetPreferences extends EvaluationBrief {
  count: number;
}
export interface EvaluatorPreferences {
  overallFocus: string;
  toolsFocus: string;
  skillsFocus: string;
  criteria: string;
  strictness: "lenient" | "balanced" | "strict";
}
export interface ComponentPreferences {
  dataset: DatasetPreferences;
  evaluators: EvaluatorPreferences;
}
export interface ComponentSuggestionPreferences {
  overallPreferences: EvaluationPreferences;
  componentPreferences: ComponentPreferences;
}
interface ComponentGenerationPreferences {
  overallPreferences?: EvaluationPreferences;
  componentPreferences?: ComponentPreferences;
}
export interface EvaluationItem {
  name: string;
  scenario: string;
  input: string;
  expectedOutput: string;
  trajectory: string[];
  checks: string[];
}
export interface GeneratedDataset {
  name: string;
  description: string;
  items: EvaluationItem[];
}
export interface EvaluationDimension {
  name: string;
  description: string;
  basis: string;
  minScore: number;
  maxScore: number;
  rationale: string;
}
export interface EvaluatorDefinition {
  name: string;
  description: string;
  dimensions: EvaluationDimension[];
  prompt: string;
}
export interface GeneratedEvaluators {
  overall: EvaluatorDefinition;
  tools: EvaluatorDefinition;
  skills: EvaluatorDefinition;
}
export interface QualityAgentSource {
  runtimeId?: string;
  region?: string;
  appName?: string;
  info: AgentInfo | null | undefined;
  infoLoading?: boolean;
  draft?: AgentDraft;
}
export async function loadQualityAgentContext(source: QualityAgentSource, signal: AbortSignal): Promise<QualityAgentContext> {
  const info = source.runtimeId
    ? source.info ?? await getRuntimeAgentInfo(source.runtimeId, source.region || "", source.appName || "")
    : source.info && source.appName && !source.info.draft
      ? await getAgentInfo(source.appName, { loadDraft: true })
      : source.info;
  signal.throwIfAborted();
  const draft = info
    ? info.draft ?? (!source.runtimeId && source.draft && [info.name, info.graph?.id].includes(source.draft.name) ? source.draft : undefined)
    : source.draft;
  const { context, skillReferences } = buildQualityAgentContext(info, draft);
  const environments = new Map([context, ...context.subAgentDetails].flatMap(node => node.environment ? [[`${node.environment.id}/${node.environment.version}`, node.environment] as const] : []));
  const reads = [
    ...[...environments.values()].map(reference => async () => {
      try {
        const manifest = await getEnvironmentManifest(reference.id, reference.version, signal);
        signal.throwIfAborted();
        context.environments.push(qualityEnvironmentContext(reference, manifest));
      } catch (error) {
        if (signal.aborted) throw error;
        context.contextNotes.push(`environment ${reference.id}/${reference.version}: its manifest could not be read; installed capabilities and Skills are unknown`);
      }
    }),
    ...skillReferences.map(({ target, selected }) => async () => {
      try {
        const detail = await getSkillDetail(selected.skillSpaceId!, selected.skillId!, selected.version, selected.skillSpaceRegion, undefined, undefined, undefined, signal);
        signal.throwIfAborted();
        target.instructions = detail.skillMd.slice(0, 30000);
        if (!target.description) target.description = detail.description.slice(0, 3000);
        if (detail.skillMd.length > 30000) context.contextNotes.push(`Skill ${target.name}: instructions truncated at 30000 characters`);
      } catch (error) {
        if (signal.aborted) throw error;
        context.contextNotes.push(`Skill ${target.name}: the configured version's instructions could not be read; use only the supplied name and description`);
      }
    }),
  ];
  // Bound parallel metadata reads without making one request for every unrelated resource.
  for (let index = 0; index < reads.length; index += 4) {
    signal.throwIfAborted();
    await Promise.all(reads.slice(index, index + 4).map(read => read()));
  }
  signal.throwIfAborted();
  return context;
}

export class QualityRequestError extends Error {
  constructor(readonly code: "timeout" | "unauthorized" | "failed", readonly diagnostics = "") { super(code); }
}

interface QualityRequest {
  agent: QualityAgentContext;
  runtimeId: string;
  region: string;
  language: "zh-CN" | "en-US";
}

async function requestQuality<T>(operation: string, body: QualityRequest, signal: AbortSignal, timeoutMs = 190000): Promise<T> {
  const response = await studioFetch(`/web/quality/${operation}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  }, timeoutMs);
  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const detail = payload && typeof payload === "object" && "detail" in payload ? payload.detail : null;
    const diagnostics = detail && typeof detail === "object" && "diagnostics" in detail && typeof detail.diagnostics === "string" ? detail.diagnostics : "";
    throw new QualityRequestError(response.status === 504 ? "timeout" : [401, 403, 404].includes(response.status) ? "unauthorized" : "failed", diagnostics);
  }
  return response.json() as Promise<T>;
}

export function autofillQualityBrief(body: QualityRequest, signal: AbortSignal) {
  return requestQuality<EvaluationBrief>("autofill", body, signal);
}

export function generateQualityDataset(body: QualityRequest & EvaluationBrief & { count: number } & ComponentGenerationPreferences, signal: AbortSignal) {
  const timeoutMs = Math.ceil(Math.ceil(body.count / 20) / 4) * 180000 + 40000;
  return requestQuality<GeneratedDataset>("generate", body, signal, timeoutMs);
}

export function generateQualityEvaluators(body: QualityRequest & ComponentGenerationPreferences, signal: AbortSignal) {
  return requestQuality<GeneratedEvaluators>("evaluators", body, signal);
}

export function generateQualityPreferences(body: QualityRequest & { overallPreferences: EvaluationPreferences }, signal: AbortSignal) {
  return requestQuality<ComponentPreferences>("preferences", body, signal);
}

export function suggestQualityPreferences(body: QualityRequest & { field: PreferenceSuggestionField } & Partial<ComponentSuggestionPreferences>, signal: AbortSignal) {
  return requestQuality<{ suggestions: PreferenceSuggestion[] }>("preference-suggestions", body, signal);
}
