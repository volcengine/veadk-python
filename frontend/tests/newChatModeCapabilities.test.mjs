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
const capabilitySource = readFileSync(
  new URL("../src/adk/newChatCapabilities.ts", import.meta.url),
  "utf8",
);

test("loads temporary-session and Skill-creation capabilities independently", () => {
  assert.match(capabilitySource, /\/web\/sandbox\/capabilities/);
  assert.match(capabilitySource, /\/web\/skill-creator\/capabilities/);
  assert.match(capabilitySource, /export async function getSandboxCapability/);
  assert.match(capabilitySource, /export async function getSkillCreatorCapability/);
  assert.match(capabilitySource, /enabled:\s*boolean/);
  assert.match(appSource, /getSandboxCapability/);
  assert.match(appSource, /getSkillCreatorCapability/);
  assert.match(appSource, /Promise\.allSettled/);
  assert.match(appSource, /temporaryEnabled/);
  assert.match(appSource, /skillCreateEnabled/);
});

test("disables built-in Agents and Skill creation until configured", () => {
  assert.match(composerSource, /temporaryEnabled\?: boolean/);
  assert.match(composerSource, /skillCreateEnabled\?: boolean/);
  assert.match(composerSource, /temporaryEnabled=\{temporaryEnabled\}/);
  assert.match(composerSource, /skillCreateEnabled=\{skillCreateEnabled\}/);
  assert.match(selectorSource, /temporaryEnabled\?: boolean/);
  assert.match(selectorSource, /skillCreateEnabled\?: boolean/);
  assert.match(selectorSource, /管理员未配置/);
  assert.match(selectorSource, /if \(mode\.value === "temporary"\) return temporaryEnabled/);
  assert.match(selectorSource, /if \(mode\.value === "skill-create"\) return skillCreateEnabled/);
  assert.match(selectorSource, /return modeEnabled\(mode\) !== true/);
  assert.match(selectorSource, /if \(modeDisabled\(mode\)\) return/);
  assert.match(selectorSource, /disabled=\{modeDisabled\(mode\)\}/);
  assert.match(
    appSource,
    /mode === "temporary" && !newChatCapabilities\.temporaryEnabled/,
  );
  assert.doesNotMatch(selectorSource, /启动时检查运行环境/);
  assert.doesNotMatch(selectorSource, /value:\s*"agent"[\s\S]*?disabled:\s*true/);
});

test("marks Skill creation as Beta only inside the dropdown option", () => {
  assert.match(
    selectorSource,
    /mode\.value === "skill-create"[\s\S]*?new-chat-mode__beta[\s\S]*?Beta/,
  );
  assert.equal(selectorSource.match(/>Beta</g)?.length, 1);
});
