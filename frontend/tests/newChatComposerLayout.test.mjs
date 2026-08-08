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
const featureCarouselSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatFeatureCarousel.tsx", import.meta.url),
  "utf8",
);
const featureCarouselStylesSource = readFileSync(
  new URL("../src/ui/new-chat-modes/new-chat-feature-carousel.css", import.meta.url),
  "utf8",
);
const newChatAgentPickerSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatAgentPicker.tsx", import.meta.url),
  "utf8",
);
const newChatAgentPickerStylesSource = readFileSync(
  new URL("../src/ui/new-chat-modes/new-chat-agent-picker.css", import.meta.url),
  "utf8",
);

test("expands only the new-chat composer into a multiline input", () => {
  assert.match(composerSource, /composer--has-task composer--task-/);
  assert.match(composerSource, /rows=\{newChatLayout \? 4 : 1\}/);
  assert.match(
    appSource,
    /newChatLayout=\{!sandboxSession && turns\.length === 0\}/,
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
  assert.doesNotMatch(selectorSource, /value: "skill-create"|创建 Skill/);
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
    /\.new-chat-mode__menus\s*\{[\s\S]*?top:\s*calc\(100% \+ 7px\);[\s\S]*?left:\s*0;/,
  );
  assert.match(selectorSource, /<AgentIdentityIcon className="new-chat-mode__agent-icon"/);
  assert.match(selectorSource, /className="new-chat-mode__temporary-icon"[\s\S]*?m10 2\.8 6\.1 3\.45/);
  assert.doesNotMatch(selectorSource, /M5 6\.2h10v7\.6H5z/);
  assert.doesNotMatch(selectorSource, /<AgentSelector/);
  assert.match(navbarSource, /<AgentSelector[\s\S]*?variant="navbar"/);
  assert.match(selectorSource, /Codex 智能体/);
  assert.match(selectorSource, /\{ label: "ArkClaw", kind: "openclaw" \}/);
  assert.match(selectorSource, /\{ label: "Hermes 智能体", kind: "hermes" \}/);
  assert.match(
    selectorSource,
    /<SandboxAgentIcon kind="codex" className="new-chat-mode__builtin-icon"/,
  );
  assert.match(
    selectorSource,
    /<SandboxAgentIcon kind=\{kind\} className="new-chat-mode__builtin-icon"/,
  );
  assert.doesNotMatch(selectorSource, />[CAH]<\/span>/);
  assert.match(
    modeStylesSource,
    /\.new-chat-mode__builtin-icon\s*\{[\s\S]*?width:\s*24px;[\s\S]*?stroke-width:\s*1\.75;/,
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

test("keeps the mode submenu inside narrow viewports", () => {
  assert.match(
    selectorSource,
    /className="new-chat-mode__menus"[\s\S]*?className="new-chat-mode__menu"[\s\S]*?className="new-chat-mode__submenu"/,
  );
  assert.match(
    modeStylesSource,
    /@media \(max-width:\s*640px\)[\s\S]*?\.new-chat-mode__menus\s*\{[\s\S]*?width:\s*min\(320px, calc\(100vw - 48px\)\);[\s\S]*?flex-direction:\s*column;/,
  );
});

test("reveals the refreshed welcome heading and placeholder after Agent connection", () => {
  const revealKeyframes = stylesSource.match(
    /@keyframes welcome-text-reveal\s*\{([\s\S]*?)\n\}/,
  )?.[1] ?? "";
  const placeholderRule = stylesSource.match(
    /\.composer-placeholder-reveal\s*\{\s*position:\s*absolute;([^}]*)\}/,
  )?.[1] ?? "";
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
  assert.match(stylesSource, /\.welcome-title,[\s\S]*?\.composer-placeholder-reveal\s*\{[\s\S]*?welcome-text-reveal 900ms/);
  assert.match(stylesSource, /@keyframes welcome-text-reveal[\s\S]*?clip-path:\s*inset\(0 100% 0 0\)[\s\S]*?clip-path:\s*inset\(0 0 0 0\)/);
  assert.doesNotMatch(revealKeyframes, /opacity:/);
  assert.match(stylesSource, /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.welcome-title,[\s\S]*?\.composer-placeholder-reveal[\s\S]*?animation:\s*none/);
  assert.match(stylesSource, /\.composer--new-chat \.comp-input::placeholder\s*\{[\s\S]*?color:\s*transparent/);
  assert.doesNotMatch(stylesSource, /\.comp-input::placeholder\s*\{[\s\S]*?animation:\s*welcome-text-reveal/);
  assert.match(composerSource, /placeholder=\{placeholderText\}/);
  assert.match(composerSource, /newChatLayout && value\.length === 0[\s\S]*?key=\{placeholderText\}[\s\S]*?className="composer-placeholder-reveal"[\s\S]*?aria-hidden="true"/);
  assert.match(stylesSource, /\.composer-placeholder-reveal\s*\{[\s\S]*?pointer-events:\s*none/);
  assert.match(placeholderRule, /width:\s*max-content;[\s\S]*?max-width:\s*calc\(100% - 20px\)/);
  assert.doesNotMatch(placeholderRule, /right:\s*10px/);
});

test("shows a larger auto-advancing feature carousel near the bottom of the main panel", () => {
  assert.match(appSource, /import \{ NewChatFeatureCarousel \}/);
  assert.match(appSource, /className="welcome"[\s\S]*?<NewChatFeatureCarousel \/>/);
  assert.match(
    featureCarouselSource,
    /随心应变[\s\S]*?支持多类 Agent[\s\S]*?一键成型[\s\S]*?自动构建 Agent[\s\S]*?一搜即达[\s\S]*?全局搜索[\s\S]*?开箱即用[\s\S]*?丰富内置工具/,
  );
  assert.doesNotMatch(featureCarouselSource, /new-chat-feature-card__index|padStart/);
  assert.doesNotMatch(featureCarouselStylesSource, /new-chat-feature-card__index/);
  assert.match(featureCarouselSource, /type FeatureIllustrationKind = "agents" \| "build" \| "search" \| "tools"/);
  assert.match(featureCarouselSource, /function FeatureIllustration/);
  assert.match(featureCarouselSource, /kind === "agents"[\s\S]*?kind === "build"[\s\S]*?kind === "search"/);
  assert.match(featureCarouselSource, /className="new-chat-feature-card__illustration"/);
  assert.match(
    featureCarouselSource,
    /new-chat-feature-card__illustration-connectors[\s\S]*?M43 27\.5V33\.5H22V38\.5[\s\S]*?new-chat-feature-card__illustration-surfaces/,
  );
  assert.match(featureCarouselSource, /M39\.5 21h7/);
  assert.doesNotMatch(featureCarouselSource, /M38\.5 21c1\.7-2\.6 7\.3-2\.6 9 0/);
  assert.match(featureCarouselSource, /aria-hidden="true"/);
  assert.match(featureCarouselSource, /type CarouselApi/);
  assert.match(featureCarouselSource, /opts=\{\{ align: "start", loop: true \}\}/);
  assert.match(featureCarouselSource, /setApi=\{setApi\}/);
  assert.match(featureCarouselSource, /window\.setInterval\(\(\) => api\.scrollNext\(\), 6_000\)/);
  assert.match(featureCarouselSource, /window\.clearInterval\(intervalId\)/);
  assert.match(featureCarouselSource, /prefers-reduced-motion: reduce/);
  assert.match(featureCarouselSource, /onPointerEnter=\{\(\) => setPointerPaused\(true\)\}/);
  assert.match(featureCarouselSource, /onFocusCapture=\{\(\) => setFocusPaused\(true\)\}/);
  assert.match(featureCarouselSource, /const \[visible, setVisible\] = useState\(true\)/);
  assert.match(featureCarouselSource, /if \(!visible\) return null/);
  assert.match(
    featureCarouselSource,
    /aria-label="关闭新特性轮播"[\s\S]*?onClick=\{\(\) => setVisible\(false\)\}/,
  );
  assert.match(
    featureCarouselStylesSource,
    /\.new-chat-feature-carousel\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?bottom:\s*10px;/,
  );
  assert.match(
    featureCarouselStylesSource,
    /grid-template-columns:\s*28px minmax\(0, 230px\) 28px;[\s\S]*?column-gap:\s*12px;/,
  );
  assert.match(
    featureCarouselStylesSource,
    /\.new-chat-feature-card\s*\{[\s\S]*?height:\s*104px;/,
  );
  assert.match(
    featureCarouselStylesSource,
    /\.new-chat-feature-carousel \.ui-carousel__track\s*\{[\s\S]*?margin-left:\s*-10px;/,
  );
  assert.match(
    featureCarouselStylesSource,
    /\.new-chat-feature-carousel \.ui-carousel__item\s*\{[\s\S]*?padding-left:\s*10px;/,
  );
  const featureCardRule = featureCarouselStylesSource.match(
    /\.new-chat-feature-card\s*\{([\s\S]*?)\n\}/,
  )?.[1] ?? "";
  assert.match(featureCardRule, /border:\s*0;/);
  assert.match(featureCardRule, /background:\s*hsl\(var\(--muted\) \/ 0\.58\)/);
  assert.match(stylesSource, /\.welcome-feature-pill\s*\{[\s\S]*?background:\s*hsl\(var\(--muted\)\)/);
  assert.match(
    featureCarouselStylesSource,
    /\.new-chat-feature-card__illustration\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?width:\s*86px;/,
  );
  assert.match(
    featureCarouselStylesSource,
    /\.new-chat-feature-card__illustration\s*\{[\s\S]*?stroke-width:\s*1\.25;[\s\S]*?shape-rendering:\s*geometricPrecision;/,
  );
  assert.match(
    featureCarouselStylesSource,
    /\.new-chat-feature-card__illustration-surfaces\s*\{[\s\S]*?fill:\s*hsl\(var\(--panel\) \/ 0\.82\);/,
  );
  assert.match(
    featureCarouselStylesSource,
    /\.new-chat-feature-carousel__close\s*\{[\s\S]*?left:\s*41px;[\s\S]*?width:\s*28px;[\s\S]*?height:\s*28px;/,
  );
  assert.doesNotMatch(
    featureCarouselStylesSource.match(
      /\.new-chat-feature-carousel__close\s*\{([\s\S]*?)\n\}/,
    )?.[1] ?? "",
    /right:/,
  );
  assert.doesNotMatch(featureCarouselStylesSource, /aspect-ratio:\s*16 \/ 9/);
});

test("keeps the Agent picker aligned without extra highlighting or guidance", () => {
  assert.match(newChatAgentPickerSource, /className="new-chat-agent-picker"/);
  assert.doesNotMatch(newChatAgentPickerSource, /is-unselected|new-chat-agent-picker-guide|aria-describedby/);
  assert.doesNotMatch(newChatAgentPickerStylesSource, /is-unselected|new-chat-agent-picker__guide/);
  assert.match(
    newChatAgentPickerStylesSource,
    /\.new-chat-agent-picker__trigger > span\s*\{[\s\S]*?display:\s*flex;[\s\S]*?align-items:\s*center;[\s\S]*?line-height:\s*20px;/,
  );
  assert.match(
    newChatAgentPickerStylesSource,
    /\.new-chat-agent-picker__trigger-icon,[\s\S]*?\.new-chat-agent-picker__trigger-chevron\s*\{[\s\S]*?display:\s*block;/,
  );
  assert.doesNotMatch(newChatAgentPickerStylesSource, /new-chat-agent-picker-bounce/);
});

test("reveals feature details on hover or keyboard focus", () => {
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
  assert.doesNotMatch(composerSource, /skillCreateEnabled|SkillCreateIcon|创建 Skill/);
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
