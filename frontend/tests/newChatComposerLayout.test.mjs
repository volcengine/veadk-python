import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const composerSource = readFileSync(
  new URL("../src/ui/Composer.tsx", import.meta.url),
  "utf8",
);
const appSource = readFileSync(
  new URL("../src/App.tsx", import.meta.url),
  "utf8",
);
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
const newChatAgentPickerSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatAgentPicker.tsx", import.meta.url),
  "utf8",
);
const newChatAgentPickerStylesSource = readFileSync(
  new URL(
    "../src/ui/new-chat-modes/new-chat-agent-picker.css",
    import.meta.url,
  ),
  "utf8",
);
const workspaceTabsSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatWorkspaceTabs.tsx", import.meta.url),
  "utf8",
);
const builtinToolIconsSource = readFileSync(
  new URL("../src/ui/builtin-tools/icons.tsx", import.meta.url),
  "utf8",
);
const skillPickerSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatSkillPicker.tsx", import.meta.url),
  "utf8",
);
const skillControlsSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatSkillControls.tsx", import.meta.url),
  "utf8",
);
const compactSelectSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatCompactSelect.tsx", import.meta.url),
  "utf8",
);
const workspaceStylesSource = readFileSync(
  new URL("../src/ui/new-chat-modes/new-chat-workspace.css", import.meta.url),
  "utf8",
);
const videoControlsSource = readFileSync(
  new URL("../src/ui/new-chat-modes/NewChatVideoControls.tsx", import.meta.url),
  "utf8",
);
const videoTypesSource = readFileSync(
  new URL("../src/ui/new-chat-modes/video-types.ts", import.meta.url),
  "utf8",
);
const videoStylesSource = readFileSync(
  new URL(
    "../src/ui/new-chat-modes/new-chat-video-controls.css",
    import.meta.url,
  ),
  "utf8",
);
const videoApiSource = readFileSync(
  new URL("../src/adk/video.ts", import.meta.url),
  "utf8",
);
const videoTaskSource = readFileSync(
  new URL("../src/ui/new-chat-modes/video-task.ts", import.meta.url),
  "utf8",
);
const videoTaskDialogSource = readFileSync(
  new URL(
    "../src/ui/new-chat-modes/NewChatVideoTaskDialog.tsx",
    import.meta.url,
  ),
  "utf8",
);
const videoTaskDialogStylesSource = readFileSync(
  new URL(
    "../src/ui/new-chat-modes/new-chat-video-task-dialog.css",
    import.meta.url,
  ),
  "utf8",
);
const sandboxComposerSource = readFileSync(
  new URL("../src/ui/SandboxComposer.tsx", import.meta.url),
  "utf8",
);

test("expands only the new-chat composer into a multiline input", () => {
  assert.match(composerSource, /composer--has-task composer--task-/);
  assert.match(composerSource, /rows=\{newChatLayout \? 4 : 1\}/);
  assert.match(
    appSource,
    /newChatLayout=\{!sandboxSession && turns\.length === 0\}/,
  );
  assert.match(
    stylesSource,
    /\.composer--new-chat \.composer-box[\s\S]*?min-height:/,
  );
  assert.match(
    stylesSource,
    /\.composer--new-chat \.composer-box[\s\S]*?border-color:/,
  );
  assert.match(
    stylesSource,
    /\.composer--new-chat \.composer-box[\s\S]*?box-shadow:/,
  );
  assert.match(
    stylesSource,
    /\.composer--new-chat \.comp-input[\s\S]*?min-height:/,
  );
  assert.match(
    stylesSource,
    /\.composer--new-chat \.composer-menu-wrap[\s\S]*?z-index: 5;[\s\S]*?bottom: 10px/,
  );
  assert.match(
    stylesSource,
    /\.composer--new-chat \.comp-send[\s\S]*?bottom: 10px/,
  );
  assert.match(
    stylesSource,
    /\.composer--new-chat \.comp-send \.icon[\s\S]*?width: 20px/,
  );
});

