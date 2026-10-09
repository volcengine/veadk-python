import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

function source(path) {
  return readFileSync(new URL(path, import.meta.url), "utf8");
}

const clientSource = source("../src/adk/client.ts");
const environmentSource = source("../src/ui/EnvironmentCenter.tsx");
const workspaceSource = source("../src/ui/WorkspaceCenter.tsx");
const manageSource = source("../src/ui/ManageAgents.tsx");
const selectorSource = source("../src/ui/AgentSelector.tsx");

test("treats unconfigured optional persistence as an unavailable empty state", () => {
  assert.ok(environmentSource.includes("isStorageUnavailable(cause)"));
  assert.ok(environmentSource.includes("setEnvironments([])"));
  assert.ok(workspaceSource.includes("isStorageUnavailable(cause)"));
  assert.ok(workspaceSource.includes("setWorkspaces([])"));
  assert.match(environmentSource, /environmentCenter.storageUnavailable/);
  assert.match(workspaceSource, /workspace.storageUnavailable/);
});

test("copies Runtime secrets without rendering or persisting their values", () => {
  assert.match(clientSource, /copyRuntimeEnvironmentSecret/);
  assert.ok(clientSource.includes("await navigator.clipboard.writeText(payload.value)"));
  assert.ok(manageSource.includes("copyRuntimeEnvironmentSecret(runtimeId, region, envKey)"));
  assert.doesNotMatch(manageSource, /setRevealed|revealed ?/);
  assert.ok(selectorSource.includes('e.sensitive ? "••••••••" : e.value'));
});
