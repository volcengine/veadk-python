import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const navbarSource = readFileSync(
  new URL("../src/ui/Navbar.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);

test("uses the selected Agent in new-chat, search, and conversation headers", () => {
  assert.doesNotMatch(appSource, /function activeSessionTitle|conversationTitle/);
  assert.match(appSource, /agentLabel=\{labelOf\}/);
  assert.match(appSource, /agentsSource=\{agentsSource\}/);
  assert.match(appSource, /void refreshAgentLibrary\(\)/);
  assert.match(
    appSource,
    /if \(agentsSource === "cloud"\) \{[\s\S]*?remoteIds[\s\S]*?remoteIds\.includes\(saved\)[\s\S]*?remoteIds\[0\] \?\? ""/,
  );
  assert.doesNotMatch(appSource, /if \(agentsSource === "cloud"\) \{\s*setAppName\(""\)/);
  assert.match(navbarSource, /appName \? label\(appName\) : "选择 Agent"/);
  assert.match(navbarSource, /<AgentSelector[\s\S]*?variant="navbar"/);
});

test("keeps the Agent trigger visually aligned with the previous title", () => {
  assert.match(
    stylesSource,
    /\.agent-dd-trigger\s*\{[\s\S]*?font-size:\s*16px;[\s\S]*?font-weight:\s*650;/,
  );
  assert.match(stylesSource, /\.agent-dd-current\s*\{[\s\S]*?text-overflow:\s*ellipsis;/);
  assert.match(
    stylesSource,
    /\.navbar-left\s*\{[\s\S]*?container-type:\s*inline-size;/,
  );
  assert.match(
    stylesSource,
    /\.agent-dd\s*\{[\s\S]*?max-width:\s*33\.333cqw;/,
  );
  assert.match(
    stylesSource,
    /\.agent-dd-trigger\s*\{[\s\S]*?max-width:\s*100%;/,
  );
});
