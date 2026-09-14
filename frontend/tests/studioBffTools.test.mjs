import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

const clientSource = source("../src/adk/client.ts");
const appSource = source("../src/App.tsx");
const composerSource = source("../src/ui/Composer.tsx");
const railSource = source("../src/ui/AgentTopology.tsx");
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

test("A2A model selection is request scoped and capability gated", () => {
  assert.match(clientSource, /modelId\?: string/);
  assert.match(clientSource, /model_id: modelId\.trim\(\)/);
  assert.match(appSource, /selectableModels\.length > 1/);
  assert.match(appSource, /modelId: requestedModel/);
  assert.match(composerSource, /selectableModels\.length > 1/);
  assert.match(composerSource, /disabled=\{busy\}/);
});

test("Studio sends BFF tools only as implementation support for environment mounts", () => {
  assert.doesNotMatch(appSource, /veadk\.sessionStudioToolMounts\.v1/);
  assert.doesNotMatch(appSource, /studioToolIdsBySession/);
  assert.match(appSource, /const canMountSessionEnvironment = ENVIRONMENT_STUDIO_TOOL_IDS\.every/);
  assert.match(appSource, /ENVIRONMENT_STUDIO_TOOL_IDS/);
  assert.match(appSource, /platformTools: studioToolRuntime \? platformTools : undefined/);
  assert.doesNotMatch(railSource, /selectedStudioToolIds/);
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

test("Agent information omits generic BFF tool selection and Composer stays unchanged", () => {
  assert.doesNotMatch(railSource, /<StudioToolDialog/);
  assert.doesNotMatch(railSource, /addStudioToolHere/);
  assert.doesNotMatch(composerSource, /StudioToolPicker|StudioToolChips|studioTools/);
});

test("Session Skill Space mounting augments static Agent skills", () => {
  assert.match(railSource, /const skills = uniqueSkills\(\[/);
  assert.match(railSource, /selectedSessionSkills\.map/);
  assert.match(railSource, /<SkillSpacePicker/);
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
