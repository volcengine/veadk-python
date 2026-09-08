import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const composerSource = readFileSync(
  new URL("../src/ui/Composer.tsx", import.meta.url),
  "utf8",
);
const controlsSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatSkillControls.tsx", import.meta.url),
  "utf8",
);
const skillCenterSource = readFileSync(
  new URL("../src/ui/SkillCenter.tsx", import.meta.url),
  "utf8",
);
const generationSource = readFileSync(
  new URL("../src/ui/skills/SkillGenerationWorkspace.tsx", import.meta.url),
  "utf8",
);
const skillStylesSource = readFileSync(
  new URL("../src/ui/skills/skills.css", import.meta.url),
  "utf8",
);

test("routes homepage Skill submissions into the Skill workbench", () => {
  assert.match(appSource, /const \[skillCenterLaunch, setSkillCenterLaunch\]/);
  assert.match(
    appSource,
    /newChatWorkspaceMode === "skill"[\s\S]*?initialIntent: text\.trim\(\)[\s\S]*?setSkillCenterLaunch\(launch\)/,
  );
  assert.match(appSource, /setLibraryTab\("skills"\)[\s\S]*?setSkillCenter\(true\)/);
  assert.match(appSource, /<LibraryView[\s\S]*?skillInitialWorkspace=\{skillCenterLaunch\}/);
  assert.match(composerSource, /onSkillTargetChange/);
  assert.match(controlsSource, /onOptimizationSourceChange/);
});

test("keeps the selected optimization Skill and its source Space together", () => {
  assert.match(controlsSource, /onOptimizationSourceChange\?\.\(\{ space, skill \}\)/);
  assert.match(appSource, /const target = newChatSkillTarget/);
  assert.match(appSource, /skillSpaceId: target\.space\.id/);
  assert.match(appSource, /skillId: target\.skill\.skillId/);
  assert.match(appSource, /version: target\.skill\.version/);
  assert.match(appSource, /space: target\.space/);
});

test("asks homepage creation users for a publish Space only after generation", () => {
  assert.match(generationSource, /space\?: SkillSpaceRef/);
  assert.match(generationSource, /availableSpaces\?: SkillSpaceRef\[\]/);
  assert.match(generationSource, /initialIntent\?: string/);
  assert.match(generationSource, /useState\(initialIntent\)/);
  assert.match(generationSource, /const needsPublishSpace = operation === "create" && !space/);
  assert.match(
    generationSource,
    /active\.task\?\.state === "ready"[\s\S]*?needsPublishSpace[\s\S]*?<SkillConfigSelect[\s\S]*?label=\{t\("generation\.uploadToSpace"\)\}/,
  );
  assert.match(generationSource, /disabled=\{Boolean\(action\) \|\| Boolean\(publishedId\) \|\| !publishSpace\}/);
  assert.match(generationSource, /skillSpaceIds: \[publishSpace\.id\]/);
  assert.match(skillStylesSource, /\.skill-generation__ready-actions/);
  assert.match(skillStylesSource, /\.skill-generation__publish-target/);
});

test("preserves the current Space for creation launched inside Skill Center", () => {
  assert.match(skillCenterSource, /initialWorkspace\?: SkillCenterWorkspaceLaunch/);
  assert.match(skillCenterSource, /useState<SkillSpaceRef \| null>\(initialWorkspace\?\.space \?\? null\)/);
  assert.match(skillCenterSource, /space=\{selectedSpace \?\? undefined\}/);
  assert.match(skillCenterSource, /availableSpaces=\{spaces\}/);
  assert.match(generationSource, /const publishSpace = space \?\? selectedPublishSpace/);
  assert.match(generationSource, /operation === "optimize" \? t\("generation\.overwrite"\) : needsPublishSpace \? t\("generation\.uploadToSelectedSpace"\) : t\("generation\.uploadToCurrentSpace"\)/);
});
