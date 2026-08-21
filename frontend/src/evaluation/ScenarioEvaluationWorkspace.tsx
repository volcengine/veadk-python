import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  convertFeedbackCandidate,
  finalizeScenarioPublishRecovery,
  getScenarioEvaluationWorkspace,
  mergeFeedbackCandidate,
  publishDatasetVersion,
  publishSceneVersion,
  rejectFeedbackCandidate,
  reviewFeedbackCandidate,
  saveDatasetDraft,
  saveSceneDraft,
  ScenarioEvaluationApiError,
} from "../adk/scenarioEvaluation";
import type {
  EvaluationRunVersion,
  FeedbackCandidateVersion,
  QualityRecommendationValue,
  ScenarioEvaluationWorkspaceData,
} from "./types";
import {
  buildPublishActionPresentation,
  latestVersionForDraft,
} from "./scenarioEvaluationPresentation";
import { buildSceneEvaluatorGroups } from "./scenarioEvaluatorGroups";
import {
  buildScenarioEvaluationJourney,
  type JourneyActionId,
  type JourneyStepId,
} from "./scenarioEvaluationJourney";
import { ScenarioEvaluationJourneyView } from "./ScenarioEvaluationJourneyView";
import { GovernancePanel as GroupedGovernancePanel } from "./ScenarioEvaluationPreparation";
import {
  CandidatePanel,
  FormalEvaluationPanel,
  ResultsPanel,
  SkippedEvaluationDecisionPanel,
} from "./ScenarioEvaluationRuns";
import type {
  MutationFeedbackState,
  MutationRunner,
  MutationSuccess,
} from "./scenarioEvaluationWorkspaceTypes";
import "./ScenarioEvaluationWorkspace.css";

type FeedbackAction = "review" | "reject" | "merge" | "convert";

const recommendationLabels: Record<QualityRecommendationValue, string> = {
  recommend: "建议发布",
  do_not_recommend: "不建议发布",
  indeterminate: "无法判断",
};

function newestRun(runs: EvaluationRunVersion[]): EvaluationRunVersion | null {
  return [...runs].sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt))[0] ?? null;
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

function randomId(prefix: string): string {
  const suffix = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return `${prefix}-${suffix}`;
}

function splitLines(value: string): string[] {
  return value.split("\n").map((item) => item.trim()).filter(Boolean);
}

function lastItem<T>(items: T[]): T | undefined {
  return items[items.length - 1];
}

function mutationMessage(error: unknown): string {
  if (error instanceof ScenarioEvaluationApiError) return error.message;
  return error instanceof Error ? error.message : String(error);
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="se-empty">
      <strong>{title}</strong>
      <span>{description}</span>
    </div>
  );
}

function PublishVersionControl({
  actionKey,
  mutationKey,
  mutationFeedback,
  publishedVersion,
  onPublish,
}: {
  actionKey: string;
  mutationKey: string;
  mutationFeedback: MutationFeedbackState | null;
  publishedVersion: number | null;
  onPublish: () => void;
}) {
  const feedback = mutationFeedback?.key === actionKey
    ? {
        kind: mutationFeedback.kind,
        message: mutationFeedback.message,
        publishedVersion: mutationFeedback.publishedVersion,
      }
    : null;
  const presentation = buildPublishActionPresentation({
    isRunning: mutationKey === actionKey,
    publishedVersion,
    feedback,
  });
  const statusId = `${actionKey.replace(/[^a-zA-Z0-9_-]/g, "-")}-status`;

  return (
    <span className={`se-publish-control is-${presentation.tone}`}>
      <button
        type="button"
        disabled={Boolean(mutationKey) || presentation.disabled}
        aria-busy={mutationKey === actionKey}
        aria-describedby={presentation.status ? statusId : undefined}
        onClick={onPublish}
      >
        {presentation.label}
      </button>
      {presentation.status && (
        <small
          id={statusId}
          className="se-action-feedback"
          role={presentation.tone === "error" ? "alert" : undefined}
        >
          {presentation.status}
        </small>
      )}
    </span>
  );
}

