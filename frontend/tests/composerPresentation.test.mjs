import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
const composerSource = readFileSync(
  new URL("../src/ui/Composer.tsx", import.meta.url),
  "utf8",
);
const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);

test("shows session metadata only after the conversation starts", () => {
  assert.match(appSource, /showMeta=\{turns\.length > 0 && !sandboxSession\}/);
  assert.match(
    composerSource,
    /\{showMeta && \(\s*<div className="composer-meta">/,
  );
});

test("first message renders before session creation finishes", () => {
  assert.match(
    appSource,
    /setPendingTurns\(optimisticTurns\);\s*setInitializingSession\(true\);/,
  );
  assert.match(appSource, /sid = await ensureSession\(!createsSession\)/);
  assert.match(
    appSource,
    /setTurnsFor\(sid,\s*\(current\)\s*=>\s*createsSession\s*\?\s*optimisticTurns\s*:\s*\[\.\.\.current,\s*\.\.\.optimisticTurns\],\s*\);[\s\S]*?setSessionId\(sid\);[\s\S]*?setInitializingSession\(false\);/,
  );
  assert.match(appSource, /const conversationBusy = busy \|\| initializingSession/);
  assert.match(composerSource, /sessionInitializing \? "初始化中" : sessionId \|\| "—"/);
});

test("subsequent messages append to the active session transcript", () => {
  assert.match(
    appSource,
    /createsSession\s*\?\s*optimisticTurns\s*:\s*\[\.\.\.current,\s*\.\.\.optimisticTurns\]/,
  );
  assert.doesNotMatch(appSource, /setTurnsFor\(sid, optimisticTurns\);/);
});

test("new-session failure restores the submitted text", () => {
  assert.match(
    appSource,
    /catch \(e\) \{\s*if \(createsSession\) \{[\s\S]*?setInput\(text\);[\s\S]*?setInvocation\(selectedInvocation\);/,
  );
});

test("welcome screen offers a broader set of prompts", () => {
  const greetings = appSource.match(/const GREETINGS = \[([\s\S]*?)\];/)?.[1] ?? "";
  assert.ok((greetings.match(/"/g)?.length ?? 0) >= 20);
  assert.match(greetings, /今天想先解决哪件事？/);
  assert.match(greetings, /我在，随时可以开始/);
});

test("shows full session titles on hover instead of internal ids", () => {
  assert.match(sidebarSource, /const title = sessionTitle\(s\.events\)/);
  assert.match(sidebarSource, /title=\{title\}/);
  assert.doesNotMatch(sidebarSource, /title=\{s\.id\}/);
});

test("renders a normal-font session id with an inline copy action", () => {
  assert.match(composerSource, /navigator\.clipboard\.writeText\(sessionId\)/);
  assert.match(composerSource, /className="composer-session-copy"/);
  assert.match(composerSource, /复制会话 ID/);
  assert.match(
    stylesSource,
    /\.composer-session-id\s*\{[^}]*font-family:\s*inherit/,
  );
});

test("addresses the selected Agent by its display name in the composer", () => {
  assert.match(
    appSource,
    /agentName=\{[\s\S]*?sandboxSession[\s\S]*?"AgentKit 沙箱"[\s\S]*?labelOf\(appName\)/,
  );
  assert.match(composerSource, /`向 \$\{agentName\} 发消息…`/);
  assert.doesNotMatch(composerSource, /给智能体发消息/);
});

test("composer slot keeps the input full width in the centered welcome layout", () => {
  const sandboxStyles = readFileSync(
    new URL("../src/ui/SandboxSession.css", import.meta.url),
    "utf8",
  );
  assert.match(appSource, /className=\{`composer-slot\$\{sandboxSession/);
  assert.match(sandboxStyles, /\.composer-slot\s*\{[^}]*width:\s*100%/);
  assert.match(sandboxStyles, /\.composer-slot\s*\{[^}]*min-width:\s*0/);
});
