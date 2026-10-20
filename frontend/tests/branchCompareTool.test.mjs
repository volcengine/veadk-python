import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { build } from "esbuild";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");
const blocksSource = read("../src/blocks.ts");
const cardSource = read("../src/ui/builtin-tools/BranchCompareCard.tsx");
const stylesSource = read("../src/ui/builtin-tools/branch-compare.css");
const registrySource = read("../src/ui/builtin-tools/registry.ts");

async function loadBranchData() {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(
      "../src/ui/builtin-tools/branchCompareData.ts",
      import.meta.url,
    ))],
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node20",
    write: false,
  });
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(
    result.outputFiles[0].contents,
  ).toString("base64")}`;
  return import(moduleUrl);
}

test("merges streamed deltas independently and hydrates final results", async () => {
  const { applyBranchCompareProgress, parseBranchCompare } = await loadBranchData();
  const args = {
    prompt: "设计方案",
    branches: [
      { label: "稳妥", instruction: "兼容现有流程" },
      { label: "创新", instruction: "对话式创建" },
    ],
  };
  const first = applyBranchCompareProgress(args, undefined, {
    toolName: "branch_compare",
    requestId: "request-1",
    branchIndex: 1,
    label: "创新",
    delta: "边聊",
    status: "running",
  });
  const second = applyBranchCompareProgress(args, first, {
    toolName: "branch_compare",
    requestId: "request-1",
    branchIndex: 1,
    label: "创新",
    delta: "边预览",
    status: "completed",
  });

  assert.equal(second.branches[0].label, "稳妥");
  assert.equal(second.branches[1].content, "边聊边预览");
  assert.equal(second.branches[1].status, "completed");
  assert.equal(parseBranchCompare(args, {
    result: {
      branches: [
        { label: "稳妥", content: "最终一", status: "completed" },
        { label: "创新", content: "最终二", status: "completed" },
      ],
    },
  }, "completed").branches[0].content, "最终一");
});

test("renders a distilled responsive comparison without status labels", () => {
  assert.match(registrySource, /branch_compare:[\s\S]*?hideHeader: true/);
  assert.match(cardSource, /<Badge color="info" size="sm" variant="soft">/);
  assert.equal((cardSource.match(/t\("blocks\.branchCompare\.continue"\)/g) ?? []).length, 1);
  assert.match(cardSource, /disabled=\{branch\.status !== "completed"\}/);
  assert.doesNotMatch(cardSource, /生成中|已完成|>A<|>B</);
  assert.match(stylesSource, /grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(stylesSource, /max-height:\s*240px/);
  assert.match(stylesSource, /overflow-y:\s*auto/);
  assert.match(stylesSource, /max-height:\s*min\(42vh, 280px\)/);
  assert.match(stylesSource, /@media \(max-width: 760px\)/);
  assert.match(blocksSource, /parseBranchCompareProgress/);
  assert.match(blocksSource, /block\.callId !== progress\.requestId/);
  assert.match(blocksSource, /callId:\s*fc\.id/);
});
