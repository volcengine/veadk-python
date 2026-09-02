import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

const clientSource = source("../src/adk/client.ts");
const appSource = source("../src/App.tsx");
const composerSource = source("../src/ui/Composer.tsx");
const railSource = source("../src/ui/AgentTopology.tsx");
const dialogSource = source("../src/ui/StudioToolDialog.tsx");
const blocksSource = source("../src/ui/Blocks.tsx");
const stylesSource = source("../src/styles.css");

test("runSSE sends an explicit per-run platform tool selection", () => {
  assert.match(clientSource, /platformTools\?: readonly string\[\]/);
  assert.match(clientSource, /platform_tools: \[\.\.\.platformTools\]/);
  assert.match(
    clientSource,
    /runtime-tool-channel\/\$\{encodeURIComponent\(runtimeId\)\}\/capabilities/,
  );
});

test("Studio keeps BFF tool selection separate per session", () => {
  assert.match(appSource, /studioToolIdsBySession/);
  assert.match(appSource, /studioToolSelectionKey\(appName, userId, sessionId\)/);
  assert.match(appSource, /platformTools: studioToolRuntime \? platformTools : undefined/);
  assert.match(railSource, /selectedStudioToolIds=\{selectedStudioToolIds\}/);
});

test("BFF tool discovery keeps a stable hook order across login", () => {
  const capabilityCall = appSource.indexOf(
    "getRuntimeStudioToolCapabilities(\n      studioToolRuntime.runtimeId",
  );
  const authenticationReturn = appSource.indexOf("if (authError) {");

  assert.ok(capabilityCall >= 0, "capability discovery should be present");
  assert.ok(authenticationReturn >= 0, "authentication gate should be present");
  assert.ok(capabilityCall < authenticationReturn);
});

test("Agent information owns BFF tool selection and Composer stays unchanged", () => {
  assert.match(railSource, /<StudioToolDialog/);
  assert.match(railSource, /在此对话中添加 Studio 工具/);
  assert.match(dialogSource, /aria-label="搜索 Studio 工具"/);
  assert.match(dialogSource, /aria-pressed=\{active\}/);
  assert.doesNotMatch(composerSource, /StudioToolPicker|StudioToolChips|studioTools/);
});

test("dynamic Skill mounting is absent while static Agent skills remain", () => {
  assert.match(railSource, /const skills = uniqueSkills\(info\.skills\)/);
  assert.doesNotMatch(railSource, /SkillCapabilityDialog|onAddCapability/);
  assert.doesNotMatch(clientSource, /SessionCapabilities|addSessionCapability/);
  assert.doesNotMatch(appSource, /requiresSessionCapabilityRunner/);
});

test("BFF-generated artifacts expose a direct Studio download", () => {
  assert.match(blocksSource, /record\.studio_artifacts/);
  assert.match(blocksSource, /href=\{artifact\.contentUrl\}/);
  assert.match(blocksSource, /download=\{artifact\.name\}/);
  assert.match(stylesSource, /\.studio-tool-artifacts a\s*\{/);
});
