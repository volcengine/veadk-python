import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);
const dialogSource = readFileSync(
  new URL("../src/ui/AgentKitCliDialog.tsx", import.meta.url),
  "utf8",
);
const sandboxControlsSource = readFileSync(
  new URL("../src/ui/SandboxControls.tsx", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/agentkitCli.ts", import.meta.url),
  "utf8",
);
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

test("keeps the CLI and Developer Resources shortcuts beside the account", () => {
  assert.match(sidebarSource, /onAgentKitCli: \(\) => void/);
  assert.doesNotMatch(sidebarSource, /AgentKitPromoCard/);
  assert.match(sidebarSource, /className="sidebar-user-shortcuts"[\s\S]*?aria-label=\{t\("sidebar:account\.shortcuts"\)\}/);
  assert.match(sidebarSource, /<Tooltip compact content=\{t\("sidebar:account\.tryCli"\)\}>/);
  assert.match(sidebarSource, /<Tooltip compact content=\{t\("sidebar:account\.developerResources"\)\}>/);
  assert.match(sidebarSource, /aria-label=\{t\("sidebar:account\.tryCli"\)\}/);
  assert.match(sidebarSource, /aria-label=\{t\("sidebar:account\.developerResources"\)\}/);
  assert.equal(sidebarSource.indexOf(">AgentKit 文档</span>"), -1);
  assert.equal(sidebarSource.indexOf(">AgentKit 控制台</span>"), -1);
  assert.match(
    sidebarSource,
    /import \{ MarkerCode \} from "@openai\/apps-sdk-ui\/components\/Icon"/,
  );
  assert.match(
    sidebarSource,
    /aria-label=\{t\("sidebar:account\.tryCli"\)\}[\s\S]*?<MarkerCode className="icon" \/>/,
  );
  assert.match(appSource, /onAgentKitCli=\{\(\) => setAgentKitCliOpen\(true\)\}/);
  assert.match(appSource, /<AgentKitCliDialog[\s\S]*?open=\{agentKitCliOpen\}/);
});

test("initializes a non-persistent per-user AgentKit CLI session", () => {
  assert.match(clientSource, /const API = "\/web\/agentkit-cli"/);
  assert.match(clientSource, /JSON\.stringify\(\{ persistent: false \}\)/);
  assert.match(dialogSource, /agentKitCliClient\.listSessions/);
  assert.match(dialogSource, /agentKitCliClient\.createSession/);
  assert.match(dialogSource, /agentKitCliClient\.openSession/);
  assert.match(dialogSource, /agentKitCliClient\.launchTerminal/);
  assert.match(dialogSource, /t\(`agentKitCli\.loading\.\$\{state\}`\)/);
  assert.match(dialogSource, /onStage\("searching"\)/);
  assert.match(dialogSource, /onStage\("creating"\)/);
  assert.match(dialogSource, /onStage\("connecting"\)/);
});

test("reuses the current terminal launch while its session is valid", () => {
  assert.match(
    dialogSource,
    /if \(launch && isLaunchReusable\(expireAt, Date\.now\(\)\)\) \{[\s\S]*?setState\("ready"\);[\s\S]*?return undefined;/,
  );
  assert.doesNotMatch(
    dialogSource,
    /if \(!open\) return undefined;[\s\S]{0,120}setLaunch\(null\);/,
  );
  assert.match(dialogSource, /<DialogShell[\s\S]*?keepMounted/);
  assert.match(sandboxControlsSource, /if \(!open && !keepMounted\) return null/);
  assert.match(sandboxControlsSource, /hidden=\{!open\}/);
});

test("shows configuration, retry, terminal, and expiry states", () => {
  assert.match(
    clientSource,
    /agentKitCliUnconfiguredMessage\(\): string/,
  );
  assert.match(dialogSource, /t\("agentKitCli\.recyclingHoursMinutes", \{ hours, minutes \}\)/);
  assert.match(dialogSource, /t\("agentKitCli\.recyclingMinutes", \{ minutes \}\)/);
  assert.doesNotMatch(dialogSource, /在专属 Dev Sandbox Session 中体验 AgentKit CLI/);
  assert.match(dialogSource, /t\("agentKitCli\.requestFailed"\)/);
  assert.match(dialogSource, /agentkit-cli-error-detail/);
  assert.match(dialogSource, /t\("agentKitCli\.connectionError", \{ message: raw \}\)/);
  assert.match(clientSource, /httpErrorMessage\(response, fallback\)/);
  assert.match(dialogSource, /t\("agentKitCli\.retry"\)/);
  assert.match(dialogSource, /title=\{t\("agentKitCli\.terminalTitle"\)\}/);
});
