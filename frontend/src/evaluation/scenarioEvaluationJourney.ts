import type { SceneEvaluatorGroup } from "./scenarioEvaluatorGroups";
import type {
  EvaluationDependencies,
  EvaluationRunVersion,
  ScenarioEvaluationWorkspaceData,
} from "./types";

export type JourneyStepId =
  | "scene"
  | "dataset"
  | "evaluator"
  | "policy"
  | "candidate"
  | "run"
  | "decision";

export type JourneyStepState =
  | "not_started"
  | "active"
  | "complete"
  | "needs_attention";

export type JourneyActionId =
  | "create_scene"
  | "create_dataset"
  | "configure_evaluator"
  | "publish_policy"
  | "open_agent_update"
  | "start_evaluation"
  | "wait_evaluation"
  | "review_result"
  | "retry_evaluation"
  | "view_failed_samples"
  | "publish"
  | "skip_publish"
  | "risk_publish";

export interface ScenarioEvaluationJourneyStep {
  id: JourneyStepId;
  number: number;
  label: string;
  goal: string;
  why: string;
  requirements: string[];
  state: JourneyStepState;
  summary: string;
  locked: boolean;
  blockedReason: string | null;
}

export interface ScenarioEvaluationJourney {
  steps: ScenarioEvaluationJourneyStep[];
  totalSteps: 7;
  currentStepId: JourneyStepId;
  currentStepNumber: number;
  nextAction: {
    id: JourneyActionId;
    label: string;
    description: string;
    targetId?: string;
    disabledReason?: string;
  };
  latestCandidateId: string | null;
  latestPolicyVersionId: string | null;
  currentRunId: string | null;
}

export interface ScenarioEvaluationJourneyOptions {
  evaluationSkipped?: boolean;
}

export const STUDIO_EVALUATION_ENVIRONMENT = "studio-evaluation-v1";

const stepDefinitions: Array<Pick<
  ScenarioEvaluationJourneyStep,
  "id" | "label" | "goal" | "why" | "requirements"
>> = [
  {
    id: "scene",
    label: "定义业务场景",
    goal: "明确要验证的业务行为和通过标准",
    why: "业务场景决定后续数据、评估器和结论分别在验证什么。",
    requirements: ["填写用户任务", "填写通过标准", "发布业务场景版本"],
  },
  {
    id: "dataset",
    label: "准备评测数据",
    goal: "准备能代表业务要求的输入和期望结果",
    why: "评测数据为自动评测提供稳定、可重复的业务样本。",
    requirements: ["选择业务场景", "填写输入和期望输出", "发布评测数据版本"],
  },
  {
    id: "evaluator",
    label: "配置并校准场景评估器",
    goal: "用人工判断校验自动判断是否可信",
    why: "正式评测前先确认自动判断能够复现人工判断。",
    requirements: ["准备检查项", "完成模拟输出和人工判断", "校准准确并发布"],
  },
  {
    id: "policy",
    label: "创建评测方案",
    goal: "固定本次评测使用的完整版本口径",
    why: "评测方案把场景、数据和评估器的不可变版本绑定在一起。",
    requirements: ["覆盖全部启用场景", "绑定当前数据和评估器版本", "发布评测方案"],
  },
  {
    id: "candidate",
    label: "生成待测版本",
    goal: "冻结要接受评测的 Agent 快照",
    why: "评测与后续发布必须针对同一个只读版本，避免结果漂移。",
    requirements: ["完成 Agent 编辑", "生成只读待测版本"],
  },
  {
    id: "run",
    label: "运行正式评测",
    goal: "使用固定方案执行正式验证",
    why: "正式评测生成可追溯的运行证据和质量建议。",
    requirements: ["确认待测版本和评测方案", "完成正式评测或明确选择暂不评测"],
  },
  {
    id: "decision",
    label: "查看结论并决定发布",
    goal: "根据证据选择发布或继续改进",
    why: "质量建议帮助开发者在发布前理解风险和失败样本。",
    requirements: ["查看质量建议", "查看判断依据", "选择发布或继续改进"],
  },
];

function latestEnabledScenes(workspace: ScenarioEvaluationWorkspaceData) {
  const latest = new Map<string, ScenarioEvaluationWorkspaceData["scenes"][number]>();
  for (const scene of workspace.scenes) {
    const current = latest.get(scene.sceneId);
    if (!current || scene.version > current.version) latest.set(scene.sceneId, scene);
  }
  return [...latest.values()].filter((scene) => scene.enabled);
}