function QualityStrip({
  workspace,
  evaluationSkipped = false,
}: {
  workspace: ScenarioEvaluationWorkspaceData;
  evaluationSkipped?: boolean;
}) {
  const latestCandidate = [...workspace.candidates]
    .sort((left, right) => Date.parse(right.createdAt) - Date.parse(left.createdAt))[0];
  const run = newestRun(
    latestCandidate
      ? workspace.runs.filter((item) => item.candidateId === latestCandidate.candidateId)
      : [],
  );
  const recommendation = run?.recommendation?.value ?? null;
  const running = run?.status === "queued" || run?.status === "running";
  const validity = evaluationSkipped
    ? "已选择暂不评测"
    : running
    ? "评测运行中"
    : run?.status === "cancelled"
      ? "本次已取消"
      : run?.status === "failed"
        ? "评测异常"
        : recommendation
          ? "证据已生成"
          : "尚未评测";
  const path = evaluationSkipped
    ? "跳过评测发布"
    : running
    ? "等待或取消评测"
    : recommendation === "recommend"
      ? "普通发布"
      : recommendation
        ? "风险发布"
        : "跳过评测发布";
  const riskCount = (run?.recommendation?.warningSceneVersionIds.length ?? 0)
    + workspace.badcases.filter((item) => item.status !== "closed").length;

  return (
    <section className={`se-quality-strip${recommendation ? ` is-${recommendation}` : ""}`} aria-label="发布质量状态">
      <div>
        <span>评测有效性</span>
        <strong>{validity}</strong>
      </div>
      <div>
        <span>质量建议</span>
        <strong>{recommendation ? recommendationLabels[recommendation] : "未形成结论"}</strong>
      </div>
      <div>
        <span>风险项</span>
        <strong>{riskCount} 项</strong>
      </div>
      <div>
        <span>对比基线</span>
        <strong>{run?.baselineVersionId ? `线上版本 ${run.baselineVersionId}` : "首次发布绝对标准"}</strong>
      </div>
      <div>
        <span>当前发布路径</span>
        <strong>{path}</strong>
      </div>
      <p>质量建议不等于发布权限；最终发布由有权限的开发者或管理员主动确认。</p>
    </section>
  );
}

interface ScenarioEvaluationWorkspaceProps {
  agentId: string;
  onOpenAgentUpdate?: () => void;
  updateUnavailableReason?: string;
  updateLoading?: boolean;
}

