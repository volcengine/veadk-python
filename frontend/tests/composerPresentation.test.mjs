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
  assert.match(appSource, /showMeta=\{turns\.length > 0\}/);
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
    /setTurnsFor\(sid, optimisticTurns\);[\s\S]*?setSessionId\(sid\);[\s\S]*?setInitializingSession\(false\);/,
  );
  assert.match(appSource, /const conversationBusy = busy \|\| initializingSession/);
  assert.match(composerSource, /sessionInitializing \? "初始化中" : sessionId \|\| "—"/);
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
  assert.match(appSource, /agentName=\{appName \? labelOf\(appName\) : "Agent"\}/);
  assert.match(composerSource, /`向 \$\{agentName\} 发消息…`/);
  assert.doesNotMatch(composerSource, /给智能体发消息/);
});
