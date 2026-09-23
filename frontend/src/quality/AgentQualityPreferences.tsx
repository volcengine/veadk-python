import { useEffect, useId, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { useTranslation } from "react-i18next";
import {
  generateQualityDataset, generateQualityEvaluators, generateQualityPreferences,
  QualityRequestError,
  type ComponentPreferences, type ComponentSuggestionPreferences, type EvaluationPreferences, type EvaluationPreference, type QualityAgentSource, type PreferenceSuggestionField,
} from "../adk/quality";
import { ModalButton } from "../components/composites/ModalButton";
import { CardLayout } from "../components/layouts/CardLayout";
import { Button } from "../components/primitives/Button";
import { InputWithTailIcon } from "../components/primitives/InputWithTailIcon";
import { Radio } from "../components/primitives/Radio";
import { PillTag } from "../components/primitives/PillTag";
import { Skeleton } from "../components/primitives/Skeleton";
import { Table, TableCellText, type TableColumn } from "../components/primitives/Table";
import { Textarea } from "../components/primitives/Textarea";
import { QualityErrorDetails } from "./QualityErrorDetails";
import { hasPreferenceSuggestion, outputState, preferenceSignature, togglePreferenceSuggestion, type QualityPreferenceRecord } from "./preferences";
import { usePreferenceSuggestions } from "./usePreferenceSuggestions";
import { DatasetCountField } from "./DatasetCountField";
import { DATASET_COUNT_DEFAULT, datasetCountError } from "./datasetCount";
import "./AgentQualityPreferences.css";

const EMPTY_PREFERENCES: EvaluationPreferences = {
  name: "", goal: "", scenarios: "", successCriteria: "", unacceptableErrors: "", preference: "balanced",
};
const FOCUSES = ["outcome", "trajectory", "balanced"] as const;
const STRICTNESS = ["lenient", "balanced", "strict"] as const;
type ComponentKind = "dataset" | "evaluators";

interface Props {
  source: QualityAgentSource;
  records: QualityPreferenceRecord[];
  setRecords: Dispatch<SetStateAction<QualityPreferenceRecord[]>>;
  onView: (kind: ComponentKind, id: string) => void;
}

function describeError(cause: unknown) {
  return cause instanceof QualityRequestError
    ? { code: cause.code, diagnostics: cause.diagnostics }
    : { code: "failed", diagnostics: "" };
}

export function AgentQualityPreferences({ source, records, setRecords, onView }: Props) {
  const { t, i18n } = useTranslation("ui");
  const q = (key: string) => t(`agentWorkspace.qualityManagement.preferenceForm.${key}`);
  const id = useId();
  const formRef = useRef<HTMLFormElement>(null);
  const stepRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const pending = useRef<AbortController | null>(null);
  const [open, setOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [step, setStep] = useState<"overall" | "components">("overall");
  const [overall, setOverall] = useState<EvaluationPreferences>(EMPTY_PREFERENCES);
  const [components, setComponents] = useState<ComponentPreferences | null>(null);
  const [componentSuggestionContext, setComponentSuggestionContext] = useState<ComponentSuggestionPreferences>();
  const [datasetCount, setDatasetCount] = useState(String(DATASET_COUNT_DEFAULT));
  const countError = step === "components" ? datasetCountError(datasetCount) : null;
  const [busy, setBusy] = useState<"preferences" | "components" | null>(null);
  const [generating, setGenerating] = useState<ComponentKind[]>([]);
  const [error, setError] = useState<ReturnType<typeof describeError> | null>(null);
  const [notice, setNotice] = useState("");
  const suggestions = usePreferenceSuggestions(source, i18n.resolvedLanguage?.startsWith("zh") ? "zh-CN" : "en-US", open && !busy, step === "components" ? componentSuggestionContext : undefined);
  const record = records.find(row => row.id === editingId);
  const reviewChanged = Boolean(record && components && (!record.components || preferenceSignature(overall, components) !== preferenceSignature(record.overall, record.components)));

  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => { if (open) stepRef.current?.focus(); }, [step, open]);
  useEffect(() => {
    if (open && (error || record?.errors)) errorRef.current?.scrollIntoView({ block: "nearest" });
  }, [error, record?.errors, open]);

  function close() {
    pending.current?.abort();
    pending.current = null;
    setBusy(null);
    setGenerating([]);
    setOpen(false);
  }

  function edit(row?: QualityPreferenceRecord) {
    setEditingId(row?.id ?? null);
    setOverall(row?.overall ?? { ...EMPTY_PREFERENCES });
    setComponents(row?.components ?? null);
    setComponentSuggestionContext(row?.components ? { overallPreferences: row.overall, componentPreferences: row.components } : undefined);
    setDatasetCount(String(row?.components?.dataset.count ?? DATASET_COUNT_DEFAULT));
    setStep(row?.components ? "components" : "overall");
    setError(null);
    setOpen(true);
  }

  function save(nextComponents: ComponentPreferences | null) {
    const key = editingId ?? crypto.randomUUID();
    const value = { overall, components: nextComponents, updatedAt: new Date().toISOString() };
    setEditingId(key);
    setRecords(previous => previous.some(row => row.id === key)
      ? previous.map(row => row.id === key ? { ...row, ...value, errors: JSON.stringify([row.overall, row.components]) === JSON.stringify([overall, nextComponents]) ? row.errors : undefined } : row)
      : [{ id: key, ...value }, ...previous]);
    return key;
  }

  function updateRecord(key: string, update: (row: QualityPreferenceRecord) => QualityPreferenceRecord) {
    setRecords(previous => previous.map(row => row.id === key ? update(row) : row));
  }

  async function submit() {
    if (pending.current || countError || !formRef.current?.reportValidity()) return;
    const controller = new AbortController();
    pending.current = controller;
    const operation = step === "overall" ? "preferences" : "components";
    setBusy(operation);
    setError(null);
    const key = save(step === "overall" ? null : components);
    try {
      const agent = await suggestions.loadAgent(controller.signal);
      controller.signal.throwIfAborted();
      const request = {
        agent, runtimeId: source.runtimeId || "", region: source.region || "",
        language: i18n.resolvedLanguage?.startsWith("zh") ? "zh-CN" as const : "en-US" as const,
        overallPreferences: overall,
      };
      if (operation === "preferences") {
        const result = await generateQualityPreferences(request, controller.signal);
        controller.signal.throwIfAborted();
        setComponents(result);
        setComponentSuggestionContext({ overallPreferences: overall, componentPreferences: result });
        setDatasetCount(String(result.dataset.count));
        updateRecord(key, row => ({ ...row, components: result, errors: undefined }));
        setStep("components");
      } else if (components) {
        const signature = preferenceSignature(overall, components);
        const kinds = (["dataset", "evaluators"] as const).filter(kind => record?.[kind]?.signature !== signature);
        setGenerating([...kinds]);
        updateRecord(key, row => ({ ...row, errors: undefined }));
        const input = { ...request, componentPreferences: components };
        const results = await Promise.allSettled(kinds.map(async kind => {
          try {
            if (kind === "dataset") {
              const value = await generateQualityDataset({ ...input, ...components.dataset }, controller.signal);
              controller.signal.throwIfAborted();
              updateRecord(key, row => ({ ...row, dataset: { value, signature }, updatedAt: new Date().toISOString() }));
            } else {
              const value = await generateQualityEvaluators(input, controller.signal);
              controller.signal.throwIfAborted();
              updateRecord(key, row => ({ ...row, evaluators: { value, signature }, updatedAt: new Date().toISOString() }));
            }
          } catch (cause) {
            if (!controller.signal.aborted) updateRecord(key, row => ({ ...row, errors: { ...row.errors, [kind]: describeError(cause) } }));
            throw cause;
          } finally {
            if (!controller.signal.aborted) setGenerating(previous => previous.filter(value => value !== kind));
          }
        }));
        controller.signal.throwIfAborted();
        if (results.every(result => result.status === "fulfilled")) {
          setNotice(q("generated"));
          setOpen(false);
        }
      }
    } catch (cause) {
      if (!controller.signal.aborted) setError(describeError(cause));
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        setBusy(null);
        setGenerating([]);
      }
    }
  }

  function focusField(value: EvaluationPreference, onChange: (value: EvaluationPreference) => void, name: string) {
    return <fieldset className="agent-quality__field" disabled={Boolean(busy)}>
      <legend>{q("preference")}</legend>
      <div className="agent-quality__choices">
        {FOCUSES.map(option => <Radio key={option} name={`${id}-${name}`} value={option} checked={value === option} onChange={() => onChange(option)} label={q(`focus.${option}`)} />)}
      </div>
    </fieldset>;
  }

  function textField(label: string, value: string, onChange: (value: string) => void, required = true, suggestionField?: PreferenceSuggestionField) {
    const fieldSuggestions = suggestionField ? suggestions.fields[suggestionField] : null;
    return <div className="agent-quality__field" key={label}>
      <label htmlFor={`${id}-${label}`}>{q(label)}</label>
      <Textarea id={`${id}-${label}`} fullWidth maxLength={6000} required={required} disabled={Boolean(busy)}
        placeholder={q(`${label}Placeholder`)} value={value} onChange={event => onChange(event.target.value)} />
      {fieldSuggestions && <div className="quality-preferences__suggestions" role="group" aria-label={t("agentWorkspace.qualityManagement.preferenceForm.suggestionGroup", { field: q(label) })} aria-busy={fieldSuggestions.loading}>
        {fieldSuggestions.loading ? <>
          <span className="quality-preferences__suggestion-placeholder"><Skeleton width="medium" /></span>
          <span className="quality-preferences__suggestion-placeholder"><Skeleton width="short" /></span>
        </> : fieldSuggestions.data?.map(suggestion => {
          const selected = hasPreferenceSuggestion(value, suggestion.text);
          const atLimit = !selected && togglePreferenceSuggestion(value, suggestion.text) === value;
          return <PillTag key={suggestion.text} selected={selected} disabled={Boolean(busy) || atLimit}
            title={atLimit ? q("suggestionLimit") : suggestion.text}
            onSelectedChange={() => onChange(togglePreferenceSuggestion(value, suggestion.text))}>{suggestion.label}</PillTag>;
        })}
      </div>}
      {fieldSuggestions?.error && <div className="quality-preferences__suggestion-error">
        <div className="quality-preferences__review-actions">
          <p className="agent-quality__error" role="alert">{q("suggestionsFailed")}</p>
          <Button variant="link" disabled={Boolean(busy) || suggestions.loading} onClick={suggestions.retry}>{q("retrySuggestions")}</Button>
        </div>
        <QualityErrorDetails diagnostics={fieldSuggestions.error.diagnostics} />
      </div>}
    </div>;
  }

  const columns: TableColumn<QualityPreferenceRecord>[] = [
    { key: "name", title: q("name"), width: "25%", render: row => <TableCellText title={<Button variant="link" onClick={() => edit(row)}>{row.overall.name}</Button>} description={row.overall.goal} descriptionLines={2} /> },
    { key: "focus", title: q("preference"), render: row => q(`focus.${row.overall.preference}`) },
    ...(["dataset", "evaluators"] as const).map(kind => ({
      key: kind, title: q(kind), render: (row: QualityPreferenceRecord) => <div className="quality-preferences__output-cell">
        {row[kind] ? <Button variant="link" onClick={() => onView(kind, row.id)}>{kind === "dataset" ? t("agentWorkspace.qualityManagement.itemCount", { count: row.dataset!.value.items.length }) : q("evaluatorCount")}</Button> : <span>{q(row.components ? "pending" : "awaitingPreferences")}</span>}
        {row[kind] && outputState(row, kind) === "outdated" && <span className="agent-quality__hint">{q("outdated")}</span>}
        {row.errors?.[kind] && <span className="agent-quality__error">{q("failed")}</span>}
      </div>,
    })),
    { key: "actions", title: q("actions"), width: 128, render: row => <Button variant="link" onClick={() => edit(row)}>{q(row.components ? "adjust" : "continue")}</Button> },
  ];
  const hasErrors = Boolean(record?.errors && Object.keys(record.errors).length);

  return <Table aria-label={q("table")} columns={columns} data={records} rowKey={row => row.id} minWidth={640}
    emptyContent={q("empty")} toolbarStart={<span className="agent-quality__notice" role="status">{notice}</span>}
    toolbarEnd={<ModalButton label={q("add")} title={q(editingId ? "editTitle" : "add")}
      open={open} onOpenChange={next => next ? edit() : close()} closeOnConfirm={false}
      size="large" topGlow={false} data-theme="light" cancelLabel={q("close")} closeLabel={q("close")}
      confirmLabel={q(busy ? "generating" : step === "overall" ? "generatePreferences" : hasErrors && !reviewChanged ? "retry" : "generateComponents")}
      confirmDisabled={Boolean(busy) || Boolean(countError)} confirmLoading={Boolean(busy)} onConfirm={() => formRef.current?.requestSubmit()}>
      <form ref={formRef} className="agent-quality__form" onSubmit={event => { event.preventDefault(); void submit(); }}>
        <ol className="quality-preferences__steps" aria-label={q("steps")}>
          <li aria-current={step === "overall" ? "step" : undefined}>1 {q("overallStep")}</li>
          <li aria-current={step === "components" ? "step" : undefined}>2 {q("componentsStep")}</li>
        </ol>
        <h4 ref={stepRef} tabIndex={-1} className="quality-preferences__step-title">{step === "overall" ? q("overallHint") : q("componentsHint")}</h4>
        {suggestions.loading && <span className="quality-preferences__announcement" role="status">{q("loadingSuggestions")}</span>}
        {step === "overall" ? <>
          <div className="agent-quality__field">
            <label htmlFor={`${id}-name`}>{q("name")}</label>
            <InputWithTailIcon id={`${id}-name`} tailIcon={null} required maxLength={300} disabled={Boolean(busy)} placeholder={q("namePlaceholder")} value={overall.name} onChange={event => setOverall(previous => ({ ...previous, name: event.target.value }))} />
          </div>
          {(["goal", "scenarios", "successCriteria", "unacceptableErrors"] as const).map(field => textField(field, overall[field], value => setOverall(previous => ({ ...previous, [field]: value })), field !== "unacceptableErrors", field))}
          {focusField(overall.preference, preference => setOverall(previous => ({ ...previous, preference })), "overall-focus")}
        </> : components && <>
          <div className="quality-preferences__review-actions">
            <Button variant="link" disabled={Boolean(busy)} onClick={() => { setError(null); setStep("overall"); }}>{q("back")}</Button>
            <Button variant="outline" disabled={Boolean(busy) || Boolean(countError)} onClick={() => { if (!countError && formRef.current?.reportValidity()) { save(components); close(); } }}>{q("save")}</Button>
          </div>
          <CardLayout title={q("datasetPreferences")} icon={null} showClose={false} size="content">
            <div className="agent-quality__form">
              {focusField(components.dataset.preference, preference => setComponents({ ...components, dataset: { ...components.dataset, preference } }), "dataset-focus")}
              {textField("datasetScenarios", components.dataset.scenario, scenario => setComponents({ ...components, dataset: { ...components.dataset, scenario } }), true, "datasetScenarios")}
              {textField("datasetRequirements", components.dataset.requirements, requirements => setComponents({ ...components, dataset: { ...components.dataset, requirements } }), true, "datasetRequirements")}
              <DatasetCountField id={`${id}-count`} label={q("count")} value={datasetCount} disabled={Boolean(busy)} onChange={value => {
                setDatasetCount(value);
                if (!datasetCountError(value)) setComponents({ ...components, dataset: { ...components.dataset, count: Number(value) } });
              }} />
            </div>
          </CardLayout>
          <CardLayout title={q("evaluatorPreferences")} icon={null} showClose={false} size="content">
            <div className="agent-quality__form">
              {(["overallFocus", "toolsFocus", "skillsFocus", "criteria"] as const).map(field => textField(
                field, components.evaluators[field], value => setComponents({ ...components, evaluators: { ...components.evaluators, [field]: value } }), true, field,
              ))}
              <fieldset className="agent-quality__field" disabled={Boolean(busy)}>
                <legend>{q("strictness")}</legend>
                <div className="agent-quality__choices">{STRICTNESS.map(strictness => <Radio key={strictness} name={`${id}-strictness`} value={strictness} checked={components.evaluators.strictness === strictness} onChange={() => setComponents({ ...components, evaluators: { ...components.evaluators, strictness } })} label={q(`strictnessOptions.${strictness}`)} />)}</div>
              </fieldset>
            </div>
          </CardLayout>
          <div ref={errorRef}>{(["dataset", "evaluators"] as const).map(kind => <div key={kind}>
            {(busy === "components" || record?.[kind] || record?.errors?.[kind]) && <p className="agent-quality__hint" role="status">{q(kind)}：{q(generating.includes(kind) ? "generating" : record?.errors?.[kind] ? "failed" : record ? outputState({ ...record, overall, components }, kind) : "pending")}</p>}
            {record?.errors?.[kind] && <><p className="agent-quality__error" role="alert">{t(`agentWorkspace.qualityManagement.errors.${record.errors[kind]!.code}`)}</p><QualityErrorDetails diagnostics={record.errors[kind]!.diagnostics} /></>}
          </div>)}</div>
        </>}
        {error && <div ref={step === "overall" ? errorRef : undefined} role="alert"><p className="agent-quality__error">{t(`agentWorkspace.qualityManagement.errors.${error.code}`)}</p><QualityErrorDetails diagnostics={error.diagnostics} /></div>}
      </form>
    </ModalButton>} />;
}
