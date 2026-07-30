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
    /if \(agentsSource === "cloud"\) \{[\s\S]*?remoteSelectionIds\(connections\)[\s\S]*?if \(saved && remoteIds\.includes\(saved\)\) return saved;[\s\S]*?return "";/,
  );
  assert.doesNotMatch(appSource, /remoteIds\[0\] \?\? ""/);
  assert.doesNotMatch(appSource, /if \(agentsSource === "cloud"\) \{\s*setAppName\(""\)/);
  assert.match(navbarSource, /appName \? label\(appName\) : "选择 Agent"/);
  assert.match(navbarSource, /agentsSource === "cloud"[\s\S]*?aria-label="切换智能体"/);
  assert.match(navbarSource, /<ArrowLeftRight aria-hidden="true"/);
  assert.match(appSource, /onBrowseAgents=\{openMyAgentsPage\}/);
});

test("shows the Codex identity instead of the Agent picker in sandbox sessions", () => {
  assert.match(
    appSource,
    /title=\{[\s\S]*?sandboxSession[\s\S]*?\? "Codex 智能体"[\s\S]*?: myAgents/,
  );
});

test("redirects new chat to Agent selection when no Agent is active", () => {
  assert.match(
    appSource,
    /function openNewChat\(\)[\s\S]*?!hasAgentSelection\(appName, apps, connections\)[\s\S]*?setMyAgents\(true\)[\s\S]*?showToast\("请先选择 agent"\)[\s\S]*?return;/,
  );
  assert.match(appSource, /if \(appName\) clearSelectedAgentAfterRemoval\(\)/);
  assert.match(appSource, /onNewChat=\{openNewChat\}/);
  assert.match(appSource, /className="app-toast" role="status" aria-live="polite"/);
  assert.match(stylesSource, /\.app-toast\s*\{[\s\S]*?position:\s*fixed;/);
});

test("only using an Agent selects it for the main conversation", () => {
  assert.match(
    appSource,
    /const connectMyAgent[\s\S]*?connectRuntime[\s\S]*?setAppName\(agentId\)/,
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
