import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const composerSource = readFileSync(
  new URL("../src/ui/Composer.tsx", import.meta.url),
  "utf8",
);
const pickerSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatAgentPicker.tsx", import.meta.url),
  "utf8",
);
const pickerStyles = readFileSync(
  new URL("../src/ui/new-chat-modes/new-chat-agent-picker.css", import.meta.url),
  "utf8",
);
const agentFaceSource = readFileSync(
  new URL("../src/ui/AgentFaceIcon.tsx", import.meta.url),
  "utf8",
);
const globalStyles = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);

test("opens the new-chat screen without a selected Agent", () => {
  const openNewChat = appSource.match(
    /function openNewChat\(\) \{([\s\S]*?)\n  \}\n\n  async function removeSession/,
  )?.[1] ?? "";

  assert.match(openNewChat, /setMyAgents\(false\)/);
  assert.match(openNewChat, /startNewChat\(\)/);
  assert.doesNotMatch(openNewChat, /hasAgentSelection/);
  assert.doesNotMatch(openNewChat, /请先选择 Agent/);
});

test("keeps message actions disabled while leaving the Agent picker available", () => {
  assert.match(composerSource, /<NewChatAgentPicker/);
  assert.match(composerSource, /disabled=\{agentPickerDisabled\}/);
  assert.match(composerSource, /disabled=\{disabled \|\| !allowAttachments\}/);
  assert.match(appSource, /agentPickerDisabled=\{!userId \|\| conversationBusy\}/);
  assert.match(
    appSource,
    /newChatMode === "agent" && !appName/,
    "the textarea, attachments, and send action remain disabled without an Agent",
  );
});

