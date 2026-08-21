import { useEffect, useMemo, useState } from "react";
import {
  publishEvaluatorGroup,
  publishPolicyVersion,
  recommendEvaluatorDrafts,
  saveEvaluatorDraft,
  savePolicyDraft,
  trialEvaluatorDraft,
} from "../adk/scenarioEvaluation";
import {
  buildSceneEvaluatorGroups,
  combineSceneEvaluatorTrialResults,
  type SceneEvaluatorGroup,
} from "./scenarioEvaluatorGroups";
import { latestVersionForDraft } from "./scenarioEvaluationPresentation";
import type {
  EvaluatorTrialReport,
  PolicySceneBinding,
  ScenarioEvaluationWorkspaceData,
} from "./types";
import type {
  MutationFeedbackState,
  MutationRunner,
} from "./scenarioEvaluationWorkspaceTypes";

const calibrationLabels: Record<SceneEvaluatorGroup["calibrationState"], string> = {
  not_started: "尚未校准",
  accurate: "校准准确",
  inaccurate: "存在误判",
  unavailable: "校准未完成",
};

function trialOutcomeLabel(outcome: EvaluatorTrialReport["results"][number]["outcome"]): string {
  return {
    pass: "通过",
    fail: "不通过",
    infra_error: "基础设施异常",
    cancelled: "已取消",
  }[outcome];
}

function randomId(prefix: string): string {
  const suffix = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return `${prefix}-${suffix}`;
}

function latestItem<T>(items: T[]): T | undefined {
  return items[items.length - 1];
}

type TrialCheck = {
  label: string;
  hardFailure: boolean;
  result: EvaluatorTrialReport["results"][number];
};