function sameIds(left: string[], right: string[]): boolean {
  return [...left].sort().join("\n") === [...right].sort().join("\n");
}

function sameDependencies(
  actual: EvaluationDependencies,
  expected: EvaluationDependencies,
): boolean {
  return actual.candidateId === expected.candidateId
    && actual.baselineVersionId === expected.baselineVersionId
    && actual.policyVersionId === expected.policyVersionId
    && actual.environmentFingerprint === expected.environmentFingerprint
    && sameIds(actual.sceneVersionIds, expected.sceneVersionIds)
    && sameIds(actual.datasetVersionIds, expected.datasetVersionIds)
    && sameIds(actual.evaluatorVersionIds, expected.evaluatorVersionIds);
}

function changedDependencyLabels(
  actual: EvaluationDependencies,
  expected: EvaluationDependencies,
): string[] {
  const labels: string[] = [];
  if (actual.candidateId !== expected.candidateId) labels.push("待测版本");
  if (actual.baselineVersionId !== expected.baselineVersionId) labels.push("线上对比版本");
  if (!sameIds(actual.sceneVersionIds, expected.sceneVersionIds)) labels.push("业务场景版本");
  if (!sameIds(actual.datasetVersionIds, expected.datasetVersionIds)) labels.push("评测数据版本");
  if (!sameIds(actual.evaluatorVersionIds, expected.evaluatorVersionIds)) labels.push("场景评估器版本");
  if (actual.policyVersionId !== expected.policyVersionId) labels.push("评测方案版本");
  if (actual.environmentFingerprint !== expected.environmentFingerprint) labels.push("评测环境");
  return labels;
}

function buildSteps(
  currentStepId: JourneyStepId,
  currentState: "active" | "needs_attention",
  currentSummary: string,
): ScenarioEvaluationJourneyStep[] {
  const currentIndex = stepDefinitions.findIndex((step) => step.id === currentStepId);
  return stepDefinitions.map((definition, index) => {
    const state: JourneyStepState = index < currentIndex
      ? "complete"
      : index === currentIndex
        ? currentState
        : "not_started";
    return {
      ...definition,
      number: index + 1,
      state,
      summary: state === "complete"
        ? "已完成"
        : index === currentIndex
          ? currentSummary
          : `等待完成第 ${currentIndex + 1} 步`,
      locked: index > currentIndex,
      blockedReason: state === "needs_attention" ? currentSummary : null,
    };
  });
}

function journeyAt(
  currentStepId: JourneyStepId,
  nextAction: ScenarioEvaluationJourney["nextAction"],
  options: {
    state?: "active" | "needs_attention";
    candidateId?: string | null;
    policyVersionId?: string | null;
    runId?: string | null;
    summary?: string;
  } = {},
): ScenarioEvaluationJourney {
  const currentStepNumber = stepDefinitions.findIndex((step) => step.id === currentStepId) + 1;
  return {
    steps: buildSteps(
      currentStepId,
      options.state ?? "active",
      options.summary ?? nextAction.description,
    ),
    totalSteps: 7,
    currentStepId,
    currentStepNumber,
    nextAction,
    latestCandidateId: options.candidateId ?? null,
    latestPolicyVersionId: options.policyVersionId ?? null,
    currentRunId: options.runId ?? null,
  };
}

function decisionJourney(
  candidateId: string,
  policyVersionId: string,
  run: EvaluationRunVersion,
): ScenarioEvaluationJourney {
  const doNotRecommend = run.recommendation?.value === "do_not_recommend";
  const indeterminate = run.recommendation?.value === "indeterminate";
  const nextAction: ScenarioEvaluationJourney["nextAction"] = indeterminate
    ? {
        id: "retry_evaluation",
        label: "修复环境或重新评测",
        description: "本次无法形成质量判断，检查评测环境后重新运行。",
        targetId: "formal-evaluation",
      }
    : doNotRecommend
      ? {
          id: "view_failed_samples",
          label: "查看失败样本",
          description: "当前版本不建议发布，先查看失败样本并返回修改 Agent。",
          targetId: "failed-samples",
        }
      : {
          id: "publish",
          label: "去发布",
          description: "当前评测口径下建议发布，可前往发布确认。",
          targetId: "quality-result",
        };
  const summary = indeterminate
    ? "本次评测无法形成质量判断"
    : doNotRecommend
      ? "质量建议为不建议发布"
      : "质量建议为建议发布";
  return journeyAt("decision", nextAction, {
    state: doNotRecommend || indeterminate ? "needs_attention" : "active",
    summary,
    candidateId,
    policyVersionId,
    runId: run.evaluationId,
  });
}

