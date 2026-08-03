import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const iconsSource = readFileSync(
  new URL("../src/ui/icons/SandboxAgentIcons.tsx", import.meta.url),
  "utf8",
);
const pickerSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatAgentPicker.tsx", import.meta.url),
  "utf8",
);
const myAgentsSource = readFileSync(
  new URL("../src/ui/MyAgents.tsx", import.meta.url),
  "utf8",
);
const selectorSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatModeSelector.tsx", import.meta.url),
  "utf8",
);

test("sandbox agent icons share one local outline system", () => {
  for (const icon of ["CodexAgentIcon", "OpenClawAgentIcon", "HermesAgentIcon"]) {
    assert.match(iconsSource, new RegExp(`export function ${icon}`));
  }
  assert.equal((iconsSource.match(/viewBox="0 0 24 24"/g) ?? []).length, 3);
  assert.equal((iconsSource.match(/stroke="currentColor"/g) ?? []).length, 3);
  assert.equal((iconsSource.match(/strokeWidth="1\.75"/g) ?? []).length, 3);
});

test("all sandbox agent entry points use the shared vector icons", () => {
  assert.match(pickerSource, /<SandboxAgentIcon kind=\{type\}/);
  assert.match(myAgentsSource, /<SandboxAgentIcon kind=\{type\}/);
  assert.match(selectorSource, /<SandboxAgentIcon kind="codex"/);
  assert.match(selectorSource, /<SandboxAgentIcon kind=\{kind\}/);
  assert.doesNotMatch(selectorSource, /builtin-agents\/.*\.png/);
});