export function ScenarioEvaluationWorkspace({
  agentId,
  onOpenAgentUpdate,
  updateUnavailableReason = "",
  updateLoading = false,
}: ScenarioEvaluationWorkspaceProps) {
  const [selectedStepId, setSelectedStepId] = useState<JourneyStepId>("scene");
  const [workspace, setWorkspace] = useState<ScenarioEvaluationWorkspaceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ScenarioEvaluationApiError | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const [mutationKey, setMutationKey] = useState("");
  const [mutationFeedback, setMutationFeedback] = useState<MutationFeedbackState | null>(null);
  const [evaluationSkipped, setEvaluationSkipped] = useState(false);
  const requestSequenceRef = useRef(0);
  const mutationInFlightRef = useRef(false);
  const evaluatorGroups = useMemo(
    () => workspace ? buildSceneEvaluatorGroups(workspace) : [],
    [workspace],
  );
  const journey = useMemo(
    () => workspace
      ? buildScenarioEvaluationJourney(workspace, evaluatorGroups, { evaluationSkipped })
      : null,
    [evaluationSkipped, evaluatorGroups, workspace],
  );

  const refresh = () => setReloadToken((value) => value + 1);

  useEffect(() => {
    if (journey) setSelectedStepId(journey.currentStepId);
  }, [agentId, journey?.currentStepId]);

  useEffect(() => {
    setEvaluationSkipped(false);
  }, [agentId]);

  useEffect(() => {
    const controller = new AbortController();
    const sequence = requestSequenceRef.current + 1;
    requestSequenceRef.current = sequence;
    setLoading(true);
    setError(null);
    void getScenarioEvaluationWorkspace(agentId, controller.signal)
      .then((next) => {
        if (sequence !== requestSequenceRef.current || next.agentId !== agentId) return;
        setWorkspace(next);
      })
      .catch((caught: unknown) => {
        if (controller.signal.aborted || sequence !== requestSequenceRef.current) return;
        setError(
          caught instanceof ScenarioEvaluationApiError
            ? caught
            : new ScenarioEvaluationApiError(0, "network_error", mutationMessage(caught)),
        );
      })
      .finally(() => {
        if (!controller.signal.aborted && sequence === requestSequenceRef.current) setLoading(false);
      });
    return () => controller.abort();
  }, [agentId, reloadToken]);

  const hasActiveEvaluation = workspace?.runs.some(
    (run) => run.status === "queued" || run.status === "running",
  ) ?? false;

  useEffect(() => {
    if (!hasActiveEvaluation) return undefined;
    const timer = window.setInterval(
      () => setReloadToken((value) => value + 1),
      1500,
    );
    return () => window.clearInterval(timer);
  }, [hasActiveEvaluation]);

  async function mutate<T>(
    key: string,
    action: () => Promise<T>,
    successMessage?: (result: T) => MutationSuccess,
  ): Promise<T | undefined> {
    if (mutationInFlightRef.current) return undefined;
    mutationInFlightRef.current = true;
    setMutationKey(key);
    setMutationFeedback(null);
    try {
      const result = await action();
      const success = successMessage?.(result);
      if (success) {
        setMutationFeedback({
          key,
          kind: "success",
          ...(typeof success === "string" ? { message: success } : success),
        });
      }
      refresh();
      return result;
    } catch (caught) {
      setMutationFeedback({ key, kind: "error", message: mutationMessage(caught) });
      refresh();
      return undefined;
    } finally {
      mutationInFlightRef.current = false;
      setMutationKey("");
    }
  }

  if (loading && !workspace) {
    return <div className="se-state" role="status"><span className="loading-gap-spinner" />正在加载场景评测工作区</div>;
  }

  if (error && !workspace) {
    const forbidden = error.status === 403;
    return (
      <div className="se-state is-error" role="alert">
        <strong>{forbidden ? "权限不足" : "场景评测暂不可用"}</strong>
        <span>{error.message}</span>
        {error.retryable && <button type="button" onClick={refresh}>重试</button>}
      </div>
    );
  }

  if (!workspace || !journey) return null;
  const activeJourney = journey;

  const assetPublishFeedback = mutationFeedback
    && /^publish-(scene|dataset|evaluator|policy)-/.test(mutationFeedback.key);

  function scrollToTarget(targetId?: string) {
    if (!targetId) return;
    requestAnimationFrame(() => {
      document.getElementById(targetId)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function handlePrimaryAction(action: JourneyActionId) {
    if (action === "open_agent_update" || action === "publish" || action === "skip_publish") {
      onOpenAgentUpdate?.();
      return;
    }
    const stepId: JourneyStepId = action === "create_scene"
      ? "scene"
      : action === "create_dataset"
        ? "dataset"
        : action === "configure_evaluator"
          ? "evaluator"
          : action === "publish_policy"
            ? "policy"
            : action === "view_failed_samples" || action === "review_result"
              ? "decision"
              : "run";
    setSelectedStepId(stepId);
    scrollToTarget(activeJourney.nextAction.targetId);
  }

  function selectPreviousStep() {
    const selectedIndex = activeJourney.steps.findIndex((step) => step.id === selectedStepId);
    if (selectedIndex > 0) setSelectedStepId(activeJourney.steps[selectedIndex - 1].id);
  }

  const needsAgentUpdate = activeJourney.nextAction.id === "open_agent_update"
    || activeJourney.nextAction.id === "publish"
    || activeJourney.nextAction.id === "skip_publish";
  const primaryActionDisabled = needsAgentUpdate
    && (updateLoading || Boolean(updateUnavailableReason) || !onOpenAgentUpdate);
  const primaryActionReason = needsAgentUpdate
    ? updateLoading
      ? "正在检查 Agent 更新能力"
      : updateUnavailableReason || (!onOpenAgentUpdate ? "当前入口暂时无法打开 Agent 编辑流程" : "")
    : "";

  return (
    <div className="se-workspace" aria-busy={loading || Boolean(mutationKey)}>
      <div className="se-live-region" aria-live="polite" aria-atomic="true">
        {mutationKey
          ? mutationKey.startsWith("publish-")
            ? "正在发布版本"
            : "操作进行中"
          : mutationFeedback?.message ?? ""}
      </div>
      <QualityStrip workspace={workspace} evaluationSkipped={evaluationSkipped} />
      {error && (
        <div className="se-inline-alert" role="alert">
          <span>{error.message}</span>
          <button type="button" onClick={refresh}>重试</button>
        </div>
      )}
      {mutationFeedback?.kind === "error" && !assetPublishFeedback && (
        <div className="se-inline-alert" role="alert">{mutationFeedback.message}</div>
      )}
      {mutationFeedback?.kind === "success" && (
        <div className="se-inline-alert is-success" role="status">{mutationFeedback.message}</div>
      )}
      {workspace.publishRecoveryIssues.map((issue) => (
        <div className="se-inline-alert is-warning" role="alert" key={issue.intent.intentId}>
          <span>运行环境已部署，但已发布版本或发布记录尚未完整写入。</span>
          <button type="button" disabled={Boolean(mutationKey)} onClick={() => void mutate(`recover-publish-${issue.intent.intentId}`, () => finalizeScenarioPublishRecovery(issue.intent.intentId, { agentId }))}>重试审计收口</button>
        </div>
      ))}
      <ScenarioEvaluationJourneyView
        journey={activeJourney}
        selectedStepId={selectedStepId}
        onSelectStep={setSelectedStepId}
        onPrevious={selectPreviousStep}
        onPrimaryAction={handlePrimaryAction}
        primaryActionDisabled={primaryActionDisabled}
        primaryActionReason={primaryActionReason}
      >
        {selectedStepId === "scene" && <StandardsPanel step="scene" agentId={agentId} workspace={workspace} mutationKey={mutationKey} mutationFeedback={mutationFeedback} mutate={mutate} />}
        {selectedStepId === "dataset" && (
          <div className="se-section-stack">
            <StandardsPanel step="dataset" agentId={agentId} workspace={workspace} mutationKey={mutationKey} mutationFeedback={mutationFeedback} mutate={mutate} />
            <details className="se-supporting-source">
              <summary>从用户反馈补充评测样本</summary>
              <FeedbackPanel agentId={agentId} items={workspace.feedbackCandidates} scenes={workspace.scenes} mutationKey={mutationKey} mutate={mutate} />
            </details>
          </div>
        )}
        {selectedStepId === "evaluator" && <GroupedGovernancePanel step="evaluator" agentId={agentId} workspace={workspace} mutationKey={mutationKey} mutationFeedback={mutationFeedback} mutate={mutate} />}
        {selectedStepId === "policy" && <GroupedGovernancePanel step="policy" agentId={agentId} workspace={workspace} mutationKey={mutationKey} mutationFeedback={mutationFeedback} mutate={mutate} />}
        {selectedStepId === "candidate" && <CandidatePanel workspace={workspace} />}
        {selectedStepId === "run" && <FormalEvaluationPanel
          agentId={agentId}
          workspace={workspace}
          mutationKey={mutationKey}
          mutate={mutate}
          onStartEvaluation={() => setEvaluationSkipped(false)}
          onSkipEvaluation={() => setEvaluationSkipped(true)}
          skipEvaluationDisabled={updateLoading || Boolean(updateUnavailableReason) || !onOpenAgentUpdate}
          skipEvaluationReason={updateLoading
            ? "正在检查 Agent 更新能力"
            : updateUnavailableReason || (!onOpenAgentUpdate ? "当前入口暂时无法打开 Agent 发布流程" : "")}
        />}
        {selectedStepId === "decision" && (activeJourney.nextAction.id === "skip_publish"
          ? <SkippedEvaluationDecisionPanel />
          : <ResultsPanel agentId={agentId} workspace={workspace} mutationKey={mutationKey} mutate={mutate} />)}
      </ScenarioEvaluationJourneyView>
    </div>
  );
}

function FeedbackPanel({
  agentId,
  items,
  scenes,
  mutationKey,
  mutate,
}: {
  agentId: string;
  items: FeedbackCandidateVersion[];
  scenes: ScenarioEvaluationWorkspaceData["scenes"];
  mutationKey: string;
  mutate: MutationRunner;
}) {
  const [activeId, setActiveId] = useState("");
  const [action, setAction] = useState<FeedbackAction>("review");
  const [input, setInput] = useState("");
  const [expectedOutput, setExpectedOutput] = useState("");
  const [detail, setDetail] = useState("");
  const [targetId, setTargetId] = useState("");
  const [datasetName, setDatasetName] = useState("反馈回归集");
  const [redactionConfirmed, setRedactionConfirmed] = useState(false);
  const [sceneVersionId, setSceneVersionId] = useState("");
  const [passCriteria, setPassCriteria] = useState("");

  const pending = items.filter((item) => item.decision === "pending");

  function open(item: FeedbackCandidateVersion, nextAction: FeedbackAction) {
    setActiveId(item.candidateId);
    setAction(nextAction);
    setInput(item.reviewedInput || item.source.input);
    setExpectedOutput(item.expectedOutput || item.source.output);
    setDetail("");
    setTargetId("");
    setRedactionConfirmed(false);
    const scene = lastItem(scenes.filter((candidate) => candidate.enabled));
    setSceneVersionId(scene?.sceneVersionId ?? "");
    setPassCriteria(scene?.passCriteria.join("\n") ?? "");
  }

  function submit(event: FormEvent, item: FeedbackCandidateVersion) {
    event.preventDefault();
    const key = `feedback-${item.candidateId}-${action}`;
    if (action === "review") {
      void mutate(key, () => reviewFeedbackCandidate(item.candidateId, {
        agentId,
        expectedRevision: item.revision,
        input,
        expectedOutput,
        comment: detail,
      }));
    } else if (action === "reject") {
      void mutate(key, () => rejectFeedbackCandidate(item.candidateId, {
        agentId,
        expectedRevision: item.revision,
        reason: detail,
      }));
    } else if (action === "merge") {
      void mutate(key, () => mergeFeedbackCandidate(item.candidateId, {
        agentId,
        expectedRevision: item.revision,
        targetCandidateId: targetId,
        reason: detail,
      }));
    } else {
      const existing = items.find((candidate) => candidate.targetDatasetId);
      void mutate(key, () => convertFeedbackCandidate(item.candidateId, {
        agentId,
        expectedRevision: item.revision,
        datasetId: existing?.targetDatasetId ?? randomId("dataset"),
        expectedDatasetRevision: 0,
        datasetName,
        sceneVersionId,
        passCriteria: splitLines(passCriteria),
        redactionStatus: redactionConfirmed ? "redacted" : "pending",
      }));
    }
  }

  return (
    <section className="se-section-stack">
      <header className="se-section-head"><div><h3>反馈候选</h3><p>原始反馈保持只读，审核决定另存为新版本。</p></div><span>{pending.length} 条待审核</span></header>
      {items.length === 0 ? (
        <EmptyState title="暂无反馈候选" description="用户点赞或点踩后，带有运行证据的记录会出现在这里。" />
      ) : (
        <div className="se-card-list">
          {items.map((item) => (
            <article className="se-record-card" key={`${item.candidateId}-${item.revision}`}>
              <header><div><strong>{item.source.rating === "good" ? "正向反馈" : "问题反馈"}</strong><span>{item.decision}</span></div><time>{displayTime(item.createdAt)}</time></header>
              <dl><div><dt>用户输入</dt><dd>{item.source.input}</dd></div><div><dt>Agent 输出</dt><dd>{item.source.output}</dd></div></dl>
              <footer>
                {(["review", "reject", "merge", "convert"] as const).map((nextAction) => {
                  const allowed = nextAction === "convert"
                    ? item.decision === "reviewed"
                    : item.decision === "pending";
                  return <button
                    type="button"
                    key={nextAction}
                    disabled={Boolean(mutationKey) || !allowed}
                    onClick={() => open(item, nextAction)}
                  >
                    {{ review: "审核", reject: "驳回", merge: "合并", convert: "转为评测样本" }[nextAction]}
                  </button>;
                })}
              </footer>
              {activeId === item.candidateId && (item.decision === "pending" || (item.decision === "reviewed" && action === "convert")) && (
                <form className="se-inline-form" onSubmit={(event) => submit(event, item)}>
                  {action === "review" && <><label><span>审核后输入</span><textarea required value={input} onChange={(event) => setInput(event.currentTarget.value)} /></label><label><span>期望输出</span><textarea required value={expectedOutput} onChange={(event) => setExpectedOutput(event.currentTarget.value)} /></label></>}
                  {action === "merge" && <label><span>目标反馈编号</span><input required value={targetId} onChange={(event) => setTargetId(event.currentTarget.value)} /></label>}
                  {action === "convert" && <><label><span>评测数据名称</span><input required value={datasetName} onChange={(event) => setDatasetName(event.currentTarget.value)} /></label><label><span>归属业务场景版本</span><select required value={sceneVersionId} onChange={(event) => { const value = event.currentTarget.value; setSceneVersionId(value); setPassCriteria(scenes.find((scene) => scene.sceneVersionId === value)?.passCriteria.join("\n") ?? ""); }}><option value="">选择已发布业务场景</option>{scenes.filter((scene) => scene.enabled).map((scene) => <option key={scene.sceneVersionId} value={scene.sceneVersionId}>{scene.name} · v{scene.version}</option>)}</select></label><label><span>通过标准（每行一项）</span><textarea required value={passCriteria} onChange={(event) => setPassCriteria(event.currentTarget.value)} /></label><label className="se-check"><input type="checkbox" required checked={redactionConfirmed} onChange={(event) => setRedactionConfirmed(event.currentTarget.checked)} /><span>已检查并完成敏感信息脱敏</span></label></>}
                  {action !== "convert" && <label><span>{action === "review" ? "审核备注" : "原因"}</span><input required={action !== "review"} value={detail} onChange={(event) => setDetail(event.currentTarget.value)} /></label>}
                  <div><button type="button" onClick={() => setActiveId("")}>取消</button><button type="submit" className="is-primary" disabled={Boolean(mutationKey)}>确认</button></div>
                </form>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function StandardsPanel({ step, agentId, workspace, mutationKey, mutationFeedback, mutate }: {
  step: "scene" | "dataset";
  agentId: string;
  workspace: ScenarioEvaluationWorkspaceData;
  mutationKey: string;
  mutationFeedback: MutationFeedbackState | null;
  mutate: MutationRunner;
}) {
  const [sceneName, setSceneName] = useState("");
  const [sceneDescription, setSceneDescription] = useState("");
  const [sceneTask, setSceneTask] = useState("");
  const [scenePassCriteria, setScenePassCriteria] = useState("");
  const [sceneHardFailures, setSceneHardFailures] = useState("");
  const [sceneOwner, setSceneOwner] = useState("");
  const [requirement, setRequirement] = useState<"must_pass" | "observation">("must_pass");
  const [datasetName, setDatasetName] = useState("");
  const [caseInput, setCaseInput] = useState("");
  const [caseExpected, setCaseExpected] = useState("");
  const [caseContext, setCaseContext] = useState("");
  const [caseTestDataRefs, setCaseTestDataRefs] = useState("");
  const [casePrerequisites, setCasePrerequisites] = useState("");
  const [caseSourceType, setCaseSourceType] = useState<"manual" | "file" | "debug_run">("manual");
  const [caseSourceRefs, setCaseSourceRefs] = useState("studio:manual");
  const [caseSceneVersionId, setCaseSceneVersionId] = useState("");
  const [casePassCriteria, setCasePassCriteria] = useState("");
  const [caseForbidden, setCaseForbidden] = useState("");
  const [caseRedactionConfirmed, setCaseRedactionConfirmed] = useState(false);

  useEffect(() => {
    const selected = workspace.scenes.find((scene) => scene.sceneVersionId === caseSceneVersionId)
      ?? lastItem(workspace.scenes.filter((scene) => scene.enabled));
    if (!selected) return;
    setCaseSceneVersionId(selected.sceneVersionId);
    setCasePassCriteria((value) => value || selected.passCriteria.join("\n"));
  }, [caseSceneVersionId, workspace.scenes]);

  return (
    <div className="se-section-stack">
      {step === "scene" && <section className="se-work-card" id="scene-form">
        <header><div><h3>业务场景</h3><p>开发者保存草稿，管理员发布不可变版本。</p></div><span>{workspace.scenes.length} 个版本</span></header>
        <form onSubmit={(event) => {
          event.preventDefault();
          void mutate("save-scene", () => saveSceneDraft({ agentId, sceneId: randomId("scene"), expectedRevision: 0, name: sceneName, description: sceneDescription, userTask: sceneTask, passCriteria: splitLines(scenePassCriteria), hardFailureConditions: splitLines(sceneHardFailures), ownerId: sceneOwner, linkedDatasetIds: [], enabled: true, requirement }), () => "业务场景草稿已保存，可在下方发布版本");
        }}>
          <label><span>场景名称</span><input required value={sceneName} onChange={(event) => setSceneName(event.currentTarget.value)} /></label>
          <label><span>场景说明</span><textarea required value={sceneDescription} onChange={(event) => setSceneDescription(event.currentTarget.value)} /></label>
          <label><span>用户任务</span><textarea required value={sceneTask} onChange={(event) => setSceneTask(event.currentTarget.value)} /></label>
          <label><span>通过标准（每行一项）</span><textarea required value={scenePassCriteria} onChange={(event) => setScenePassCriteria(event.currentTarget.value)} /></label>
          <label><span>硬失败条件（每行一项）</span><textarea required value={sceneHardFailures} onChange={(event) => setSceneHardFailures(event.currentTarget.value)} /></label>
          <label><span>负责人</span><input required value={sceneOwner} onChange={(event) => setSceneOwner(event.currentTarget.value)} /></label>
          <label><span>场景属性</span><select value={requirement} onChange={(event) => setRequirement(event.currentTarget.value as typeof requirement)}><option value="must_pass">必过</option><option value="observation">观察</option></select></label>
          <button type="submit" className="is-primary" disabled={Boolean(mutationKey)}>保存场景草稿</button>
        </form>
        <div className="se-version-list">
          {workspace.sceneDrafts.map((draft) => {
            const actionKey = `publish-scene-${draft.sceneId}-${draft.revision}`;
            const publishedVersion = latestVersionForDraft(
              workspace.scenes.filter((item) => item.sceneId === draft.sceneId),
              draft.revision,
            );
            return <div key={draft.sceneId}><span><strong>{draft.name}</strong><small>草稿 r{draft.revision} · {draft.requirement === "must_pass" ? "必过" : "观察"}</small></span><PublishVersionControl actionKey={actionKey} mutationKey={mutationKey} mutationFeedback={mutationFeedback} publishedVersion={publishedVersion} onPublish={() => void mutate(actionKey, () => publishSceneVersion({ agentId, assetId: draft.sceneId, draftRevision: draft.revision }), (version) => ({ message: `业务场景“${version.name}”已发布为 v${version.version}`, publishedVersion: version.version }))} /></div>;
          })}
        </div>
      </section>}
      {step === "dataset" && <section className="se-work-card" id="dataset-form">
        <header><div><h3>评测数据</h3><p>先创建一条结构化评测样本，后续可持续加入审核反馈。</p></div><span>{workspace.datasets.length} 个版本</span></header>
        <form onSubmit={(event) => {
          event.preventDefault();
          void mutate("save-dataset", () => saveDatasetDraft({ agentId, datasetId: randomId("dataset"), expectedRevision: 0, name: datasetName, cases: [{ caseId: randomId("case"), sceneVersionId: caseSceneVersionId, input: caseInput, expectedOutput: caseExpected, preloadedContext: caseContext, testDataRefs: splitLines(caseTestDataRefs), prerequisites: splitLines(casePrerequisites), passCriteria: splitLines(casePassCriteria), labels: [], forbiddenOutput: splitLines(caseForbidden), sourceFeedbackCandidateIds: [], sourceType: caseSourceType, sourceRefs: splitLines(caseSourceRefs), redactionStatus: caseRedactionConfirmed ? "redacted" : "pending" }] }), () => "评测数据草稿已保存，可在下方发布版本");
        }}>
          <label><span>评测数据名称</span><input required value={datasetName} onChange={(event) => setDatasetName(event.currentTarget.value)} /></label>
          <label><span>业务场景版本</span><select required value={caseSceneVersionId} onChange={(event) => { const value = event.currentTarget.value; setCaseSceneVersionId(value); setCasePassCriteria(workspace.scenes.find((scene) => scene.sceneVersionId === value)?.passCriteria.join("\n") ?? ""); }}><option value="">选择已发布业务场景</option>{workspace.scenes.filter((scene) => scene.enabled).map((scene) => <option key={scene.sceneVersionId} value={scene.sceneVersionId}>{scene.name} · v{scene.version}</option>)}</select></label>
          <label><span>评测样本输入</span><textarea required value={caseInput} onChange={(event) => setCaseInput(event.currentTarget.value)} /></label>
          <label><span>预置上下文</span><textarea value={caseContext} onChange={(event) => setCaseContext(event.currentTarget.value)} /></label>
          <label><span>测试数据 / 环境引用（每行一项）</span><textarea value={caseTestDataRefs} onChange={(event) => setCaseTestDataRefs(event.currentTarget.value)} /></label>
          <label><span>前置条件（每行一项）</span><textarea value={casePrerequisites} onChange={(event) => setCasePrerequisites(event.currentTarget.value)} /></label>
          <label><span>期望输出</span><textarea required value={caseExpected} onChange={(event) => setCaseExpected(event.currentTarget.value)} /></label>
          <label><span>通过标准（每行一项）</span><textarea required value={casePassCriteria} onChange={(event) => setCasePassCriteria(event.currentTarget.value)} /></label>
          <label><span>禁止结果（每行一项）</span><textarea value={caseForbidden} onChange={(event) => setCaseForbidden(event.currentTarget.value)} /></label>
          <label><span>来源类型</span><select value={caseSourceType} onChange={(event) => { const value = event.currentTarget.value as typeof caseSourceType; setCaseSourceType(value); setCaseSourceRefs(value === "manual" ? "studio:manual" : ""); }}><option value="manual">人工新增</option><option value="file">文件导入</option><option value="debug_run">调试、运行或调用链</option></select></label>
          <label><span>来源引用（每行一项）</span><textarea required value={caseSourceRefs} onChange={(event) => setCaseSourceRefs(event.currentTarget.value)} /></label>
          <label className="se-check"><input type="checkbox" required checked={caseRedactionConfirmed} onChange={(event) => setCaseRedactionConfirmed(event.currentTarget.checked)} /><span>已检查来源并完成敏感信息脱敏</span></label>
          <button type="submit" className="is-primary" disabled={Boolean(mutationKey) || !caseSceneVersionId}>保存评测数据草稿</button>
        </form>
        <div className="se-version-list">
          {workspace.datasetDrafts.map((draft) => {
            const actionKey = `publish-dataset-${draft.datasetId}-${draft.revision}`;
            const publishedVersion = latestVersionForDraft(
              workspace.datasets.filter((item) => item.datasetId === draft.datasetId),
              draft.revision,
            );
            return <div key={draft.datasetId}><span><strong>{draft.name}</strong><small>草稿 r{draft.revision} · {draft.cases.length} 个评测样本</small></span><PublishVersionControl actionKey={actionKey} mutationKey={mutationKey} mutationFeedback={mutationFeedback} publishedVersion={publishedVersion} onPublish={() => void mutate(actionKey, () => publishDatasetVersion({ agentId, assetId: draft.datasetId, draftRevision: draft.revision }), (version) => ({ message: `评测数据“${version.name}”已发布为 v${version.version}`, publishedVersion: version.version }))} /></div>;
          })}
        </div>
      </section>}
    </div>
  );
}
