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
const sandboxComposerSource = readFileSync(
  new URL("../src/ui/SandboxComposer.tsx", import.meta.url),
  "utf8",
);
const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);
const blocksSource = readFileSync(
  new URL("../src/ui/Blocks.tsx", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);

test("matches conversation copy to thinking status typography", () => {
  assert.match(stylesSource, /\.bubble\s*\{[^}]*font-size:\s*14\.5px/);
  assert.match(stylesSource, /\.md\s*\{[^}]*font-size:\s*14\.5px/);
  assert.match(stylesSource, /\.md\s*\{[^}]*line-height:\s*1\.65/);
});

test("aligns the conversation composer with the transcript content column", () => {
  assert.match(
    stylesSource,
    /\.conversation-composer-slot\s*\{[^}]*padding:\s*6px 16px 18px/,
  );
  assert.match(
    stylesSource,
    /\.conversation-composer-slot > \.composer-slot > \.composer\s*\{[^}]*padding:\s*0/,
  );
  assert.match(
    appSource,
    /<div className="conversation-composer-slot">\s*\{composer\}\s*<\/div>/,
  );
});

test("smoothly positions new turns and follows streamed output until interrupted", () => {
  assert.match(
    appSource,
    /el\.scrollTo\(\{ top: el\.scrollHeight, behavior: "smooth" \}\)/,
  );
  assert.match(
    appSource,
    /className=\{`transcript\$\{activeConversationPresenting \? " is-streaming" : ""\}`\}/,
  );
  assert.doesNotMatch(appSource, /useStickToBottom<HTMLDivElement>\(turns\)/);
  assert.match(
    appSource,
    /conversationAutoFollowRef\.current =\s*el\.scrollHeight - el\.scrollTop - el\.clientHeight < 32/,
  );
  assert.match(
    appSource,
    /!conversationAutoFollowRef\.current \|\|[\s\S]*?conversationSmoothScrollRef\.current[\s\S]*?el\.scrollTop = el\.scrollHeight/,
  );
  assert.match(
    appSource,
    /conversationSmoothScrollRef\.current = false;[\s\S]*?const current = scrollRef\.current;[\s\S]*?conversationAutoFollowRef\.current[\s\S]*?current\.scrollTop = current\.scrollHeight/,
  );
  assert.match(
    stylesSource,
    /\.transcript\.is-streaming\s*\{[^}]*overflow-anchor:\s*none/,
  );
  assert.match(
    stylesSource,
    /\.transcript\.is-streaming > \.turn--assistant:last-child\s*\{[^}]*min-height:\s*max\(0px, calc\(100% - 180px\)\)/,
  );
  assert.match(blocksSource, /STREAM_FRAME_INTERVAL_MS = 28/);
  assert.match(blocksSource, /window\.requestAnimationFrame\(renderFrame\)/);
  assert.match(blocksSource, /Math\.min\(18, Math\.max\(2, Math\.ceil\(remaining \/ 6\)\)\)/);
  assert.match(blocksSource, /prefers-reduced-motion: reduce/);
  assert.match(
    blocksSource,
    /cancelAnimationFrame\(frameRef\.current\);\s*frameRef\.current = null/,
  );
  assert.match(
    appSource,
    /streaming=\{isLast && \(activeConversationBusy \|\| presentingStream\)\}/,
  );
  assert.match(appSource, /finishStreamPresentation[\s\S]*?2400/);
  assert.match(appSource, /onStreamFrame=\{isLast \? followConversationStreamFrame : undefined\}/);
  assert.match(blocksSource, /!done \|\| streaming/);
});

test("keeps thinking and tool status copy legible below the answer hierarchy", () => {
  const builtinStylesSource = readFileSync(
    new URL("../src/ui/builtin-tools/builtin-tools.css", import.meta.url),
    "utf8",
  );
  assert.match(stylesSource, /\.think-label\s*\{[^}]*font-size:\s*14\.5px/);
  assert.match(stylesSource, /\.tool-name\s*\{[^}]*font-size:\s*14\.5px/);
  assert.match(stylesSource, /\.think-body\s*\{[^}]*font-size:\s*14px/);
  assert.match(
    builtinStylesSource,
    /\.builtin-tool-label\s*\{[^}]*font-size:\s*14\.5px/,
  );
  assert.match(stylesSource, /\.think-body\s*\{[^}]*margin:\s*0/);
  assert.match(stylesSource, /\.think-body\s*\{[^}]*padding:\s*0/);
  assert.match(stylesSource, /\.think-body\s*\{[^}]*border-left:\s*0/);
});

test("collapses untouched thinking as soon as answer text starts streaming", () => {
  assert.match(blocksSource, /answerStarted\?: boolean/);
  assert.match(
    blocksSource,
    /if \(!touched\.current\) setOpen\(!\(done \|\| answerStarted\)\)/,
  );
  assert.match(
    blocksSource,
    /blocks\.slice\(i \+ 1\)\.some\([\s\S]*?block\.kind === "text"[\s\S]*?block\.text\.trim\(\)/,
  );
  assert.match(blocksSource, /answerStarted=\{answerStarted\}/);
});

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
  assert.match(sidebarSource, /title: sessionTitle\(session\.events\)/);
  assert.match(sidebarSource, /title=\{item\.title\}/);
  assert.doesNotMatch(sidebarSource, /title=\{item\.id\}/);
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

test("uses product-specific composer copy for Agent and sandbox sessions", () => {
  assert.match(
    appSource,
    /<SandboxComposer[\s\S]*?appName=\{appName\}/,
  );
  assert.match(appSource, /agentName=\{appName \? labelOf\(appName\) : "Agent"\}/);
  assert.match(composerSource, /`向 \$\{agentName\} 发消息…`/);
  assert.match(composerSource, /请先选择智能体/);
  assert.doesNotMatch(composerSource, /给智能体发消息/);
  assert.match(
    sandboxComposerSource,
    /textOnly\s*\?\s*"继续说明你想实现或调整的内容"\s*:\s*"向 AgentKit 沙箱发送消息，输入 \/ 查看命令，输入 \$ 调用 Skill…"/,
  );
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
