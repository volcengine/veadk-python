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
const activitySource = readFileSync(
  new URL("../src/ui/skill-create/SkillConversationStream.tsx", import.meta.url),
  "utf8",
);
const skillStylesSource = readFileSync(
  new URL("../src/ui/skill-create/skill-create.css", import.meta.url),
  "utf8",
);

test("offers Agent, temporary Sandbox, and Skill creation modes in the new-chat composer", () => {
  assert.match(selectorSource, /value: "agent"[\s\S]*?label: "Agent"/);
  assert.match(selectorSource, /value: "temporary"[\s\S]*?AgentKit 沙箱/);
  assert.match(selectorSource, /value: "skill-create"[\s\S]*?label: "创建 Skill"/);
  assert.match(selectorSource, /aria-haspopup="listbox"/);
  assert.match(composerSource, /<NewChatModeSelector/);
  assert.match(composerSource, /SKILL_MODELS\.join\(" 和 "\)/);
  assert.match(composerSource, /描述你想创建的 Skill.*并行创建/);
  assert.match(appSource, /mode === "temporary"[\s\S]*?openSandboxLaunch\(\)/);
});

test("preserves the existing Agent submit flow and resets mode on a new chat", () => {
  assert.match(
    appSource,
    /if \(!sandboxSession && newChatMode === "skill-create"\)[\s\S]*?return;[\s\S]*?const text = input;[\s\S]*?send\(text, atts, selectedInvocation\)/,
  );
  assert.match(appSource, /function startNewChat\(\)[\s\S]*?setNewChatMode\("agent"\)/);
  assert.match(
    appSource,
    /showModeSelector=\{[\s\S]*?skillJob === null &&[\s\S]*?canCreateAgents[\s\S]*?\}/,
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
  assert.match(apiSource, /status !== "provisioning" && status !== "running"/);
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
  assert.match(workspaceSource, /NOT_FOUND_GRACE_MS = 30_000/);
  assert.match(workspaceSource, /apiError\?\.status === 404 && Date\.now\(\) < notFoundDeadline/);
  assert.match(workspaceSource, /apiError\?\.status === 403 \|\| apiError\?\.status === 404/);
  assert.match(workspaceSource, /if \(!unavailable\) timer = window\.setTimeout\(poll, POLL_INTERVAL_MS\)/);
  assert.match(workspaceSource, /<SkillCandidatePane/);
  assert.match(workspaceSource, /publishDisabled=\{publishingId !== undefined/);
  assert.match(candidateSource, /<TextShimmer/);
  assert.match(candidateSource, /<SkillConversationStream/);
  assert.match(
    activitySource,
    /activities\.filter\(\(activity\) => activity\.kind !== "status"\)\.map/,
  );
  assert.match(activitySource, /activity\.kind === "message"/);
  assert.match(activitySource, /activity\.kind === "thinking"/);
  assert.match(activitySource, /activity\.kind === "tool"/);
  assert.match(activitySource, /<Blocks blocks=\{blocks\}/);
  assert.match(
    skillStylesSource,
    /\.skill-conversation \.think-head,[\s\S]*?grid-template-columns:\s*20px minmax\(0, 1fr\) 13px;/,
  );
  assert.match(
    skillStylesSource,
    /\.skill-conversation \.think-label,[\s\S]*?font-size:\s*13px;[\s\S]*?text-align:\s*left;/,
  );
  assert.match(
    skillStylesSource,
    /\.skill-candidate\s*\{[\s\S]*?grid-template-rows:\s*auto minmax\(0, 1fr\);/,
  );
  assert.match(
    skillStylesSource,
    /\.skill-candidate__view\s*\{[\s\S]*?overflow-y:\s*auto;/,
  );
  assert.match(candidateSource, /正在准备 Sandbox/);
  assert.match(candidateSource, /正在生成 Skill/);
  assert.match(candidateSource, /正在校验结构/);
  assert.match(candidateSource, /正在打包/);
  assert.doesNotMatch(candidateSource, /等待生成/);
  assert.match(candidateSource, /下载 ZIP/);
  assert.match(candidateSource, /添加到 AgentKit/);
  assert.match(candidateSource, /publishing \|\| publishDisabled/);
  assert.match(candidateSource, /skillSpaceIds/);
  assert.match(candidateSource, /projectName/);
  assert.match(candidateSource, /skillId/);
});

test("opens provisional A/B panes immediately and recovers polling for a real job", () => {
  assert.match(appSource, /const provisionalJob: SkillCreationJob/);
  assert.match(appSource, /status: "provisioning"/);
  assert.match(appSource, /setSkillJob\(provisionalJob\)[\s\S]*?createSkillJob\(prompt,/);
  assert.match(appSource, /setSkillJob\(null\)[\s\S]*?setInput\(prompt\)/);
  assert.match(workspaceSource, /setJob\(initialJob\)/);
  assert.match(workspaceSource, /initialJob\.id\.startsWith\("pending-"\)/);
  assert.doesNotMatch(workspaceSource, /initialJob\.status === "provisioning"/);
  assert.match(appSource, /const creationRun = \+\+skillCreationRunRef\.current/);
  assert.match(appSource, /skillCreationRunRef\.current === creationRun/);
  assert.match(apiSource, /normalizeActivities\(candidate\.activities\)/);
  assert.match(apiSource, /application\/x-ndjson/);
  assert.match(apiSource, /onProgress\?\.\(latest\)/);
});
