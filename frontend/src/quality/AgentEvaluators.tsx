import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  generateQualityEvaluators,
  loadQualityAgentContext,
  QualityRequestError,
  type EvaluatorDefinition,
  type GeneratedEvaluators,
  type QualityAgentSource,
} from "../adk/quality";
import { Button } from "../components/primitives/Button";
import { Dropdown } from "../components/primitives/Dropdown";
import { EmptyState } from "../components/primitives/EmptyState";
import { Skeleton } from "../components/primitives/Skeleton";
import { Select } from "../components/primitives/Select";
import { CardLayout } from "../components/layouts/CardLayout";
import "./AgentEvaluators.css";
import { QualityErrorDetails } from "./QualityErrorDetails";
import { outputState, type QualityPreferenceRecord } from "./preferences";

const EVALUATOR_TYPES = ["overall", "tools", "skills"] as const;

function EvaluatorCard({ evaluator }: { evaluator: EvaluatorDefinition }) {
  const { t } = useTranslation("ui");
  const q = (key: string) => t(`agentWorkspace.qualityManagement.evaluators.${key}`);
  const promptId = useId();
  const [expanded, setExpanded] = useState(false);
  const [expandedDimension, setExpandedDimension] = useState<number | null>(null);
  const preview = evaluator.prompt.length > 220 ? `${evaluator.prompt.slice(0, 220)}…` : evaluator.prompt;

  return (
    <CardLayout title={evaluator.name} icon={null} showClose={false} size="content">
      <div className="agent-evaluators__card-content">
        <p className="agent-evaluators__description">{evaluator.description}</p>
        <div className="agent-evaluators__field">
          <h4>{q("dimensions")}</h4>
          <div className="agent-evaluators__dimensions">
            {evaluator.dimensions.map((dimension, index) => (
              <Dropdown
                key={index}
                label={dimension.name}
                fullWidth
                open={expandedDimension === index}
                onOpenChange={open => setExpandedDimension(open ? index : null)}
              >
                <dl className="agent-evaluators__dimension-details">
                  <div className="agent-evaluators__dimension-text"><dt>{q("dimensionDescription")}</dt><dd>{dimension.description}</dd></div>
                  <div className="agent-evaluators__dimension-text"><dt>{q("dimensionBasis")}</dt><dd>{dimension.basis}</dd></div>
                  <div><dt>{q("minScore")}</dt><dd>{dimension.minScore}</dd></div>
                  <div><dt>{q("maxScore")}</dt><dd>{dimension.maxScore}</dd></div>
                  <div className="agent-evaluators__dimension-text"><dt>{q("dimensionRationale")}</dt><dd>{dimension.rationale}</dd></div>
                </dl>
              </Dropdown>
            ))}
          </div>
        </div>
        <div className="agent-evaluators__field">
          <h4>{q("prompt")}</h4>
          <p id={promptId} className="agent-evaluators__prompt" data-expanded={expanded || undefined} tabIndex={expanded ? 0 : undefined}>
            {expanded ? evaluator.prompt : preview}
          </p>
          {evaluator.prompt.length > 220 && (
            <Button variant="link" size="compact" aria-expanded={expanded} aria-controls={promptId} onClick={() => setExpanded(value => !value)}>
              {q(expanded ? "collapsePrompt" : "expandPrompt")}
            </Button>
          )}
        </div>
      </div>
    </CardLayout>
  );
}

