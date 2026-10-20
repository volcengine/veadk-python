import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

test("prepares Agent data before committing the visible selection", () => {
  const handler = appSource.match(
    /const refreshCurrentAgentAndStartNewChat = async \(id: string\) => \{([\s\S]*?)\n  \};/,
  )?.[1] ?? "";

  assert.match(handler, /await Promise\.all\(/);
  assert.match(handler, /loadHydratedSessions\(id, userId\)/);
  assert.match(handler, /getAgentInfo\(id\)/);
  assert.match(handler, /getAutomaticEvaluationStatuses/);
  assert.ok(
    handler.indexOf("await Promise.all(") < handler.indexOf("setAppName(id)"),
    "the visible Agent must not change until preparation finishes",
  );
  assert.equal(
    handler.match(/startNewChat\(\)/g)?.length ?? 0,
    1,
    "an Agent selection should initialize the new chat exactly once",
  );
});

test("does not reload prepared sessions after the atomic selection commit", () => {
  assert.match(appSource, /const preparedAgentSelectionRef = useRef/);
  assert.match(
    appSource,
    /const preparedSelection = preparedAgentSelectionRef\.current;[\s\S]*?preparedSelection\?\.agentId === appName[\s\S]*?preparedAgentSelectionRef\.current = null;[\s\S]*?return;[\s\S]*?const list = await refreshSessions\(appName\)/,
  );
});
