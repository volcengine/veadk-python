import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const composerSource = readFileSync(
  new URL("../src/ui/Composer.tsx", import.meta.url),
  "utf8",
);
const selectorSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatModeSelector.tsx", import.meta.url),
  "utf8",
);
const apiSource = readFileSync(
  new URL("../src/ui/skill-create/api.ts", import.meta.url),
  "utf8",
);
const typesSource = readFileSync(
  new URL("../src/ui/skill-create/types.ts", import.meta.url),
  "utf8",
);
const workspaceSource = readFileSync(
  new URL("../src/ui/skill-create/SkillCreateWorkspace.tsx", import.meta.url),
  "utf8",
);
const candidateSource = readFileSync(
  new URL("../src/ui/skill-create/SkillCandidatePane.tsx", import.meta.url),
  "utf8",
);

test("offers Agent, disabled temporary, and Skill creation modes in the new-chat composer", () => {
  assert.match(selectorSource, /value: "agent"[\s\S]*?label: "Agent 模式"/);
  assert.match(selectorSource, /value: "temporary"[\s\S]*?disabled: true/);
  assert.match(selectorSource, /value: "skill-create"[\s\S]*?label: "Skill 创建"/);
  assert.match(selectorSource, /aria-haspopup="listbox"/);
  assert.match(composerSource, /<NewChatModeSelector/);
  assert.match(composerSource, /描述 Skill 要解决的问题、适用场景和期望输出/);
});

test("preserves the existing Agent submit flow and resets mode on a new chat", () => {
  assert.match(
    appSource,
    /if \(newChatMode === "skill-create"\)[\s\S]*?return;[\s\S]*?const text = input;[\s\S]*?send\(text, atts, selectedInvocation\)/,
  );
  assert.match(appSource, /function startNewChat\(\)[\s\S]*?setNewChatMode\("agent"\)/);
  assert.match(
    appSource,
    /showModeSelector=\{[\s\S]*?skillJob === null && canCreateAgents[\s\S]*?\}/,
  );
  assert.match(
    appSource,
    /mode === "skill-create"[\s\S]*?discardDraftAttachments\(attachments\)[\s\S]*?setAttachments\(\[\]\)/,
  );
  assert.match(appSource, /discardSkillCreation\(\)[\s\S]*?deleteSkillJob\(job\.id\)/);
});

test("uses the fixed A/B models and real backend job, download, and publish endpoints", () => {
  assert.match(typesSource, /doubao-seed-2-0-pro-260215/);
  assert.match(typesSource, /deepseek-v4-flash-260425/);
  assert.match(apiSource, /apiRequest\("\/jobs"/);
  assert.match(apiSource, /JSON\.stringify\(\{ prompt \}\)/);
  assert.doesNotMatch(apiSource, /JSON\.stringify\(\{ prompt, models/);
  assert.match(apiSource, /"jobId"/);
  assert.match(apiSource, /status !== "running" && status !== "completed"/);
  assert.match(apiSource, /normalizeStage\(candidate\.stage\)/);
  assert.match(apiSource, /"elapsedMs", "elapsed_ms"/);
  assert.match(apiSource, /getSkillJob/);
  assert.match(apiSource, /deleteSkillJob[\s\S]*?method: "DELETE"/);
  assert.match(apiSource, /\/download`/);
  assert.match(apiSource, /\/publish`/);
  assert.doesNotMatch(apiSource, /mock|setTimeout/iu);
});

test("renders independent candidate progress with shimmer and actionable completed results", () => {
  assert.match(workspaceSource, /SKILL_MODELS\.map/);
  assert.match(workspaceSource, /setTimeout\(poll, 1100\)/);
  assert.match(workspaceSource, /<SkillCandidatePane/);
  assert.match(workspaceSource, /publishDisabled=\{publishingId !== undefined/);
  assert.match(candidateSource, /<TextShimmer/);
  assert.match(candidateSource, /正在准备 Sandbox/);
  assert.match(candidateSource, /正在生成 Skill/);
  assert.match(candidateSource, /正在校验结构/);
  assert.match(candidateSource, /正在打包/);
  assert.match(candidateSource, /下载 ZIP/);
  assert.match(candidateSource, /添加到 AgentKit/);
  assert.match(candidateSource, /publishing \|\| publishDisabled/);
  assert.match(candidateSource, /skillSpaceIds/);
  assert.match(candidateSource, /projectName/);
  assert.match(candidateSource, /skillId/);
});