export function AgentEvaluators({ source, records, filter, onFilterChange }: {
  source: QualityAgentSource;
  records: QualityPreferenceRecord[];
  filter: string;
  onFilterChange: (value: string) => void;
}) {
  const { t, i18n } = useTranslation("ui");
  const q = (key: string) => t(`agentWorkspace.qualityManagement.evaluators.${key}`);
  const p = (key: string) => t(`agentWorkspace.qualityManagement.preferenceForm.${key}`);
  const pending = useRef<AbortController | null>(null);
  const [evaluators, setEvaluators] = useState<GeneratedEvaluators | null>(null);
  const [phase, setPhase] = useState<"loadingAgent" | "generating" | null>(null);
  const [error, setError] = useState("");
  const [diagnostics, setDiagnostics] = useState("");

  useEffect(() => () => pending.current?.abort(), []);

  function cancel() {
    pending.current?.abort();
    pending.current = null;
    setPhase(null);
  }

  async function generate() {
    if (pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    setPhase("loadingAgent");
    setError("");
    setDiagnostics("");
    onFilterChange("direct");
    try {
      const agent = await loadQualityAgentContext(source, controller.signal);
      if (controller.signal.aborted) return;
      setPhase("generating");
      const result = await generateQualityEvaluators({
        agent,
        runtimeId: source.runtimeId || "",
        region: source.region || "",
        language: i18n.resolvedLanguage?.startsWith("zh") ? "zh-CN" : "en-US",
      }, controller.signal);
      if (controller.signal.aborted) return;
      setEvaluators(result);
    } catch (cause) {
      if (controller.signal.aborted) return;
      setError(cause instanceof QualityRequestError ? cause.code : "failed");
      setDiagnostics(cause instanceof QualityRequestError ? cause.diagnostics : "");
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        setPhase(null);
      }
    }
  }

  const groups = [
    ...records.flatMap(row => row.evaluators ? [{ id: row.id, name: row.overall.name, value: row.evaluators.value, outdated: outputState(row, "evaluators") === "outdated" }] : []),
    ...(evaluators ? [{ id: "direct", name: p("direct"), value: evaluators, outdated: false }] : []),
  ].filter(group => filter === "all" || filter === group.id);

  return (
    <div className="agent-evaluators">
      <div className="agent-evaluators__toolbar">
        <div className="quality-preferences__filter-control"><Select aria-label={p("filter")} value={filter} onChange={event => onFilterChange(event.target.value)} options={[
          { value: "all", label: p("all") }, { value: "direct", label: p("direct") },
          ...records.map(row => ({ value: row.id, label: row.overall.name })),
        ]} /></div>
        <div className="agent-evaluators__actions">
          {phase && <Button variant="outline" onClick={cancel}>{q("cancel")}</Button>}
          <Button loading={Boolean(phase)} loadingLabel={q("generating")} onClick={() => void generate()}>
            {records.length ? p("generateDirectEvaluators") : q(evaluators ? "regenerate" : "generate")}
          </Button>
        </div>
      </div>
      {error && <p className="agent-evaluators__error" role="alert">{q(`errors.${error}`)}</p>}
      {error && <QualityErrorDetails diagnostics={diagnostics} />}
      {phase && (filter === "all" || filter === "direct") ? (
        <div className="agent-evaluators__grid" aria-hidden="true">
          {EVALUATOR_TYPES.map(type => (
            <CardLayout key={type} title={q(`names.${type}`)} icon={null} showClose={false} size="content">
              <div className="agent-evaluators__card-content">
                <div className="agent-evaluators__skeleton-lines">
                  <Skeleton />
                  <Skeleton width="medium" />
                </div>
                <div className="agent-evaluators__skeleton-lines">
                  <Skeleton width="short" />
                  <Skeleton shape="block" />
                </div>
              </div>
            </CardLayout>
          ))}
        </div>
      ) : groups.length > 0 ? (
        groups.map(group => <section key={group.id} className="agent-evaluators__group" aria-label={group.name}>
          <h3 className="agent-evaluators__group-title">{group.name}</h3>
          {group.outdated && <p className="agent-quality__hint">{p("outdatedHint")}</p>}
          <div className="agent-evaluators__grid">
            {EVALUATOR_TYPES.map(type => <EvaluatorCard key={type} evaluator={group.value[type]} />)}
          </div>
        </section>)
      ) : (
        <EmptyState icon={null} title={q("empty")} description={q("emptyHint")} />
      )}
    </div>
  );
}
