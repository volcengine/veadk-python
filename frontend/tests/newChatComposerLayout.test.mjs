import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const composerSource = readFileSync(
  new URL("../src/ui/Composer.tsx", import.meta.url),
  "utf8",
);
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const selectorSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatModeSelector.tsx", import.meta.url),
  "utf8",
);
const sidebarSource = readFileSync(
  new URL("../src/ui/Sidebar.tsx", import.meta.url),
  "utf8",
);
const agentSelectorSource = readFileSync(
  new URL("../src/ui/AgentSelector.tsx", import.meta.url),
  "utf8",
);
const navbarSource = readFileSync(
  new URL("../src/ui/Navbar.tsx", import.meta.url),
  "utf8",
);
const modeStylesSource = readFileSync(
  new URL("../src/ui/new-chat-modes/new-chat-modes.css", import.meta.url),
  "utf8",
);
const stylesSource = readFileSync(
  new URL("../src/styles.css", import.meta.url),
  "utf8",
);

test("expands only the new-chat composer into a multiline input", () => {
  assert.match(
    composerSource,
    /className=\{`composer\$\{newChatLayout \? " composer--new-chat" : ""\}\$\{skillMode \? " composer--skill-mode" : ""\}`\}/,
  );
  assert.match(composerSource, /rows=\{newChatLayout \? 4 : 1\}/);
  assert.match(
    appSource,
    /newChatLayout=\{!sandboxSession && turns\.length === 0 && skillJob === null\}/,
  );
  assert.match(stylesSource, /\.composer--new-chat \.composer-box[\s\S]*?min-height:/);
  assert.match(stylesSource, /\.composer--new-chat \.composer-box[\s\S]*?border-color:/);
  assert.match(stylesSource, /\.composer--new-chat \.composer-box[\s\S]*?box-shadow:/);
  assert.match(stylesSource, /\.composer--new-chat \.comp-input[\s\S]*?min-height:/);
  assert.match(stylesSource, /\.composer--new-chat \.composer-menu-wrap[\s\S]*?bottom: 10px/);
  assert.match(stylesSource, /\.composer--new-chat \.comp-send[\s\S]*?bottom: 10px/);
  assert.match(stylesSource, /\.composer--new-chat \.comp-send \.icon[\s\S]*?width: 20px/);
});

test("keeps alternate chat modes hidden from the new-chat composer", () => {
  assert.match(appSource, /showModeSelector=\{false\}/);
  assert.match(composerSource, /<NewChatModeSelector[\s\S]*?value=\{newChatMode\}/);
  assert.match(selectorSource, /value: "agent"[\s\S]*?label: "Agent"/);
  assert.match(selectorSource, /value: "temporary"[\s\S]*?label: "内置智能体"/);
  assert.match(selectorSource, /value: "skill-create"[\s\S]*?label: "创建 Skill"/);
  assert.match(
    stylesSource,
    /\.composer--new-chat \.new-chat-mode[\s\S]*?left: 52px[\s\S]*?bottom: 10px/,
  );
  assert.match(
    modeStylesSource,
    /\.composer--new-chat \.new-chat-mode__trigger[\s\S]*?font-size: 15px/,
  );
  assert.match(
    modeStylesSource,
    /\.new-chat-mode__menu\s*\{[\s\S]*?top:\s*calc\(100% \+ 7px\);[\s\S]*?left:\s*0;/,
  );
  assert.match(selectorSource, /<AgentIdentityIcon className="new-chat-mode__agent-icon"/);
  assert.match(selectorSource, /className="new-chat-mode__temporary-icon"[\s\S]*?m10 2\.8 6\.1 3\.45/);
  assert.doesNotMatch(selectorSource, /M5 6\.2h10v7\.6H5z/);
  assert.doesNotMatch(selectorSource, /<AgentSelector/);
  assert.match(navbarSource, /<AgentSelector[\s\S]*?variant="navbar"/);
  assert.match(selectorSource, /Codex 智能体/);
  assert.match(selectorSource, /codexLogo/);
  assert.match(selectorSource, /\{ label: "ArkClaw", logo: arkClawLogo \}/);
  assert.match(selectorSource, /\{ label: "Hermes 智能体", logo: hermesLogo \}/);
  assert.match(selectorSource, /className="new-chat-mode__builtin-icon" src=\{logo\}/);
  assert.doesNotMatch(selectorSource, />[CAH]<\/span>/);
  assert.match(
    modeStylesSource,
    /\.new-chat-mode__builtin-icon\s*\{[\s\S]*?width:\s*24px;[\s\S]*?object-fit:\s*contain;/,
  );
  assert.match(agentSelectorSource, /variant\?: "drawer" \| "navbar"/);
  assert.doesNotMatch(sidebarSource, /<AgentSelector/);
  assert.doesNotMatch(sidebarSource, /className=\{`agent-row/);
  assert.match(stylesSource, /\.welcome\s*\{[\s\S]*?gap:\s*40px;/);
  assert.match(
    stylesSource,
    /\.welcome\s*\{[\s\S]*?padding:\s*0 16px clamp\(96px, 18vh, 152px\);/,
  );
});

test("shows animated starter prompts below the empty new-chat composer", () => {
  assert.match(composerSource, /const STARTER_PROMPTS = \[/);
  assert.match(composerSource, /function AnalyzePromptIcon\(\)/);
  assert.match(composerSource, /function PlanPromptIcon\(\)/);
  assert.match(composerSource, /function RewritePromptIcon\(\)/);
  assert.doesNotMatch(composerSource, /\bLightbulb\b|\bListChecks\b|\bPencilLine\b/);
  assert.match(
    composerSource,
    /newChatLayout && newChatMode === "agent" && !value\.trim\(\)/,
  );
  assert.match(composerSource, /className="prompt-suggestions"/);
  assert.match(composerSource, /onClick=\{\(\) => applyStarterPrompt\(prompt\.text\)\}/);
  assert.match(composerSource, /ref\.current\?\.focus\(\)/);
  assert.match(stylesSource, /\.prompt-suggestion\s*\{[\s\S]*?font-size:\s*15px;/);
  assert.match(stylesSource, /\.comp-input\s*\{[\s\S]*?font-size:\s*15px;/);
  assert.match(
    stylesSource,
    /\.composer--new-chat\s*\{[\s\S]*?position:\s*relative;/,
  );
  assert.match(
    stylesSource,
    /\.prompt-suggestions\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?top:\s*calc\(100% \+ 18px\);/,
  );
  assert.match(stylesSource, /@keyframes prompt-suggestion-enter/);
  assert.match(
    stylesSource,
    /\.prompt-suggestion > svg\s*\{[\s\S]*?stroke:\s*currentColor;/,
  );
  assert.match(
    stylesSource,
    /\.prompt-suggestion:nth-child\(1\):hover > svg\s*\{[\s\S]*?transform:/,
  );
  assert.match(
    stylesSource,
    /\.prompt-suggestion:nth-child\(2\):hover > svg\s*\{[\s\S]*?transform:/,
  );
  assert.match(
    stylesSource,
    /\.prompt-suggestion:nth-child\(3\):hover > svg\s*\{[\s\S]*?transform:/,
  );
  assert.match(
    stylesSource,
    /\.prompt-suggestion:nth-child\(2\)[\s\S]*?animation-delay:/,
  );
  assert.match(
    stylesSource,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.prompt-suggestion[\s\S]*?animation: none/,
  );
});
