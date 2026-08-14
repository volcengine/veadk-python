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

test("loads built-in Sandbox, Skill, and Harness capabilities independently", () => {
  assert.match(capabilitySource, /\/web\/sandbox\/capabilities/);
  assert.match(capabilitySource, /\/web\/\$\{kind\}\/capabilities/);
  assert.match(capabilitySource, /export async function getSandboxCapability/);
  assert.match(capabilitySource, /export async function getSandboxAgentCapability/);
  assert.doesNotMatch(capabilitySource, /skill-creator/);
  assert.match(capabilitySource, /enabled:\s*boolean/);
  assert.match(appSource, /getSandboxCapability/);
  assert.match(appSource, /getSandboxAgentCapability\("deepseek-harness"\)/);
  assert.match(appSource, /getSkillWorkbenchCapability/);
  assert.match(appSource, /Promise\.allSettled/);
  assert.match(appSource, /listSessionBuiltinTools\(agentId\)/);
  assert.match(
    appSource,
    /harnessEnabled:\s*!!agentId && harnessResult\.status === "fulfilled"/,
  );
  assert.match(appSource, /newChatCapabilities\.agentId === appName/);
  assert.match(
    appSource,
    /agentId \? listSessionBuiltinTools\(agentId\) : Promise\.resolve<string\[\]>\(\[\]\)/,
    "an empty Agent selection still checks global modes without probing Harness",
  );
  assert.match(appSource, /ready:\s*true/);
  assert.match(appSource, /正在检查 Agent 能力/);
  assert.match(appSource, /temporaryEnabled/);
  assert.match(appSource, /deepseekHarnessEnabled/);
  assert.match(appSource, /skillCustomizationEnabled/);
  assert.doesNotMatch(appSource, /skillCreateEnabled/);
  assert.match(
    appSource,
    /const connectMyAgent[\s\S]*?await refreshCurrentAgentAndStartNewChat\(agentId\)/,
  );
  assert.match(
    appSource,
    /const refreshCurrentAgentAndStartNewChat[\s\S]*?await probeNewChatCapabilities\(id\)[\s\S]*?setAppName\(id\)[\s\S]*?startNewChat\(\)/,
  );
  assert.match(appSource, /newChatCapabilitiesCacheRef/);
});

test("disables built-in Agents until configured", () => {
  assert.match(composerSource, /temporaryEnabled\?: boolean/);
  assert.match(composerSource, /temporaryEnabled=\{temporaryEnabled\}/);
  assert.match(composerSource, /deepseekHarnessEnabled\?: boolean/);
  assert.match(composerSource, /deepseekHarnessEnabled=\{deepseekHarnessEnabled\}/);
  assert.match(selectorSource, /temporaryEnabled\?: boolean/);
  assert.match(selectorSource, /deepseekHarnessEnabled\?: boolean/);
  assert.match(selectorSource, /管理员未配置/);
  assert.match(selectorSource, /if \(temporaryEnabled === true \|\| deepseekHarnessEnabled === true\) return true/);
  assert.match(selectorSource, /return modeEnabled\(mode\) !== true/);
  assert.match(selectorSource, /if \(modeDisabled\(mode\)\) return/);
  assert.match(selectorSource, /disabled=\{modeDisabled\(mode\)\}/);
  assert.match(
    appSource,
    /mode === "temporary" && !newChatCapabilities\.temporaryEnabled/,
  );
  assert.match(
    appSource,
    /mode === "deepseek-harness"[\s\S]*?!newChatCapabilities\.deepseekHarnessEnabled/,
  );
  assert.doesNotMatch(selectorSource, /启动时检查运行环境/);
  assert.doesNotMatch(selectorSource, /value:\s*"agent"[\s\S]*?disabled:\s*true/);
  assert.doesNotMatch(selectorSource, /skill-create|创建 Skill/);
});
