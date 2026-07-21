import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const selectorSource = readFileSync(
  new URL("../src/ui/AgentSelector.tsx", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);
const runtimeIconSource = readFileSync(
  new URL("../src/ui/RuntimeIdentityIcon.tsx", import.meta.url),
  "utf8",
);
const capabilityIconSource = readFileSync(
  new URL("../src/ui/CapabilityIcons.tsx", import.meta.url),
  "utf8",
);

test("each Runtime row has two-line metadata and explicit actions", () => {
  assert.doesNotMatch(selectorSource, /HOVER_PREVIEW_DELAY_MS|schedulePreview/);
  assert.match(selectorSource, /className="agentsel-item-main"/);
  assert.match(selectorSource, /className="agentsel-item-meta"/);
  assert.match(selectorSource, /agentsel-item agentsel-runtime-item/);
  assert.match(selectorSource, /className="agentsel-connect"/);
  assert.match(selectorSource, /className=\{`agentsel-info/);
  assert.match(selectorSource, /onClick=\{\(\) => togglePreview\(rt\)\}/);
  assert.match(selectorSource, /previewed && \([\s\S]*?<RuntimePreviewPanel/);
  assert.match(selectorSource, /role="tablist"/);
  assert.match(selectorSource, /Agent 信息[\s\S]*?Runtime 信息/);
  assert.match(
    selectorSource,
    /getRuntimeAgentInfo\(runtimeId, runtimeRegion\)/,
  );
  assert.match(clientSource, /fetchRemoteApps\("", "", ep\)/);
});

test("Runtime rows scroll above a permanently pinned pager", () => {
  assert.match(
    selectorSource,
    /\) : \(\s*<div className="agentsel-body agentsel-body--cloud">/,
  );
  assert.doesNotMatch(
    selectorSource,
    /agentsSource === "local" \? \(\s*<div className="agentsel-body agentsel-body--cloud">/,
  );
  assert.match(selectorSource, /<div className="agentsel-pager">/);
  assert.doesNotMatch(selectorSource, /!mineOnly && \(page > 0 \|\| hasNext\)/);
  assert.match(
    stylesSource,
    /\.agentsel-body--cloud\s*\{[\s\S]*?overflow:\s*hidden;/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-body--cloud \.agentsel-listwrap\s*\{[\s\S]*?flex:\s*1;[\s\S]*?overflow-y:\s*auto;/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-body--cloud \.agentsel-listwrap\s*\{[\s\S]*?scrollbar-gutter:\s*auto;/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-pager\s*\{[\s\S]*?flex:\s*0 0 36px;/,
  );
});

test("Runtime metadata failures use bounded, actionable Chinese messages", () => {
  assert.match(
    clientSource,
    /httpErrorMessage\(res, "读取 Agent 列表失败"\)/,
  );
  assert.match(
    clientSource,
    /httpErrorMessage\(res, "加载 Runtime 详情失败"\)/,
  );
  assert.match(selectorSource, /该 Runtime 已不存在或列表信息已过期，请刷新列表后重试。/);
  assert.match(selectorSource, /当前账号无权访问该 Runtime，请检查所属 Project 和访问权限。/);
  assert.match(selectorSource, /该 Agent Server 版本暂不支持信息预览。/);
  assert.match(selectorSource, /该 Runtime 暂时无法访问，请确认其状态为“就绪”后重试。/);
  assert.match(
    stylesSource,
    /\.agentsel-error\s*\{[^}]*max-width:\s*100%;[^}]*overflow-wrap:\s*anywhere;/,
  );
});

test("Agent information includes structure, capabilities, and mounted components", () => {
  assert.match(clientSource, /components\?: AgentComponent\[\]/);
  assert.match(clientSource, /skills:\s*info\.skills \?\? \[\]/);
  assert.match(clientSource, /subAgents:\s*info\.subAgents \?\? \[\]/);
  assert.match(selectorSource, /title="子 Agent"/);
  assert.match(selectorSource, /title="工具"/);
  assert.match(selectorSource, /<SkillCapabilityIcon \/>[\s\S]*?技能/);
  assert.match(selectorSource, /<Boxes className="icon" \/>[\s\S]*?挂载组件/);
  assert.match(selectorSource, /COMPONENT_KIND_LABELS/);
  assert.doesNotMatch(selectorSource, /\b(?:Sparkles|Wrench)\b/);
  assert.match(capabilityIconSource, /function ToolCapabilityIcon/);
  assert.match(capabilityIconSource, /function SkillCapabilityIcon/);
});

test("Runtime rows and detail use the custom live-execution mark", () => {
  assert.doesNotMatch(selectorSource, /\bCpu\b/);
  assert.match(selectorSource, /<RuntimeIdentityIcon \/>/);
  assert.match(runtimeIconSource, /A live execution orbit/);
  assert.match(runtimeIconSource, /M6\.85 12h2\.8/);
});

test("Runtime status and region labels are localized", () => {
  assert.match(selectorSource, /ready:\s*"就绪"/);
  assert.match(selectorSource, /unreleased:\s*"未发布"/);
  assert.match(selectorSource, /runtimeStatusLabel\(rt\.status\)/);
  assert.match(selectorSource, /regionLabel\(detail\.region\)/);
  assert.doesNotMatch(selectorSource, /regionLabel\(rt\.region\)/);
});

test("Runtime region selection defaults to Beijing without an all-regions query", () => {
  assert.match(
    selectorSource,
    /useState<RegionFilter>\("cn-beijing"\)/,
  );
  assert.doesNotMatch(selectorSource, /value:\s*"all",\s*label:\s*"全部"/);
  assert.match(
    stylesSource,
    /\.agentsel-regions\s*\{[\s\S]*?grid-template-columns:\s*repeat\(2, 1fr\);/,
  );
});

test("the tabbed detail panel constrains long content and narrow viewports", () => {
  assert.match(
    stylesSource,
    /\.agentsel\s*\{[\s\S]*?flex-wrap:\s*wrap;[\s\S]*?width:\s*min\(320px, var\(--agentsel-available-width\)\);/,
  );
  assert.match(
    stylesSource,
    /\.agentsel\.has-detail\s*\{[\s\S]*?width:\s*min\(688px, var\(--agentsel-available-width\)\);/,
  );
  assert.match(
    stylesSource,
    /\.sidebar\.is-collapsed \.agentsel\s*\{[\s\S]*?--agentsel-available-width:\s*calc\(100vw - 70px\);/,
  );
  assert.match(
    stylesSource,
    /\.agentsel\s*\{[\s\S]*?gap:\s*8px;[\s\S]*?background:\s*transparent;[\s\S]*?border:\s*0;/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-main\s*\{[\s\S]*?border-radius:\s*12px;[\s\S]*?box-shadow:/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-main\s*\{[\s\S]*?height:\s*100%;[\s\S]*?max-height:\s*100%;/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-detail\s*\{[\s\S]*?border-radius:\s*12px;[\s\S]*?box-shadow:/,
  );
  assert.match(
    stylesSource,
    /@container \(max-width:\s*527px\)[\s\S]*?height:\s*calc\(\(100% - 8px\) \/ 2\);/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-description\s*\{[\s\S]*?max-height:\s*104px;[\s\S]*?overflow-y:\s*auto;/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-chip\s*\{[\s\S]*?max-width:\s*100%;[\s\S]*?text-overflow:\s*ellipsis;/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-item-main\s*\{[\s\S]*?flex-direction:\s*column;/,
  );
  assert.match(
    selectorSource,
    /className=\{`agentsel \$\{previewed \? "has-detail" : ""\}`\}/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-list\s*\{[\s\S]*?gap:\s*0;/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-item\s*\{[\s\S]*?min-height:\s*46px;[\s\S]*?padding:\s*4px 0;/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-item-main\s*\{[\s\S]*?gap:\s*4px;/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-detail-tabs-slider\s*\{[\s\S]*?transition:\s*transform/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-preview-head\s*\{[^}]*padding:\s*7px 14px;/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-item:hover\s*\{[^}]*box-shadow:\s*none;[^}]*transform:\s*none;/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-runtime-item:hover\s*\{[^}]*background:\s*none;/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-runtime-item\.active,[\s\S]*?\.agentsel-runtime-item\.is-previewed\s*\{[^}]*background:\s*none;/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-info\.active\s*\{[^}]*background:\s*transparent;/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-tab-panel\[hidden\]\s*\{[\s\S]*?display:\s*none;/,
  );
  assert.doesNotMatch(selectorSource, /<code className="agentsel-env-[kv]"/);
  assert.match(
    stylesSource,
    /\.agentsel-env-k\s*\{[^}]*font-family:\s*inherit;/,
  );
  assert.match(
    stylesSource,
    /\.agentsel-env-v\s*\{[^}]*font-family:\s*inherit;/,
  );
  assert.match(
    stylesSource,
    /@media \(max-width:\s*860px\)[\s\S]*?\.agentsel\s*\{[\s\S]*?--agentsel-available-width:\s*calc\(100vw - 218px\);/,
  );
});
