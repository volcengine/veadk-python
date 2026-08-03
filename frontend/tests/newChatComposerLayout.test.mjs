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
const taskToolsSource = readFileSync(
  new URL("../src/ui/new-chat-modes/taskTools.ts", import.meta.url),
  "utf8",
);
const featureNoticeSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatFeatureNotice.tsx", import.meta.url),
  "utf8",
);

test("expands only the new-chat composer into a multiline input", () => {
  assert.match(
    composerSource,
    /className=\{`composer\$\{newChatLayout \? " composer--new-chat" : ""\}\$\{skillMode \? " composer--skill-mode" : ""\}\$\{selectedTask \? ` composer--has-task composer--task-\$\{selectedTask\.value\}` : ""\}`\}/,
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
  assert.match(stylesSource, /\.welcome\s*\{[\s\S]*?gap:\s*32px;/);
  assert.match(
    stylesSource,
    /\.welcome\s*\{[\s\S]*?padding:\s*0 16px clamp\(88px, 16vh, 136px\);/,
  );
});

test("reveals the refreshed welcome heading and placeholder after Agent connection", () => {
  assert.match(
    appSource,
    /key=\{`welcome-\$\{newChatCapabilities\.agentId \?\? appName\}`\}/,
  );
  assert.match(
    appSource,
    /<NewChatFeatureNotice canUpdate=\{access\.role === "admin"\} \/>/,
  );
  assert.match(featureNoticeSource, /className="welcome-feature-pill"[\s\S]*?焕然一新[\s\S]*?查看新特性/);
  assert.match(stylesSource, /--feature-link:\s*208 100% 47\.45%/);
  assert.match(stylesSource, /\.welcome-primary\s*\{[\s\S]*?gap:\s*32px;/);
  assert.match(stylesSource, /\.welcome-heading\s*\{[\s\S]*?gap:\s*72px;/);
  assert.match(stylesSource, /\.welcome-title,[\s\S]*?\.composer--new-chat \.comp-input::placeholder\s*\{[\s\S]*?welcome-text-reveal 900ms/);
  assert.match(stylesSource, /@keyframes welcome-text-reveal[\s\S]*?clip-path:\s*inset\(0 100% 0 0\)[\s\S]*?clip-path:\s*inset\(0 0 0 0\)/);
  assert.match(stylesSource, /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.welcome-title,[\s\S]*?\.composer--new-chat \.comp-input::placeholder[\s\S]*?animation:\s*none/);
});

test("hides the carousel and reveals feature details on hover or keyboard focus", () => {
  assert.doesNotMatch(appSource, /NewChatFeatureCarousel/);
  assert.match(featureNoticeSource, /role="tooltip"/);
  assert.match(featureNoticeSource, /多地域智能体/);
  assert.match(featureNoticeSource, /会话内切换/);
  assert.match(featureNoticeSource, /可视化执行画布/);
  assert.match(stylesSource, /\.welcome-feature-pill:hover \.welcome-feature-popover/);
  assert.match(stylesSource, /\.welcome-feature-pill:focus-within \.welcome-feature-popover/);
});

test("shows task capsules for Harness agents without generic starter prompts", () => {
  assert.doesNotMatch(composerSource, /STARTER_PROMPTS|AnalyzePromptIcon|PlanPromptIcon|RewritePromptIcon/);
  assert.match(composerSource, /const TASK_SHORTCUTS = \[/);
  assert.match(taskToolsSource, /ppt:\s*\["ppt_generate"\]/);
  assert.match(taskToolsSource, /image:\s*\["image_generate"\]/);
  assert.match(taskToolsSource, /video:\s*\["video_generate"\]/);
  assert.match(taskToolsSource, /video:\s*\["video_task_query"\]/);
  assert.match(composerSource, /availableTaskShortcuts/);
  assert.match(composerSource, /value: "ppt"[\s\S]*?label: "PPT"[\s\S]*?经营表现[\s\S]*?项目名称】进展[\s\S]*?输出解决方案[\s\S]*?行业主题】趋势/);
  assert.match(composerSource, /value: "image"[\s\S]*?label: "图片生成"[\s\S]*?发布会主视觉[\s\S]*?电商海报[\s\S]*?概念效果图[\s\S]*?企业社媒配图/);
  assert.match(composerSource, /value: "video"[\s\S]*?label: "视频生成"[\s\S]*?30 秒宣传片[\s\S]*?45 秒发布视频[\s\S]*?企业培训视频[\s\S]*?20 秒预热视频/);
  assert.match(composerSource, /skillCreateEnabled === true \? \([\s\S]*?onClick=\{\(\) => onModeChange\?\.\("skill-create"\)\}/);
  assert.doesNotMatch(composerSource, /disabled=\{busy \|\| skillCreateEnabled !== true\}/);
  assert.match(composerSource, /<SkillCreateIcon \/>[\s\S]*?<span>创建 Skill<\/span>/);
  assert.match(composerSource, /className="task-shortcuts"/);
  assert.match(composerSource, /harnessEnabled && !selectedTask/);
  assert.match(composerSource, /className="prompt-suggestions"/);
  assert.doesNotMatch(composerSource, /applyStarterPrompt|aria-label="快捷提示"/);
  assert.match(composerSource, /onClick=\{\(\) => applyTaskShortcut\(task\)\}/);
  assert.match(composerSource, /function applyTaskShortcut[\s\S]*?onTaskChange\?\.\(task\.value\)[\s\S]*?setSelectionRange\(value\.length, value\.length\)/);
  assert.doesNotMatch(composerSource, /function applyTaskShortcut[\s\S]*?onChange\(task\.prompt\)/);
  assert.match(composerSource, /selectedTask\.prompts\.map\(\(prompt\) =>/);
  assert.match(composerSource, /aria-label=\{`\$\{selectedTask\.label\}企业提示词`\}/);
  assert.match(composerSource, /onClick=\{\(\) => applyTaskPrompt\(prompt\)\}/);
  assert.match(composerSource, /setSelectionRange\(placeholderStart \+ 1, placeholderEnd\)/);
  assert.match(stylesSource, /\.task-shortcuts\s*\{[\s\S]*?justify-content:\s*center;/);
  assert.match(stylesSource, /\.task-shortcut\s*\{[\s\S]*?border-radius:\s*999px;/);
  assert.match(stylesSource, /\.task-shortcut\s*\{[\s\S]*?font-size:\s*15px;/);
  assert.match(stylesSource, /\.task-shortcut\s*\{[\s\S]*?flex:\s*0 0 auto;/);
  assert.match(stylesSource, /\.task-shortcut\s*\{[\s\S]*?white-space:\s*nowrap;/);
  assert.match(stylesSource, /\.prompt-suggestion > span\s*\{[\s\S]*?white-space:\s*nowrap;[\s\S]*?text-overflow:\s*ellipsis;[\s\S]*?transition:\s*max-height/);
  assert.match(stylesSource, /\.prompt-suggestion:hover > span,[\s\S]*?max-height:\s*4\.5em;[\s\S]*?white-space:\s*normal;/);
});

test("shows the selected task between add and Agent and reveals cancel on hover", () => {
  assert.match(composerSource, /className=\{`new-chat-task-chip new-chat-task-chip--\$\{selectedTask\.value\}`\}/);
  assert.match(composerSource, /aria-label=\{`取消\$\{selectedTask\.label\}任务`\}/);
  assert.match(composerSource, /onClick=\{clearTask\}/);
  assert.match(composerSource, /function clearTask\(\)[\s\S]*?onTaskChange\?\.\(null\)[\s\S]*?onChange\(""\)/);
  assert.match(composerSource, /new-chat-task-chip__task-icon/);
  assert.match(composerSource, /new-chat-task-chip__remove-icon/);
  assert.match(stylesSource, /\.new-chat-task-chip\s*\{[\s\S]*?left:\s*52px;[\s\S]*?background:\s*transparent;/);
  assert.match(stylesSource, /\.composer--new-chat\.composer--has-task \.new-chat-mode\s*\{\s*left:\s*138px;/);
  assert.match(stylesSource, /\.composer--new-chat\.composer--task-image \.new-chat-mode,[\s\S]*?left:\s*176px;/);
  assert.match(stylesSource, /\.new-chat-task-chip--image,[\s\S]*?width:\s*116px;/);
  assert.match(stylesSource, /\.new-chat-task-chip > span:last-child[\s\S]*?white-space:\s*nowrap;/);
  assert.match(stylesSource, /\.new-chat-task-chip\s*\{[\s\S]*?color:\s*hsl\(262 34% 52%\)/);
  assert.match(stylesSource, /\.new-chat-task-chip:hover,[\s\S]*?background:\s*hsl\(260 36% 96%\)/);
  assert.match(stylesSource, /\.new-chat-task-chip__remove-icon\s*\{[\s\S]*?opacity:\s*0;/);
  assert.match(stylesSource, /\.new-chat-task-chip:hover \.new-chat-task-chip__remove-icon,[\s\S]*?opacity:\s*1;/);
  assert.match(appSource, /const \[newChatTask, setNewChatTask\] = useState<NewChatTask \| null>\(null\)/);
  assert.match(appSource, /newChatTask=\{sandboxSession \? null : newChatTask\}/);
  assert.match(appSource, /onTaskChange=\{setNewChatTask\}/);
  assert.match(appSource, /function startNewChat\(\)[\s\S]*?setNewChatTask\(null\)/);
});

test("shows a removable Skill label inside the composer", () => {
  assert.match(composerSource, /newChatLayout && skillMode && onModeChange/);
  assert.match(composerSource, /className="new-chat-task-chip new-chat-task-chip--skill"/);
  assert.match(composerSource, /aria-label="退出创建 Skill"/);
  assert.match(composerSource, /onClick=\{\(\) => onModeChange\("agent"\)\}/);
  assert.match(composerSource, /<SkillCreateIcon className="new-chat-task-chip__task-icon"/);
  assert.match(composerSource, /<span>Skill<\/span>/);
  assert.match(stylesSource, /\.new-chat-task-chip--skill\s*\{[\s\S]*?left:\s*10px;[\s\S]*?width:\s*86px;/);
});
