import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const clientSource = readFileSync(
  new URL("../src/adk/embeddedAgents.ts", import.meta.url),
  "utf8",
);
const directorySource = readFileSync(
  new URL("../src/ui/MyAgents.tsx", import.meta.url),
  "utf8",
);
const workspaceSource = readFileSync(
  new URL("../src/ui/EmbeddedAgentWorkspace.tsx", import.meta.url),
  "utf8",
);
const workspaceStyles = readFileSync(
  new URL("../src/ui/EmbeddedAgentWorkspace.css", import.meta.url),
  "utf8",
);

test("lists, creates, and connects Hermes and OpenClaw AgentKit sessions", () => {
  assert.match(clientSource, /export type EmbeddedAgentKind = "openclaw" \| "hermes"/);
  assert.ok(clientSource.includes("return `/web/${kind}`;"));
  assert.match(clientSource, /async listSessions/);
  assert.match(clientSource, /async connect/);
  assert.match(clientSource, /\/connect`/);
  assert.match(clientSource, /async disconnect/);
  assert.match(clientSource, /\/web\/embedded\/\$\{encodeURIComponent\(session\.id\)\}/);
  assert.match(clientSource, /method: "POST"/);
  assert.match(directorySource, /embeddedAgentClient\.listSessions/);
  assert.match(directorySource, /EmbeddedSessionCard/);
  assert.match(directorySource, /onCreateEmbeddedAgent\(activeType\)/);
  assert.match(
    clientSource,
    /body: JSON\.stringify\(\{ displayName: options\.displayName\?\.trim\(\) \?\? "" \}\)/,
  );
  assert.match(
    appSource,
    /embeddedAgentClient\.start\(kind, \{ displayName, signal \}\)/,
  );
  assert.match(appSource, /function openEmbeddedAgentLaunch\(kind: EmbeddedAgentKind\)/);
  assert.match(
    appSource,
    /<SandboxLaunchDialog[\s\S]*?agentLabel=\{embeddedAgentLaunchLabel\}/,
  );
  assert.match(appSource, /embeddedAgentClient\.connect\(session, signal\)/);
  assert.match(appSource, /embeddedAgentClient\.disconnect\(active\)/);
});

test("shows same-origin WebUI and Terminal iframe tabs without refresh or external-open controls", () => {
  assert.match(workspaceSource, /role="tablist"/);
  assert.match(workspaceSource, /主页面/);
  assert.match(workspaceSource, /Terminal/);
  assert.match(workspaceSource, /session\.webuiUrl/);
  assert.match(workspaceSource, /session\.terminalUrl/);
  assert.match(workspaceSource, /<iframe/);
  assert.doesNotMatch(workspaceSource, /刷新|reload|window\.open|target="_blank"|新窗口/);
  assert.match(workspaceSource, /aria-label=\{`关闭 \$\{detail\.label\} 工作区`\}/);
});

test("keeps Studio auth out of sandbox iframe and terminal URLs", () => {
  assert.match(clientSource, /webuiUrl: value\.webuiUrl/);
  assert.match(clientSource, /terminalUrl: value\.terminalUrl/);
  assert.doesNotMatch(clientSource, /webuiUrl: withAuth\(/);
  assert.doesNotMatch(clientSource, /terminalUrl: withAuth\(/);
});

test("mounts each iframe once and preserves its connection while switching tabs", () => {
  assert.match(workspaceSource, /const \[visited, setVisited\]/);
  assert.match(workspaceSource, /if \(!visited\[item\]\) return null/);
  assert.match(workspaceSource, /hidden=\{!active\}/);
  assert.match(workspaceSource, /current\[next\] \? current : \{ \.\.\.current, \[next\]: true \}/);
  assert.match(workspaceStyles, /\.embedded-agent-panel\s*\{[\s\S]*?display: none/);
  assert.match(workspaceStyles, /\.embedded-agent-panel\.is-active\s*\{[\s\S]*?display: flex/);
});

test("keeps the iframe height chain anchored to the remaining workspace", () => {
  assert.match(
    workspaceStyles,
    /\.embedded-agent-stage\s*\{[\s\S]*?display:\s*flex;[\s\S]*?overflow:\s*hidden;/,
  );
  assert.match(
    workspaceStyles,
    /\.embedded-agent-panel iframe\s*\{[\s\S]*?flex:\s*1;[\s\S]*?display:\s*block;[\s\S]*?min-height:\s*0;/,
  );
});

test("supports keyboard tab navigation and reduced motion", () => {
  assert.match(workspaceSource, /ArrowLeft/);
  assert.match(workspaceSource, /ArrowRight/);
  assert.match(workspaceSource, /aria-selected=\{surface === "webui"\}/);
  assert.match(workspaceSource, /aria-selected=\{surface === "terminal"\}/);
  assert.match(workspaceStyles, /@media \(prefers-reduced-motion: reduce\)/);
});
