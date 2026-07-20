import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const manageSource = readFileSync(
  new URL("../src/ui/ManageAgents.tsx", import.meta.url),
  "utf8",
);
const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const connectionsSource = readFileSync(
  new URL("../src/adk/connections.ts", import.meta.url),
  "utf8",
);
const manageStyles = readFileSync(
  new URL("../src/ui/ManageAgents.css", import.meta.url),
  "utf8",
);

test("managed runtimes can connect through the global Agent selector", () => {
  assert.match(manageSource, /onConnect:\s*\(runtime:\s*ManagedRuntime\)/);
  assert.match(manageSource, /连接到此 Agent/);
  assert.match(manageSource, /currentRuntimeId === rt\.runtimeId[\s\S]*?已连接/);
  assert.match(
    appSource,
    /<ManageAgentsView[\s\S]*?currentRuntimeId=\{currentRuntime\?\.runtimeId\}[\s\S]*?onConnect=\{connectManagedRuntime\}/,
  );
  assert.match(
    manageStyles,
    /@media \(max-width:\s*700px\)[\s\S]*?\.manage-item-actions\s*\{[\s\S]*?width:\s*100%;/,
  );
});

test("runtime connection probing is shared with the Agent selector", () => {
  assert.match(connectionsSource, /export async function connectRuntime/);
  assert.match(connectionsSource, /probeRuntimeApps\(runtimeId, region\)/);
  assert.match(connectionsSource, /addRuntimeConnection\(/);
  assert.match(connectionsSource, /return remoteAppId\(connection\.id, apps\[0\]\)/);
});
