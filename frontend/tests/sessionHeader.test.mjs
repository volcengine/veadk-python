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
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);

test("keeps Agent selection state without a global conversation header", () => {
  assert.doesNotMatch(appSource, /function activeSessionTitle|conversationTitle/);
  assert.doesNotMatch(appSource, /<Navbar\b/);
  assert.match(appSource, /void refreshAgentLibrary\(\)/);
  assert.match(
    appSource,
    /if \(agentsSource === "cloud"\) \{[\s\S]*?remoteSelectionIds\(connections\)[\s\S]*?if \(current && remoteIds\.includes\(current\)\) return current;[\s\S]*?return "";/,
  );
  assert.doesNotMatch(appSource, /if \(saved && remoteIds\.includes\(saved\)\) return saved/);
  assert.doesNotMatch(appSource, /setAppName\(valid \? saved : fallback \|\| ""\)/);
  assert.doesNotMatch(appSource, /remoteIds\[0\] \?\? ""/);
  assert.doesNotMatch(appSource, /if \(agentsSource === "cloud"\) \{\s*setAppName\(""\)/);
  assert.match(navbarSource, /appName \? label\(appName\) : t\("navbar\.selectAgent"\)/);
  assert.match(navbarSource, /agentsSource === "cloud"[\s\S]*?aria-label=\{t\("navbar\.switchAgent"\)\}/);
  assert.match(navbarSource, /<ArrowLeftRight aria-hidden="true"/);
});

test("does not add a sandbox title row above the main content", () => {
  assert.doesNotMatch(appSource, /<Navbar\b/);
  assert.match(appSource, /<section className="main-shell">\s*<main\s+className=/);
});

test("opens new chat even when no Agent is active", () => {
  const handler = appSource.match(
    /function openNewChat\(\) \{([\s\S]*?)\n  \}\n\n  async function removeSession/,
  )?.[1] ?? "";
  assert.match(handler, /setMyAgents\(false\)/);
  assert.match(handler, /startNewChat\(\)/);
  assert.doesNotMatch(handler, /hasAgentSelection|showToast|setMyAgents\(true\)/);
  assert.match(
    appSource,
    /onNewChat=\{\(\) => requestIntelligentNavigation\(openNewChat\)\}/,
  );
});

test("only using an Agent selects it for the main conversation", () => {
  assert.match(
    appSource,
    /const connectMyAgent[\s\S]*?connectRuntime[\s\S]*?await refreshCurrentAgentAndStartNewChat\(agentId\)/,
  );
  const detailHandlerStart = appSource.indexOf("const openMyAgentDetails");
  const detailHandlerEnd = appSource.indexOf("\n  };", detailHandlerStart);
  assert.ok(detailHandlerStart >= 0 && detailHandlerEnd > detailHandlerStart);
  assert.doesNotMatch(
    appSource.slice(detailHandlerStart, detailHandlerEnd),
    /setAppName\(/,
  );
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

test("uses POST fallbacks for deletes routed through an API gateway", () => {
  assert.match(
    clientSource,
    /runtimeMethodOverride[\s\S]*?method:\s*"POST"[\s\S]*?_method",\s*"DELETE"/,
  );
  assert.match(
    clientSource,
    /deleteSessionMedia[\s\S]*?\/delete`[\s\S]*?method:\s*"POST"/,
  );
});
