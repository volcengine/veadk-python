import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { autofillQualityBrief, generateQualityDataset, loadQualityAgentContext, QualityRequestError, type EvaluationBrief, type GeneratedDataset, type QualityAgentContext, type QualityAgentSource } from "../adk/quality";
import { ModalButton } from "../components/composites/ModalButton";
import { Drawer } from "../components/composites/Drawer";
import { Button } from "../components/primitives/Button";
import { EmptyState } from "../components/primitives/EmptyState";
import { Radio } from "../components/primitives/Radio";
import { Table, type TableColumn } from "../components/primitives/Table";
import { Textarea } from "../components/primitives/Textarea";
import { UnderlineTabs } from "../components/primitives/UnderlineTabs";
import { Select } from "../components/primitives/Select";
import { AgentEvaluators } from "./AgentEvaluators";
import { AgentQualityPreferences } from "./AgentQualityPreferences";
import { outputState, type QualityPreferenceRecord } from "./preferences";
import { QualityErrorDetails } from "./QualityErrorDetails";
import { DatasetCountField } from "./DatasetCountField";
import { DATASET_COUNT_DEFAULT, datasetCountError } from "./datasetCount";
import "./AgentQualityManagement.css";

interface EvaluationSetRow extends GeneratedDataset {
  id: string;
  updatedAt: string;
  preferenceId?: string;
  preferenceName?: string;
  outdated?: boolean;
}

const QUALITY_TABS = ["preferences", "datasets", "evaluators", "results"] as const;
const PREFERENCES = ["trajectory", "outcome", "balanced"] as const;

