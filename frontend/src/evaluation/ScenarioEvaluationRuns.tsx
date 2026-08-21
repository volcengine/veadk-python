import { useEffect, useMemo, useState } from "react";
import {
  cancelFormalEvaluation,
  retryInvalidEvaluationAttempt,
  startFormalEvaluation,
} from "../adk/scenarioEvaluation";
import type {
  AttemptEvidence,
  EvaluationRunVersion,
  QualityRecommendationValue,
  ScenarioEvaluationWorkspaceData,
} from "./types";
import type { MutationRunner } from "./scenarioEvaluationWorkspaceTypes";

const recommendationLabels: Record<QualityRecommendationValue, string> = {
  recommend: "建议发布",
  do_not_recommend: "不建议发布",
  indeterminate: "无法判断",
};

const runStatusLabels: Record<EvaluationRunVersion["status"], string> = {
  queued: "排队中",
  running: "评测中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

const outcomeLabels: Record<AttemptEvidence["outcome"], string> = {
  pass: "通过",
  fail: "不通过",
  infra_error: "基础设施异常",
  cancelled: "已取消",
};

const publishPathLabels = {
  normal: "标准发布",
  skip: "跳过评测发布",
  risk: "风险确认发布",
} as const;

function displayRunError(value: string): string {
  if (/^Candidate has no generated runtime project snapshot\.?$/i.test(value.trim())) {
    return "待测版本缺少运行项目快照，请返回 Agent 编辑流程重新生成待测版本。";
  }
  return value.replace(/\bCandidate\b/gi, "待测版本");
}

function displayTime(value: string): string {
  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp)
    ? value
    : new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(timestamp);
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="se-empty">
      <strong>{title}</strong>
      <span>{description}</span>
    </div>
  );
}

export function CandidatePanel({ workspace }: {
  workspace: ScenarioEvaluationWorkspaceData;
}) {
  return (
    <section className="se-work-card" id="candidate-list">
      <header><div><h3>待测版本</h3><p>待测版本是发布与正式评测共用的只读快照。</p></div><span>{workspace.candidates.length} 个版本</span></header>
      {workspace.candidates.length === 0 ? <EmptyState title="暂无待测版本" description="从 Agent 更新流程的部署确认页生成不可变版本。" /> : <div className="se-version-list">{workspace.candidates.map((item) => <div key={item.candidateId}><span><strong>待测版本 v{item.version}</strong><small>{displayTime(item.createdAt)} · 只读快照</small></span>{workspace.publishedVersion?.candidateId === item.candidateId && <em>当前已发布</em>}</div>)}</div>}
    </section>
  );
}

export function FormalEvaluationPanel({
  agentId,
  workspace,
  mutationKey,
  mutate,
  onStartEvaluation,
  onSkipEvaluation,
  skipEvaluationDisabled = false,
  skipEvaluationReason = "",
}: {
  agentId: string;
  workspace: ScenarioEvaluationWorkspaceData;
  mutationKey: string;
  mutate: MutationRunner;
  onStartEvaluation?: () => void;
  onSkipEvaluation?: () => void;
  skipEvaluationDisabled?: boolean;
  skipEvaluationReason?: string;
}) {
  const [candidateId, setCandidateId] = useState("");
  const [policyVersionId, setPolicyVersionId] = useState("");
  const latestCandidateId = [...workspace.candidates]
    .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt))[0]
    ?.candidateId ?? "";
  useEffect(() => {
    setCandidateId(latestCandidateId);
    setPolicyVersionId((value) => value || workspace.policies[workspace.policies.length - 1]?.policyVersionId || "");
  }, [latestCandidateId, workspace.policies]);
  const selectedCandidate = workspace.candidates.find((item) => item.candidateId === candidateId);
  const environmentFingerprint = selectedCandidate?.environmentFingerprint ?? "";
  const running = workspace.runs.find((item) => item.status === "queued" || item.status === "running");
  const latestFailed = [...workspace.runs]
    .filter((item) => item.status === "failed")
    .sort((left, right) => Date.parse(right.updatedAt) - Date.parse(left.updatedAt))[0]
    ?? null;

  return (
      <section className="se-work-card" id="formal-evaluation">
        <header><div><h3>正式评测</h3><p>完整评测方案中的必过场景不可删减，每个评测样本执行三次。</p></div></header>
        {latestFailed && (
          <div className="se-run-failure" role="alert">
            <strong>上次正式评测失败</strong>
            <p>{latestFailed.errorMessage
              ? displayRunError(latestFailed.errorMessage)
              : "本次评测未生成有效结果，请检查运行环境。"}</p>
            <small>修复后可重新发起评测。</small>
          </div>
        )}
        {running ? (
          <div className="se-running" role="status"><span className="loading-gap-spinner" /><div><strong>{running.status === "queued" ? "正在排队" : "正在评测"}</strong><small>评测完成前发布入口仅支持等待或取消。</small></div><button type="button" disabled={Boolean(mutationKey)} onClick={() => void mutate(`cancel-run-${running.evaluationId}`, () => cancelFormalEvaluation(agentId, running.evaluationId))}>取消评测</button></div>
        ) : (
          <form onSubmit={(event) => {
            event.preventDefault();
            onStartEvaluation?.();
            void mutate("start-run", () => startFormalEvaluation({ agentId, candidateId, policyVersionId, environmentFingerprint }));
          }}>
            <label><span>待测版本</span><select required value={candidateId} onChange={(event) => setCandidateId(event.currentTarget.value)}>{workspace.candidates.map((item) => <option key={item.candidateId} value={item.candidateId}>待测版本 v{item.version}</option>)}</select></label>
            <label><span>评测方案</span><select required value={policyVersionId} onChange={(event) => setPolicyVersionId(event.currentTarget.value)}>{workspace.policies.map((item) => <option key={item.policyVersionId} value={item.policyVersionId}>{item.name} · v{item.version}</option>)}</select></label>
            <div className="se-form-note"><span>评测环境</span><strong>使用待测版本冻结的部署配置</strong></div>
            <div className="se-form-actions">
              <button type="button" disabled={Boolean(mutationKey) || skipEvaluationDisabled || !onSkipEvaluation} onClick={onSkipEvaluation}>暂不评测，继续发布</button>
              <button type="submit" className="is-primary" disabled={Boolean(mutationKey) || !candidateId || !policyVersionId}>发起正式评测</button>
            </div>
            {skipEvaluationReason && <small className="se-action-disabled-reason">{skipEvaluationReason}</small>}
          </form>
        )}
      </section>
  );
}