test("keeps alternate chat modes hidden from the new-chat composer", () => {
  assert.match(appSource, /showModeSelector=\{false\}/);
  assert.match(
    composerSource,
    /<NewChatModeSelector[\s\S]*?value=\{newChatMode\}/,
  );
  assert.match(selectorSource, /value: "agent"[\s\S]*?labelKey: "mode\.agent\.label"/);
  assert.match(selectorSource, /value: "temporary"[\s\S]*?labelKey: "mode\.builtin\.label"/);
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
  assert.match(
    selectorSource,
    /<AgentFaceIcon className="new-chat-mode__agent-icon"/,
  );
  assert.doesNotMatch(selectorSource, /AgentIdentityIcon/);
  assert.match(agentSelectorSource, /import \{ AgentFaceIcon \}/);
  assert.doesNotMatch(agentSelectorSource, /AgentIdentityIcon/);
  assert.equal(
    existsSync(new URL("../src/ui/AgentIdentityIcon.tsx", import.meta.url)),
    false,
  );
  assert.match(
    selectorSource,
    /className="new-chat-mode__temporary-icon"[\s\S]*?m10 2\.8 6\.1 3\.45/,
  );
  assert.doesNotMatch(selectorSource, /M5 6\.2h10v7\.6H5z/);
  assert.doesNotMatch(selectorSource, /<AgentSelector/);
  assert.match(navbarSource, /<AgentSelector[\s\S]*?variant="navbar"/);
  assert.match(selectorSource, /mode\.codex\.label/);
  assert.match(selectorSource, /mode\.deepseekHarness\.label/);
  assert.match(selectorSource, /\{ labelKey: "mode\.arkClaw", kind: "openclaw" \}/);
  assert.match(selectorSource, /\{ labelKey: "mode\.hermes", kind: "hermes" \}/);
  assert.match(
    selectorSource,
    /<SandboxAgentIcon kind=\{agent\.kind\} className="new-chat-mode__builtin-icon"/,
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

test("layers pill-shaped workspace tabs behind the new-chat input", () => {
  assert.match(
    appSource,
    /showWorkspaceTabs=\{!sandboxSession && turns\.length === 0\}/,
  );
  assert.match(
    composerSource,
    /<NewChatWorkspaceTabs[\s\S]*?value=\{newChatWorkspaceMode\}/,
  );
  assert.match(
    composerSource,
    /<NewChatWorkspaceTabs[\s\S]*?<div[\s\S]*?className="composer-box"/,
  );
  assert.match(
    workspaceTabsSource,
    /role="tablist"[\s\S]*?aria-label=\{t\("workspace\.label"\)\}/,
  );
  assert.match(
    workspaceTabsSource,
    /role="tab"[\s\S]*?aria-selected=\{selected\}/,
  );
  assert.match(
    workspaceTabsSource,
    /labelKey: "workspace\.agent"[\s\S]*?labelKey: "workspace\.skill"[\s\S]*?labelKey: "workspace\.video"/,
  );
  assert.match(workspaceTabsSource, /AgentFaceIcon/);
  assert.match(
    workspaceTabsSource,
    /import \{ ToolsSkills \} from "@openai\/apps-sdk-ui\/components\/Icon"/,
  );
  assert.match(workspaceTabsSource, /function AnimatedSkillIcon/);
  assert.match(workspaceTabsSource, /new-chat-workspace-tabs__skill-shape is-triangle/);
  assert.match(workspaceTabsSource, /new-chat-workspace-tabs__skill-shape is-circle/);
  assert.match(workspaceTabsSource, /new-chat-workspace-tabs__skill-shape is-square/);
  assert.match(workspaceTabsSource, /VideoGenerateIcon/);
  assert.doesNotMatch(workspaceTabsSource, /\bSkillIcon\b/);
  assert.match(builtinToolIconsSource, /video-generate-icon__clapper/);
  assert.match(workspaceTabsSource, /import \{ motion \} from "motion\/react"/);
  assert.match(
    workspaceTabsSource,
    /layoutId="new-chat-workspace-active-pill"/,
  );
  assert.match(
    workspaceTabsSource,
    /layout:\s*\{[\s\S]*?duration:\s*0\.24,[\s\S]*?ease:\s*\[0\.22, 1, 0\.36, 1\]/,
  );
  assert.match(
    workspaceTabsSource,
    /ArrowRight[\s\S]*?ArrowLeft[\s\S]*?Home[\s\S]*?End/,
  );
  assert.match(
    workspaceStylesSource,
    /\.new-chat-workspace-tabs\s*\{[\s\S]*?align-self:\s*flex-start;[\s\S]*?width:\s*100%;[\s\S]*?height:\s*76px;[\s\S]*?margin:\s*0 0 -26px;[\s\S]*?padding:\s*8px 10px 34px;/,
  );
  assert.doesNotMatch(
    workspaceStylesSource,
    /\.new-chat-workspace-tabs\s*\{[^}]*\bborder:/,
  );
  assert.match(
    workspaceStylesSource,
    /\.new-chat-workspace-tabs__tab\s*\{[\s\S]*?flex:\s*0 0 104px;[\s\S]*?width:\s*104px;[\s\S]*?min-height:\s*34px;[\s\S]*?border-radius:\s*10px;[\s\S]*?font-size:\s*14px;[\s\S]*?font-weight:\s*400;/,
  );
  assert.match(
    workspaceStylesSource,
    /\.new-chat-workspace-tabs__tab\.is-active\s*\{[\s\S]*?font-weight:\s*400;/,
  );
  assert.match(
    workspaceStylesSource,
    /\.new-chat-workspace-tabs__slider\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?inset:\s*0;[\s\S]*?pointer-events:\s*none;/,
  );
  assert.match(
    stylesSource,
    /\.composer--new-chat \.composer-box\s*\{[\s\S]*?z-index:\s*2;/,
  );
  assert.match(
    workspaceStylesSource,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?transition:\s*none/,
  );
  assert.match(
    workspaceStylesSource,
    /skill-shape\.is-triangle[\s\S]*?translateY\(-1px\)/,
  );
  assert.match(
    workspaceStylesSource,
    /skill-shape\.is-circle[\s\S]*?rotate\(-6deg\)/,
  );
  assert.match(
    workspaceStylesSource,
    /skill-shape\.is-square[\s\S]*?rotate\(6deg\)/,
  );
  assert.match(
    workspaceStylesSource,
    /video-generate-icon__clapper[\s\S]*?rotate\(-14deg\)/,
  );
});

test("hides skill customization until the administrator Dev Sandbox is usable", () => {
  assert.match(appSource, /getSkillWorkbenchCapability/);
  assert.match(appSource, /skillCustomizationEnabled/);
  assert.match(
    appSource,
    /newChatWorkspaceMode !== "skill"[\s\S]*?setNewChatWorkspaceMode\("agent"\)/,
  );
  assert.match(
    composerSource,
    /skillCustomizationEnabled=\{skillCustomizationEnabled\}/,
  );
  assert.match(workspaceTabsSource, /skillCustomizationEnabled = false/);
  assert.match(
    workspaceTabsSource,
    /filter\(\(mode\) => mode\.value !== "skill"\)/,
  );
});

test("keeps the built-in Agent types and adds the two skill actions", () => {
  assert.match(
    newChatAgentPickerSource,
    /\{ id: "general", labelKey: "agentPicker\.types\.general" \}/,
  );
  assert.match(
    newChatAgentPickerSource,
    /\{ id: "codex", labelKey: "agentPicker\.types\.codex" \}/,
  );
  assert.match(
    newChatAgentPickerSource,
    /\{ id: "deepseek-harness", labelKey: "agentPicker\.types\.deepseekHarness" \}/,
  );
  assert.match(
    newChatAgentPickerSource,
    /\{ id: "openclaw", labelKey: "agentPicker\.types\.openclaw" \}/,
  );
  assert.match(
    newChatAgentPickerSource,
    /\{ id: "hermes", labelKey: "agentPicker\.types\.hermes" \}/,
  );
  assert.match(
    composerSource,
    /newChatWorkspaceMode === "agent"[\s\S]*?<NewChatAgentPicker/,
  );
  assert.match(
    composerSource,
    /newChatWorkspaceMode === "skill"[\s\S]*?<NewChatSkillControls/,
  );
  assert.match(skillPickerSource, /value: "create", labelKey: "skill\.actions\.create"/);
  assert.match(skillPickerSource, /value: "optimize", labelKey: "skill\.actions\.optimize"/);
  assert.match(skillPickerSource, /role="listbox"[\s\S]*?role="option"/);
  assert.match(skillPickerSource, /Escape/);
  assert.match(skillPickerSource, /ArrowDown/);
  assert.match(skillPickerSource, /ArrowUp/);
  assert.match(skillControlsSource, /label=\{t\("skill\.style"\)\}[\s\S]*?label=\{t\("skill\.model"\)\}/);
  assert.match(skillControlsSource, /getSkillWorkbenchCapability/);
  assert.match(skillControlsSource, /<NewChatSkillTargetPicker/);
  assert.match(skillControlsSource, /listSkillSpaces/);
  assert.match(skillControlsSource, /listSkillsInSpace/);
  assert.match(compactSelectSource, /searchable/);
  assert.match(compactSelectSource, /role="listbox"[\s\S]*?role="option"/);
  assert.match(compactSelectSource, /Escape/);
  assert.match(compactSelectSource, /ArrowDown/);
  assert.match(compactSelectSource, /ArrowUp/);
  assert.match(
    workspaceStylesSource,
    /\.new-chat-skill-controls\s*\{[\s\S]*?right:\s*52px;[\s\S]*?bottom:\s*10px;[\s\S]*?left:\s*52px;/,
  );
  assert.match(
    composerSource,
    /const placeholderText\s*=[\s\S]*?newChatWorkspaceMode === "agent"[\s\S]*?composer\.selectAgentFirst[\s\S]*?workspacePlaceholder/,
  );
  assert.doesNotMatch(
    composerSource,
    /newChatWorkspaceMode === "video"\s*&&[^\n]*<NewChat(?:Agent|Skill)Picker/,
  );
});

test("mounts video creation controls only in the ordinary new-chat workspace", () => {
  assert.match(composerSource, /NewChatInlineAssetInput/);
  assert.match(composerSource, /NewChatVideoControls/);
  assert.match(composerSource, /<AnimatePresence initial=\{false\}>/);
  assert.match(
    composerSource,
    /newChatLayout\s*&&\s*showWorkspaceTabs\s*&&\s*newChatWorkspaceMode === "video"[\s\S]*?<NewChatVideoControls/,
  );
  assert.match(
    composerSource,
    /<NewChatVideoControls[\s\S]*?config=\{newChatVideoConfig\}[\s\S]*?onChange=\{setNewChatVideoConfig\}/,
  );
  assert.match(
    composerSource,
    /useState\(\s*DEFAULT_NEW_CHAT_VIDEO_CONFIG,\s*\)/,
  );
  assert.match(
    appSource,
    /newChatWorkspaceMode === "agent"[\s\S]*?newChatMode === "agent"[\s\S]*?!appName/,
  );
  assert.match(composerSource, /getVideoCapabilities\(controller\.signal\)/);
  assert.match(
    composerSource,
    /onVideoSubmit\?\.\(value\.trim\(\), newChatVideoConfig, videoCapabilities\)/,
  );
  assert.doesNotMatch(composerSource, /视频生成功能暂未开放/);
  assert.match(
    composerSource,
    /taskMode === "video_editing"[\s\S]*?taskMode === "video_extension"/,
  );
  assert.match(
    composerSource,
    /requiredInlineAsset[\s\S]*?referenceVideo[\s\S]*?firstFrame/,
  );
  assert.match(
    composerSource,
    /<NewChatInlineAssetInput[\s\S]*?asset=\{requiredInlineAsset\.asset\}[\s\S]*?kind=\{requiredInlineAsset\.kind\}/,
  );
  assert.match(
    videoControlsSource,
    /URL\.createObjectURL\(asset\)[\s\S]*?URL\.revokeObjectURL/,
  );
  assert.match(
    videoStylesSource,
    /\.new-chat-inline-video__tile\s*\{[\s\S]*?border:\s*1px dashed[\s\S]*?rotate\(-6deg\)/,
  );
  assert.match(
    videoStylesSource,
    /new-chat-inline-video__tile:hover[\s\S]*?rotate\(0deg\)/,
  );
  assert.match(
    videoControlsSource,
    /videoEditingMode \|\| videoExtensionMode \? null : \(/,
  );
  assert.match(
    videoControlsSource,
    /firstLastFrameMode \? \([\s\S]*?label=\{t\("video\.controls\.lastFrame"\)\}/,
  );
  assert.doesNotMatch(
    videoControlsSource,
    /firstLastFrameMode \? \([\s\S]*?<VideoAssetInput[\s\S]*?label="首帧"/,
  );
});

test("keeps workspace tabs and video controls out of Codex Sandbox conversations", () => {
  assert.match(
    appSource,
    /newChatLayout=\{!sandboxSession && turns\.length === 0\}/,
  );
  assert.match(
    appSource,
    /showWorkspaceTabs=\{!sandboxSession && turns\.length === 0\}/,
  );
  assert.match(
    appSource,
    /newChatWorkspaceMode=\{sandboxSession \? "agent" : newChatWorkspaceMode\}/,
  );
  assert.match(
    composerSource,
    /newChatLayout\s*&&\s*showWorkspaceTabs\s*&&\s*newChatWorkspaceMode === "video"/,
  );
  assert.doesNotMatch(
    sandboxComposerSource,
    /NewChatWorkspaceTabs|NewChatVideoControls|NewChatVideoConfig|newChatWorkspaceMode/,
  );
});

test("defines the video defaults, modes, and progressive media inputs", () => {
  assert.match(
    videoTypesSource,
    /VIDEO_TASK_MODES[\s\S]*?"auto"[\s\S]*?"text_to_video"[\s\S]*?"reference_to_video"[\s\S]*?"video_editing"[\s\S]*?"video_extension"[\s\S]*?"first_last_frame"/,
  );
  for (const ratio of ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16"]) {
    assert.match(videoTypesSource, new RegExp(ratio));
  }
  assert.match(
    videoTypesSource,
    /VIDEO_RESOLUTION_OPTIONS[\s\S]*?480p[\s\S]*?720p/,
  );
  assert.match(
    videoTypesSource,
    /DEFAULT_NEW_CHAT_VIDEO_CONFIG[\s\S]*?taskMode:\s*"auto"[\s\S]*?aspectRatio:\s*"16:9"[\s\S]*?resolution:\s*"720p"[\s\S]*?durationSeconds:\s*8/,
  );
  assert.match(videoControlsSource, /min="4"[\s\S]*?max="30"/);
  assert.match(videoControlsSource, /config\.taskMode === "first_last_frame"/);
  assert.match(
    videoControlsSource,
    /videoEditingMode = config\.taskMode === "video_editing"/,
  );
  assert.match(
    videoControlsSource,
    /previewUrl && kind === "image"[\s\S]*?<img/,
  );
  assert.match(videoControlsSource, /referenceImage/);
  assert.match(videoControlsSource, /referenceVideo/);
  assert.match(composerSource, /firstFrame/);
  assert.match(videoControlsSource, /lastFrame/);
});

test("loads provider-native video models from backend capabilities", () => {
  assert.match(videoApiSource, /GET|\/capabilities/);
  assert.match(videoApiSource, /generationModel:\s*string/);
  assert.match(videoApiSource, /enhancerModel:\s*string/);
  assert.match(videoApiSource, /assetStorageUnavailableReason:\s*string/);
  assert.match(videoApiSource, /form\.set\("role", kind\)/);
  assert.match(videoApiSource, /"\/prompts\/enhance"/);
  assert.match(videoApiSource, /taskMode:\s*VideoTaskMode/);
  assert.match(videoApiSource, /resolvedTaskMode:\s*VideoTaskMode/);
  assert.match(videoApiSource, /`\/tasks\/\$\{encodeURIComponent\(taskId\)\}`/);
  assert.doesNotMatch(
    videoTypesSource,
    /export type VideoPromptEnhanceModel|VIDEO_PROMPT_MODEL_OPTIONS/,
  );
  const configInterface =
    videoTypesSource.match(
      /export interface NewChatVideoConfig\s*\{([\s\S]*?)\n\}/,
    )?.[1] ?? "";
  const defaultConfig =
    videoTypesSource.match(
      /DEFAULT_NEW_CHAT_VIDEO_CONFIG[^=]*=\s*\{([\s\S]*?)\n\};/,
    )?.[1] ?? "";
  assert.doesNotMatch(configInterface, /promptEnhanceModel/);
  assert.doesNotMatch(defaultConfig, /promptEnhanceModel/);
  assert.doesNotMatch(videoControlsSource, /cloudProvider:/);
  assert.match(videoControlsSource, /enhancerModel:\s*string/);
  assert.doesNotMatch(
    videoControlsSource,
    /label="增强模型"|options=\{VIDEO_PROMPT_MODEL_OPTIONS\}|update\("promptEnhanceModel"/,
  );
  assert.match(
    videoControlsSource,
    /new-chat-video-controls__assets[\s\S]*?new-chat-video-controls__model-hint[\s\S]*?video\.controls\.enhancerHint/,
  );
  assert.match(composerSource, /videoCapabilities\?\.generationModel/);
  assert.match(composerSource, /videoCapabilities\?\.enhancerModel/);
  assert.match(
    composerSource,
    /assetStorageAvailable=\{[\s\S]*?videoCapabilities\?\.assetStorageAvailable \?\? false\s*\}/,
  );
  assert.match(
    videoControlsSource,
    /管理员未配置持久化存储|assetStorageUnavailableReason/,
  );
});

test("reveals video controls with reduced-motion support", () => {
  assert.match(videoControlsSource, /motion\.section/);
  assert.match(videoControlsSource, /= useReducedMotion\(\)/);
  assert.match(videoControlsSource, /initial=\{/);
  assert.match(videoControlsSource, /animate=\{/);
  assert.match(videoControlsSource, /exit=\{/);
  assert.match(videoControlsSource, /opacity/);
  assert.match(
    videoStylesSource,
    /\.new-chat-video-controls\s*\{[\s\S]*?position:\s*absolute;[\s\S]*?top:\s*calc\(100% - 8px\);[\s\S]*?background:\s*hsl\(var\(--muted\)/,
  );
  assert.match(
    composerSource,
    /className="new-chat-video-task-mode"[\s\S]*?label=\{t\("composer\.taskMode"\)\}[\s\S]*?hideLabel[\s\S]*?videoModeOptions\.filter/,
  );
  assert.match(
    videoStylesSource,
    /\.new-chat-video-task-mode\s*\{[\s\S]*?width:\s*fit-content;[\s\S]*?max-width:\s*220px;/,
  );
  assert.match(
    videoStylesSource,
    /\.new-chat-video-task-mode \.new-chat-compact-select__trigger\s*\{[\s\S]*?width:\s*auto;[\s\S]*?min-width:\s*96px;[\s\S]*?max-width:\s*220px;/,
  );
  assert.doesNotMatch(videoControlsSource, /label="任务模式"/);
  assert.match(
    composerSource,
    /className="new-chat-video-generation-model"[\s\S]*?videoCapabilities\?\.generationModel/,
  );
  assert.doesNotMatch(composerSource, /<span>生成模型<\/span>/);
  assert.match(
    videoControlsSource,
    /className="new-chat-video-controls__parameters"[\s\S]*?video\.controls\.aspectRatio[\s\S]*?video\.controls\.resolution[\s\S]*?video\.controls\.duration[\s\S]*?new-chat-video-controls__assets/,
  );
  assert.match(
    videoStylesSource,
    /\.new-chat-video-controls__parameters\s*\{[\s\S]*?display:\s*grid;[\s\S]*?grid-template-columns:\s*repeat\(3, minmax\(0, 1fr\)\)/,
  );
  assert.match(videoStylesSource, /\.new-chat-video-controls__model-hint\s*\{/);
  assert.match(
    videoStylesSource,
    /\.new-chat-video-generation-model\s*\{[\s\S]*?right:\s*52px;[\s\S]*?bottom:\s*10px;/,
  );
  assert.match(
    videoStylesSource,
    /\.new-chat-video-controls__model-hint\s*\{[\s\S]*?justify-content:\s*center;[\s\S]*?text-align:\s*center;/,
  );
});

test("runs and restores the accessible video generation task dialog", () => {
  assert.match(appSource, /enhanceVideoPrompt\(/);
  assert.match(appSource, /uploadVideoAsset\(/);
  assert.match(appSource, /createVideoTask\(/);
  assert.match(appSource, /getVideoTask\(/);
  assert.match(appSource, /errors\.videoExtendRequiresVideo/);
  assert.match(appSource, /errors\.videoReferenceRequired/);
  assert.match(appSource, /errors\.textVideoRejectsReferences/);
  assert.match(appSource, /config\.taskMode === "text_to_video"\) return \[\]/);
  assert.match(appSource, /setVideoTaskDialogOpen\(false\)/);
  assert.match(appSource, /onOpenVideoTask=/);
  assert.match(
    videoTaskSource,
    /"optimizing"[\s\S]*?"generating"[\s\S]*?"success"[\s\S]*?"error"/,
  );
  assert.match(videoTaskSource, /video\.task\.steps\.optimizationActive/);
  assert.match(videoTaskSource, /video\.task\.steps\.optimizationDone/);
  assert.match(videoTaskDialogSource, /role="dialog"/);
  assert.match(videoTaskDialogSource, /aria-modal="true"/);
  assert.match(videoTaskDialogSource, /aria-live="polite"/);
  assert.doesNotMatch(
    videoTaskDialogSource,
    /new-chat-video-task-dialog__icon/,
  );
  assert.match(videoTaskDialogSource, /new-chat-video-task-step__label/);
  assert.match(videoTaskDialogSource, /new-chat-video-task-step__loading/);
  assert.match(
    videoTaskDialogSource,
    /import \{ TextShimmer \} from "\.\.\/text-shimmer\/TextShimmer"/,
  );
  assert.match(videoTaskDialogSource, /new-chat-video-task-preview__loading/);
  assert.match(
    videoTaskDialogSource,
    /<TextShimmer[\s\S]*?as="strong"[\s\S]*?\{activeStatus\}[\s\S]*?<\/TextShimmer>/,
  );
  assert.match(
    videoTaskDialogSource,
    /video\.task\.runningHint/,
  );
  assert.match(videoTaskDialogSource, /video\.task\.backgroundHint/);
  assert.match(videoTaskDialogSource, /role="progressbar"/);
  assert.match(videoTaskDialogSource, /aria-valuetext=/);
  assert.match(videoTaskDialogSource, /video\.task\.elapsed/);
  assert.doesNotMatch(
    videoTaskDialogSource,
    /new-chat-video-task-step__marker/,
  );
  assert.doesNotMatch(
    videoTaskDialogSource,
    /function CheckIcon|function ErrorIcon|function VideoTaskIcon/,
  );
  assert.match(videoTaskDialogSource, /currentVideoTaskStatus/);
  assert.match(
    videoTaskDialogSource,
    /<video[\s\S]*?controls[\s\S]*?playsInline/,
  );
  assert.match(videoTaskDialogSource, /onClick=\{onDownload\}/);
  assert.match(appSource, /downloadVideoTask\(current\.remoteTaskId\)/);
  assert.match(
    videoTaskDialogStylesSource,
    /\.new-chat-video-task-steps li\s*\{[\s\S]*?border-bottom:\s*2px solid hsl\(var\(--border\)\);/,
  );
  assert.doesNotMatch(
    videoTaskDialogStylesSource,
    /\.new-chat-video-task-step__marker\s*\{/,
  );
  assert.doesNotMatch(
    videoTaskDialogStylesSource,
    /\.new-chat-video-task-dialog__icon\s*\{/,
  );
  assert.match(videoTaskDialogSource, /video\.task\.activationHint/);
  assert.match(videoTaskDialogSource, /className="new-chat-video-task-error" role="alert"/);
  assert.match(
    videoTaskDialogStylesSource,
    /\.new-chat-video-task-error\s*\{[\s\S]*?max-height:\s*220px;[\s\S]*?overflow-y:\s*auto;/,
  );
  assert.match(
    videoTaskDialogStylesSource,
    /\.new-chat-video-task-error p\s*\{[\s\S]*?overflow-wrap:\s*anywhere;[\s\S]*?white-space:\s*pre-wrap;/,
  );
  assert.match(videoTaskDialogStylesSource, /prefers-reduced-motion:\s*reduce/);
  assert.match(
    videoTaskDialogStylesSource,
    /new-chat-video-task-step__loading[\s\S]*?animation:\s*new-chat-video-task-spin/,
  );
  assert.match(
    videoTaskDialogStylesSource,
    /new-chat-video-task-preview__loading[\s\S]*?animation:\s*new-chat-video-task-spin/,
  );
  assert.match(
    videoTaskDialogStylesSource,
    /new-chat-video-task-progress > span[\s\S]*?animation:\s*new-chat-video-task-progress/,
  );
});

test("aligns the skill action picker with adjacent controls without an icon", () => {
  assert.doesNotMatch(skillPickerSource, /import \{ SkillIcon \}/);
  assert.doesNotMatch(skillPickerSource, /<SkillIcon/);
  assert.doesNotMatch(
    workspaceStylesSource,
    /\.new-chat-skill-picker__icon\s*\{/,
  );
  assert.match(
    workspaceStylesSource,
    /\.new-chat-skill-picker__trigger\s*\{[\s\S]*?min-height:\s*36px;[\s\S]*?font-size:\s*13px;/,
  );
  assert.match(
    workspaceStylesSource,
    /\.new-chat-skill-picker__option\s*\{[\s\S]*?font-size:\s*13px;/,
  );
  assert.match(
    skillControlsSource,
    /className="new-chat-skill-controls__model"[\s\S]*?label=\{t\("skill\.model"\)\}[\s\S]*?hideLabel/,
  );
  assert.match(
    workspaceStylesSource,
    /\.new-chat-skill-controls__model\s*\{[\s\S]*?margin-left:\s*auto;/,
  );
  assert.match(
    workspaceStylesSource,
    /\.new-chat-skill-controls__style\s*\{[\s\S]*?flex:\s*0 1 auto;[\s\S]*?max-width:\s*180px;/,
  );
  assert.match(
    workspaceStylesSource,
    /\.new-chat-skill-controls__model\s*\{[\s\S]*?flex:\s*0 1 auto;[\s\S]*?max-width:\s*240px;/,
  );
  assert.match(
    workspaceStylesSource,
    /\.new-chat-skill-controls__(?:style|model) \.new-chat-compact-select__trigger\s*\{[\s\S]*?width:\s*auto;/,
  );
  assert.match(
    workspaceStylesSource,
    /\.new-chat-skill-controls__model \.new-chat-compact-select__menu\s*\{[\s\S]*?right:\s*0;[\s\S]*?left:\s*auto;/,
  );
});

test("opens skill and video dropdowns on deliberate mouse hover", () => {
  for (const source of [skillPickerSource, compactSelectSource]) {
    assert.match(source, /HOVER_OPEN_DELAY_MS = 120/);
    assert.match(source, /HOVER_CLOSE_DELAY_MS = 180/);
    assert.match(
      source,
      /onPointerEnter=\{\(event\) => \{\s*if \(event\.pointerType === "mouse"\)/,
    );
    assert.match(
      source,
      /onPointerLeave=\{\(event\) => \{\s*if \(event\.pointerType === "mouse"\)/,
    );
  }
  assert.match(compactSelectSource, /focusSearchOnOpenRef/);
  assert.match(compactSelectSource, /openMenu\(false\)/);
  assert.match(compactSelectSource, /openMenu\(true\)/);
  assert.match(compactSelectSource, /new-chat-compact-select__spinner/);
  assert.match(
    compactSelectSource,
    /showLoading \? \([\s\S]*?new-chat-compact-select__spinner[\s\S]*?: \([\s\S]*?new-chat-compact-select__value/,
  );
  assert.match(
    workspaceStylesSource,
    /@keyframes new-chat-compact-select-spin[\s\S]*?transform:\s*rotate\(360deg\)/,
  );
  assert.match(
    workspaceStylesSource,
    /\.new-chat-compact-select__chevron\s*\{[\s\S]*?transition:\s*transform 140ms ease;/,
  );
  assert.doesNotMatch(
    workspaceStylesSource,
    /\.new-chat-compact-select__chevron\s*\{[\s\S]*?margin-left:\s*auto;/,
  );
  assert.match(
    workspaceStylesSource,
    /\.new-chat-compact-select__menu\s*\{[^}]*left:\s*0;/,
  );
  assert.doesNotMatch(
    workspaceStylesSource,
    /^\.new-chat-compact-select__menu\s*\{[^}]*right:\s*0;/m,
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
  const revealKeyframes =
    stylesSource.match(
      /@keyframes welcome-text-reveal\s*\{([\s\S]*?)\n\}/,
    )?.[1] ?? "";
  const placeholderRule =
    stylesSource.match(
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
  assert.match(
    featureNoticeSource,
    /className="welcome-feature-pill"[\s\S]*?featureNotice\.badge[\s\S]*?featureNotice\.view/,
  );
  assert.match(stylesSource, /--feature-link:\s*208 100% 47\.45%/);
  assert.match(stylesSource, /\.welcome-primary\s*\{[\s\S]*?gap:\s*32px;/);
  assert.match(stylesSource, /\.welcome-heading\s*\{[\s\S]*?gap:\s*72px;/);
  assert.match(
    stylesSource,
    /\.welcome-title,[\s\S]*?\.composer-placeholder-reveal\s*\{[\s\S]*?welcome-text-reveal 900ms/,
  );
  assert.match(
    stylesSource,
    /@keyframes welcome-text-reveal[\s\S]*?clip-path:\s*inset\(0 100% 0 0\)[\s\S]*?clip-path:\s*inset\(0 0 0 0\)/,
  );
  assert.doesNotMatch(revealKeyframes, /opacity:/);
  assert.match(
    stylesSource,
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.welcome-title,[\s\S]*?\.composer-placeholder-reveal[\s\S]*?animation:\s*none/,
  );
  assert.match(
    stylesSource,
    /\.composer--new-chat \.comp-input::placeholder\s*\{[\s\S]*?color:\s*transparent/,
  );
  assert.doesNotMatch(
    stylesSource,
    /\.comp-input::placeholder\s*\{[\s\S]*?animation:\s*welcome-text-reveal/,
  );
  assert.match(composerSource, /placeholder=\{placeholderText\}/);
  assert.match(
    composerSource,
    /newChatLayout && value\.length === 0[\s\S]*?key=\{placeholderText\}[\s\S]*?className="composer-placeholder-reveal"[\s\S]*?aria-hidden="true"/,
  );
  assert.match(
    stylesSource,
    /\.composer-placeholder-reveal\s*\{[\s\S]*?pointer-events:\s*none/,
  );
  assert.match(
    placeholderRule,
    /width:\s*max-content;[\s\S]*?max-width:\s*calc\(100% - 20px\)/,
  );
  assert.doesNotMatch(placeholderRule, /right:\s*10px/);
});

test("keeps the Agent picker aligned without extra highlighting or guidance", () => {
  assert.match(newChatAgentPickerSource, /className="new-chat-agent-picker"/);
  assert.doesNotMatch(
    newChatAgentPickerSource,
    /is-unselected|new-chat-agent-picker-guide|aria-describedby/,
  );
  assert.doesNotMatch(
    newChatAgentPickerStylesSource,
    /is-unselected|new-chat-agent-picker__guide/,
  );
  assert.match(
    newChatAgentPickerStylesSource,
    /\.new-chat-agent-picker__trigger > span\s*\{[\s\S]*?display:\s*flex;[\s\S]*?align-items:\s*center;[\s\S]*?line-height:\s*20px;/,
  );
  assert.doesNotMatch(
    newChatAgentPickerSource,
    /new-chat-agent-picker__trigger-icon/,
  );
  assert.match(
    newChatAgentPickerStylesSource,
    /\.new-chat-agent-picker__trigger-chevron\s*\{\s*display:\s*block;/,
  );
  assert.doesNotMatch(
    newChatAgentPickerStylesSource,
    /new-chat-agent-picker-bounce/,
  );
});

test("reveals feature details on hover or keyboard focus", () => {
  assert.match(featureNoticeSource, /role="tooltip"/);
  assert.match(featureNoticeSource, /featureNotice\.defaultNotes\.multiRegion/);
  assert.match(featureNoticeSource, /featureNotice\.defaultNotes\.switchAgent/);
  assert.match(featureNoticeSource, /featureNotice\.defaultNotes\.visualCanvas/);
  assert.match(
    stylesSource,
    /\.welcome-feature-pill:hover \.welcome-feature-popover/,
  );
  assert.match(
    stylesSource,
    /\.welcome-feature-pill:focus-within \.welcome-feature-popover/,
  );
});

test("shows task capsules for Harness agents without generic starter prompts", () => {
  assert.doesNotMatch(
    composerSource,
    /STARTER_PROMPTS|AnalyzePromptIcon|PlanPromptIcon|RewritePromptIcon/,
  );
  assert.match(composerSource, /const TASK_SHORTCUTS = \[/);
  assert.match(taskToolsSource, /ppt:\s*\["ppt_generate"\]/);
  assert.match(taskToolsSource, /image:\s*\["image_generate"\]/);
  assert.match(taskToolsSource, /video:\s*\["video_generate"\]/);
  assert.match(taskToolsSource, /video:\s*\["video_task_query"\]/);
  assert.match(composerSource, /availableTaskShortcuts/);
  assert.match(
    composerSource,
    /value: "ppt"[\s\S]*?composer\.prompts\.ppt\.quarterlyReview[\s\S]*?composer\.prompts\.ppt\.projectUpdate[\s\S]*?composer\.prompts\.ppt\.solutionProposal[\s\S]*?composer\.prompts\.ppt\.industryAnalysis/,
  );
  assert.match(
    composerSource,
    /value: "image"[\s\S]*?composer\.prompts\.image\.launchVisual[\s\S]*?composer\.prompts\.image\.ecommercePoster[\s\S]*?composer\.prompts\.image\.conceptRendering[\s\S]*?composer\.prompts\.image\.socialGraphic/,
  );
  assert.match(
    composerSource,
    /value: "video"[\s\S]*?composer\.prompts\.video\.brandFilm[\s\S]*?composer\.prompts\.video\.productLaunch[\s\S]*?composer\.prompts\.video\.trainingVideo[\s\S]*?composer\.prompts\.video\.eventTeaser/,
  );
  assert.doesNotMatch(
    composerSource,
    /skillCreateEnabled|SkillCreateIcon|创建 Skill/,
  );
  assert.match(composerSource, /className="task-shortcuts"/);
  assert.match(composerSource, /harnessEnabled\s*&&\s*!selectedTask/);
  assert.match(composerSource, /className="prompt-suggestions"/);
  assert.doesNotMatch(
    composerSource,
    /applyStarterPrompt|aria-label="快捷提示"/,
  );
  assert.match(composerSource, /onClick=\{\(\) => applyTaskShortcut\(task\)\}/);
  assert.match(
    composerSource,
    /function applyTaskShortcut[\s\S]*?onTaskChange\?\.\(task\.value\)[\s\S]*?setSelectionRange\(value\.length, value\.length\)/,
  );
  assert.doesNotMatch(
    composerSource,
    /function applyTaskShortcut[\s\S]*?onChange\(task\.prompt\)/,
  );
  assert.match(composerSource, /selectedTask\.prompts\.map\(\(prompt\) =>/);
  assert.match(
    composerSource,
    /t\("composer\.enterprisePrompts"/,
  );
  assert.match(composerSource, /onClick=\{\(\) => applyTaskPrompt\(translatedPrompt\)\}/);
  assert.match(
    composerSource,
    /setSelectionRange\(placeholderStart \+ 1, placeholderEnd\)/,
  );
  assert.match(
    stylesSource,
    /\.task-shortcuts\s*\{[\s\S]*?justify-content:\s*center;/,
  );
  assert.match(
    stylesSource,
    /\.task-shortcut\s*\{[\s\S]*?border-radius:\s*999px;/,
  );
  assert.match(stylesSource, /\.task-shortcut\s*\{[\s\S]*?font-size:\s*15px;/);
  assert.match(stylesSource, /\.task-shortcut\s*\{[\s\S]*?flex:\s*0 0 auto;/);
  assert.match(
    stylesSource,
    /\.task-shortcut\s*\{[\s\S]*?white-space:\s*nowrap;/,
  );
  assert.match(
    stylesSource,
    /\.prompt-suggestion > span\s*\{[\s\S]*?white-space:\s*nowrap;[\s\S]*?text-overflow:\s*ellipsis;[\s\S]*?transition:\s*max-height/,
  );
  assert.match(
    stylesSource,
    /\.prompt-suggestion:hover > span,[\s\S]*?max-height:\s*4\.5em;[\s\S]*?white-space:\s*normal;/,
  );
});

test("shows the selected task between add and Agent and reveals cancel on hover", () => {
  assert.match(
    composerSource,
    /className=\{`new-chat-task-chip new-chat-task-chip--\$\{selectedTask\.value\}`\}/,
  );
  assert.match(
    composerSource,
    /aria-label=\{t\("composer\.cancelTask"/,
  );
  assert.match(composerSource, /onClick=\{clearTask\}/);
  assert.match(
    composerSource,
    /function clearTask\(\)[\s\S]*?onTaskChange\?\.\(null\)[\s\S]*?onChange\(""\)/,
  );
  assert.match(composerSource, /new-chat-task-chip__task-icon/);
  assert.match(composerSource, /new-chat-task-chip__remove-icon/);
  assert.match(
    stylesSource,
    /\.new-chat-task-chip\s*\{[\s\S]*?left:\s*52px;[\s\S]*?background:\s*transparent;/,
  );
  assert.match(
    stylesSource,
    /\.composer--new-chat\.composer--has-task \.new-chat-mode\s*\{\s*left:\s*138px;/,
  );
  assert.match(
    stylesSource,
    /\.composer--new-chat\.composer--task-image \.new-chat-mode,[\s\S]*?left:\s*176px;/,
  );
  assert.match(
    stylesSource,
    /\.new-chat-task-chip--image,[\s\S]*?width:\s*116px;/,
  );
  assert.match(
    stylesSource,
    /\.new-chat-task-chip > span:last-child[\s\S]*?white-space:\s*nowrap;/,
  );
  assert.match(
    stylesSource,
    /\.new-chat-task-chip\s*\{[\s\S]*?color:\s*hsl\(262 34% 52%\)/,
  );
  assert.match(
    stylesSource,
    /\.new-chat-task-chip:hover,[\s\S]*?background:\s*hsl\(260 36% 96%\)/,
  );
  assert.match(
    stylesSource,
    /\.new-chat-task-chip__remove-icon\s*\{[\s\S]*?opacity:\s*0;/,
  );
  assert.match(
    stylesSource,
    /\.new-chat-task-chip:hover \.new-chat-task-chip__remove-icon,[\s\S]*?opacity:\s*1;/,
  );
  assert.match(
    appSource,
    /const \[newChatTask, setNewChatTask\] = useState<NewChatTask \| null>\(null\)/,
  );
  assert.match(
    appSource,
    /newChatTask=\{sandboxSession \? null : newChatTask\}/,
  );
  assert.match(appSource, /onTaskChange=\{setNewChatTask\}/);
  assert.match(
    appSource,
    /function startNewChat\(\)[\s\S]*?setNewChatTask\(null\)/,
  );
});