export function AgentQualityManagement(source: QualityAgentSource) {
  const { t, i18n } = useTranslation("ui");
  const q = (key: string) => t(`agentWorkspace.qualityManagement.${key}`);
  const id = useId();
  const formRef = useRef<HTMLFormElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const pending = useRef<AbortController | null>(null);
  const [activeTab, setActiveTab] = useState("preferences");
  const [preferences, setPreferences] = useState<QualityPreferenceRecord[]>([]);
  const [datasetFilter, setDatasetFilter] = useState("all");
  const [evaluatorFilter, setEvaluatorFilter] = useState("all");
  const [open, setOpen] = useState(false);
  const [datasets, setDatasets] = useState<EvaluationSetRow[]>([]);
  const [brief, setBrief] = useState<EvaluationBrief>({ preference: "balanced", scenario: "", requirements: "" });
  const [count, setCount] = useState(String(DATASET_COUNT_DEFAULT));
  const countError = datasetCountError(count);
  const [busy, setBusy] = useState<"autofill" | "generate" | null>(null);
  const [phase, setPhase] = useState("");
  const [error, setError] = useState("");
  const [diagnostics, setDiagnostics] = useState("");
  const [notice, setNotice] = useState("");
  const [context, setContext] = useState<QualityAgentContext | null>(null);

  useEffect(() => () => pending.current?.abort(), []);
  useEffect(() => {
    if (error) errorRef.current?.scrollIntoView({ block: "nearest" });
  }, [error]);

  function changeOpen(next: boolean) {
    if (!next) {
      pending.current?.abort();
      pending.current = null;
      setBusy(null);
      setPhase("");
    }
    setError("");
    setOpen(next);
  }

  async function run(operation: "autofill" | "generate") {
    if (pending.current) return;
    if (operation === "generate" && (countError || !formRef.current?.reportValidity())) return;
    const controller = new AbortController();
    pending.current = controller;
    setBusy(operation);
    setError("");
    setDiagnostics("");
    setPhase("loadingAgent");
    try {
      const agent = await loadQualityAgentContext(source, controller.signal);
      if (controller.signal.aborted) return;
      setContext(agent);
      setPhase(operation === "autofill" ? "filling" : "generating");
      const request = {
        agent,
        runtimeId: source.runtimeId || "",
        region: source.region || "",
        language: i18n.resolvedLanguage?.startsWith("zh") ? "zh-CN" as const : "en-US" as const,
      };
      if (operation === "autofill") {
        const result = await autofillQualityBrief(request, controller.signal);
        if (controller.signal.aborted) return;
        setBrief(result);
        setPhase("filled");
      } else {
        const result = await generateQualityDataset({ ...request, ...brief, count: Number(count) }, controller.signal);
        if (controller.signal.aborted) return;
        setDatasets(previous => [{ ...result, id: crypto.randomUUID(), updatedAt: new Date().toISOString() }, ...previous]);
        setDatasetFilter("direct");
        setNotice(t("agentWorkspace.qualityManagement.generated", { count: result.items.length }));
        setOpen(false);
        setPhase("");
      }
    } catch (cause) {
      if (controller.signal.aborted) return;
      setError(cause instanceof QualityRequestError ? `errors.${cause.code}` : "errors.failed");
      setDiagnostics(cause instanceof QualityRequestError ? cause.diagnostics : "");
      setPhase("");
    } finally {
      if (pending.current === controller) {
        pending.current = null;
        setBusy(null);
      }
    }
  }

  const tabs = QUALITY_TABS.map((value) => ({
    value,
    label: t(`agentWorkspace.qualityManagement.tabs.${value}`),
    id: `${id}-${value}-tab`,
    panelId: `${id}-${value}-panel`,
  }));
  const allDatasets: EvaluationSetRow[] = [
    ...preferences.flatMap(row => row.dataset ? [{ ...row.dataset.value, id: row.id, updatedAt: row.updatedAt, preferenceId: row.id, preferenceName: row.overall.name, outdated: outputState(row, "dataset") === "outdated" }] : []),
    ...datasets,
  ];
  const visibleDatasets = allDatasets.filter(row => datasetFilter === "all" || (row.preferenceId || "direct") === datasetFilter);
  const columns: TableColumn<EvaluationSetRow>[] = [
    { key: "name", title: t("common.name"), render: (row) => (
      <Drawer
        trigger={<Button variant="link">{row.name}</Button>}
        title={row.name}
        description={t("agentWorkspace.qualityManagement.itemCount", { count: row.items.length })}
        width={720}
        surface="solid"
        data-theme="light"
        closeLabel={q("close")}
      >
        <div className="agent-quality__cases">
          {row.items.map((item, index) => (
            <details key={index} className="agent-quality__case" open={index === 0}>
              <summary>{index + 1}. {item.name}</summary>
              <dl className="agent-quality__case-content">
                <dt>{q("scenario")}</dt><dd>{item.scenario}</dd>
                <dt>{q("input")}</dt><dd>{item.input}</dd>
                <dt>{q("expectedOutput")}</dt><dd>{item.expectedOutput}</dd>
                {item.trajectory.length > 0 && <><dt>{q("expectedTrajectory")}</dt><dd><ol>{item.trajectory.map((step, stepIndex) => <li key={stepIndex}>{step}</li>)}</ol></dd></>}
                <dt>{q("checks")}</dt><dd><ul>{item.checks.map((check, checkIndex) => <li key={checkIndex}>{check}</li>)}</ul></dd>
              </dl>
            </details>
          ))}
        </div>
      </Drawer>
    ) },
    { key: "description", title: t("common.description"), render: (row) => row.description },
    { key: "preference", title: q("tabs.preferences"), render: row => <div>{row.preferenceName || q("preferenceForm.direct")}{row.outdated && <p className="agent-quality__hint">{q("preferenceForm.outdated")}</p>}</div> },
    { key: "sampleCount", title: q("sampleCount"), render: (row) => row.items.length },
    { key: "updatedAt", title: q("updatedAt"), render: (row) => new Date(row.updatedAt).toLocaleString(i18n.resolvedLanguage, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) },
  ];

  return (
    <section className="agent-quality" data-theme="light" aria-label={t("agentWorkspace.sections.quality")}>
      <UnderlineTabs
        aria-label={t("agentWorkspace.sections.quality")}
        items={tabs}
        value={activeTab}
        onValueChange={setActiveTab}
      />
      {tabs.map((tab) => (
        <div
          key={tab.value}
          id={tab.panelId}
          role="tabpanel"
          aria-labelledby={tab.id}
          hidden={activeTab !== tab.value}
          tabIndex={0}
          className="agent-quality__panel"
        >
          {tab.value === "preferences" ? (
            <AgentQualityPreferences source={source} records={preferences} setRecords={setPreferences} onView={(kind, preferenceId) => {
              if (kind === "dataset") { setDatasetFilter(preferenceId); setActiveTab("datasets"); }
              else { setEvaluatorFilter(preferenceId); setActiveTab("evaluators"); }
            }} />
          ) : tab.value === "datasets" ? (
            <Table
              aria-label={tab.label}
              columns={columns}
              data={visibleDatasets}
              rowKey={(row) => row.id}
              minWidth={640}
              emptyContent={t("agentWorkspace.qualityManagement.emptyDatasets")}
              toolbarStart={<div className="quality-preferences__filter"><div className="quality-preferences__filter-control"><Select aria-label={q("preferenceForm.filter")} value={datasetFilter} onChange={event => setDatasetFilter(event.target.value)} options={[
                { value: "all", label: q("preferenceForm.all") },
                { value: "direct", label: q("preferenceForm.direct") },
                ...preferences.map(row => ({ value: row.id, label: row.overall.name })),
              ]} /></div><span className="agent-quality__notice" role="status" hidden={!notice}>{notice}</span></div>}
              toolbarEnd={
                <ModalButton
                  label={q("add")}
                  title={q("add")}
                  open={open}
                  onOpenChange={changeOpen}
                  closeOnConfirm={false}
                  topGlow={false}
                  size="large"
                  data-theme="light"
                  cancelLabel={q("cancel")}
                  closeLabel={q("close")}
                  confirmLabel={busy === "generate" ? q("generating") : q("generate")}
                  confirmDisabled={Boolean(busy) || Boolean(countError)}
                  confirmLoading={busy === "generate"}
                  onConfirm={() => formRef.current?.requestSubmit()}
                >
                  <form ref={formRef} className="agent-quality__form" onSubmit={event => { event.preventDefault(); void run("generate"); }}>
                    <div className="agent-quality__autofill">
                      <p>{q("autofillHint")}</p>
                      <Button type="button" variant="outline" onClick={() => void run("autofill")} loading={busy === "autofill"} disabled={Boolean(busy)}>{q("autofill")}</Button>
                    </div>
                    <fieldset className="agent-quality__field" disabled={Boolean(busy)}>
                      <legend>{q("preference")}</legend>
                      <div className="agent-quality__choices">
                        {PREFERENCES.map(value => <Radio key={value} name={`${id}-preference`} value={value} checked={brief.preference === value} onChange={() => setBrief(previous => ({ ...previous, preference: value }))} label={q(`preferences.${value}`)} />)}
                      </div>
                      <p className="agent-quality__hint">{q(`preferenceHints.${brief.preference}`)}</p>
                    </fieldset>
                    <div className="agent-quality__field">
                      <label htmlFor={`${id}-scenario`}>{q("scenario")}</label>
                      <Textarea id={`${id}-scenario`} fullWidth required maxLength={6000} disabled={Boolean(busy)} placeholder={q("scenarioPlaceholder")} value={brief.scenario} onChange={event => setBrief(previous => ({ ...previous, scenario: event.target.value }))} />
                    </div>
                    <div className="agent-quality__field">
                      <label htmlFor={`${id}-requirements`}>{q("requirements")}</label>
                      <Textarea id={`${id}-requirements`} fullWidth required maxLength={6000} disabled={Boolean(busy)} placeholder={q("requirementsPlaceholder")} value={brief.requirements} onChange={event => setBrief(previous => ({ ...previous, requirements: event.target.value }))} />
                    </div>
                    <DatasetCountField id={`${id}-count`} label={q("count")} value={count} disabled={Boolean(busy)} onChange={setCount} />
                    {phase && <p className="agent-quality__hint" role="status">{q(phase)}</p>}
                    {context && <details className="agent-quality__context">
                      <summary>{q("agentContext")}: {context.name}</summary>
                      <p>{context.description}</p>
                      <p>{q("systemPrompt")}</p>
                      <p className="agent-quality__prompt">{context.instruction || q("missingPrompt")}</p>
                      {context.tools.length > 0 && <p>{q("tools")}: {context.tools.join(", ")}</p>}
                    </details>}
                    {error && <p ref={errorRef} className="agent-quality__error" role="alert">{q(error)}</p>}
                    {error && <QualityErrorDetails diagnostics={diagnostics} />}
                  </form>
                </ModalButton>
              }
            />
          ) : tab.value === "evaluators" ? (
            <AgentEvaluators source={source} records={preferences} filter={evaluatorFilter} onFilterChange={setEvaluatorFilter} />
          ) : (
            <EmptyState
              icon={null}
              title={t("agentWorkspace.qualityManagement.notAvailable")}
            />
          )}
        </div>
      ))}
    </section>
  );
}
