import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const migrationSource = readFileSync(
  new URL("../src/create/LegacyMigrationCreate.tsx", import.meta.url),
  "utf8",
);
const migrationStyles = readFileSync(
  new URL("../src/create/LegacyMigrationCreate.css", import.meta.url),
  "utf8",
);

test("offers existing-system migration from the add-agent chooser", () => {
  assert.match(appSource, /key: "migration"[\s\S]*?title: "从存量系统迁移"/);
  assert.match(appSource, /function MigrationIcon/);
  assert.match(appSource, /visibleCreateView === "migration"/);
  assert.match(appSource, /<LegacyMigrationCreate/);
});

test("shows every framework supported by AgentKit CLI migrate", () => {
  for (const framework of [
    "langgraph",
    "langchain",
    "adk",
    "strands",
    "agentcore",
    "dify",
    "any",
  ]) {
    assert.match(migrationSource, new RegExp(`id: "${framework}"`));
  }
  assert.match(migrationSource, /role="tablist"/);
  assert.match(migrationSource, /role="tab"/);
});

test("uses project archives for structured frameworks and YAML for Dify", () => {
  assert.match(migrationSource, /accept=\{framework\.inputKind === "yaml"/);
  assert.match(migrationSource, /from "\.\/skills\/zip"/);
  assert.match(migrationSource, /parseDocument\(yaml\)/);
  assert.match(migrationSource, /入口对象/);
  assert.match(migrationSource, /启动远程 Sandbox/);
});

test("keeps the migration workspace responsive and visually aligned", () => {
  assert.match(migrationStyles, /\.migration-workspace\s*\{[\s\S]*?grid-template-columns:/);
  assert.match(migrationStyles, /@media \(max-width: 900px\)/);
  assert.doesNotMatch(migrationStyles, /font-family:\s*(monospace|[^;]*Mono)/i);
});