test("renders a two-level Agent type and runtime menu", () => {
  assert.match(pickerSource, /label: "通用智能体"/);
  assert.match(pickerSource, /label: "Codex 智能体"/);
  assert.match(pickerSource, /label: "OpenClaw 智能体"/);
  assert.match(pickerSource, /label: "Hermes 智能体"/);
  assert.match(pickerSource, /aria-label="智能体类型"/);
  assert.match(pickerSource, /aria-label=\{`\$\{activeTypeLabel\}列表`\}/);
  assert.match(pickerSource, /getRuntimes\(\{[\s\S]*?region: "all"[\s\S]*?pageSize: PAGE_SIZE/);
  assert.match(pickerSource, /onSelectRuntime\(runtime\)/);
  assert.match(appSource, /onSelectRuntime=\{async \(runtime\) => \{[\s\S]*?connectMyAgent/);
  assert.match(pickerSource, /暂未开放/);
  assert.match(pickerSource, /disabled/);
  assert.match(pickerStyles, /\.new-chat-agent-picker__submenu/);
});

test("reuses the blinking Sidebar Agent face for the trigger and general type", () => {
  assert.match(pickerSource, /import \{ AgentFaceIcon \} from "\.\.\/AgentFaceIcon"/);
  assert.match(
    pickerSource,
    /className = "new-chat-agent-picker__type-icon"[\s\S]*?type === "general"[\s\S]*?<AgentFaceIcon className=\{className\}/,
  );
  assert.match(
    pickerSource,
    /<AgentFaceIcon className="new-chat-agent-picker__trigger-icon"/,
  );
  assert.match(agentFaceSource, /sidebar-agent-face__eye/);
  assert.match(
    globalStyles,
    /\.sidebar-agent-face__eye\s*\{[\s\S]*?animation: sidebar-agent-blink 1s ease-in-out infinite/,
  );
  assert.match(
    globalStyles,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.sidebar-agent-face__eye\s*\{[\s\S]*?animation: none/,
  );
});

test("uses compact official empty states without fake actions", () => {
  assert.match(
    pickerSource,
    /from "@openai\/apps-sdk-ui\/components\/EmptyMessage"/,
  );
  assert.match(
    pickerSource,
    /runtimes\.length === 0[\s\S]*?className="new-chat-agent-picker__empty"[\s\S]*?<EmptyMessage\.Icon[\s\S]*?size="sm"[\s\S]*?<AgentFaceIcon[\s\S]*?<EmptyMessage\.Title[^>]*>[\s\S]*?暂无通用智能体[\s\S]*?<\/EmptyMessage\.Title>/,
  );
  assert.match(
    pickerSource,
    /activeType !== "general"[\s\S]*?className="new-chat-agent-picker__empty"[\s\S]*?<AgentTypeIcon[\s\S]*?type=\{activeType\}[\s\S]*?<EmptyMessage\.Title[^>]*>[\s\S]*?\{activeTypeLabel\}[\s\S]*?<\/EmptyMessage\.Title>[\s\S]*?<EmptyMessage\.Description[^>]*>[\s\S]*?暂未开放[\s\S]*?<\/EmptyMessage\.Description>/,
  );
  assert.doesNotMatch(pickerSource, /new-chat-agent-picker__empty[\s\S]*?<Button/);
  assert.match(pickerStyles, /\.new-chat-agent-picker__empty\s*\{[\s\S]*?min-height: 116px/);
});

test("supports recovery, keyboard navigation, and focus return", () => {
  assert.match(pickerSource, /role="alert"/);
  assert.match(pickerSource, /重新加载/);
  assert.match(pickerSource, /正在加载智能体/);
  assert.match(pickerSource, /正在连接/);
  assert.match(pickerSource, /if \(connectingRuntimeId\) return/);
  assert.match(pickerSource, /event\.key === "ArrowDown"/);
  assert.match(pickerSource, /event\.key === "ArrowUp"/);
  assert.match(pickerSource, /event\.key === "ArrowRight"/);
  assert.match(pickerSource, /event\.key === "ArrowLeft"/);
  assert.match(pickerSource, /event\.key === "Enter"/);
  assert.match(pickerSource, /event\.key === "Escape"/);
  assert.match(pickerSource, /triggerRef\.current\?\.focus\(\)/);
  assert.match(pickerSource, /requestIdRef\.current/);
  assert.match(pickerSource, /RUNTIME_LOAD_TIMEOUT_MS = 15_000/);
  assert.match(pickerSource, /Promise\.race\(/);
  assert.match(pickerSource, /window\.setTimeout\([\s\S]*?加载智能体超时/);
  assert.match(pickerSource, /window\.clearTimeout\(timeoutId\)/);
  const errorBranch = pickerSource.slice(
    pickerSource.indexOf("error && runtimes.length === 0"),
    pickerSource.indexOf(": runtimes.length === 0 ?"),
  );
  assert.doesNotMatch(errorBranch, /<EmptyMessage/);
});

test("opens on deliberate mouse hover and closes only after leaving the picker", () => {
  assert.match(pickerSource, /HOVER_OPEN_DELAY_MS = 120/);
  assert.match(pickerSource, /HOVER_CLOSE_DELAY_MS = 180/);
  assert.match(
    pickerSource,
    /onPointerEnter=\{\(event\) => \{\s*if \(event\.pointerType === "mouse"\) cancelHoverClose\(\)/,
  );
  assert.match(
    pickerSource,
    /onPointerLeave=\{\(event\) => \{\s*if \(event\.pointerType === "mouse"\) scheduleHoverClose\(\)/,
  );
  assert.match(
    pickerSource,
    /onPointerEnter=\{\(event\) => \{\s*if \(event\.pointerType === "mouse"\) scheduleHoverOpen\(\)/,
  );
  assert.match(pickerSource, /window\.setTimeout\([\s\S]*?HOVER_OPEN_DELAY_MS/);
  assert.match(pickerSource, /window\.setTimeout\([\s\S]*?HOVER_CLOSE_DELAY_MS/);
  assert.match(pickerSource, /onClick=\{\(\) => open \? close\(\) : openPicker\(true\)\}/);
  assert.match(pickerSource, /event\.key === "ArrowDown" \|\| event\.key === "ArrowUp"/);
});