export function SkippedEvaluationDecisionPanel() {
  return (
    <section className="se-work-card" id="quality-result">
      <header><div><h3>未运行正式评测</h3><p>当前待测版本没有质量建议或自动评测证据。</p></div><span>未评测</span></header>
      <div className="se-skip-decision" role="status">
        <strong>继续发布将进入跳过评测发布路径</strong>
        <p>发布前需要再次确认风险、填写跳过原因，并保留审计记录。</p>
      </div>
    </section>
  );
}

export function RunsPanel(props: {
  agentId: string;
  workspace: ScenarioEvaluationWorkspaceData;
  mutationKey: string;
  mutate: MutationRunner;
}) {
  return (
    <div className="se-two-column se-runs-layout">
      <CandidatePanel workspace={props.workspace} />
      <FormalEvaluationPanel {...props} />
    </div>
  );
}

export function ResultsPanel({ agentId, workspace, mutationKey, mutate }: {
  agentId: string;
  workspace: ScenarioEvaluationWorkspaceData;
  mutationKey: string;
  mutate: MutationRunner;
}) {
  const sortedRuns = useMemo(() => [...workspace.runs].sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt)), [workspace.runs]);
  const candidateVersionById = useMemo(
    () => new Map(workspace.candidates.map((item) => [item.candidateId, item.version])),
    [workspace.candidates],
  );
  return (
    <div className="se-results-grid">
      <section className="se-work-card se-evidence" id="quality-result">
        <header><div><h3>质量建议与证据</h3><p>从质量建议逐级查看业务场景、评测样本、执行记录、内部检查与调用链。</p></div><span>{sortedRuns.length} 次运行</span></header>
        {sortedRuns.length === 0 ? <EmptyState title="暂无正式评测" description="生成待测版本并选择已发布评测方案后，可发起首次评测。" /> : sortedRuns.map((run) => <RunEvidence key={`${run.evaluationId}-${run.revision}`} agentId={agentId} run={run} candidateVersion={candidateVersionById.get(run.candidateId) ?? null} mutationKey={mutationKey} mutate={mutate} />)}
      </section>
      <section className="se-work-card" id="failed-samples">
        <header><div><h3>失败样本</h3><p>业务失败会自动生成记录；只有同口径的新待测版本复测通过才会关闭。</p></div><span>{workspace.badcases.length} 条</span></header>
        {workspace.badcases.length === 0 ? <EmptyState title="暂无失败样本" description="正式评测样本失败后，问题会带着版本与证据自动进入这里。" /> : <div className="se-version-list">{workspace.badcases.map((item) => <div key={item.badcaseId}><span><strong>{item.caseId}</strong><small>{item.status === "closed" ? "已关闭" : item.status === "verifying" ? "待复测" : "待修复"} · 来源评测 {item.sourceEvaluationId}</small></span><em>{item.status === "closed" ? "已关闭" : item.status === "verifying" ? "待复测" : "待修复"}</em></div>)}</div>}
        <div className="se-published-summary"><span>已发布版本</span>{workspace.publishedVersion ? <strong>v{workspace.publishedVersion.version} · {publishPathLabels[workspace.publishedVersion.publishPath]}</strong> : <strong>尚未发布</strong>}</div>
      </section>
    </div>
  );
}

