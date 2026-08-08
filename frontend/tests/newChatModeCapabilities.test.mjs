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

test("loads temporary-session and Harness capabilities independently", () => {
  assert.match(capabilitySource, /\/web\/sandbox\/capabilities/);
  assert.match(capabilitySource, /export async function getSandboxCapability/);
  assert.doesNotMatch(capabilitySource, /skill-creator/);
  assert.match(capabilitySource, /enabled:\s*boolean/);
  assert.match(appSource, /getSandboxCapability/);
  assert.match(appSource, /Promise\.allSettled/);
  assert.match(appSource, /listSessionBuiltinTools\(agentId\)/);
  assert.match(appSource, /harnessEnabled:\s*harnessResult\.status === "fulfilled"/);
  assert.match(appSource, /newChatCapabilities\.agentId === appName/);
  assert.match(
    appSource,
    /const newChatCapabilitiesReady =\s*!appName \|\|/,
    "an empty Agent selection must not wait for a capability probe",
  );
  assert.match(appSource, /ready:\s*true/);
  assert.match(appSource, /正在检查 Agent 能力/);
  assert.match(appSource, /temporaryEnabled/);
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
  assert.match(selectorSource, /temporaryEnabled\?: boolean/);
  assert.match(selectorSource, /管理员未配置/);
  assert.match(selectorSource, /if \(mode\.value === "temporary"\) return temporaryEnabled/);
  assert.match(selectorSource, /return modeEnabled\(mode\) !== true/);
  assert.match(selectorSource, /if \(modeDisabled\(mode\)\) return/);
  assert.match(selectorSource, /disabled=\{modeDisabled\(mode\)\}/);
  assert.match(
    appSource,
    /mode === "temporary" && !newChatCapabilities\.temporaryEnabled/,
  );
  assert.doesNotMatch(selectorSource, /启动时检查运行环境/);
  assert.doesNotMatch(selectorSource, /value:\s*"agent"[\s\S]*?disabled:\s*true/);
  assert.doesNotMatch(selectorSource, /skill-create|创建 Skill/);
});