export function buildScenarioEvaluationJourney(
  workspace: ScenarioEvaluationWorkspaceData,
  groups: SceneEvaluatorGroup[],
  options: ScenarioEvaluationJourneyOptions = {},
): ScenarioEvaluationJourney {
  const activeRun = [...workspace.runs]
    .filter((item) => item.status === "queued" || item.status === "running")
    .sort((left, right) => Date.parse(right.updatedAt) - Date.parse(left.updatedAt))[0]
    ?? null;
  if (activeRun) {
    return journeyAt("run", {
      id: "wait_evaluation",
      label: "等待评测完成",
      description: activeRun.status === "queued"
        ? "正式评测正在排队，完成后会生成质量建议。"
        : "正式评测正在运行，完成后会生成质量建议。",
      targetId: "formal-evaluation",
    }, {
      candidateId: activeRun.candidateId,
      policyVersionId: activeRun.policyVersionId,
      runId: activeRun.evaluationId,
    });
  }

  const activeScenes = latestEnabledScenes(workspace);
  if (activeScenes.length === 0) {
    return journeyAt("scene", {
      id: "create_scene",
      label: "创建业务场景",
      description: "先定义用户任务、通过标准和严重失败条件。",
      targetId: "scene-form",
    });
  }

  const sceneWithoutData = activeScenes.find((scene) =>
    !workspace.datasets.some((item) =>
      item.cases.some((sample) => sample.sceneVersionId === scene.sceneVersionId)));
  if (sceneWithoutData) {
    return journeyAt("dataset", {
      id: "create_dataset",
      label: "创建评测数据",
      description: `为“${sceneWithoutData.name}”准备至少一个已发布评测样本。`,
      targetId: "dataset-form",
    });
  }

  const incompleteEvaluatorScene = activeScenes.find((scene) => {
    const group = groups.find((item) => item.sceneVersionId === scene.sceneVersionId);
    return !group
      || group.ordinaryCheckCount === 0
      || (scene.hardFailureConditions.length > 0 && group.severeCheckCount === 0)
      || group.calibrationState !== "accurate"
      || group.publishState !== "published";
  });
  if (incompleteEvaluatorScene) {
    const group = groups.find((item) =>
      item.sceneVersionId === incompleteEvaluatorScene.sceneVersionId);
    return journeyAt("evaluator", {
      id: "configure_evaluator",
      label: "配置场景评估器",
      description: group?.calibrationBlockReason
        ?? `校准并发布“${incompleteEvaluatorScene.name}”的场景评估器。`,
      targetId: "evaluator-form",
    }, {
      state: group && (
        group.calibrationState === "inaccurate"
        || group.calibrationState === "unavailable"
      )
        ? "needs_attention"
        : "active",
    });
  }

  const selectedDatasets = activeScenes.map((scene) =>
    workspace.datasets
      .filter((item) => item.cases.some((sample) =>
        sample.sceneVersionId === scene.sceneVersionId))
      .sort((left, right) => right.version - left.version)[0]);
  const currentPolicy = [...workspace.policies]
    .sort((left, right) => right.version - left.version)
    .find((item) =>
      item.bindings.length === activeScenes.length
      && activeScenes.every((scene, index) => {
        const binding = item.bindings.find((candidateBinding) =>
          candidateBinding.sceneVersionId === scene.sceneVersionId);
        const group = groups.find((candidateGroup) =>
          candidateGroup.sceneVersionId === scene.sceneVersionId);
        return Boolean(
          binding
          && group
          && binding.datasetVersionId === selectedDatasets[index]?.datasetVersionId
          && binding.requirement === scene.requirement
          && sameIds(binding.evaluatorVersionIds, group.latestPublishedVersionIds),
        );
      }));
  if (!currentPolicy) {
    return journeyAt("policy", {
      id: "publish_policy",
      label: "发布评测方案",
      description: "用当前业务场景、评测数据和场景评估器发布完整评测方案。",
      targetId: "policy-form",
    });
  }

  const latestCandidate = [...workspace.candidates]
    .sort((left, right) => {
      const createdDifference = Date.parse(right.createdAt) - Date.parse(left.createdAt);
      if (!Number.isNaN(createdDifference) && createdDifference !== 0) return createdDifference;
      const versionDifference = right.version - left.version;
      return versionDifference || right.candidateId.localeCompare(left.candidateId);
    })[0] ?? null;
  if (!latestCandidate) {
    return journeyAt("candidate", {
      id: "open_agent_update",
      label: "编辑并生成待测版本",
      description: "打开 Agent 编辑流程，生成供评测和发布共用的只读版本。",
      targetId: "candidate-list",
    }, { policyVersionId: currentPolicy.policyVersionId });
  }

  const expectedDependencies: EvaluationDependencies = {
    candidateId: latestCandidate.candidateId,
    baselineVersionId: workspace.publishedVersion?.publishedVersionId ?? null,
    sceneVersionIds: activeScenes.map((scene) => scene.sceneVersionId),
    datasetVersionIds: selectedDatasets.map((item) => item.datasetVersionId),
    evaluatorVersionIds: activeScenes.flatMap((scene) =>
      groups.find((item) => item.sceneVersionId === scene.sceneVersionId)
        ?.latestPublishedVersionIds ?? []),
    policyVersionId: currentPolicy.policyVersionId,
    environmentFingerprint: latestCandidate.environmentFingerprint || STUDIO_EVALUATION_ENVIRONMENT,
  };
  const currentRun = [...workspace.runs]
    .filter((item) => sameDependencies(item.dependencies, expectedDependencies))
    .sort((left, right) => Date.parse(right.updatedAt) - Date.parse(left.updatedAt))[0]
    ?? null;
  if (currentRun?.status === "succeeded" && currentRun.recommendation) {
    return decisionJourney(
      latestCandidate.candidateId,
      currentPolicy.policyVersionId,
      currentRun,
    );
  }
  if (options.evaluationSkipped) {
    return journeyAt("decision", {
      id: "skip_publish",
      label: "继续发布确认",
      description: "已选择暂不运行正式评测，当前没有质量建议；继续发布需要确认风险并填写原因。",
      targetId: "quality-result",
    }, {
      state: "needs_attention",
      summary: "已选择暂不评测，当前没有质量建议",
      candidateId: latestCandidate.candidateId,
      policyVersionId: currentPolicy.policyVersionId,
      runId: currentRun?.evaluationId ?? null,
    });
  }
  if (currentRun?.status === "cancelled" || currentRun?.status === "failed") {
    const failed = currentRun.status === "failed";
    return journeyAt("run", {
      id: "retry_evaluation",
      label: failed ? "修复问题并重新评测" : "重新开始正式评测",
      description: failed
        ? "本次评测执行失败，未生成有效质量建议；修复问题后可重新评测，也可暂不评测。"
        : "本次评测已取消，未生成有效质量建议；可以重新开始，也可暂不评测。",
      targetId: "formal-evaluation",
    }, {
      state: "needs_attention",
      candidateId: latestCandidate.candidateId,
      policyVersionId: currentPolicy.policyVersionId,
      runId: currentRun.evaluationId,
    });
  }
  if (!currentRun && workspace.runs.length > 0) {
    const historicalRun = [...workspace.runs]
      .sort((left, right) => Date.parse(right.updatedAt) - Date.parse(left.updatedAt))[0];
    const changed = changedDependencyLabels(
      historicalRun.dependencies,
      expectedDependencies,
    );
    return journeyAt("run", {
      id: "retry_evaluation",
      label: "按当前口径重新评测",
      description: `${changed.join("、") || "评测依赖"}已变化，历史结果仅供查看。`,
      targetId: "formal-evaluation",
    }, {
      state: "needs_attention",
      candidateId: latestCandidate.candidateId,
      policyVersionId: currentPolicy.policyVersionId,
      runId: historicalRun.evaluationId,
    });
  }

  return journeyAt("run", {
    id: "start_evaluation",
    label: "开始正式评测",
    description: "使用当前待测版本和评测方案执行正式评测；也可选择暂不评测。",
    targetId: "formal-evaluation",
  }, {
    candidateId: latestCandidate.candidateId,
    policyVersionId: currentPolicy.policyVersionId,
  });
}