function RunEvidence({ agentId, run, candidateVersion, mutationKey, mutate }: {
  agentId: string;
  run: EvaluationRunVersion;
  candidateVersion: number | null;
  mutationKey: string;
  mutate: MutationRunner;
}) {
  const label = run.recommendation ? recommendationLabels[run.recommendation.value] : runStatusLabels[run.status];
  return (
    <details className="se-run-evidence">
      <summary><span><strong>{label}</strong><small>{displayTime(run.updatedAt)} · {candidateVersion == null ? "待测版本号不可用" : `待测版本 v${candidateVersion}`}</small></span><em>{runStatusLabels[run.status]}</em></summary>
      {run.errorMessage && <p className="se-evidence-error">{displayRunError(run.errorMessage)}</p>}
      {run.scenes.map((scene) => (
        <details key={scene.sceneVersionId}>
          <summary><strong>业务场景</strong><span>{scene.sceneVersionId} · {scene.requirement === "must_pass" ? "必过" : "观察"}</span></summary>
          {scene.cases.map((item) => (
            <details key={item.caseVersionId}>
              <summary><strong>评测样本</strong><span>{item.caseVersionId}</span></summary>
              <AttemptEvidenceList agentId={agentId} run={run} sceneVersionId={scene.sceneVersionId} caseId={item.caseVersionId} target="candidate" attempts={item.candidateAttempts} mutationKey={mutationKey} mutate={mutate} />
              {item.baselineAttempts.length > 0 && <AttemptEvidenceList agentId={agentId} run={run} sceneVersionId={scene.sceneVersionId} caseId={item.caseVersionId} target="baseline" attempts={item.baselineAttempts} mutationKey={mutationKey} mutate={mutate} />}
            </details>
          ))}
        </details>
      ))}
    </details>
  );
}

function AttemptEvidenceList({ agentId, run, sceneVersionId, caseId, target, attempts, mutationKey, mutate }: {
  agentId: string;
  run: EvaluationRunVersion;
  sceneVersionId: string;
  caseId: string;
  target: "candidate" | "baseline";
  attempts: AttemptEvidence[];
  mutationKey: string;
  mutate: MutationRunner;
}) {
  return <section className="se-attempt-group"><h5>{target === "candidate" ? "待测版本" : "对比基线"}</h5>{attempts.map((attempt) => (
    <details key={`${target}-${attempt.attemptIndex}`}>
      <summary><strong>第 {attempt.attemptIndex} 次执行</strong><span>{outcomeLabels[attempt.outcome]}{attempt.manualRetryCount ? ` · 手动重试 ${attempt.manualRetryCount} 次` : ""}</span></summary>
      {attempt.evaluatorResults.map((result) => <div className="se-evaluator-result" key={result.evaluatorVersionId}><strong>内部检查</strong><span>{result.evaluatorVersionId} · {outcomeLabels[result.outcome]}</span><p>{result.reason || "无补充理由"}</p></div>)}
      {attempt.errorMessage && <p className="se-evidence-error">{attempt.errorMessage}</p>}
      {attempt.traceRef ? <a href={attempt.traceRef} target="_blank" rel="noreferrer">打开调用链</a> : <span className="se-muted">调用链不可用</span>}
      {attempt.supersededInvalidAttempts.length > 0 && <details className="se-retry-history"><summary>查看被替换的异常记录</summary>{attempt.supersededInvalidAttempts.map((history, index) => <p key={`${history.sessionId}-${index}`}>{history.sessionId || "无会话记录"} · {history.errorMessage || "基础设施异常"}</p>)}</details>}
      {attempt.outcome === "infra_error" && <button type="button" disabled={Boolean(mutationKey)} onClick={() => void mutate(`retry-${run.evaluationId}-${target}-${caseId}-${attempt.attemptIndex}`, () => retryInvalidEvaluationAttempt(run.evaluationId, { agentId, sceneVersionId, caseId, target, attemptIndex: attempt.attemptIndex }))}>仅重试无效执行</button>}
    </details>
  ))}</section>;
}