export function GovernancePanel({
  step,
  agentId,
  workspace,
  mutationKey,
  mutationFeedback,
  mutate,
}: {
  step: "evaluator" | "policy";
  agentId: string;
  workspace: ScenarioEvaluationWorkspaceData;
  mutationKey: string;
  mutationFeedback: MutationFeedbackState | null;
  mutate: MutationRunner;
}) {
  const groups = useMemo(() => buildSceneEvaluatorGroups(workspace), [workspace]);
  const activeScenes = useMemo(() => {
    const latest = new Map<string, ScenarioEvaluationWorkspaceData["scenes"][number]>();
    workspace.scenes.forEach((scene) => {
      const current = latest.get(scene.sceneId);
      if (!current || scene.version > current.version) latest.set(scene.sceneId, scene);
    });
    return [...latest.values()].filter((scene) => scene.enabled);
  }, [workspace.scenes]);
  const [evaluatorName, setEvaluatorName] = useState("");
  const [evaluatorKind, setEvaluatorKind] = useState<"deterministic" | "llm_rubric">("deterministic");
  const [rule, setRule] = useState("output_contains_expected");
  const [rubric, setRubric] = useState("");
  const [hardFailure, setHardFailure] = useState(false);
  const [evaluatorSceneVersionId, setEvaluatorSceneVersionId] = useState("");
  const [activeGroupId, setActiveGroupId] = useState("");
  const [trialDatasetVersionId, setTrialDatasetVersionId] = useState("");
  const [trialCaseId, setTrialCaseId] = useState("");
  const [trialHumanJudgment, setTrialHumanJudgment] = useState<"pass" | "fail">("pass");
  const [trialOutput, setTrialOutput] = useState("");
  const [trialChecks, setTrialChecks] = useState<TrialCheck[]>([]);
  const [policyName, setPolicyName] = useState("");
  const [policySelections, setPolicySelections] = useState<Record<string, {
    datasetVersionId: string;
    evaluatorVersionIds: string[];
  }>>({});
  const activeGroup = groups.find((group) => group.sceneVersionId === activeGroupId) ?? null;
  const compatibleDatasets = activeGroup
    ? workspace.datasets.filter((item) => item.cases.some((sample) =>
        sample.sceneVersionId === activeGroup.sceneVersionId))
    : [];
  const trialDataset = compatibleDatasets.find((item) =>
    item.datasetVersionId === trialDatasetVersionId);
  const compatibleCases = trialDataset?.cases.filter((item) =>
    item.sceneVersionId === activeGroup?.sceneVersionId) ?? [];
  const trialCase = compatibleCases.find((item) => item.caseId === trialCaseId);
  const combinedTrial = trialChecks.length > 0
    ? combineSceneEvaluatorTrialResults(trialHumanJudgment, trialChecks)
    : null;

  useEffect(() => {
    setEvaluatorSceneVersionId((value) =>
      value || latestItem(activeScenes)?.sceneVersionId || "");
  }, [activeScenes]);

  useEffect(() => {
    setPolicySelections((current) => Object.fromEntries(activeScenes.map((scene) => {
      const datasets = workspace.datasets.filter((item) => item.cases.some((sample) =>
        sample.sceneVersionId === scene.sceneVersionId));
      const group = groups.find((item) => item.sceneVersionId === scene.sceneVersionId);
      const previous = current[scene.sceneVersionId];
      return [scene.sceneVersionId, {
        datasetVersionId: datasets.some((item) =>
          item.datasetVersionId === previous?.datasetVersionId)
          ? previous.datasetVersionId
          : latestItem(datasets)?.datasetVersionId ?? "",
        evaluatorVersionIds: group?.latestPublishedVersionIds ?? [],
      }];
    })));
  }, [activeScenes, groups, workspace.datasets]);

  const policyReady = activeScenes.length > 0 && activeScenes.every((scene) => {
    const selection = policySelections[scene.sceneVersionId];
    const group = groups.find((item) => item.sceneVersionId === scene.sceneVersionId);
    return Boolean(
      selection?.datasetVersionId
      && group?.publishState === "published"
      && group.calibrationState === "accurate"
      && selection.evaluatorVersionIds.length === group.latestPublishedVersionIds.length,
    );
  });

  function openCalibration(group: SceneEvaluatorGroup) {
    const datasets = workspace.datasets.filter((item) => item.cases.some((sample) =>
      sample.sceneVersionId === group.sceneVersionId));
    const dataset = latestItem(datasets);
    setActiveGroupId(group.sceneVersionId);
    setTrialDatasetVersionId(dataset?.datasetVersionId ?? "");
    setTrialCaseId(dataset?.cases.find((item) =>
      item.sceneVersionId === group.sceneVersionId)?.caseId ?? "");
    setTrialHumanJudgment("pass");
    setTrialOutput("");
    setTrialChecks([]);
  }

  function publishGroup(group: SceneEvaluatorGroup) {
    const actionKey = `publish-scene-evaluator-${group.sceneVersionId}`;
    void mutate(actionKey, async () => {
      const result = await publishEvaluatorGroup({
        agentId,
        sceneVersionId: group.sceneVersionId,
        drafts: group.drafts.map((draft) => ({
          evaluatorId: draft.evaluatorId,
          draftRevision: draft.revision,
        })),
      });
      return { name: group.sceneName, count: result.checkCount };
    }, (result) => `场景评估器“${result.name}”已发布，共 ${result.count} 项检查`);
  }

  return (
    <div className="se-section-stack">
      {step === "evaluator" && <section className="se-work-card" id="evaluator-form">
        <header>
          <div><h3>场景评估器</h3><p>一个业务场景对应一个场景评估器，内部可包含普通检查和严重失败检查。</p></div>
          <span>{groups.length} 个</span>
        </header>
        <div className="se-scene-evaluator-list">
          {groups.map((group) => {
            const actionKey = `publish-scene-evaluator-${group.sceneVersionId}`;
            const feedback = mutationFeedback?.key === actionKey ? mutationFeedback : null;
            const publishLabel = mutationKey === actionKey
              ? "正在发布…"
              : group.publishState === "published"
                ? "已发布"
                : group.publishState === "partial"
                  ? "重试未发布项"
                  : "发布场景评估器";
            return (
              <article className="se-scene-evaluator" key={group.sceneVersionId}>
                <header>
                  <div><strong>{group.sceneName}</strong><small>{calibrationLabels[group.calibrationState]}</small></div>
                  <em>{group.publishState === "published" ? "已发布" : group.publishState === "partial" ? "部分发布" : "草稿"}</em>
                </header>
                <div className="se-scene-evaluator-counts">
                  <span>普通检查 {group.ordinaryCheckCount} 项</span>
                  <span>严重失败检查 {group.severeCheckCount} 项</span>
                </div>
                {group.drafts.length > 0 && (
                  <details className="se-internal-checks">
                    <summary>查看 {group.drafts.length} 项内部检查</summary>
                    <ul>{group.drafts.map((draft) => <li key={draft.evaluatorId}>{draft.name} · {draft.hardFailure ? "严重失败检查" : "普通检查"}</li>)}</ul>
                  </details>
                )}
                <footer>
                  <button type="button" disabled={Boolean(mutationKey) || group.drafts.length === 0} onClick={() => openCalibration(group)}>校准场景评估器</button>
                  <button type="button" className="is-primary" disabled={Boolean(mutationKey) || group.drafts.length === 0 || group.calibrationState !== "accurate" || group.publishState === "published"} onClick={() => publishGroup(group)}>{publishLabel}</button>
                  <button type="button" disabled={Boolean(mutationKey)} onClick={() => void mutate(`recommend-${group.sceneVersionId}`, () => recommendEvaluatorDrafts(agentId, group.sceneVersionId))}>生成推荐检查</button>
                </footer>
                {group.calibrationBlockReason && <small className="se-action-disabled-reason">{group.calibrationBlockReason}</small>}
                {feedback && <small className={`se-action-feedback is-${feedback.kind}`} role={feedback.kind === "error" ? "alert" : "status"}>{feedback.message}</small>}
              </article>
            );
          })}
        </div>

        {activeGroup && (
          <form className="se-trial-form" onSubmit={(event) => {
            event.preventDefault();
            if (!trialDataset || !trialCase) return;
            setTrialChecks([]);
            void mutate(`trial-group-${activeGroup.sceneVersionId}`, async () => {
              const checks = await Promise.all(activeGroup.drafts.map(async (draft) => {
                const report = await trialEvaluatorDraft(draft.evaluatorId, {
                  agentId,
                  expectedRevision: draft.revision,
                  datasetVersionId: trialDataset.datasetVersionId,
                  samples: [{
                    sampleId: trialCase.caseId,
                    input: trialCase.input,
                    expectedOutput: trialCase.expectedOutput,
                    agentOutput: trialOutput,
                    expectedOutcome: trialHumanJudgment,
                    forbiddenOutput: trialCase.forbiddenOutput,
                  }],
                });
                return {
                  label: draft.name,
                  hardFailure: draft.hardFailure,
                  result: report.results[0],
                };
              }));
              setTrialChecks(checks);
              return checks;
            }, () => `场景评估器“${activeGroup.sceneName}”已完成校准`);
          }}>
            <header className="se-calibration-head">
              <div><h4>校准“{activeGroup.sceneName}”</h4><p>先给出模拟 Agent 输出和人工判断，再运行全部内部检查并比较结果。</p></div>
              <button type="button" onClick={() => setActiveGroupId("")}>关闭</button>
            </header>
            <div className="se-calibration-context">
              <label><span>评测数据版本</span><select required value={trialDatasetVersionId} onChange={(event) => {
                const value = event.currentTarget.value;
                const dataset = compatibleDatasets.find((item) => item.datasetVersionId === value);
                setTrialDatasetVersionId(value);
                setTrialCaseId(dataset?.cases.find((item) => item.sceneVersionId === activeGroup.sceneVersionId)?.caseId ?? "");
                setTrialChecks([]);
              }}><option value="">选择已发布评测数据</option>{compatibleDatasets.map((item) => <option key={item.datasetVersionId} value={item.datasetVersionId}>{item.name} · v{item.version}</option>)}</select></label>
              <label><span>评测样本</span><select required value={trialCaseId} onChange={(event) => { setTrialCaseId(event.currentTarget.value); setTrialChecks([]); }}>{compatibleCases.map((item) => <option key={item.caseId} value={item.caseId}>{item.caseId} · {item.input}</option>)}</select></label>
            </div>
            <section className="se-calibration-step">
              <header><span>1</span><div><strong>模拟 Agent 输出</strong><small>填写要交给场景评估器判断的完整输出。</small></div></header>
              <textarea aria-label="模拟 Agent 输出" required value={trialOutput} onChange={(event) => { setTrialOutput(event.currentTarget.value); setTrialChecks([]); }} placeholder="输入一段模拟的 Agent 输出" />
            </section>
            <fieldset className="se-calibration-step se-calibration-judgment">
              <legend><span>2</span><span><strong>人工判断</strong><small>这是本次校准使用的正确答案。</small></span></legend>
              <div className="se-calibration-choices">
                <label><input type="radio" name={`calibration-${activeGroup.sceneVersionId}`} value="pass" checked={trialHumanJudgment === "pass"} onChange={() => { setTrialHumanJudgment("pass"); setTrialChecks([]); }} /><span><strong>通过</strong><small>这份输出符合业务场景标准</small></span></label>
                <label><input type="radio" name={`calibration-${activeGroup.sceneVersionId}`} value="fail" checked={trialHumanJudgment === "fail"} onChange={() => { setTrialHumanJudgment("fail"); setTrialChecks([]); }} /><span><strong>不通过</strong><small>这份输出不符合业务场景标准</small></span></label>
              </div>
            </fieldset>
            <section className="se-calibration-step se-calibration-run">
              <header><span>3</span><div><strong>试跑场景评估器</strong><small>系统将运行全部内部检查，并合并为一个判断。</small></div></header>
              <button type="submit" className="is-primary" disabled={Boolean(mutationKey) || !trialCase || !trialOutput.trim()}>{mutationKey === `trial-group-${activeGroup.sceneVersionId}` ? "评估中…" : "试跑场景评估器"}</button>
            </section>
            {combinedTrial && (
              <section className={`se-calibration-result is-${combinedTrial.tone}`} role="status">
                <header><span>4</span><div><strong>对比判断结果</strong><small>并列查看人工基准与场景评估器的合并判断。</small></div></header>
                <div className="se-calibration-comparison">
                  <div><span>人工判断</span><strong>{combinedTrial.humanJudgment}</strong></div>
                  <div><span>场景评估器综合判断</span><strong>{combinedTrial.evaluatorJudgment}</strong></div>
                </div>
                <div className="se-calibration-verdict"><span>准确性结论</span><strong>{combinedTrial.verdict}</strong><p>判断理由：{combinedTrial.explanation}</p></div>
                <details className="se-calibration-details"><summary>查看内部检查结果</summary><ul>{trialChecks.map((check) => <li key={check.label}><strong>{check.label}</strong><span>{trialOutcomeLabel(check.result.outcome)} · {check.result.errorMessage || check.result.reason || "无补充理由"}</span></li>)}</ul></details>
              </section>
            )}
          </form>
        )}

        <details className="se-advanced-editor">
          <summary>添加或调整内部检查</summary>
          <form onSubmit={(event) => {
            event.preventDefault();
            void mutate("save-evaluator", () => saveEvaluatorDraft({
              agentId,
              evaluatorId: randomId("evaluator"),
              expectedRevision: 0,
              name: evaluatorName,
              sceneVersionId: evaluatorSceneVersionId,
              kind: evaluatorKind,
              rule: evaluatorKind === "deterministic" ? rule : "",
              rubric: evaluatorKind === "llm_rubric" ? rubric : "",
              hardFailure,
            }), () => "内部检查草稿已保存，可继续校准场景评估器");
          }}>
            <label><span>检查名称</span><input required value={evaluatorName} onChange={(event) => setEvaluatorName(event.currentTarget.value)} /></label>
            <label><span>适用业务场景版本</span><select required value={evaluatorSceneVersionId} onChange={(event) => setEvaluatorSceneVersionId(event.currentTarget.value)}><option value="">选择已发布业务场景</option>{activeScenes.map((scene) => <option key={scene.sceneVersionId} value={scene.sceneVersionId}>{scene.name} · v{scene.version}</option>)}</select></label>
            <label><span>检查类型</span><select value={evaluatorKind} onChange={(event) => setEvaluatorKind(event.currentTarget.value as typeof evaluatorKind)}><option value="deterministic">受控确定性规则</option><option value="llm_rubric">大模型评分标准</option></select></label>
            {evaluatorKind === "deterministic" ? <label><span>确定性规则</span><select value={rule} onChange={(event) => setRule(event.currentTarget.value)}><option value="output_contains_expected">输出包含期望内容</option><option value="output_excludes_forbidden">输出不含禁止内容</option><option value="output_contains_tool_evidence">输出包含工具证据</option></select></label> : <label><span>评分标准</span><textarea required value={rubric} onChange={(event) => setRubric(event.currentTarget.value)} placeholder="逐项描述必须满足的业务标准" /></label>}
            <label className="se-check"><input type="checkbox" checked={hardFailure} onChange={(event) => setHardFailure(event.currentTarget.checked)} /><span>命中时视为严重失败</span></label>
            <button type="submit" className="is-primary" disabled={Boolean(mutationKey) || !evaluatorSceneVersionId}>保存内部检查草稿</button>
          </form>
        </details>
      </section>}

      {step === "policy" && <section className="se-work-card" id="policy-form">
        <header><div><h3>评测方案</h3><p>方案锁定业务场景、评测数据和场景评估器的完整版本口径。</p></div><span>{workspace.policies.length} 个版本</span></header>
        {!policyReady && <div className="se-note">请先为全部启用场景准备评测数据，并校准、发布对应的场景评估器。</div>}
        <form onSubmit={(event) => {
          event.preventDefault();
          if (!policyReady) return;
          const bindings: PolicySceneBinding[] = activeScenes.map((scene) => ({
            sceneVersionId: scene.sceneVersionId,
            datasetVersionId: policySelections[scene.sceneVersionId].datasetVersionId,
            evaluatorVersionIds: policySelections[scene.sceneVersionId].evaluatorVersionIds,
            requirement: scene.requirement,
          }));
          void mutate("save-policy", () => savePolicyDraft({ agentId, policyId: randomId("policy"), expectedRevision: 0, name: policyName, bindings }), () => "评测方案草稿已保存，可在下方发布版本");
        }}>
          <label><span>方案名称</span><input required value={policyName} onChange={(event) => setPolicyName(event.currentTarget.value)} /></label>
          {activeScenes.map((scene) => {
            const selection = policySelections[scene.sceneVersionId] ?? { datasetVersionId: "", evaluatorVersionIds: [] };
            const datasets = workspace.datasets.filter((item) => item.cases.some((sample) => sample.sceneVersionId === scene.sceneVersionId));
            const group = groups.find((item) => item.sceneVersionId === scene.sceneVersionId);
            return <fieldset className="se-policy-binding" key={scene.sceneVersionId}><legend>{scene.name} · {scene.requirement === "must_pass" ? "必过" : "观察"}</legend><label><span>评测数据版本</span><select required value={selection.datasetVersionId} onChange={(event) => setPolicySelections((current) => ({ ...current, [scene.sceneVersionId]: { ...selection, datasetVersionId: event.currentTarget.value } }))}><option value="">选择覆盖该业务场景的评测数据</option>{datasets.map((item) => <option key={item.datasetVersionId} value={item.datasetVersionId}>{item.name} · v{item.version}</option>)}</select></label><div className="se-policy-evaluator"><span>场景评估器</span><strong>{group?.publishState === "published" ? `已包含 ${group.latestPublishedVersionIds.length} 项内部检查` : "尚未完整发布"}</strong></div></fieldset>;
          })}
          <button type="submit" className="is-primary" disabled={Boolean(mutationKey) || !policyReady}>保存评测方案草稿</button>
        </form>
        <div className="se-version-list">{workspace.policyDrafts.map((draft) => {
          const actionKey = `publish-policy-${draft.policyId}-${draft.revision}`;
          const publishedVersion = latestVersionForDraft(workspace.policies.filter((item) => item.policyId === draft.policyId), draft.revision);
          const feedback = mutationFeedback?.key === actionKey ? mutationFeedback : null;
          return <div key={draft.policyId}><span><strong>{draft.name}</strong><small>草稿 r{draft.revision} · {draft.bindings.length} 个业务场景</small></span><span className="se-publish-control"><button type="button" disabled={Boolean(mutationKey) || publishedVersion !== null} onClick={() => void mutate(actionKey, () => publishPolicyVersion({ agentId, assetId: draft.policyId, draftRevision: draft.revision }), (version) => ({ message: `评测方案“${version.name}”已发布为 v${version.version}`, publishedVersion: version.version }))}>{publishedVersion !== null ? `已发布 v${publishedVersion}` : mutationKey === actionKey ? "正在发布…" : feedback?.kind === "error" ? "重新发布" : "发布评测方案"}</button>{feedback && <small className="se-action-feedback" role={feedback.kind === "error" ? "alert" : "status"}>{feedback.message}</small>}</span></div>;
        })}</div>
      </section>}
    </div>
  );
}
