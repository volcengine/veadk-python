import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

async function loadJourneyViewModule() {
  try {
    const result = await build({
      entryPoints: [
        fileURLToPath(
          new URL("../src/evaluation/ScenarioEvaluationJourneyView.tsx", import.meta.url),
        ),
      ],
      bundle: true,
      format: "esm",
      platform: "node",
      target: "node20",
      write: false,
    });
    const source = result.outputFiles[0]?.text;
    if (!source) return null;
    return import(
      `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
    );
  } catch {
    return null;
  }
}

const journeyView = await loadJourneyViewModule();

function journey(overrides = {}) {
  const definitions = [
    ["scene", "定义业务场景"],
    ["dataset", "准备评测数据"],
    ["evaluator", "配置并校准场景评估器"],
    ["policy", "创建评测方案"],
    ["candidate", "生成待测版本"],
    ["run", "运行正式评测"],
    ["decision", "查看结论并决定发布"],
  ];
  return {
    steps: definitions.map(([id, label], index) => ({
      id,
      number: index + 1,
      label,
      goal: index === 4 ? "冻结要接受评测的 Agent 快照" : `${label}目标`,
      why: index === 4 ? "评测与发布必须使用同一个只读版本。" : `${label}意义`,
      requirements: [`完成${label}`],
      state: index < 4 ? "complete" : index === 4 ? "active" : "not_started",
      summary: index < 4 ? "已完成" : index === 4 ? "尚未生成待测版本" : "等待前置步骤",
      locked: index > 4,
      blockedReason: null,
    })),
    totalSteps: 7,
    currentStepId: "candidate",
    currentStepNumber: 5,
    nextAction: {
      id: "open_agent_update",
      label: "编辑并生成待测版本",
      description: "打开 Agent 编辑流程，生成供评测和发布共用的只读版本。",
    },
    latestCandidateId: null,
    latestPolicyVersionId: "policy-v1",
    currentRunId: null,
    ...overrides,
  };
}

test("renders seven fixed steps and one current-step workspace", () => {
  assert.ok(journeyView, "expected the journey view module to compile");
  const html = renderToStaticMarkup(React.createElement(
    journeyView.ScenarioEvaluationJourneyView,
    {
      journey: journey(),
      selectedStepId: "candidate",
      onSelectStep() {},
      onPrevious() {},
      onPrimaryAction() {},
    },
    React.createElement("div", null, "待测版本内容"),
  ));

  for (const label of [
    "定义业务场景",
    "准备评测数据",
    "配置并校准场景评估器",
    "创建评测方案",
    "生成待测版本",
    "运行正式评测",
    "查看结论并决定发布",
  ]) assert.match(html, new RegExp(label));
  assert.equal((html.match(/class="se-wizard-step /g) ?? []).length, 7);
  assert.match(html, /第 5 步，共 7 步/);
  assert.match(html, /aria-current="step"/);
  assert.match(html, /当前步骤/);
  assert.match(html, /为什么要做/);
  assert.match(html, /完成本步需要/);
  assert.match(html, /已完成/);
  assert.match(html, /aria-disabled="true"/);
  assert.match(html, /编辑并生成待测版本/);
  assert.match(html, /待测版本内容/);
  assert.equal((html.match(/data-step-content/g) ?? []).length, 1);
});
