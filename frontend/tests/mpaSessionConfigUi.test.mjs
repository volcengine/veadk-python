import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const connectionsSource = readFileSync(
  new URL("../src/adk/connections.ts", import.meta.url),
  "utf8",
);
const myAgentsSource = readFileSync(
  new URL("../src/ui/MyAgents.tsx", import.meta.url),
  "utf8",
);
const workspaceSource = readFileSync(
  new URL("../src/ui/AgentWorkspace.tsx", import.meta.url),
  "utf8",
);
const workspaceStyles = readFileSync(
  new URL("../src/ui/AgentWorkspace.css", import.meta.url),
  "utf8",
);

test("propagates MPA category and active session context into Agent details", () => {
  assert.match(connectionsSource, /agentCategory\?: "general" \| "mpa"/);
  assert.match(connectionsSource, /const previous = existingIndex === -1 \? undefined : list\[existingIndex\]/);
  assert.match(connectionsSource, /agentCategory: agentCategory \?\? previous\?\.agentCategory/);
  assert.match(myAgentsSource, /const category = runtime\.agentCategory \?\? agentCategory/);
  assert.match(
    appSource,
    /connectRuntime\([\s\S]*?agentCategory: agent\.agentCategory[\s\S]*?mpaInstanceId: agent\.mpaInstanceId/,
  );
  assert.match(
    appSource,
    /agentCategory: agentDetailTarget\.agentCategory \?\? agentDetailTarget\.runtime\.agentCategory/,
  );
  assert.match(appSource, /currentSessionId=\{sessionId\}/);
  assert.match(appSource, /currentRuntimeId=\{connectedRuntimeId\}/);
  const openMyAgentsPageStart = appSource.indexOf("const openMyAgentsPage = () => {");
  const openMyAgentsPageEnd = appSource.indexOf("const openWorkspacePage = () => {", openMyAgentsPageStart);
  assert.ok(openMyAgentsPageStart >= 0 && openMyAgentsPageEnd > openMyAgentsPageStart);
  const openMyAgentsPage = appSource.slice(openMyAgentsPageStart, openMyAgentsPageEnd);
  assert.doesNotMatch(openMyAgentsPage, /setSessionId\(""\)/);
  assert.doesNotMatch(openMyAgentsPage, /viewSidRef\.current = ""/);
});

test("MPA Session configuration UI is scoped to the active MPA Session", () => {
  assert.match(
    workspaceSource,
    /type AgentSection =[\s\S]*?"sessionConfig"/,
  );
  assert.match(workspaceSource, /getMpaSessionExecutionConfig/);
  assert.match(workspaceSource, /patchMpaSessionExecutionConfig/);
  assert.match(workspaceSource, /upgradeMpaSessionProfile/);
  assert.match(
    workspaceSource,
    /selectedAgent\?\.agentCategory === "mpa"/,
  );
  assert.match(
    workspaceSource,
    /selectedAgent\?\.runtimeId === currentRuntimeId/,
  );
  assert.match(
    workspaceSource,
    /sessionExecutionConfigLoadable = Boolean\(/,
  );
  assert.match(
    workspaceSource,
    /section !== "sessionConfig" \|\|[\s\S]*?getMpaSessionExecutionConfig\(/,
  );
  assert.match(
    workspaceSource,
    /patchMpaSessionExecutionConfig\([\s\S]*?etag: selectedSessionExecutionConfig\.etag/,
  );
  assert.match(
    workspaceSource,
    /upgradeMpaSessionProfile\([\s\S]*?idempotencyKey: profileUpgradeIdempotencyKey/,
  );
  assert.match(
    workspaceSource,
    /MpaExecutionConfigRequestError[\s\S]*?error\.status === 412[\s\S]*?error\.currentState/,
  );
  assert.match(workspaceSource, /className="aw-session-config"/);
  assert.match(workspaceStyles, /\.aw-session-config\s*\{/);
  assert.match(workspaceStyles, /\.aw-session-config-grid\s*\{/);
});

test("MPA chat sends the accepted execution config revision to runSSE", () => {
  assert.match(appSource, /function lastCompletedEventId\(turns: Turn\[\] \| undefined\)/);
  assert.match(appSource, /turn\.role === "assistant" && turn\.meta\?\.eventId/);
  assert.match(appSource, /const \[appName, setAppName\] = useState\(\(\) =>[\s\S]*?localStorage\.getItem\(LS\.app\)/);
  assert.match(appSource, /const \[sessionId, setSessionId\] = useState\(\(\) =>[\s\S]*?localStorage\.getItem\(LS\.session\)/);
  assert.match(appSource, /if \(id === sessionId && turnsBySession\[id\] !== undefined\) return/);
  const resolveAuthStart = appSource.indexOf("const resolveAuth = useCallback(() => {");
  const resolveAuthEnd = appSource.indexOf("useEffect(() => {\n    resolveAuth();", resolveAuthStart);
  assert.ok(resolveAuthStart >= 0 && resolveAuthEnd > resolveAuthStart);
  const resolveAuthSource = appSource.slice(resolveAuthStart, resolveAuthEnd);
  assert.match(resolveAuthSource, /!localStorage\.getItem\(LS\.session\)/);
  assert.match(appSource, /const mpaRunConfig = await resolveMpaRunConfig\(sid, ctrl\.signal\)/);
  assert.match(appSource, /idempotencyKey: mpaRunConfig\?\.idempotencyKey/);
  assert.match(appSource, /executionConfigVersion: mpaRunConfig\?\.executionConfigVersion/);
  assert.match(appSource, /lastEventId: lastCompletedEventId\(turnsBySession\[sid\]\)/);
  assert.match(appSource, /getMpaSessionExecutionConfig\(\{[\s\S]*?runtimeId: currentConn\.runtimeId/);
  assert.match(appSource, /agentCategory === "mpa"[\s\S]*?config\.revision/);
});
